from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.deps import DbDep, SettingsDep
from app.core import rate_limit
from app.core.security import hash_password, password_needs_rehash, verify_password
from app.models import User
from app.schemas import LoginRequest, RefreshRequest, RegisterRequest, TokenResponse
from app.services import audit
from app.services.auth_service import RefreshError, issue_tokens, revoke_token, rotate_refresh_token

router = APIRouter(prefix="/auth", tags=["auth"])


def _limit(request: Request, settings, bucket: str) -> str:
    ip = rate_limit.client_ip(request)
    rate_limit.enforce(f"auth:{bucket}:{ip}", settings.rate_limit_auth_per_minute)
    return ip


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, request: Request, db: DbDep, settings: SettingsDep) -> TokenResponse:
    ip = _limit(request, settings, "register")
    email = body.email.lower()
    if await db.scalar(select(User.id).where(User.email == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists")
    user = User(
        email=email,
        password_hash=hash_password(body.password),
        display_name=body.display_name,
        routing_policy=settings.default_routing_policy,
    )
    db.add(user)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists") from None
    tokens = await issue_tokens(db, settings, user, user_agent=request.headers.get("user-agent"))
    audit.record(db, "auth.register", user_id=user.id, ip=ip)
    await db.commit()
    return tokens


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, request: Request, db: DbDep, settings: SettingsDep) -> TokenResponse:
    ip = _limit(request, settings, "login")
    user = await db.scalar(select(User).where(User.email == body.email.lower()))
    if not verify_password(body.password, user.password_hash if user else None) or not user or not user.is_active:
        audit.record(db, "auth.login_failed", user_id=user.id if user else None, ip=ip)
        await db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    if user.password_hash and password_needs_rehash(user.password_hash):
        user.password_hash = hash_password(body.password)
    tokens = await issue_tokens(db, settings, user, user_agent=request.headers.get("user-agent"))
    audit.record(db, "auth.login", user_id=user.id, ip=ip)
    await db.commit()
    return tokens


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest, request: Request, db: DbDep, settings: SettingsDep) -> TokenResponse:
    _limit(request, settings, "refresh")
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
