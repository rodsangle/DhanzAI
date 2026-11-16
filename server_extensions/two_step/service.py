"""Two-step verification rules: the sign-in challenge, second-factor checks and remembered devices.

Uses only what every DHANZ API has had since Phase 5 (settings, sessions, the rate limiter, the
audit log), so it works on servers that predate the built-in two-step verification.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from fastapi import Request
from fastapi.responses import JSONResponse
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import rate_limit
from app.db.base import utcnow
from app.services import audit

from . import core
from .models import TwoStepDevice, TwoStepRecoveryCode, TwoStepSetting

# Wrong second-factor codes per account before a pause (on top of the per-IP limit).
MAX_FAILURES = 5
FAILURE_WINDOW = 15 * 60
MAX_DEVICES = 20
_hasher = PasswordHasher()


def challenge_minutes(settings) -> int:
    return int(getattr(settings, "mfa_challenge_minutes", None) or os.environ.get("MFA_CHALLENGE_MINUTES") or 5)


def trusted_device_days(settings) -> int:
    value = getattr(settings, "trusted_device_days", None)
    if value is None:
        value = os.environ.get("TRUSTED_DEVICE_DAYS", "30")
    return max(0, min(90, int(value)))


# --- the sign-in challenge ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Ticket:
    user_id: uuid.UUID
    challenge_id: str


def create_challenge(settings, user_id: uuid.UUID) -> tuple[str, int]:
    """Proof that the password was right; useless on its own (it is not a session)."""
    now = datetime.now(UTC)
    ttl = timedelta(minutes=challenge_minutes(settings))
    payload = {"sub": str(user_id), "type": "mfa", "jti": secrets.token_hex(8), "iat": now, "exp": now + ttl}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm), int(ttl.total_seconds())


def read_challenge(settings, token: str) -> Ticket | None:
    try:
        payload = jwt.decode(
            token, settings.jwt_secret, algorithms=[settings.jwt_algorithm], options={"require": ["sub", "exp", "type"]}
        )
        if payload.get("type") != "mfa":
            return None
        return Ticket(uuid.UUID(payload["sub"]), str(payload.get("jti", "")))
    except (jwt.PyJWTError, ValueError):
        return None


async def setting_for(db: AsyncSession, user_id: uuid.UUID) -> TwoStepSetting | None:
    return await db.get(TwoStepSetting, user_id)


async def enabled_setting(db: AsyncSession, user_id: uuid.UUID) -> TwoStepSetting | None:
    row = await setting_for(db, user_id)
    return row if row is not None and row.enabled_at is not None else None


# --- second factor -----------------------------------------------------------------------------------


def _hash_code(code: str) -> str:
    return _hasher.hash(code)


def _matching(code: str, hashes: list[str]) -> int | None:
    for index, stored in enumerate(hashes):
        try:
            if _hasher.verify(stored, code):
                return index
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            continue
    return None


async def new_recovery_codes(db: AsyncSession, user_id: uuid.UUID) -> list[str]:
    """Replace the recovery codes; returns them in plain text (shown once). Caller commits."""
    await db.execute(delete(TwoStepRecoveryCode).where(TwoStepRecoveryCode.user_id == user_id))
    codes = core.new_recovery_codes()
    for code in codes:
        db.add(
            TwoStepRecoveryCode(
                user_id=user_id, code_hash=await asyncio.to_thread(_hash_code, core.normalize_recovery_code(code))
            )
        )
    return codes


async def check_factor(db: AsyncSession, settings, setting: TwoStepSetting, code: str) -> str | None:
    """A current authenticator code (each step once) or an unused recovery code; consumes it."""
    if setting.secret:
        step = core.match_step(core.decrypt_secret(settings, setting.secret), code, after=setting.last_step)
        if step is not None:
            setting.last_step = step
            return "totp"
    normalized = core.normalize_recovery_code(code)
    if len(normalized) == 12:
        unused = list(
            await db.scalars(
                select(TwoStepRecoveryCode).where(
                    TwoStepRecoveryCode.user_id == setting.user_id, TwoStepRecoveryCode.used_at.is_(None)
                )
            )
        )
        index = await asyncio.to_thread(_matching, normalized, [row.code_hash for row in unused])
        if index is not None:
            unused[index].used_at = utcnow()
            return "recovery_code"
    return None


async def guarded_check(db: AsyncSession, settings, setting: TwoStepSetting, code: str) -> str | None:
    """`check_factor` with a per-account limit on wrong codes (raises 429 when exceeded)."""
    key = f"mfa-fail:{setting.user_id}"
    retry = await rate_limit.limiter.peek(key, MAX_FAILURES, FAILURE_WINDOW)
    if retry is not None:
        raise rate_limit.too_many(retry, f"Too many wrong codes. Try again in {int(retry // 60) + 1} minutes.")
    method = await check_factor(db, settings, setting, code)
    if method is None:
        await rate_limit.limiter.hit(key, MAX_FAILURES, FAILURE_WINDOW)
    else:
        await rate_limit.limiter.clear(key)
    return method


# --- remembered devices ------------------------------------------------------------------------------


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def password_fingerprint(user) -> str:
    return _sha256(user.password_hash or "no-password")


def device_label(user_agent: str | None) -> str:
    """A readable name for the device list ("Chrome on Windows", "DHANZ app on Android")."""
    low = (user_agent or "").lower()
    systems = (
        ("android", "Android"),
        ("iphone", "iPhone"),
        ("ipad", "iPad"),
        ("windows", "Windows"),
        ("mac os", "Mac"),
        ("macintosh", "Mac"),
        ("linux", "Linux"),
    )
    apps = (("dart", "DHANZ app"), ("edg/", "Edge"), ("chrome", "Chrome"), ("firefox", "Firefox"), ("safari", "Safari"))
    system = next((name for key, name in systems if key in low), None)
    app = next((name for key, name in apps if key in low), None)
    if app and system:
        return f"{app} on {system}"
    return app or system or ((user_agent or "")[:60] or "Unknown device")


async def remember_device(db: AsyncSession, settings, user, user_agent: str | None) -> str | None:
    """Trust this device; returns its token (only the hash is stored), or None when turned off."""
    days = trusted_device_days(settings)
    if days <= 0:
        return None
    token = secrets.token_urlsafe(32)
    db.add(
        TwoStepDevice(
            user_id=user.id,
            token_hash=_sha256(token),
            password_fingerprint=password_fingerprint(user),
            label=device_label(user_agent)[:200],
            expires_at=utcnow() + timedelta(days=days),
        )
    )
    await db.flush()
    rows = list(
        await db.scalars(
            select(TwoStepDevice).where(TwoStepDevice.user_id == user.id).order_by(TwoStepDevice.created_at.desc())
        )
    )
    for old in rows[MAX_DEVICES:]:
        await db.delete(old)
    return token


async def device_trusted(db: AsyncSession, user, token: str | None) -> bool:
    if not token or not isinstance(token, str) or len(token) > 200:
        return False
    device = await db.scalar(
        select(TwoStepDevice).where(
            TwoStepDevice.token_hash == _sha256(token),
            TwoStepDevice.user_id == user.id,
            TwoStepDevice.expires_at > utcnow(),
        )
    )
    if device is None or device.password_fingerprint != password_fingerprint(user):
        return False
    device.last_used_at = utcnow()
    return True


async def forget_devices(db: AsyncSession, user_id: uuid.UUID) -> None:
    await db.execute(delete(TwoStepDevice).where(TwoStepDevice.user_id == user_id))


# --- the sign-in hook --------------------------------------------------------------------------------


async def login_hook(db: AsyncSession, settings, request: Request, user) -> JSONResponse | None:
    """Called by the sign-in route after the password was accepted, before session tokens exist.

    Returns the challenge for accounts with two-step verification (None: sign in as before).
    A remembered device (`trusted_device_token` in the request body) skips the challenge.
    """
    if await enabled_setting(db, user.id) is None:
        return None
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001 - the route already validated the body; this is only optional extra
        body = {}
    token = body.get("trusted_device_token") if isinstance(body, dict) else None
    ip = rate_limit.client_ip(request)
    if await device_trusted(db, user, token):
        return None  # the route issues the session as usual (and records the sign-in)
    challenge, expires_in = create_challenge(settings, user.id)
    audit.record(db, "auth.mfa_challenge", user_id=user.id, ip=ip, detail={"method": "password"})
    await db.commit()
    return JSONResponse(
        {
            "mfa_required": True,
            "mfa_token": challenge,
            "expires_in": expires_in,
            "method": "totp",
            "email_hint": None,
            "code_sent": False,
        }
    )


async def status(db: AsyncSession, user_id: uuid.UUID) -> dict:
    """What the app reads from user objects to show two-step verification in Settings."""
    row = await enabled_setting(db, user_id)
    return {"mfa_enabled": row is not None, "mfa_method": row.method if row else None}
