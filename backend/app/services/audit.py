from __future__ import annotations

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog

log = logging.getLogger("dhanz.audit")


def record(
    db: AsyncSession,
    action: str,
    *,
    user_id: uuid.UUID | None = None,
    ip: str | None = None,
    detail: dict | None = None,
) -> None:
    """Add an audit entry to the session; it is persisted with the caller's commit."""
    db.add(AuditLog(action=action, user_id=user_id, ip_address=ip, detail=detail))
    log.info("audit action=%s user=%s ip=%s", action, user_id, ip)
