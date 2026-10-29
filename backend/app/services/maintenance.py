"""Periodic clean-up: conversation retention, temporary chats, expired tokens, old audit entries.

Runs inside every API process (MAINTENANCE_INTERVAL_MINUTES, 0 = off). Every step is an
idempotent DELETE, so several replicas running it at the same time is harmless.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta

from sqlalchemy import and_, delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.observability import MAINTENANCE_DELETED
from app.db.base import utcnow
from app.models import AuditLog, Conversation, PasswordResetToken, RefreshToken, User

log = logging.getLogger(__name__)


async def run_maintenance(
    maker: async_sessionmaker[AsyncSession], settings: Settings, now: datetime | None = None
) -> dict[str, int]:
    now = now or utcnow()
    counts: dict[str, int] = {}
    async with maker() as db:
        # Conversations idle longer than their owner's retention period, and expired temporary chats.
        # SQL narrows the candidates (shortest allowed retention is 7 days); each user's own period is
        # applied below, which avoids database-specific date arithmetic.
        temporary_cutoff = now - timedelta(hours=settings.temporary_chat_hours)
        rows = (
            await db.execute(
                select(Conversation.id, Conversation.updated_at, Conversation.temporary, User.retention_days)
                .join(User, User.id == Conversation.user_id)
                .where(
                    or_(
                        and_(User.retention_days.is_not(None), Conversation.updated_at < now - timedelta(days=7)),
                        and_(Conversation.temporary.is_(True), Conversation.updated_at < temporary_cutoff),
                    )
                )
            )
        ).all()
        ids = [
            conv_id
            for conv_id, updated_at, temporary, retention_days in rows
            if (temporary and updated_at < temporary_cutoff)
            or (retention_days and updated_at < now - timedelta(days=retention_days))
        ]
        counts["conversations"] = await _delete_in_batches(db, Conversation, ids)
        counts["refresh_tokens"] = await _rowcount(
            db,
            # Revoked tokens stay until they expire, so reuse of a stolen rotated token is still detected.
            delete(RefreshToken).where(RefreshToken.expires_at < now),
        )
        counts["password_reset_tokens"] = await _rowcount(
            db, delete(PasswordResetToken).where(PasswordResetToken.expires_at < now - timedelta(days=1))
        )
        counts["audit_logs"] = await _rowcount(
            db, delete(AuditLog).where(AuditLog.created_at < now - timedelta(days=settings.audit_log_retention_days))
        )
        await db.commit()
    for kind, n in counts.items():
        if n:
            MAINTENANCE_DELETED.labels(kind).inc(n)
    if any(counts.values()):
        log.info("Maintenance removed %s", counts)
    return counts


async def _delete_in_batches(db: AsyncSession, model, ids: list, size: int = 500) -> int:
    total = 0
    for i in range(0, len(ids), size):
        total += await _rowcount(db, delete(model).where(model.id.in_(ids[i : i + size])))
    return total


async def _rowcount(db: AsyncSession, statement) -> int:
    result = await db.execute(statement)
    return result.rowcount or 0


async def maintenance_loop(maker: async_sessionmaker[AsyncSession], settings: Settings) -> None:
    interval = settings.maintenance_interval_minutes * 60
    await asyncio.sleep(min(interval, 30))  # let the app finish starting
    while True:
        try:
            await run_maintenance(maker, settings)
        except Exception:  # noqa: BLE001 - try again next round
            log.exception("Maintenance run failed")
        await asyncio.sleep(interval)
