from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Literal

from fastapi import APIRouter, Query, Request, Response, status
from fastapi.responses import PlainTextResponse, StreamingResponse
from sqlalchemy import func, or_, select

from app.api.deps import CurrentUser, DbDep, KnowledgeDep, OrchestratorDep, SettingsDep, get_sessionmaker, parse_uuid
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
from app.services.export import render_conversation

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.get("", response_model=ConversationList)
async def list_conversations(
    user: CurrentUser,
    db: DbDep,
    q: str | None = Query(default=None, max_length=200, description="Search titles and message text"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> ConversationList:
    stmt = select(Conversation).where(Conversation.user_id == user.id)
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
    conv = Conversation(user_id=user.id, title=(body.title or "").strip() or chat_service.DEFAULT_TITLE)
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
    format: Literal["markdown", "txt"] = "markdown",
) -> PlainTextResponse:
    conv = await chat_service.get_owned_conversation(db, user, parse_uuid(conversation_id))
    messages = await db.scalars(select(Message).where(Message.conversation_id == conv.id).order_by(Message.position))
    body = render_conversation(conv, list(messages), format)
    ext, media = ("md", "text/markdown") if format == "markdown" else ("txt", "text/plain")
    safe_title = "".join(c if c.isalnum() or c in "-_ " else "_" for c in conv.title)[:60].strip() or "conversation"
    return PlainTextResponse(
        body,
        media_type=f"{media}; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{safe_title}.{ext}"'},
    )


def _sse(events: AsyncIterator[dict]) -> StreamingResponse:
    async def body() -> AsyncIterator[str]:
        async for event in events:
            yield f"event: {event['type']}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        body(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


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
    rate_limit.enforce(f"chat:{user.id}", settings.rate_limit_chat_per_minute)
    conv = await chat_service.get_owned_conversation(db, user, parse_uuid(conversation_id))
    turn = await chat_service.prepare_send(db, settings, user, conv, body)
    return _sse(chat_service.run_turn(get_sessionmaker(request), orchestrator, settings, turn, knowledge))


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
    rate_limit.enforce(f"chat:{user.id}", settings.rate_limit_chat_per_minute)
    conv = await chat_service.get_owned_conversation(db, user, parse_uuid(conversation_id))
    turn = await chat_service.prepare_regenerate(db, settings, user, conv, body)
    return _sse(chat_service.run_turn(get_sessionmaker(request), orchestrator, settings, turn, knowledge))
