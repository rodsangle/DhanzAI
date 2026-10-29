"""Account security shared by the sign-in routes: email codes, the second factor, finishing a sign-in."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

from fastapi import Request
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import mfa, rate_limit
from app.core.config import Settings
from app.core.security import create_mfa_token, hash_token, new_numeric_code, same_hash
from app.db.base import utcnow
from app.models import MfaRecoveryCode, User, VerificationCode
from app.schemas import MfaChallenge, TokenResponse
from app.services import audit
from app.services.auth_service import issue_tokens
from app.services.mailer import Mailer

log = logging.getLogger(__name__)

EMAIL_CODE_MAX_ATTEMPTS = 5
# Wrong second-factor codes per account before a pause (on top of the per-IP limit).
MFA_MAX_FAILURES = 5
MFA_FAILURE_WINDOW = 15 * 60

_background: set[asyncio.Task] = set()


def send_in_background(mailer: Mailer, to: str, subject: str, body: str) -> None:
    """Send without delaying the response (and without its timing revealing anything)."""

    async def send() -> None:
        try:
            await mailer.send(to, subject, body)
        except Exception:  # noqa: BLE001 - delivery problems are logged, never shown
            log.exception("Could not send email: %s", subject)

    task = asyncio.create_task(send())
    _background.add(task)
    task.add_done_callback(_background.discard)


async def issue_email_code(db: AsyncSession, settings: Settings, mailer: Mailer, user: User) -> None:
    """Replace any pending code with a new one and email it. Caller commits."""
    await db.execute(
        update(VerificationCode)
        .where(
            VerificationCode.user_id == user.id,
            VerificationCode.purpose == "email",
            VerificationCode.used_at.is_(None),
        )
        .values(used_at=utcnow())
    )
    code = new_numeric_code()
    db.add(
        VerificationCode(
            user_id=user.id,
            purpose="email",
            code_hash=hash_token(code),
            attempts=0,
            expires_at=utcnow() + timedelta(minutes=settings.email_verification_ttl_minutes),
        )
    )
    text = (
        f"Hello {user.display_name},\n\n"
        f"Your DHANZ AI verification code is: {code}\n\n"
        f"Enter it in the app within {settings.email_verification_ttl_minutes} minutes to confirm this "
        "email address. If you did not create a DHANZ AI account, you can ignore this email.\n"
    )
    send_in_background(mailer, user.email, "Confirm your email for DHANZ AI", text)


async def confirm_email_code(db: AsyncSession, user: User, code: str) -> bool:
    """Mark the email verified when `code` matches the latest pending one. Caller commits."""
    pending = await db.scalar(
        select(VerificationCode)
        .where(
            VerificationCode.user_id == user.id,
            VerificationCode.purpose == "email",
            VerificationCode.used_at.is_(None),
            VerificationCode.expires_at > utcnow(),
        )
        .order_by(VerificationCode.created_at.desc())
        .limit(1)
    )
    if pending is None or pending.attempts >= EMAIL_CODE_MAX_ATTEMPTS:
        return False
    digits = "".join(ch for ch in code if ch.isdigit())
    if not same_hash(pending.code_hash, hash_token(digits)):
        pending.attempts += 1
        if pending.attempts >= EMAIL_CODE_MAX_ATTEMPTS:
            pending.used_at = utcnow()  # burnt: a new code must be requested
        return False
    pending.used_at = utcnow()
    user.email_verified_at = utcnow()
    return True


# --- second factor ---------------------------------------------------------------------------------


async def new_recovery_codes(db: AsyncSession, user: User) -> list[str]:
    """Replace the user's recovery codes; returns the plain codes (shown once). Caller commits."""
    await db.execute(delete(MfaRecoveryCode).where(MfaRecoveryCode.user_id == user.id))
    codes = mfa.new_recovery_codes()
    for code in codes:
        db.add(MfaRecoveryCode(user_id=user.id, code_hash=hash_token(mfa.normalize_recovery_code(code))))
    return codes


async def check_second_factor(db: AsyncSession, settings: Settings, user: User, code: str) -> str | None:
    """Accept an authenticator code or an unused recovery code; returns which one, or None.

    Consumes what it accepts (the TOTP step, the recovery code). Caller commits.
    """
    if user.mfa_secret is None:
        return None
    secret = mfa.decrypt_secret(settings, user.mfa_secret)
    step = mfa.match_step(secret, code, after=user.mfa_last_step)
    if step is not None:
        user.mfa_last_step = step
        return "totp"
    normalized = mfa.normalize_recovery_code(code)
    if len(normalized) == 12:
        recovery = await db.scalar(
            select(MfaRecoveryCode).where(
                MfaRecoveryCode.user_id == user.id,
                MfaRecoveryCode.code_hash == hash_token(normalized),
                MfaRecoveryCode.used_at.is_(None),
            )
        )
        if recovery is not None:
            recovery.used_at = utcnow()
            return "recovery_code"
    return None


async def guarded_second_factor(db: AsyncSession, settings: Settings, user: User, code: str) -> str | None:
    """`check_second_factor` with a per-account limit on wrong codes (raises 429 when exceeded)."""
    key = f"mfa-fail:{user.id}"
    retry = await rate_limit.limiter.peek(key, MFA_MAX_FAILURES, MFA_FAILURE_WINDOW)
    if retry is not None:
        raise rate_limit.too_many(retry, f"Too many wrong codes. Try again in {int(retry // 60) + 1} minutes.")
    method = await check_second_factor(db, settings, user, code)
    if method is None:
        await rate_limit.limiter.hit(key, MFA_MAX_FAILURES, MFA_FAILURE_WINDOW)
    else:
        await rate_limit.limiter.clear(key)
    return method


async def finish_sign_in(
    db: AsyncSession, settings: Settings, request: Request, user: User, method: str
) -> TokenResponse | MfaChallenge:
    """After the first factor: ask for the second one, or hand out the session tokens. Caller commits."""
    ip = rate_limit.client_ip(request)
    if user.mfa_enabled:
        token, expires_in = create_mfa_token(settings, user.id, method)
        audit.record(db, "auth.mfa_challenge", user_id=user.id, ip=ip, detail={"method": method})
        return MfaChallenge(mfa_token=token, expires_in=expires_in)
    tokens = await issue_tokens(db, settings, user, user_agent=request.headers.get("user-agent"))
    audit.record(db, "auth.login", user_id=user.id, ip=ip, detail={"method": method})
    return tokens
