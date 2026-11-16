"""Two-step verification endpoints, at the same paths the DHANZ app already uses."""

from __future__ import annotations

import json
import logging
from datetime import datetime

from fastapi import APIRouter, FastAPI, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select

from app.api.deps import CurrentUser, DbDep, SettingsDep, current_session, parse_uuid
from app.core import rate_limit
from app.core.security import verify_password_async
from app.db.base import utcnow
from app.models import User
from app.schemas import UserOut
from app.services import audit
from app.services.auth_service import issue_tokens, revoke_user_sessions

from . import core, service
from .models import TwoStepDevice, TwoStepRecoveryCode, TwoStepSetting

log = logging.getLogger(__name__)

auth_router = APIRouter(prefix="/auth", tags=["two-step"])
me_router = APIRouter(prefix="/users/me", tags=["two-step"])


class VerifyRequest(BaseModel):
    mfa_token: str = Field(min_length=20, max_length=2000)
    code: str = Field(min_length=6, max_length=20)
    remember_device: bool = False


class SetupRequest(BaseModel):
    password: str | None = Field(default=None, max_length=128)


class CodeRequest(BaseModel):
    code: str = Field(min_length=6, max_length=20)


class DeviceOut(BaseModel):
    id: str
    label: str
    created_at: datetime
    last_used_at: datetime
    expires_at: datetime


async def _user_json(request: Request, db, user: User) -> dict:
    """The user exactly as the server's own /users/me shows it, plus the two-step fields."""
    data = json.loads(UserOut.model_validate(user).model_dump_json())
    data.update(await service.status(db, user.id))
    data.setdefault("has_password", user.password_hash is not None)
    return data


# --- sign-in -------------------------------------------------------------------------------------------


@auth_router.post("/mfa/verify")
async def verify(body: VerifyRequest, request: Request, db: DbDep, settings: SettingsDep) -> Response:
    """Second sign-in step: the authenticator code or a recovery code."""
    ip = rate_limit.client_ip(request)
    await rate_limit.enforce(f"auth:mfa:{ip}", settings.rate_limit_auth_per_minute)
    expired = HTTPException(status.HTTP_401_UNAUTHORIZED, "This sign-in has expired. Please start again.")
    ticket = service.read_challenge(settings, body.mfa_token)
    if ticket is None:
        raise expired
    user = await db.get(User, ticket.user_id)
    setting = await service.enabled_setting(db, ticket.user_id)
    if user is None or not user.is_active or setting is None:
        raise expired
    method = await service.guarded_check(db, settings, setting, body.code)
    if method is None:
        audit.record(db, "auth.mfa_failed", user_id=user.id, ip=ip)
        await db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "That code is not correct. Check the time on your phone.")
    user_agent = request.headers.get("user-agent")
    tokens = await issue_tokens(db, settings, user, user_agent=user_agent)
    device = await service.remember_device(db, settings, user, user_agent) if body.remember_device else None
    audit.record(
        db,
        "auth.login",
        user_id=user.id,
        ip=ip,
        detail={"method": "password", "mfa": method, "remembered": bool(device)},
    )
    await db.commit()
    data = json.loads(tokens.model_dump_json())
    data["user"].update(await service.status(db, user.id))
    data["user"].setdefault("has_password", user.password_hash is not None)
    data["trusted_device_token"] = device
    return Response(json.dumps(data), media_type="application/json")


# --- settings ------------------------------------------------------------------------------------------


async def _require_password(user: User, password: str | None) -> None:
    if user.password_hash and not (password and await verify_password_async(password, user.password_hash)):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Password is incorrect")


@me_router.post("/mfa/setup")
async def setup(body: SetupRequest, user: CurrentUser, db: DbDep, settings: SettingsDep) -> dict:
    """Start turning on two-step verification: a new secret for an authenticator app (QR code).
    Nothing changes for sign-in until /users/me/mfa/enable receives a code from the app."""
    await rate_limit.enforce(f"mfa-setup:{user.id}", 5)
    row = await service.setting_for(db, user.id)
    if row is not None and row.enabled_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Two-factor authentication is already on")
    await _require_password(user, body.password)
    secret = core.new_secret()
    if row is None:
        row = TwoStepSetting(user_id=user.id)
        db.add(row)
    row.method, row.secret, row.last_step = "totp", core.encrypt_secret(settings, secret), None
    await db.commit()
    return {"secret": secret, "otpauth_uri": core.provisioning_uri(secret, user.email)}


@me_router.post("/mfa/enable")
async def enable(body: CodeRequest, request: Request, user: CurrentUser, db: DbDep, settings: SettingsDep) -> dict:
    """Confirm the authenticator app works; returns ten single-use recovery codes (shown only now)."""
    await rate_limit.enforce(f"mfa-enable:{user.id}", 10)
    row = await service.setting_for(db, user.id)
    if row is not None and row.enabled_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Two-factor authentication is already on")
    if row is None or not row.secret:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Start the setup first")
    step = core.match_step(core.decrypt_secret(settings, row.secret), body.code)
    if step is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "That code is not correct. Check the time on your phone.")
    row.last_step, row.enabled_at = step, utcnow()
    codes = await service.new_recovery_codes(db, user.id)
    # Sessions on other devices were opened with the password only.
    ended = await revoke_user_sessions(db, user.id, keep=current_session(request))
    audit.record(
        db, "user.mfa_enabled", user_id=user.id, ip=rate_limit.client_ip(request), detail={"sessions_ended": ended}
    )
    await db.commit()
    return {"recovery_codes": codes}


async def _confirmed(db, settings, user: User, code: str) -> TwoStepSetting:
    row = await service.enabled_setting(db, user.id)
    if row is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Two-factor authentication is off")
    if await service.guarded_check(db, settings, row, code) is None:
        await db.commit()  # keep the failed-attempt state
        raise HTTPException(status.HTTP_403_FORBIDDEN, "That code is not correct")
    return row


@me_router.post("/mfa/disable")
async def disable(body: CodeRequest, request: Request, user: CurrentUser, db: DbDep, settings: SettingsDep) -> dict:
    if await service.enabled_setting(db, user.id) is None:
        return await _user_json(request, db, user)
    row = await _confirmed(db, settings, user, body.code)
    await db.delete(row)
    await db.execute(delete(TwoStepRecoveryCode).where(TwoStepRecoveryCode.user_id == user.id))
    await service.forget_devices(db, user.id)
    audit.record(db, "user.mfa_disabled", user_id=user.id, ip=rate_limit.client_ip(request))
    await db.commit()
    return await _user_json(request, db, user)


@me_router.post("/mfa/recovery-codes")
async def replace_codes(
    body: CodeRequest, request: Request, user: CurrentUser, db: DbDep, settings: SettingsDep
) -> dict:
    """Replace all recovery codes (the old ones stop working)."""
    await _confirmed(db, settings, user, body.code)
    codes = await service.new_recovery_codes(db, user.id)
    audit.record(db, "user.mfa_recovery_codes_replaced", user_id=user.id, ip=rate_limit.client_ip(request))
    await db.commit()
    return {"recovery_codes": codes}


@me_router.get("/mfa/recovery-codes/remaining")
async def codes_left(user: CurrentUser, db: DbDep) -> dict:
    left = await db.scalar(
        select(func.count(TwoStepRecoveryCode.id)).where(
            TwoStepRecoveryCode.user_id == user.id, TwoStepRecoveryCode.used_at.is_(None)
        )
    )
    return {"remaining": left or 0}


@me_router.get("/trusted-devices", response_model=list[DeviceOut])
async def devices(user: CurrentUser, db: DbDep) -> list[DeviceOut]:
    rows = await db.scalars(
        select(TwoStepDevice)
        .where(TwoStepDevice.user_id == user.id, TwoStepDevice.expires_at > utcnow())
        .order_by(TwoStepDevice.last_used_at.desc())
    )
    fingerprint = service.password_fingerprint(user)
    return [
        DeviceOut(
            id=str(d.id), label=d.label, created_at=d.created_at, last_used_at=d.last_used_at, expires_at=d.expires_at
        )
        for d in rows
        if d.password_fingerprint == fingerprint
    ]


@me_router.delete("/trusted-devices/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
async def forget_device(device_id: str, request: Request, user: CurrentUser, db: DbDep) -> Response:
    device = await db.get(TwoStepDevice, parse_uuid(device_id))
    if device is None or device.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Device not found")
    await db.delete(device)
    audit.record(db, "user.trusted_device_forgotten", user_id=user.id, ip=rate_limit.client_ip(request))
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@me_router.delete("/trusted-devices", status_code=status.HTTP_204_NO_CONTENT)
async def forget_all(request: Request, user: CurrentUser, db: DbDep) -> Response:
    await service.forget_devices(db, user.id)
    audit.record(db, "user.trusted_devices_forgotten", user_id=user.id, ip=rate_limit.client_ip(request))
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- two-step status in the existing replies -----------------------------------------------------------

# Replies of the server's own routes that carry a user (or the sign-in options): the app shows
# two-step verification in Settings when a user object reports `mfa_enabled`.
USER_PATHS = ("/users/me", "/auth/login", "/auth/register", "/auth/refresh")
OPTIONS_PATH = "/auth/options"


class StatusMiddleware:
    """Adds the two-step fields to the server's own replies that carry a user (and to the sign-in
    options). Installed innermost, so it sees plain JSON before compression."""

    def __init__(self, app, *, api_prefix: str, settings, fastapi_app) -> None:
        self.app = app
        self.settings = settings
        self.fastapi_app = fastapi_app
        self.user_paths = {api_prefix + p for p in USER_PATHS}
        self.options_path = api_prefix + OPTIONS_PATH

    async def __call__(self, scope, receive, send):
        path = scope.get("path") if scope["type"] == "http" else None
        if path not in self.user_paths and path != self.options_path:
            await self.app(scope, receive, send)
            return
        start: dict = {}
        chunks: list[bytes] = []

        async def capture(message):
            if message["type"] == "http.response.start":
                start.update(message)
                return
            if message["type"] != "http.response.body":
                await send(message)
                return
            chunks.append(message.get("body", b""))
            if message.get("more_body"):
                return
            body = b"".join(chunks)
            if start.get("status") in (200, 201):
                try:
                    body = await self._augment(body, options=path == self.options_path)
                except Exception:  # noqa: BLE001 - never break the original reply
                    log.exception("Could not add two-step status to %s", path)
            headers = [(k, v) for k, v in start.get("headers", []) if k.lower() != b"content-length"]
            headers.append((b"content-length", str(len(body)).encode()))
            await send({**start, "headers": headers})
            await send({"type": "http.response.body", "body": body})

        await self.app(scope, receive, capture)

    async def _augment(self, body: bytes, *, options: bool) -> bytes:
        data = json.loads(body)
        if not isinstance(data, dict):
            return body
        if options:
            data.setdefault("mfa_email", False)
            data["trusted_device_days"] = service.trusted_device_days(self.settings)
            return json.dumps(data).encode()
        target = data.get("user") if isinstance(data.get("user"), dict) else data
        if "id" not in target or "email" not in target or "mfa_required" in data:
            return body
        async with self.fastapi_app.state.sessionmaker() as db:
            target.update(await service.status(db, parse_uuid(str(target["id"]))))
        target.setdefault("has_password", True)
        return json.dumps(data).encode()


def install(app: FastAPI) -> None:
    if getattr(app.state, "dhanz_two_step", False):
        return
    app.state.dhanz_two_step = True
    settings = app.state.settings
    prefix = settings.api_prefix
    # First in the routing order: these paths are new on servers without built-in two-step
    # verification, and come before any older handlers that share them.
    before = len(app.router.routes)
    app.include_router(auth_router, prefix=prefix)
    app.include_router(me_router, prefix=prefix)
    added = app.router.routes[before:]
    del app.router.routes[before:]
    app.router.routes[0:0] = added
    # Innermost middleware (the end of the list): it sees replies before compression.
    from starlette.middleware import Middleware

    app.user_middleware.append(Middleware(StatusMiddleware, api_prefix=prefix, settings=settings, fastapi_app=app))
