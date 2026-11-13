from __future__ import annotations

import secrets
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, FastAPI, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import delete, select

from app.api.deps import CurrentUser, DbDep, parse_uuid

try:  # servers without email verification simply have no gate
    from app.api.deps import require_verified_email
except ImportError:  # pragma: no cover - older live servers
    require_verified_email = None
from app.core import rate_limit
from app.db.base import utcnow
from app.models import Conversation, Message

from .models import ConversationArchive, SharedConversation

router = APIRouter(prefix="/conversation-extras", tags=["conversation-extras"])
public_router = APIRouter(tags=["shared"])

# Messages that finished or were stopped are part of the chat; failed or running ones are not.
_KEPT = ("complete", "stopped")


async def _owned(db, user, conversation_id: str) -> Conversation:
    conversation = await db.get(Conversation, parse_uuid(conversation_id))
    if conversation is None or conversation.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")
    return conversation


async def _messages(db, conversation: Conversation, up_to: int | None = None) -> list[Message]:
    query = select(Message).where(Message.conversation_id == conversation.id, Message.status.in_(_KEPT))
    if up_to is not None:
        query = query.where(Message.position <= up_to)
    return list(await db.scalars(query.order_by(Message.position)))


class BranchRequest(BaseModel):
    message_id: str


class BranchResult(BaseModel):
    id: uuid.UUID
    title: str


@router.post("/{conversation_id}/branch", status_code=201)
async def branch(conversation_id: str, body: BranchRequest, user: CurrentUser, db: DbDep) -> BranchResult:
    """Start a new chat containing this chat's messages up to and including one message."""
    source = await _owned(db, user, conversation_id)
    if getattr(source, "temporary", False):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Temporary chats cannot be branched.")
    target = await db.get(Message, parse_uuid(body.message_id))
    if target is None or target.conversation_id != source.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Message not found")
    copy = Conversation(user_id=user.id, title=f"Branch · {source.title}"[:200], updated_at=utcnow())
    if hasattr(source, "project_id"):
        copy.project_id = source.project_id
    db.add(copy)
    await db.flush()
    # Copy every column the server's Message has (live servers may have extra ones), with new ids.
    columns = [c.key for c in Message.__table__.columns if c.key not in ("id", "conversation_id", "position")]
    for position, message in enumerate(await _messages(db, source, target.position)):
        values = {key: getattr(message, key) for key in columns}
        db.add(Message(conversation_id=copy.id, position=position, **values))
    await db.commit()
    return BranchResult(id=copy.id, title=copy.title)


@router.get("/archived")
async def archived(user: CurrentUser, db: DbDep) -> list[dict]:
    rows = await db.execute(
        select(ConversationArchive.conversation_id, ConversationArchive.archived_at, Conversation.title)
        .join(Conversation, Conversation.id == ConversationArchive.conversation_id)
        .where(ConversationArchive.user_id == user.id)
        .order_by(ConversationArchive.archived_at.desc())
    )
    return [{"id": str(cid), "title": title, "archived_at": at.isoformat()} for cid, at, title in rows]


@router.put("/{conversation_id}/archive", status_code=204)
async def archive(conversation_id: str, user: CurrentUser, db: DbDep) -> None:
    conversation = await _owned(db, user, conversation_id)
    exists = await db.scalar(
        select(ConversationArchive.id).where(ConversationArchive.conversation_id == conversation.id)
    )
    if exists is None:
        db.add(ConversationArchive(user_id=user.id, conversation_id=conversation.id))
        await db.commit()


@router.delete("/{conversation_id}/archive", status_code=204)
async def unarchive(conversation_id: str, user: CurrentUser, db: DbDep) -> None:
    conversation = await _owned(db, user, conversation_id)
    await db.execute(delete(ConversationArchive).where(ConversationArchive.conversation_id == conversation.id))
    await db.commit()


def _snapshot(messages: list[Message]) -> list[dict]:
    """Only what a reader needs: no attachments, file names, tool activity or token counts."""
    out = []
    for m in messages:
        sources = [
            {"title": str(c.get("title") or "")[:300], "url": str(c.get("url") or "")[:2000]}
            for c in (getattr(m, "citations", None) or [])
            if isinstance(c, dict) and str(c.get("url") or "").startswith(("https://", "http://"))
        ]
        out.append(
            {
                "role": m.role,
                "content": m.content,
                "model": getattr(m, "model", None) if m.role == "assistant" else None,
                "sources": sources,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
        )
    return out


class ShareResult(BaseModel):
    token: str
    title: str
    created_at: datetime
    message_count: int


@router.post("/{conversation_id}/share", status_code=201)
async def share(conversation_id: str, user: CurrentUser, db: DbDep) -> ShareResult:
    """Freeze the chat as it is now behind a new random link."""
    await rate_limit.enforce(f"share:{user.id}", 20)
    conversation = await _owned(db, user, conversation_id)
    if getattr(conversation, "temporary", False):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Temporary chats cannot be shared.")
    messages = _snapshot(await _messages(db, conversation))
    if not messages:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "There is nothing to share yet.")
    row = SharedConversation(
        token=secrets.token_urlsafe(24),
        user_id=user.id,
        conversation_id=conversation.id,
        title=conversation.title,
        messages=messages,
    )
    db.add(row)
    await db.commit()
    return ShareResult(token=row.token, title=row.title, created_at=row.created_at, message_count=len(messages))


@router.get("/shares")
async def shares(user: CurrentUser, db: DbDep) -> list[ShareResult]:
    rows = await db.scalars(
        select(SharedConversation)
        .where(SharedConversation.user_id == user.id)
        .order_by(SharedConversation.created_at.desc())
    )
    return [
        ShareResult(token=r.token, title=r.title, created_at=r.created_at, message_count=len(r.messages or []))
        for r in rows
    ]


@router.delete("/shares/{token}", status_code=204)
async def revoke(token: str, user: CurrentUser, db: DbDep) -> None:
    row = await db.get(SharedConversation, token)
    if row is None or row.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Link not found")
    await db.delete(row)
    await db.commit()


@public_router.get("/shared/{token}")
async def shared(token: str, db: DbDep) -> dict:
    """Public, read-only. Says nothing about the owner; unknown and revoked links look the same."""
    await rate_limit.enforce(f"shared-view:{token[:16]}", 120)
    row = await db.get(SharedConversation, token) if 16 <= len(token) <= 64 else None
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This shared chat does not exist or was removed.")
    return {"title": row.title, "shared_at": row.created_at.isoformat(), "messages": row.messages}


def install(app: FastAPI) -> None:
    prefix = app.state.settings.api_prefix
    gate = [Depends(require_verified_email)] if require_verified_email is not None else None
    app.include_router(router, prefix=prefix, dependencies=gate)
    app.include_router(public_router, prefix=prefix)
