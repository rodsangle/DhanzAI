"""Server administration (role "admin"): users, usage and the audit log."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, or_, select

from app.api.deps import AdminUser, DbDep, parse_uuid
from app.core import rate_limit
from app.db.base import utcnow
from app.models import AuditLog, Conversation, KnowledgeDocument, Message, MfaRecoveryCode, User
from app.services import audit
from app.services.auth_service import revoke_user_sessions

router = APIRouter(prefix="/admin", tags=["admin"])


class AdminUserOut(BaseModel):
    id: uuid.UUID
    email: str
    display_name: str
    role: str
    is_active: bool
    email_verified: bool = True
    mfa_enabled: bool = False
    created_at: datetime
    conversations: int = 0
    messages_30d: int = 0


class AdminUserList(BaseModel):
    items: list[AdminUserOut]
    total: int


class AdminUserUpdate(BaseModel):
    is_active: bool | None = None
    role: str | None = Field(default=None, pattern="^(user|admin)$")
    # For a user who lost their authenticator and recovery codes (after checking who they are).
    reset_mfa: bool = False


class ProviderUsage(BaseModel):
    provider: str
    replies: int
    input_tokens: int
    output_tokens: int


class AdminStats(BaseModel):
    users: int
    active_users_7d: int
    conversations: int
    messages_24h: int
    replies_failed_24h: int
    documents: int
    usage_30d: list[ProviderUsage]


class AuditEntry(BaseModel):
    id: uuid.UUID
    action: str
    user_id: uuid.UUID | None
    ip_address: str | None
    detail: dict | None
    created_at: datetime


@router.get("/stats", response_model=AdminStats)
async def stats(_: AdminUser, db: DbDep) -> AdminStats:
    now = utcnow()
    user_messages = select(Message).join(Conversation).where(Message.role == "user")
    active = await db.scalar(
        select(func.count(func.distinct(Conversation.user_id)))
        .select_from(Message)
        .join(Conversation)
        .where(Message.role == "user", Message.created_at >= now - timedelta(days=7))
    )
    usage = await db.execute(
        select(
            Message.provider,
            func.count(Message.id),
            func.coalesce(func.sum(Message.input_tokens), 0),
            func.coalesce(func.sum(Message.output_tokens), 0),
        )
        .where(
            Message.role == "assistant", Message.provider.is_not(None), Message.created_at >= now - timedelta(days=30)
        )
        .group_by(Message.provider)
        .order_by(func.count(Message.id).desc())
    )
    return AdminStats(
        users=await db.scalar(select(func.count(User.id))) or 0,
        active_users_7d=active or 0,
        conversations=await db.scalar(select(func.count(Conversation.id))) or 0,
        messages_24h=await db.scalar(
            select(func.count()).select_from(
                user_messages.where(Message.created_at >= now - timedelta(days=1)).subquery()
            )
        )
        or 0,
        replies_failed_24h=await db.scalar(
            select(func.count(Message.id)).where(
                Message.role == "assistant", Message.status == "error", Message.created_at >= now - timedelta(days=1)
            )
        )
        or 0,
        documents=await db.scalar(select(func.count(KnowledgeDocument.id))) or 0,
        usage_30d=[ProviderUsage(provider=p, replies=n, input_tokens=i, output_tokens=o) for p, n, i, o in usage.all()],
    )


@router.get("/users", response_model=AdminUserList)
async def list_users(
    _: AdminUser,
    db: DbDep,
    q: str | None = Query(default=None, max_length=200, description="Search email and name"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> AdminUserList:
    stmt = select(User)
    if q:
        escaped = q.strip().lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped}%"
        stmt = stmt.where(
            or_(
                func.lower(User.email).like(pattern, escape="\\"),
                func.lower(User.display_name).like(pattern, escape="\\"),
            )
        )
    total = await db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    users = list(await db.scalars(stmt.order_by(User.created_at.desc()).limit(limit).offset(offset)))
    ids = [u.id for u in users]
    convs, msgs = {}, {}
    if ids:
        convs = dict(
            (
                await db.execute(
                    select(Conversation.user_id, func.count(Conversation.id))
                    .where(Conversation.user_id.in_(ids))
                    .group_by(Conversation.user_id)
                )
            ).all()
        )
        msgs = dict(
            (
                await db.execute(
                    select(Conversation.user_id, func.count(Message.id))
                    .join(Message, Message.conversation_id == Conversation.id)
                    .where(
                        Conversation.user_id.in_(ids),
                        Message.role == "user",
                        Message.created_at >= utcnow() - timedelta(days=30),
                    )
                    .group_by(Conversation.user_id)
                )
            ).all()
        )
    return AdminUserList(
        items=[
            AdminUserOut(
                id=u.id,
                email=u.email,
                display_name=u.display_name,
                role=u.role,
                is_active=u.is_active,
                email_verified=u.email_verified,
                mfa_enabled=u.mfa_enabled,
                created_at=u.created_at,
                conversations=convs.get(u.id, 0),
                messages_30d=msgs.get(u.id, 0),
            )
            for u in users
        ],
        total=total,
    )


@router.patch("/users/{user_id}", response_model=AdminUserOut)
async def update_user(
    user_id: str, body: AdminUserUpdate, request: Request, admin: AdminUser, db: DbDep
) -> AdminUserOut:
    target = await db.get(User, parse_uuid(user_id))
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    if target.id == admin.id and (body.is_active is False or body.role == "user"):
        raise HTTPException(status.HTTP_409_CONFLICT, "You cannot deactivate or demote your own account")
    changes: dict = {}
    if body.is_active is not None and body.is_active != target.is_active:
        target.is_active = body.is_active
        changes["is_active"] = body.is_active
        if not body.is_active:
            await revoke_user_sessions(db, target.id)  # signed out immediately
    if body.role is not None and body.role != target.role:
        target.role = body.role
        changes["role"] = body.role
        await revoke_user_sessions(db, target.id)  # new tokens carry the new role
    if body.reset_mfa and target.mfa_enabled:
        target.mfa_secret = None
        target.mfa_enabled_at = None
        target.mfa_last_step = None
        await db.execute(delete(MfaRecoveryCode).where(MfaRecoveryCode.user_id == target.id))
        changes["mfa_reset"] = True
    if changes:
        target.updated_at = utcnow()
        audit.record(
            db,
            "admin.user_updated",
            user_id=admin.id,
            ip=rate_limit.client_ip(request),
            detail={"target": str(target.id), **changes},
        )
        await db.commit()
    return AdminUserOut(
        id=target.id,
        email=target.email,
        display_name=target.display_name,
        role=target.role,
        is_active=target.is_active,
        email_verified=target.email_verified,
        mfa_enabled=target.mfa_enabled,
        created_at=target.created_at,
    )


@router.get("/audit", response_model=list[AuditEntry])
async def audit_log(
    _: AdminUser,
    db: DbDep,
    user_id: str | None = None,
    action: str | None = Query(default=None, max_length=64, description="Exact action or a prefix ending in '.'"),
    limit: int = Query(default=100, ge=1, le=500),
    before: datetime | None = Query(default=None, description="Page backwards: created_at of the last entry seen"),
) -> list[AuditEntry]:
    stmt = select(AuditLog)
    if user_id:
        stmt = stmt.where(AuditLog.user_id == parse_uuid(user_id))
    if action:
        stmt = stmt.where(AuditLog.action.startswith(action) if action.endswith(".") else AuditLog.action == action)
    if before:
        stmt = stmt.where(AuditLog.created_at < before)
    rows = await db.scalars(stmt.order_by(AuditLog.created_at.desc()).limit(limit))
    return [
        AuditEntry(
            id=r.id,
            action=r.action,
            user_id=r.user_id,
            ip_address=r.ip_address,
            detail=r.detail,
            created_at=r.created_at,
        )
        for r in rows
    ]
