from __future__ import annotations

import uuid
from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.security import create_access_token, hash_token, new_refresh_token
from app.db.base import utcnow
from app.models import RefreshToken, User
from app.schemas import TokenResponse, UserOut


class RefreshError(Exception):
    pass


async def issue_tokens(
    db: AsyncSession,
    settings: Settings,
    user: User,
    *,
    user_agent: str | None,
    family_id: uuid.UUID | None = None,
) -> TokenResponse:
    """Create an access token and a new refresh token. Caller commits."""
    access, expires_in = create_access_token(settings, user.id, user.role)
    refresh = new_refresh_token()
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hash_token(refresh),
            family_id=family_id or uuid.uuid4(),
            expires_at=utcnow() + timedelta(days=settings.refresh_token_ttl_days),
            user_agent=(user_agent or "")[:300] or None,
        )
    )
    return TokenResponse(
        access_token=access, refresh_token=refresh, expires_in=expires_in, user=UserOut.model_validate(user)
    )


async def rotate_refresh_token(
    db: AsyncSession, settings: Settings, raw_token: str, *, user_agent: str | None
) -> TokenResponse:
    row = await db.scalar(select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw_token)))
    if row is None:
        raise RefreshError("unknown token")
    if row.revoked_at is not None:
        # A rotated token was presented again: assume theft and kill the whole session family.
        await revoke_family(db, row.family_id)
        await db.commit()
        raise RefreshError("token reuse detected")
    if row.expires_at <= utcnow():
        raise RefreshError("token expired")
    user = await db.get(User, row.user_id)
    if user is None or not user.is_active:
        raise RefreshError("user inactive")
    row.revoked_at = utcnow()
    return await issue_tokens(db, settings, user, user_agent=user_agent, family_id=row.family_id)


async def revoke_family(db: AsyncSession, family_id: uuid.UUID) -> None:
    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=utcnow())
    )


async def revoke_token(db: AsyncSession, raw_token: str) -> uuid.UUID | None:
    """Revoke the session family of a refresh token. Returns the owner's id, if the token was known."""
    row = await db.scalar(select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw_token)))
    if row is None:
        return None
    await revoke_family(db, row.family_id)
    return row.user_id
