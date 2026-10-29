from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, Query, Request, Response, status
from fastapi.responses import PlainTextResponse, StreamingResponse
from sqlalchemy import func, or_, select

from app.api.deps import CurrentUser, DbDep, KnowledgeDep, OrchestratorDep, SettingsDep, get_sessionmaker, parse_uuid
from app.api.routes.projects import get_owned_project
from app.core import rate_limit
from app.db.base import utcnow
from app.models import Conversation, Message
from app.schemas import (
    ConversationCreate,
    ConversationDetail,
    ConversationList,
    ConversationOut,
    ConversationUpdate,
    MessageOut,
    RegenerateRequest,
    SendMessageRequest,
)
from app.services import chat_service
from app.services.export import render_conversation, render_pdf

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.get("", response_model=ConversationList)
async def list_conversations(
    user: CurrentUser,
    db: DbDep,
    q: str | None = Query(default=None, max_length=200, description="Search titles and message text"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    project_id: str | None = Query(default=None, description="Only conversations in this project"),
) -> ConversationList:
    stmt = select(Conversation).where(Conversation.user_id == user.id)
    if project_id:
        stmt = stmt.where(Conversation.project_id == parse_uuid(project_id))
    if q:
        escaped = q.strip().lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped}%"
        matching = select(Message.conversation_id).where(func.lower(Message.content).like(pattern, escape="\\"))
        stmt = stmt.where(or_(func.lower(Conversation.title).like(pattern, escape="\\"), Conversation.id.in_(matching)))
    total = await db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = await db.scalars(
        stmt.order_by(Conversation.pinned.desc(), Conversation.updated_at.desc()).limit(limit).offset(offset)
    )
    return ConversationList(items=[ConversationOut.model_validate(c) for c in rows], total=total or 0)


@router.post("", response_model=ConversationOut, status_code=status.HTTP_201_CREATED)
async def create_conversation(body: ConversationCreate, user: CurrentUser, db: DbDep) -> Conversation:
    if body.project_id is not None:
        await get_owned_project(db, user, body.project_id)
    conv = Conversation(
        user_id=user.id,
        title=(body.title or "").strip() or chat_service.DEFAULT_TITLE,
        project_id=body.project_id,
        temporary=body.temporary,
    )
    db.add(conv)
    await db.commit()
    return conv


@router.get("/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(conversation_id: str, user: CurrentUser, db: DbDep) -> ConversationDetail:
    conv = await chat_service.get_owned_conversation(db, user, parse_uuid(conversation_id))
    messages = await db.scalars(select(Message).where(Message.conversation_id == conv.id).order_by(Message.position))
    return ConversationDetail(
        **ConversationOut.model_validate(conv).model_dump(),
        messages=[MessageOut.model_validate(m) for m in messages],
    )


@router.patch("/{conversation_id}", response_model=ConversationOut)
async def update_conversation(
    conversation_id: str, body: ConversationUpdate, user: CurrentUser, db: DbDep
) -> Conversation:
    conv = await chat_service.get_owned_conversation(db, user, parse_uuid(conversation_id))
    if body.title is not None:
        conv.title = body.title.strip() or conv.title
    if body.pinned is not None:
        conv.pinned = body.pinned
    if "project_id" in body.model_fields_set:
        if body.project_id is not None:
            await get_owned_project(db, user, body.project_id)
        conv.project_id = body.project_id
    conv.updated_at = utcnow()
    await db.commit()
    return conv


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(conversation_id: str, user: CurrentUser, db: DbDep) -> Response:
    conv = await chat_service.get_owned_conversation(db, user, parse_uuid(conversation_id))
    await db.delete(conv)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{conversation_id}/export")
async def export_conversation(
    conversation_id: str,
    user: CurrentUser,
    db: DbDep,
    format: Literal["markdown", "txt", "pdf"] = "markdown",
) -> Response:
    conv = await chat_service.get_owned_conversation(db, user, parse_uuid(conversation_id))
    messages = list(
        await db.scalars(select(Message).where(Message.conversation_id == conv.id).order_by(Message.position))
    )
    disposition = _attachment_header(conv.title)
    if format == "pdf":
        pdf = await asyncio.to_thread(render_pdf, conv, messages)
        return Response(
            pdf,
            media_type="application/pdf",
            headers={"Content-Disposition": disposition("pdf")},
        )
    body = render_conversation(conv, messages, format)
    ext, media = ("md", "text/markdown") if format == "markdown" else ("txt", "text/plain")
    return PlainTextResponse(
        body,
        media_type=f"{media}; charset=utf-8",
        headers={"Content-Disposition": disposition(ext)},
    )


def _attachment_header(title: str):
    """Content-Disposition with an ASCII fallback name plus the full UTF-8 name (RFC 6266/5987)."""
    ascii_name = "".join(c if c.isascii() and (c.isalnum() or c in "-_ ") else "_" for c in title)[:60].strip("_ ")
    utf8_name = "".join(c for c in title if c.isprintable() and c not in '/\\"')[:60].strip() or "conversation"

    def header(ext: str) -> str:
        return (
            f"attachment; filename=\"{ascii_name or 'conversation'}.{ext}\"; filename*=UTF-8''{quote(utf8_name)}.{ext}"
        )

    return header


def _sse(events: AsyncIterator[dict]) -> StreamingResponse:
    async def body() -> AsyncIterator[str]:
        async for event in events:
            yield f"event: {event['type']}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        body(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _start_and_stream(request: Request, orchestrator, settings, knowledge, turn) -> StreamingResponse:
    """Run the reply as a background task and stream it. Disconnecting does not stop it."""
    turns = request.app.state.turns
    handle = turns.start(
        chat_service.run_turn(
            get_sessionmaker(request), orchestrator, settings, turn, knowledge, request.app.state.files
        ),
        message_id=turn.assistant_message_id,
        user_id=turn.user_id,
        conversation_id=turn.conversation_id,
    )
    return _sse(turns.subscribe(handle))


@router.post("/{conversation_id}/stop", status_code=status.HTTP_202_ACCEPTED)
async def stop_reply(conversation_id: str, request: Request, user: CurrentUser, db: DbDep) -> dict:
    """Stop the reply being generated; the partial text is kept and marked "stopped"."""
    conv = await chat_service.get_owned_conversation(db, user, parse_uuid(conversation_id))
    message_id = await chat_service.request_stop(db, conv, request.app.state.turns)
    return {"stopping": str(message_id) if message_id else None}


@router.post("/{conversation_id}/messages", summary="Send a message and stream the reply (Server-Sent Events)")
async def send_message(
    conversation_id: str,
    body: SendMessageRequest,
    request: Request,
    user: CurrentUser,
    db: DbDep,
    settings: SettingsDep,
    orchestrator: OrchestratorDep,
    knowledge: KnowledgeDep,
) -> StreamingResponse:
    await rate_limit.enforce(f"chat:{user.id}", settings.rate_limit_chat_per_minute)
    conv = await chat_service.get_owned_conversation(db, user, parse_uuid(conversation_id))
    turn = await chat_service.prepare_send(db, settings, user, conv, body)
    return _start_and_stream(request, orchestrator, settings, knowledge, turn)


@router.post("/{conversation_id}/regenerate", summary="Regenerate the last reply (Server-Sent Events)")
async def regenerate(
    conversation_id: str,
    body: RegenerateRequest,
    request: Request,
    user: CurrentUser,
    db: DbDep,
    settings: SettingsDep,
    orchestrator: OrchestratorDep,
    knowledge: KnowledgeDep,
) -> StreamingResponse:
    await rate_limit.enforce(f"chat:{user.id}", settings.rate_limit_chat_per_minute)
    conv = await chat_service.get_owned_conversation(db, user, parse_uuid(conversation_id))
    turn = await chat_service.prepare_regenerate(db, settings, user, conv, body)
    return _start_and_stream(request, orchestrator, settings, knowledge, turn)
