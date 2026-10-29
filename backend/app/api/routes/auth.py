from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

from app.api.deps import DbDep, SettingsDep
from app.core import rate_limit
from app.core.security import (
    hash_password,
    hash_token,
    new_reset_code,
    normalize_reset_code,
    password_needs_rehash,
    same_hash,
    verify_password,
)
from app.db.base import utcnow
from app.models import PasswordResetToken, User
from app.schemas import (
    AuthOptions,
    LoginRequest,
    PasswordResetConfirm,
    PasswordResetRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
)
from app.services import audit
from app.services.auth_service import (
    RefreshError,
    issue_tokens,
    revoke_token,
    revoke_user_sessions,
    rotate_refresh_token,
)

log = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])

RESET_MAX_ATTEMPTS = 5
_background: set[asyncio.Task] = set()


async def _limit(request: Request, settings, bucket: str) -> str:
    ip = rate_limit.client_ip(request)
    await rate_limit.enforce(f"auth:{bucket}:{ip}", settings.rate_limit_auth_per_minute)
    return ip


@router.get("/options", response_model=AuthOptions)
async def auth_options(request: Request, db: DbDep, settings: SettingsDep) -> AuthOptions:
    """What the sign-in screen can offer (no authentication needed)."""
    open_ = settings.allow_registration or not await db.scalar(select(func.count(User.id)))
    return AuthOptions(registration_open=open_, password_reset=request.app.state.mailer is not None)


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, request: Request, db: DbDep, settings: SettingsDep) -> TokenResponse:
    ip = await _limit(request, settings, "register")
    first_user = not await db.scalar(select(func.count(User.id)))
    if not settings.allow_registration and not first_user:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Registration is closed on this server. Ask the administrator.")
    email = body.email.lower()
    if await db.scalar(select(User.id).where(User.email == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists")
    user = User(
        email=email,
        password_hash=hash_password(body.password),
        display_name=body.display_name,
        routing_policy=settings.default_routing_policy,
        # The first account on a new server administers it.
        role="admin" if first_user else "user",
    )
    db.add(user)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists") from None
    tokens = await issue_tokens(db, settings, user, user_agent=request.headers.get("user-agent"))
    audit.record(db, "auth.register", user_id=user.id, ip=ip, detail={"role": user.role})
    await db.commit()
    return tokens


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, request: Request, db: DbDep, settings: SettingsDep) -> TokenResponse:
    ip = await _limit(request, settings, "login")
    email = body.email.lower()
    # Per-account lockout, applied to every email (registered or not) so it reveals nothing.
    lock_key, window = f"login-fail:{email}", settings.login_lockout_minutes * 60
    retry = await rate_limit.limiter.peek(lock_key, settings.login_lockout_attempts, window)
    if retry is not None:
        raise rate_limit.too_many(
            retry,
            f"Too many failed sign-in attempts for this account. Try again in {int(retry // 60) + 1} minutes "
            "or reset your password.",
        )
    user = await db.scalar(select(User).where(User.email == email))
    if not verify_password(body.password, user.password_hash if user else None) or not user or not user.is_active:
        await rate_limit.limiter.hit(lock_key, settings.login_lockout_attempts, window)
        audit.record(db, "auth.login_failed", user_id=user.id if user else None, ip=ip)
        await db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    await rate_limit.limiter.clear(lock_key)
    if user.password_hash and password_needs_rehash(user.password_hash):
        user.password_hash = hash_password(body.password)
    tokens = await issue_tokens(db, settings, user, user_agent=request.headers.get("user-agent"))
    audit.record(db, "auth.login", user_id=user.id, ip=ip)
    await db.commit()
    return tokens


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest, request: Request, db: DbDep, settings: SettingsDep) -> TokenResponse:
    await _limit(request, settings, "refresh")
    try:
        tokens = await rotate_refresh_token(
            db, settings, body.refresh_token, user_agent=request.headers.get("user-agent")
        )
    except RefreshError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired. Please sign in again.") from None
    await db.commit()
    return tokens


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(body: RefreshRequest, request: Request, db: DbDep) -> Response:
    # Works with an expired access token: possession of the refresh token is enough to end that session.
    user_id = await revoke_token(db, body.refresh_token)
    if user_id:
        audit.record(db, "auth.logout", user_id=user_id, ip=rate_limit.client_ip(request))
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/password-reset/request", status_code=status.HTTP_202_ACCEPTED)
async def request_password_reset(
    body: PasswordResetRequest, request: Request, db: DbDep, settings: SettingsDep
) -> dict:
    """Email a one-time code. Always answers the same way, whether or not the account exists."""
    mailer = request.app.state.mailer
    if mailer is None:
        raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "Password reset by email is not configured on this server")
    ip = await _limit(request, settings, "reset")
    email = body.email.lower()
    accepted = {"detail": "If an account exists for this email, a reset code has been sent."}
    if await rate_limit.limiter.hit(f"reset-mail:{email}", 3, 3600) is not None:
        return accepted  # at most 3 emails per hour per address
    user = await db.scalar(select(User).where(User.email == email))
    if user is None or not user.is_active:
        return accepted
    await db.execute(
        update(PasswordResetToken)
        .where(PasswordResetToken.user_id == user.id, PasswordResetToken.used_at.is_(None))
        .values(used_at=utcnow())
    )
    code = new_reset_code()
    db.add(
        PasswordResetToken(
            user_id=user.id,
            code_hash=hash_token(code),
            attempts=0,
            expires_at=utcnow() + timedelta(minutes=settings.password_reset_ttl_minutes),
        )
    )
    audit.record(db, "auth.password_reset_requested", user_id=user.id, ip=ip)
    await db.commit()
    pretty = f"{code[:5]}-{code[5:]}"
    text = (
        f"Hello {user.display_name},\n\n"
        f"Your DHANZ AI password reset code is: {pretty}\n\n"
        f"Enter it in the app within {settings.password_reset_ttl_minutes} minutes. "
        "If you did not ask for this, you can ignore this email; your password stays the same.\n"
    )

    async def send() -> None:
        try:
            await mailer.send(user.email, "Your DHANZ AI password reset code", text)
        except Exception:  # noqa: BLE001 - logged; the response must not reveal delivery problems
            log.exception("Could not send the password reset email")

    # Sent in the background so the response time does not reveal whether the account exists.
    task = asyncio.create_task(send())
    _background.add(task)
    task.add_done_callback(_background.discard)
    return accepted


@router.post("/password-reset/confirm", status_code=status.HTTP_204_NO_CONTENT)
async def confirm_password_reset(
    body: PasswordResetConfirm, request: Request, db: DbDep, settings: SettingsDep
) -> Response:
    ip = await _limit(request, settings, "reset-confirm")
    invalid = HTTPException(status.HTTP_400_BAD_REQUEST, "The code is invalid or has expired. Request a new one.")
    user = await db.scalar(select(User).where(User.email == body.email.lower()))
    if user is None or not user.is_active:
        raise invalid
    token = await db.scalar(
        select(PasswordResetToken)
        .where(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.used_at.is_(None),
            PasswordResetToken.expires_at > utcnow(),
        )
        .order_by(PasswordResetToken.created_at.desc())
        .limit(1)
    )
    if token is None or token.attempts >= RESET_MAX_ATTEMPTS:
        raise invalid
    if not same_hash(token.code_hash, hash_token(normalize_reset_code(body.code))):
        token.attempts += 1
        if token.attempts >= RESET_MAX_ATTEMPTS:
            token.used_at = utcnow()  # burn it: guessing must start over with a new email
        await db.commit()
        raise invalid
    token.used_at = utcnow()
    user.password_hash = hash_password(body.new_password)
    user.updated_at = utcnow()
    ended = await revoke_user_sessions(db, user.id)
    await rate_limit.limiter.clear(f"login-fail:{user.email}")
    audit.record(db, "auth.password_reset", user_id=user.id, ip=ip, detail={"sessions_ended": ended})
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
