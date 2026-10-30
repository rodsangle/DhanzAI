"""Conversation turn handling: persistence around a streamed model response."""

from __future__ import annotations

import asyncio
import base64
import dataclasses
import logging
import re
import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.db.base import utcnow
from app.models import Conversation, KnowledgeChunk, KnowledgeDocument, Memory, Message, Project, User
from app.schemas import MessageOut, RegenerateRequest, SendMessageRequest
from app.services import knowledge_service
from app.services.assistant_tools import ToolBox, ToolContext
from app.services.files_service import FilesRuntime
from app.services.knowledge_service import KnowledgeRuntime
from dhanz_ai import (
    Capability,
    ChatMessage,
    GenerationParams,
    ImagePart,
    NoModelAvailableError,
    Orchestrator,
    ProviderError,
    RoutingPolicy,
    RoutingRequest,
    build_system_prompt,
    classify_task,
)
from dhanz_knowledge import Passage, ResearchOutcome, bm25_scores, build_context, extract_urls, needs_search

log = logging.getLogger(__name__)

DEFAULT_TITLE = "New conversation"
# A "streaming" row older than this is assumed orphaned (e.g. server restart) and no longer blocks new turns.
STREAM_LOCK_SECONDS = 600
PROVIDER_FAILURE_MESSAGE = "The AI provider could not complete this reply. Please try again or pick another model."


@dataclass
class PreparedTurn:
    conversation_id: uuid.UUID
    user_message: Message | None
    assistant_message_id: uuid.UUID
    history: list[ChatMessage]
    routing: RoutingRequest
    user_id: uuid.UUID
    question: str
    web: bool | None  # True: always research, False: never, None: decide automatically
    auto_index: bool
    attachment_ids: list[uuid.UUID] = field(default_factory=list)
    project_id: uuid.UUID | None = None
    project_instructions: str | None = None
    memories: list[str] = field(default_factory=list)
    saved_memory: str | None = None  # stored from a "remember that …" message in this turn
    temporary_memory_request: bool = False  # "remember that …" in a temporary chat (not saved)
    memory_off_request: bool = False  # user asked to remember something while memory is off
    client_time: datetime | None = None  # the user's device time (with its UTC offset)


def parse_client_time(value: str | None) -> datetime | None:
    """The device clock sent with a message; ignored unless it carries a UTC offset and is plausible."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or abs(parsed - utcnow()) > timedelta(days=2):
        return None
    return parsed


# Matched against the stripped message. The captured text starts with a non-space so the parts of the
# pattern cannot overlap (no polynomial backtracking), and only short messages are tried at all.
_REMEMBER = re.compile(r"(?:please\s+)?remember(?:\s+that|\s*:)\s+(\S.{2,520})", re.I | re.S)
_REMEMBER_MAX_CHARS = 600


def remember_request(content: str) -> str | None:
    """The text of a "Remember that …" request, or None."""
    text = content.strip()
    if len(text) > _REMEMBER_MAX_CHARS:
        return None
    match = _REMEMBER.fullmatch(text)
    if not match:
        return None
    saved = match.group(1).rstrip()
    if saved[-1] in ".!":
        saved = saved[:-1].rstrip()
    return saved if 3 <= len(saved) <= 500 else None


async def _attachments(
    db: AsyncSession, settings: Settings, user: User, ids: list[uuid.UUID]
) -> list[KnowledgeDocument]:
    if len(ids) > settings.max_attachments_per_message:
        raise HTTPException(422, f"Attach at most {settings.max_attachments_per_message} files per message.")
    docs = []
    for doc_id in dict.fromkeys(ids):
        doc = await db.get(KnowledgeDocument, doc_id)
        if doc is None or doc.user_id != user.id or doc.kind != "file":
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Attached file not found")
        docs.append(doc)
    return docs


def _snapshot(docs: list[KnowledgeDocument]) -> list[dict] | None:
    return [
        {"id": str(d.id), "filename": d.title, "file_type": d.file_type, "mime_type": d.mime_type} for d in docs
    ] or None


async def _turn_context(db: AsyncSession, user: User, conv: Conversation) -> dict:
    """Project instructions and approved memories that shape this turn."""
    ctx: dict = {"project_id": conv.project_id, "project_instructions": None, "memories": []}
    if conv.project_id is not None:
        project = await db.get(Project, conv.project_id)
        if project is not None:
            ctx["project_instructions"] = project.instructions
    if user.memory_enabled and not conv.temporary:  # temporary chats neither use nor create memories
        rows = await db.scalars(select(Memory).where(Memory.user_id == user.id).order_by(Memory.created_at))
        ctx["memories"] = [m.content for m in rows]
    return ctx


async def get_owned_conversation(db: AsyncSession, user: User, conversation_id: uuid.UUID) -> Conversation:
    conv = await db.get(Conversation, conversation_id)
    # Same 404 for "missing" and "someone else's" so IDs can't be probed.
    if conv is None or conv.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")
    return conv


async def _next_position(db: AsyncSession, conversation_id: uuid.UUID) -> int:
    current = await db.scalar(select(func.max(Message.position)).where(Message.conversation_id == conversation_id))
    return 0 if current is None else current + 1


async def _ordered_messages(db: AsyncSession, conversation_id: uuid.UUID) -> list[Message]:
    rows = await db.scalars(
        select(Message).where(Message.conversation_id == conversation_id).order_by(Message.position)
    )
    return list(rows)


def build_history(messages: list[Message], max_messages: int) -> list[ChatMessage]:
    """Model-ready history: usable messages only, strictly alternating, starting with a user turn."""
    usable = [m for m in messages if m.content.strip() and (m.role == "user" or m.status in ("complete", "stopped"))][
        -max_messages:
    ]
    merged: list[ChatMessage] = []
    for m in usable:
        if merged and merged[-1].role == m.role:
            merged[-1] = ChatMessage(m.role, merged[-1].content + "\n\n" + m.content)  # type: ignore[arg-type]
        else:
            merged.append(ChatMessage(m.role, m.content))  # type: ignore[arg-type]
    while merged and merged[0].role != "user":
        merged.pop(0)
    return merged


def _routing(user: User, settings: Settings, provider: str | None, model: str | None) -> RoutingRequest:
    if bool(provider) != bool(model):
        raise HTTPException(422, "provider and model must be given together")
    try:
        policy = RoutingPolicy(user.routing_policy or settings.default_routing_policy)
    except ValueError:
        policy = RoutingPolicy(settings.default_routing_policy)
    return RoutingRequest(
        explicit_provider=provider,
        explicit_model=model,
        preferred_model_key=user.preferred_model,
        policy=policy,
    )


def _ensure_not_streaming(messages: list[Message]) -> None:
    cutoff = utcnow() - timedelta(seconds=STREAM_LOCK_SECONDS)
    if any(m.status in ("streaming", "stopping") and m.created_at > cutoff for m in messages):
        raise HTTPException(status.HTTP_409_CONFLICT, "A reply is still being generated in this conversation")


async def _add_assistant_placeholder(db: AsyncSession, conversation_id: uuid.UUID, position: int) -> Message:
    msg = Message(conversation_id=conversation_id, position=position, role="assistant", content="", status="streaming")
    db.add(msg)
    return msg


async def _commit_or_conflict(db: AsyncSession) -> None:
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Another reply is being generated in this conversation") from None


async def prepare_send(
    db: AsyncSession, settings: Settings, user: User, conv: Conversation, req: SendMessageRequest
) -> PreparedTurn:
    if len(req.content) > settings.max_message_chars:
        raise HTTPException(413, f"Message exceeds {settings.max_message_chars} characters")
    routing = _routing(user, settings, req.provider, req.model)
    _ensure_not_streaming(await _ordered_messages(db, conv.id))

    attachment_ids = list(req.attachment_ids)
    if req.edit_message_id is not None:
        target = await db.get(Message, req.edit_message_id)
        if target is None or target.conversation_id != conv.id or target.role != "user":
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Message to edit not found")
        if not attachment_ids and target.attachments:  # editing the text keeps the original files
            attachment_ids = [uuid.UUID(a["id"]) for a in target.attachments]
        await db.execute(delete(Message).where(Message.conversation_id == conv.id, Message.position >= target.position))
        await db.flush()
    docs = await _attachments(db, settings, user, attachment_ids)

    saved_memory, memory_off_request, temporary_memory_request = None, False, False
    remember = remember_request(req.content)
    if remember and conv.temporary:
        temporary_memory_request = True
    elif remember:
        if user.memory_enabled:
            saved_memory = remember
            db.add(Memory(user_id=user.id, content=saved_memory[:1000], source="chat"))
        else:
            memory_off_request = True

    position = await _next_position(db, conv.id)
    user_msg = Message(
        conversation_id=conv.id,
        position=position,
        role="user",
        content=req.content,
        attachments=_snapshot(docs),
    )
    db.add(user_msg)
    assistant = await _add_assistant_placeholder(db, conv.id, position + 1)

    if conv.title == DEFAULT_TITLE and position == 0:
        first_line = req.content.strip().splitlines()[0]
        conv.title = (first_line[:60] + "…") if len(first_line) > 60 else first_line
    conv.updated_at = utcnow()
    await _commit_or_conflict(db)

    history = build_history(await _ordered_messages(db, conv.id), settings.history_max_messages)
    return PreparedTurn(
        conv.id,
        user_msg,
        assistant.id,
        history,
        routing,
        user.id,
        req.content,
        req.web,
        user.auto_index_web and not conv.temporary,
        attachment_ids=[d.id for d in docs],
        client_time=parse_client_time(req.client_time),
        saved_memory=saved_memory,
        memory_off_request=memory_off_request,
        temporary_memory_request=temporary_memory_request,
        **await _turn_context(db, user, conv),
    )


async def prepare_regenerate(
    db: AsyncSession, settings: Settings, user: User, conv: Conversation, req: RegenerateRequest
) -> PreparedTurn:
    routing = _routing(user, settings, req.provider, req.model)
    messages = await _ordered_messages(db, conv.id)
    last_user = next((m for m in reversed(messages) if m.role == "user"), None)
    if last_user is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Nothing to regenerate")
    _ensure_not_streaming(messages)
    await db.execute(delete(Message).where(Message.conversation_id == conv.id, Message.position > last_user.position))
    assistant = await _add_assistant_placeholder(db, conv.id, last_user.position + 1)
    conv.updated_at = utcnow()
    await _commit_or_conflict(db)
    history = build_history(await _ordered_messages(db, conv.id), settings.history_max_messages)
    attachment_ids = [uuid.UUID(a["id"]) for a in last_user.attachments or []]
    # Files deleted since the original message are skipped rather than failing the regeneration.
    existing = [
        d.id
        for d in [await db.get(KnowledgeDocument, i) for i in attachment_ids]
        if d is not None and d.user_id == user.id
    ]
    return PreparedTurn(
        conv.id,
        None,
        assistant.id,
        history,
        routing,
        user.id,
        last_user.content,
        req.web,
        user.auto_index_web and not conv.temporary,
        attachment_ids=existing,
        client_time=parse_client_time(req.client_time),
        **await _turn_context(db, user, conv),
    )


async def _finalize(
    maker: async_sessionmaker[AsyncSession],
    message_id: uuid.UUID,
    *,
    text: str,
    outcome: str,
    provider: str | None,
    model: str | None,
    input_tokens: int | None,
    output_tokens: int | None,
    error: str | None,
    citations: list[dict] | None,
    tool_activity: list[dict] | None = None,
) -> MessageOut | None:
    async with maker() as db:
        msg = await db.get(Message, message_id)
        if msg is None:  # conversation deleted mid-stream
            return None
        msg.content = text
        msg.status = outcome
        msg.provider = provider
        msg.model = model
        msg.input_tokens = input_tokens
        msg.output_tokens = output_tokens
        msg.error = error
        msg.citations = citations or None
        msg.tool_activity = tool_activity or None
        conv = await db.get(Conversation, msg.conversation_id)
        if conv is not None:
            conv.updated_at = utcnow()
        await db.commit()
        return MessageOut.model_validate(msg)


@dataclass
class _Research:
    sources: str | None = None
    notes: str | None = None
    citations: list[dict] | None = None
    pages: list = field(default_factory=list)
    images: list = field(default_factory=list)


ATTACHMENT_FULL_TEXT_CHARS = 12_000  # shorter attachments are given to the model whole
ATTACHMENT_CONTEXT_BUDGET = 40_000


async def _attachment_passages(
    db: AsyncSession, turn: PreparedTurn, notes: list[str]
) -> tuple[list[Passage], list[KnowledgeDocument]]:
    """Text passages from attached documents (whole text when short, best-matching chunks otherwise)."""
    passages: list[Passage] = []
    images: list[KnowledgeDocument] = []
    for doc_id in turn.attachment_ids:
        doc = await db.get(KnowledgeDocument, doc_id)
        if doc is None:
            continue
        if doc.file_type == "image":
            images.append(doc)
            continue
        if doc.notes:
            notes.append(f"About the attached file {doc.title}: {doc.notes}")

        def passage(text: str, doc: KnowledgeDocument = doc) -> Passage:
            return Passage(text=text, url=doc.url, title=doc.title, retrieved_at=doc.created_at, origin="file")

        if not doc.content:
            continue
        if len(doc.content) <= ATTACHMENT_FULL_TEXT_CHARS:
            passages.append(passage(doc.content))
            continue
        chunks = list(
            await db.scalars(
                select(KnowledgeChunk).where(KnowledgeChunk.document_id == doc.id).order_by(KnowledgeChunk.ordinal)
            )
        )
        scores = bm25_scores(turn.question, [c.text for c in chunks])
        best = sorted(range(len(chunks)), key=lambda k: scores[k], reverse=True)[:6]
        keep = sorted({0, *best})  # the opening chunk gives context (title, abstract, headers)
        passages += [passage(chunks[k].text) for k in keep]
        notes.append(
            f"The attached file {doc.title} is long; you were given its opening and the {len(keep) - 1} passages most "
            "relevant to the question, not the whole document."
        )
    return passages, images


async def _research(
    maker: async_sessionmaker[AsyncSession], knowledge: KnowledgeRuntime | None, turn: PreparedTurn, out: _Research
) -> AsyncIterator[dict]:
    """Gather sources (attachments, web, the user's library) for this turn, yielding progress events."""
    passages: list[Passage] = []
    notes: list[str] = []
    if turn.saved_memory:
        notes.append(f"You saved this to the user's memory as they asked: “{turn.saved_memory}”. Confirm it briefly.")
    if turn.temporary_memory_request:
        notes.append(
            "The user asked you to remember something, but this is a temporary chat, so nothing was saved. Tell them "
            "to ask again in a normal chat."
        )
    if turn.memory_off_request:
        notes.append(
            "The user asked you to remember something, but memory is turned off, so nothing was saved. Tell them they "
            "can turn memory on in Settings → Memory."
        )

    async with maker() as db:
        attached, out.images = await _attachment_passages(db, turn, notes)
    passages += attached
    if attached or out.images:
        yield {"type": "research", "stage": "reading_files", "count": len(turn.attachment_ids)}

    if knowledge is not None and turn.web is not False:
        urls = extract_urls(turn.question)
        use_web = turn.web is True or needs_search(turn.question)
        if use_web and knowledge.search is None and not urls:
            notes.append(
                "Web search is not configured on this DHANZ AI server, so no live search was done. Tell the user you "
                "could not search the web for this answer."
            )
            yield {
                "type": "research",
                "stage": "unavailable",
                "detail": "Web search is not configured on this server.",
            }
        if (use_web and knowledge.search is not None) or urls:
            async for event in knowledge.pipeline().run(turn.question, use_search=use_web):
                if isinstance(event, ResearchOutcome):
                    passages += event.passages
                    out.pages = event.pages
                    failed = [f for f in event.failures if f["url"]]
                    if failed:
                        notes.append(
                            "These pages could not be read and were not used: "
                            + "; ".join(f"{f['url']} ({f['reason']})" for f in failed[:5])
                        )
                    if event.query and not event.passages:
                        notes.append("The web search returned no usable results.")
                else:
                    yield {"type": "research", "stage": event.stage, **event.detail}

    if knowledge is not None:
        async with maker() as db:
            if await knowledge_service.has_library(db, turn.user_id):
                library = await knowledge_service.search_library(
                    db, turn.user_id, turn.question, knowledge.embedder, project_id=turn.project_id
                )
                known = {p.url for p in passages}
                passages += [p for p in library if p.url not in known]

    if passages:
        budget = ATTACHMENT_CONTEXT_BUDGET if attached else 14_000
        context, citations = build_context(passages, budget_chars=budget)
        out.sources = context
        out.citations = [c.to_json() for c in citations]
        yield {"type": "research", "stage": "sources", "sources": out.citations}
    out.notes = " ".join(notes) or None


STOP_POLL_SECONDS = 1.0


async def _stop_requested(maker: async_sessionmaker[AsyncSession], message_id: uuid.UUID) -> bool:
    async with maker() as db:
        return await db.scalar(select(Message.status).where(Message.id == message_id)) == "stopping"


async def request_stop(db: AsyncSession, conv: Conversation, turns) -> uuid.UUID | None:
    """Stop the reply being generated in this conversation, wherever it runs. Returns its id."""
    msg = await db.scalar(
        select(Message)
        .where(Message.conversation_id == conv.id, Message.status == "streaming")
        .order_by(Message.position.desc())
        .limit(1)
    )
    if msg is None:
        return None
    if not turns.cancel(msg.id):  # not running in this worker: flag it for the worker that is
        msg.status = "stopping"
        await db.commit()
    return msg.id


def _toolbox(
    maker: async_sessionmaker[AsyncSession], settings: Settings, orchestrator: Orchestrator, turn: PreparedTurn
) -> ToolBox | None:
    """Tools for this reply, when enabled and the model expected to answer can call functions."""
    if not settings.assistant_tools_enabled:
        return None
    try:
        first = orchestrator.candidates(turn.routing, classify_task(turn.question))[0]
    except NoModelAvailableError:
        return None
    if Capability.TOOLS not in first.capabilities:
        return None
    return ToolBox(
        ToolContext(
            maker,
            turn.user_id,
            turn.conversation_id,
            local_offset=turn.client_time.utcoffset() if turn.client_time else None,
            settings=settings,
        )
    )


async def run_turn(
    maker: async_sessionmaker[AsyncSession],
    orchestrator: Orchestrator,
    settings: Settings,
    turn: PreparedTurn,
    knowledge: KnowledgeRuntime | None = None,
    files: FilesRuntime | None = None,
) -> AsyncIterator[dict]:
    """Stream a reply as protocol events and persist the outcome.

    Events: meta, research*, model, delta, done | error. If the client disconnects, the partial
    reply is saved with status "stopped".
    """
    yield {
        "type": "meta",
        "conversation_id": str(turn.conversation_id),
        "assistant_message_id": str(turn.assistant_message_id),
        "user_message": MessageOut.model_validate(turn.user_message).model_dump(mode="json")
        if turn.user_message
        else None,
    }

    research = _Research()
    toolbox: ToolBox | None = None
    parts: list[str] = []
    provider = model = None
    input_tokens = output_tokens = None
    outcome, error = "stopped", None
    result: MessageOut | None = None
    try:
        try:
            async for event in _research(maker, knowledge, turn, research):
                yield event
        except Exception:  # noqa: BLE001 - research problems must not prevent an answer
            log.exception("Research failed for turn %s", turn.assistant_message_id)
            research.notes = "Research failed because of an internal error, so no sources were used."
            yield {"type": "research", "stage": "error", "detail": "Research failed; answering without sources."}
        if turn.saved_memory:
            yield {"type": "memory", "action": "saved", "content": turn.saved_memory}
        memories = [*turn.memories, *([turn.saved_memory] if turn.saved_memory else [])]
        toolbox = _toolbox(maker, settings, orchestrator, turn)
        system = build_system_prompt(
            sources=research.sources,
            research_notes=research.notes,
            user_preferences="\n".join(f"- {m}" for m in dict.fromkeys(memories)) or None,
            project_instructions=turn.project_instructions,
            today=turn.client_time.date() if turn.client_time else None,
            local_time=turn.client_time.isoformat(timespec="minutes") if turn.client_time else None,
            tools=toolbox is not None,
        )
        history = list(turn.history)
        routing = turn.routing
        if research.images and files is not None and history and history[-1].role == "user":
            images = []
            for d in research.images:
                data = await files.storage.get(d.storage_key)
                images.append(ImagePart(d.mime_type, base64.b64encode(data).decode()))
            names = ", ".join(d.title for d in research.images)
            history[-1] = ChatMessage("user", f"{history[-1].content}\n\n[Attached images: {names}]", tuple(images))
            routing = dataclasses.replace(routing, required=routing.required | {Capability.VISION})
        messages = [ChatMessage("system", system), *history]
        params = GenerationParams(temperature=settings.default_temperature, max_tokens=settings.default_max_tokens)
        stream = orchestrator.stream_chat(
            messages,
            routing,
            params,
            tools=toolbox.specs if toolbox else (),
            run_tool=toolbox.run if toolbox else None,
        )
        stopped = False
        last_check = time.monotonic()
        async for rc in stream:
            # Stop requests may arrive at another server worker: they flag the row, we notice here.
            if time.monotonic() - last_check > STOP_POLL_SECONDS:
                last_check = time.monotonic()
                if await _stop_requested(maker, turn.assistant_message_id):
                    stopped = True
                    await stream.aclose()
                    break
            if (rc.model.provider, rc.model.model) != (provider, model):
                provider, model = rc.model.provider, rc.model.model
                yield {"type": "model", "provider": provider, "model": model}
            if rc.chunk.text:
                parts.append(rc.chunk.text)
                yield {"type": "delta", "text": rc.chunk.text}
            if rc.chunk.tool_calls:
                labels = list(dict.fromkeys(ToolBox.label(c.name) for c in rc.chunk.tool_calls))
                yield {"type": "tool", "stage": "running", "labels": labels}
            if rc.tool_results and toolbox:
                yield {"type": "tool", "stage": "done", "activity": toolbox.activity[-len(rc.tool_results) :]}
            if rc.chunk.done:
                input_tokens, output_tokens = rc.chunk.input_tokens, rc.chunk.output_tokens
        outcome = "stopped" if stopped else "complete"
    except NoModelAvailableError as exc:
        outcome, error = "error", str(exc)
    except ProviderError as exc:
        log.warning("Chat turn failed: %s", exc)
        outcome, error = "error", PROVIDER_FAILURE_MESSAGE
    finally:
        result = await asyncio.shield(
            _finalize(
                maker,
                turn.assistant_message_id,
                text="".join(parts),
                outcome=outcome,
                provider=provider,
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                error=error,
                citations=research.citations,
                tool_activity=toolbox.activity if toolbox else None,
            )
        )
    if outcome == "complete" and research.pages and turn.auto_index and knowledge is not None:
        knowledge_service.index_in_background(maker, turn.user_id, research.pages, knowledge.embedder)
    message = result.model_dump(mode="json") if result else None
    if outcome == "complete":
        yield {"type": "done", "message": message}
    elif outcome == "stopped":
        yield {"type": "stopped", "message": message}
    else:
        yield {"type": "error", "detail": error, "message": message}
