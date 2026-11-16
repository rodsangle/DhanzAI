"""Account security shared by the sign-in routes: email codes, the second factor, finishing a sign-in."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import secrets
from datetime import timedelta

from fastapi import Request
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import mfa, rate_limit
from app.core.config import Settings
from app.core.security import (
    create_mfa_token,
    decode_mfa_token,
    hash_single_use_code_async,
    matching_single_use_code_async,
    new_numeric_code,
)
from app.db.base import utcnow
from app.models import MfaRecoveryCode, TrustedDevice, User, VerificationCode
from app.schemas import MfaChallenge, TokenResponse
from app.services import audit
from app.services.auth_service import issue_tokens
from app.services.mailer import Mailer

log = logging.getLogger(__name__)

EMAIL_CODE_MAX_ATTEMPTS = 5
# Wrong second-factor codes per account before a pause (on top of the per-IP limit).
MFA_MAX_FAILURES = 5
MFA_FAILURE_WINDOW = 15 * 60
# Remembered devices kept per account (the oldest are forgotten first).
MAX_TRUSTED_DEVICES = 20
MFA_METHODS = ("totp", "email")

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


async def issue_code(db: AsyncSession, user: User, purpose: str, minutes: int) -> str:
    """Replace any pending code for `purpose` with a new 6-digit one; returns it (only its hash is
    stored). Caller sends it and commits."""
    await db.execute(
        update(VerificationCode)
        .where(
            VerificationCode.user_id == user.id,
            VerificationCode.purpose == purpose,
            VerificationCode.used_at.is_(None),
        )
        .values(used_at=utcnow())
    )
    code = new_numeric_code()
    db.add(
        VerificationCode(
            user_id=user.id,
            purpose=purpose,
            code_hash=await hash_single_use_code_async(code),
            attempts=0,
            expires_at=utcnow() + timedelta(minutes=minutes),
        )
    )
    return code


async def consume_code(db: AsyncSession, user: User, purpose: str, code: str) -> bool:
    """True when `code` matches the latest pending code for `purpose`; uses it up. Five wrong tries
    burn the code. Caller commits."""
    pending = await db.scalar(
        select(VerificationCode)
        .where(
            VerificationCode.user_id == user.id,
            VerificationCode.purpose == purpose,
            VerificationCode.used_at.is_(None),
            VerificationCode.expires_at > utcnow(),
        )
        .order_by(VerificationCode.created_at.desc())
        .limit(1)
    )
    if pending is None or pending.attempts >= EMAIL_CODE_MAX_ATTEMPTS:
        return False
    digits = "".join(ch for ch in code if ch.isdigit())
    if len(digits) != 6 or (await matching_single_use_code_async(digits, [pending.code_hash])) is None:
        pending.attempts += 1
        if pending.attempts >= EMAIL_CODE_MAX_ATTEMPTS:
            pending.used_at = utcnow()  # burnt: a new code must be requested
        return False
    pending.used_at = utcnow()
    return True


async def issue_email_code(db: AsyncSession, settings: Settings, mailer: Mailer, user: User) -> None:
    """Replace any pending code with a new one and email it. Caller commits."""
    code = await issue_code(db, user, "email", settings.email_verification_ttl_minutes)
    text = (
        f"Hello {user.display_name},\n\n"
        f"Your DHANZ AI verification code is: {code}\n\n"
        f"Enter it in the app within {settings.email_verification_ttl_minutes} minutes to confirm this "
        "email address. If you did not create a DHANZ AI account, you can ignore this email.\n"
    )
    send_in_background(mailer, user.email, "Confirm your email for DHANZ AI", text)


async def confirm_email_code(db: AsyncSession, user: User, code: str) -> bool:
    """Mark the email verified when `code` matches the latest pending one. Caller commits."""
    if not await consume_code(db, user, "email", code):
        return False
    user.email_verified_at = utcnow()
    return True


# --- second factor ---------------------------------------------------------------------------------


async def new_recovery_codes(db: AsyncSession, user: User) -> list[str]:
    """Replace the user's recovery codes; returns the plain codes (shown once). Caller commits."""
    await db.execute(delete(MfaRecoveryCode).where(MfaRecoveryCode.user_id == user.id))
    codes = mfa.new_recovery_codes()
    for code in codes:
        db.add(
            MfaRecoveryCode(
                user_id=user.id,
                code_hash=await hash_single_use_code_async(mfa.normalize_recovery_code(code)),
            )
        )
    return codes


def login_code_purpose(challenge_id: str) -> str:
    """Purpose of an emailed sign-in code: bound to one sign-in challenge (fits String(20))."""
    return f"mfa:{challenge_id[:16]}"


# Emailed codes for account changes (turn off, new recovery codes, password change, delete account).
MANAGE_PURPOSE = "mfa-manage"
SETUP_PURPOSE = "mfa-setup"


async def check_second_factor(
    db: AsyncSession, settings: Settings, user: User, code: str, *, challenge_id: str | None = None
) -> str | None:
    """Accept the account's second factor or an unused recovery code; returns which one, or None.

    Authenticator accounts: a TOTP code (each 30-second step once). Email accounts: the code emailed
    for this sign-in challenge (or, signed in, for account changes). Consumes what it accepts.
    Caller commits.
    """
    if not user.mfa_enabled:
        return None
    if user.mfa_method == "email":
        purpose = login_code_purpose(challenge_id) if challenge_id else MANAGE_PURPOSE
        digits = "".join(ch for ch in code if ch.isdigit())
        if len(digits) == 6 and await consume_code(db, user, purpose, digits):
            return "email_code"
    elif user.mfa_secret is not None:
        secret = mfa.decrypt_secret(settings, user.mfa_secret)
        step = mfa.match_step(secret, code, after=user.mfa_last_step)
        if step is not None:
            user.mfa_last_step = step
            return "totp"
    normalized = mfa.normalize_recovery_code(code)
    if len(normalized) == 12:
        # Argon2 salts differ per code, so the match cannot be a SQL equality on the hash.
        unused = list(
            await db.scalars(
                select(MfaRecoveryCode).where(MfaRecoveryCode.user_id == user.id, MfaRecoveryCode.used_at.is_(None))
            )
        )
        index = await matching_single_use_code_async(normalized, [row.code_hash for row in unused])
        if index is not None:
            unused[index].used_at = utcnow()
            return "recovery_code"
    return None


async def guarded_second_factor(
    db: AsyncSession, settings: Settings, user: User, code: str, *, challenge_id: str | None = None
) -> str | None:
    """`check_second_factor` with a per-account limit on wrong codes (raises 429 when exceeded)."""
    key = f"mfa-fail:{user.id}"
    retry = await rate_limit.limiter.peek(key, MFA_MAX_FAILURES, MFA_FAILURE_WINDOW)
    if retry is not None:
        raise rate_limit.too_many(retry, f"Too many wrong codes. Try again in {int(retry // 60) + 1} minutes.")
    method = await check_second_factor(db, settings, user, code, challenge_id=challenge_id)
    if method is None:
        await rate_limit.limiter.hit(key, MFA_MAX_FAILURES, MFA_FAILURE_WINDOW)
    else:
        await rate_limit.limiter.clear(key)
    return method


async def finish_sign_in(
    db: AsyncSession,
    settings: Settings,
    request: Request,
    user: User,
    method: str,
    *,
    trusted_device_token: str | None = None,
) -> TokenResponse | MfaChallenge:
    """After the first factor: ask for the second one, or hand out the session tokens. Caller commits.

    A remembered device (valid `trusted_device_token`) skips the second step. Email-code accounts
    get their sign-in code sent right away.
    """
    ip = rate_limit.client_ip(request)
    if user.mfa_enabled:
        if await trusted_device_ok(db, user, trusted_device_token):
            tokens = await issue_tokens(db, settings, user, user_agent=request.headers.get("user-agent"))
            audit.record(db, "auth.login", user_id=user.id, ip=ip, detail={"method": method, "mfa": "trusted_device"})
            return tokens
        by_email = user.mfa_method == "email"
        minutes = max(settings.mfa_challenge_minutes, settings.mfa_email_code_minutes) if by_email else None
        token, expires_in = create_mfa_token(settings, user.id, method, minutes=minutes)
        sent = False
        if by_email:
            sent = await send_login_code(db, settings, request, user, decode_mfa_token(settings, token).challenge_id)
        audit.record(db, "auth.mfa_challenge", user_id=user.id, ip=ip, detail={"method": method})
        return MfaChallenge(
            mfa_token=token,
            expires_in=expires_in,
            method="email" if by_email else "totp",
            email_hint=mask_email(user.email) if by_email else None,
            code_sent=sent,
        )
    tokens = await issue_tokens(db, settings, user, user_agent=request.headers.get("user-agent"))
    audit.record(db, "auth.login", user_id=user.id, ip=ip, detail={"method": method})
    return tokens


def mask_email(email: str) -> str:
    """`ada.lovelace@example.com` -> `a**********e@example.com` (enough to recognise, not to read)."""
    local, _, domain = email.partition("@")
    if len(local) <= 2:
        return f"{local[:1]}*@{domain}"
    return f"{local[0]}{'*' * (len(local) - 2)}{local[-1]}@{domain}"


async def send_login_code(
    db: AsyncSession, settings: Settings, request: Request, user: User, challenge_id: str
) -> bool:
    """Email the sign-in code for this challenge. False when email is not configured. Caller commits."""
    mailer: Mailer | None = getattr(request.app.state, "mailer", None)
    if mailer is None:
        return False
    code = await issue_code(db, user, login_code_purpose(challenge_id), settings.mfa_email_code_minutes)
    text = (
        f"Hello {user.display_name},\n\n"
        f"Your DHANZ AI sign-in code is: {code}\n\n"
        f"It works for {settings.mfa_email_code_minutes} minutes, for this sign-in only. Never share it: DHANZ "
        "will never ask you for it.\n\n"
        "If you are not signing in right now, someone has your password. Change it in DHANZ AI "
        "(Settings → Security) as soon as you can.\n"
    )
    send_in_background(mailer, user.email, f"{code} is your DHANZ AI sign-in code", text)
    return True


async def send_manage_code(db: AsyncSession, settings: Settings, mailer: Mailer, user: User, purpose: str) -> None:
    """Email a code that confirms a security change (setting up or managing email codes). Caller commits."""
    code = await issue_code(db, user, purpose, settings.mfa_email_code_minutes)
    action = "turn on two-step verification" if purpose == SETUP_PURPOSE else "confirm a security change"
    text = (
        f"Hello {user.display_name},\n\n"
        f"Your DHANZ AI code to {action} is: {code}\n\n"
        f"It works for {settings.mfa_email_code_minutes} minutes. If you did not ask for it, change your "
        "password: someone may be signed in to your account.\n"
    )
    send_in_background(mailer, user.email, f"{code} is your DHANZ AI security code", text)


def security_notice(request: Request, user: User, subject: str, what: str) -> None:
    """Tell the account owner about a security change by email (when email is configured)."""
    mailer: Mailer | None = getattr(request.app.state, "mailer", None)
    if mailer is None:
        return
    text = (
        f"Hello {user.display_name},\n\n{what}\n\n"
        "If this was you, there is nothing to do. If it was not, change your password now and contact "
        "the DHANZ AI administrator.\n"
    )
    send_in_background(mailer, user.email, f"DHANZ AI security: {subject}", text)


# --- remembered (trusted) devices ------------------------------------------------------------------


def _device_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def device_label(user_agent: str | None) -> str:
    """A readable name for the device list ("Chrome on Windows", "DHANZ app on Android")."""
    ua = user_agent or ""
    low = ua.lower()
    system = next(
        (
            name
            for key, name in (
                ("android", "Android"),
                ("iphone", "iPhone"),
                ("ipad", "iPad"),
                ("windows", "Windows"),
                ("mac os", "Mac"),
                ("macintosh", "Mac"),
                ("linux", "Linux"),
            )
            if key in low
        ),
        None,
    )
    app = next(
        (
            name
            for key, name in (
                ("dart", "DHANZ app"),
                ("edg/", "Edge"),
                ("chrome", "Chrome"),
                ("firefox", "Firefox"),
                ("safari", "Safari"),
            )
            if key in low
        ),
        None,
    )
    if app and system:
        return f"{app} on {system}"
    return app or system or (ua[:60] or "Unknown device")


async def remember_device(db: AsyncSession, settings: Settings, user: User, user_agent: str | None) -> str | None:
    """Trust this device for `trusted_device_days`; returns the token for the client to keep (shown
    once, only its hash is stored), or None when the feature is off. Caller commits."""
    if settings.trusted_device_days <= 0:
        return None
    token = secrets.token_urlsafe(32)
    db.add(
        TrustedDevice(
            user_id=user.id,
            token_hash=_device_hash(token),
            label=device_label(user_agent)[:200],
            expires_at=utcnow() + timedelta(days=settings.trusted_device_days),
        )
    )
    await db.flush()
    devices = list(
        await db.scalars(
            select(TrustedDevice).where(TrustedDevice.user_id == user.id).order_by(TrustedDevice.created_at.desc())
        )
    )
    for old in devices[MAX_TRUSTED_DEVICES:]:
        await db.delete(old)
    return token


async def trusted_device_ok(db: AsyncSession, user: User, token: str | None) -> bool:
    """True when `token` is an unexpired remembered device of this user (and notes its use)."""
    if not token or len(token) > 200:
        return False
    device = await db.scalar(
        select(TrustedDevice).where(
            TrustedDevice.token_hash == _device_hash(token),
            TrustedDevice.user_id == user.id,
            TrustedDevice.expires_at > utcnow(),
        )
    )
    if device is None:
        return False
    device.last_used_at = utcnow()
    return True


async def forget_trusted_devices(db: AsyncSession, user_id) -> None:
    """Every remembered device must do the second step again. Caller commits."""
    await db.execute(delete(TrustedDevice).where(TrustedDevice.user_id == user_id))


def clear_mfa(user: User) -> None:
    """Turn two-step verification off on the user row (recovery codes and devices are separate)."""
    user.mfa_secret = None
    user.mfa_enabled_at = None
    user.mfa_last_step = None
    user.mfa_method = None
