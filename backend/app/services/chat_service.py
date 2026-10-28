"""Conversation turn handling: persistence around a streamed model response."""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import timedelta

from fastapi import HTTPException, status
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.db.base import utcnow
from app.models import Conversation, Message, User
from app.schemas import MessageOut, RegenerateRequest, SendMessageRequest
from app.services import knowledge_service
from app.services.knowledge_service import KnowledgeRuntime
from dhanz_ai import (
    ChatMessage,
    GenerationParams,
    NoModelAvailableError,
    Orchestrator,
    ProviderError,
    RoutingPolicy,
    RoutingRequest,
    build_system_prompt,
)
from dhanz_knowledge import ResearchOutcome, build_context, extract_urls, needs_search

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
    if any(m.status == "streaming" and m.created_at > cutoff for m in messages):
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

    if req.edit_message_id is not None:
        target = await db.get(Message, req.edit_message_id)
        if target is None or target.conversation_id != conv.id or target.role != "user":
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Message to edit not found")
        await db.execute(delete(Message).where(Message.conversation_id == conv.id, Message.position >= target.position))
        await db.flush()

    position = await _next_position(db, conv.id)
    user_msg = Message(conversation_id=conv.id, position=position, role="user", content=req.content)
    db.add(user_msg)
    assistant = await _add_assistant_placeholder(db, conv.id, position + 1)

    if conv.title == DEFAULT_TITLE and position == 0:
        first_line = req.content.strip().splitlines()[0]
        conv.title = (first_line[:60] + "…") if len(first_line) > 60 else first_line
    conv.updated_at = utcnow()
    await _commit_or_conflict(db)

    history = build_history(await _ordered_messages(db, conv.id), settings.history_max_messages)
    return PreparedTurn(
        conv.id, user_msg, assistant.id, history, routing, user.id, req.content, req.web, user.auto_index_web
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
    return PreparedTurn(
        conv.id, None, assistant.id, history, routing, user.id, last_user.content, req.web, user.auto_index_web
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


async def _research(
    maker: async_sessionmaker[AsyncSession], knowledge: KnowledgeRuntime | None, turn: PreparedTurn, out: _Research
) -> AsyncIterator[dict]:
    """Gather sources (web + the user's library) for this turn, yielding progress events."""
    if knowledge is None or turn.web is False:
        return
    urls = extract_urls(turn.question)
    use_web = turn.web is True or needs_search(turn.question)
    passages = []
    notes = []

    if use_web and knowledge.search is None and not urls:
        notes.append(
            "Web search is not configured on this DHANZ AI server, so no live search was done. Tell the user you "
            "could not search the web for this answer."
        )
        yield {"type": "research", "stage": "unavailable", "detail": "Web search is not configured on this server."}
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

    async with maker() as db:
        if await knowledge_service.has_library(db, turn.user_id):
            library = await knowledge_service.search_library(db, turn.user_id, turn.question, knowledge.embedder)
            known = {p.url for p in passages}
            passages += [p for p in library if p.url not in known]

    if passages:
        context, citations = build_context(passages)
        out.sources = context
        out.citations = [c.to_json() for c in citations]
        yield {"type": "research", "stage": "sources", "sources": out.citations}
    out.notes = " ".join(notes) or None


async def run_turn(
    maker: async_sessionmaker[AsyncSession],
    orchestrator: Orchestrator,
    settings: Settings,
    turn: PreparedTurn,
    knowledge: KnowledgeRuntime | None = None,
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
        system = build_system_prompt(sources=research.sources, research_notes=research.notes)
        messages = [ChatMessage("system", system), *turn.history]
        params = GenerationParams(temperature=settings.default_temperature, max_tokens=settings.default_max_tokens)
        async for rc in orchestrator.stream_chat(messages, turn.routing, params):
            if (rc.model.provider, rc.model.model) != (provider, model):
                provider, model = rc.model.provider, rc.model.model
                yield {"type": "model", "provider": provider, "model": model}
            if rc.chunk.text:
                parts.append(rc.chunk.text)
                yield {"type": "delta", "text": rc.chunk.text}
            if rc.chunk.done:
                input_tokens, output_tokens = rc.chunk.input_tokens, rc.chunk.output_tokens
        outcome = "complete"
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
            )
        )
    if outcome == "complete" and research.pages and turn.auto_index and knowledge is not None:
        knowledge_service.index_in_background(maker, turn.user_id, research.pages, knowledge.embedder)
    message = result.model_dump(mode="json") if result else None
    if outcome == "complete":
        yield {"type": "done", "message": message}
    else:
        yield {"type": "error", "detail": error, "message": message}
