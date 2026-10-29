"""Password hashing and token handling."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.config import Settings

_hasher = PasswordHasher()
# Verified against when the user does not exist, so login timing doesn't reveal which emails are registered.
_DUMMY_HASH = _hasher.hash("dummy-password-for-timing")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


# Argon2 deliberately takes ~50-100 ms of CPU: run it in a worker thread so one sign-in does not
# stall every other request (and streaming reply) handled by the same process.
async def hash_password_async(password: str) -> str:
    return await asyncio.to_thread(hash_password, password)


async def verify_password_async(password: str, password_hash: str | None) -> bool:
    return await asyncio.to_thread(verify_password, password, password_hash)


def password_needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


def create_access_token(
    settings: Settings, user_id: uuid.UUID, role: str, session_id: uuid.UUID | None = None
) -> tuple[str, int]:
    now = datetime.now(UTC)
    ttl = timedelta(minutes=settings.access_token_ttl_minutes)
    payload = {
        "sub": str(user_id),
        "role": role,
        "type": "access",
        "iat": now,
        "exp": now + ttl,
        "jti": uuid.uuid4().hex,
    }
    if session_id is not None:
        payload["sid"] = str(session_id)  # the refresh-token family: revoking it ends this token too
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm), int(ttl.total_seconds())


class InvalidTokenError(Exception):
    pass


def create_mfa_token(settings: Settings, user_id: uuid.UUID, method: str) -> tuple[str, int]:
    """Proof that the first sign-in factor (password, Google, Apple) succeeded; useless on its own."""
    now = datetime.now(UTC)
    ttl = timedelta(minutes=settings.mfa_challenge_minutes)
    payload = {"sub": str(user_id), "type": "mfa", "amr": method, "iat": now, "exp": now + ttl}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm), int(ttl.total_seconds())


def decode_mfa_token(settings: Settings, token: str) -> tuple[uuid.UUID, str]:
    try:
        payload = jwt.decode(
            token, settings.jwt_secret, algorithms=[settings.jwt_algorithm], options={"require": ["sub", "exp", "type"]}
        )
        if payload.get("type") != "mfa":
            raise InvalidTokenError("wrong token type")
        return uuid.UUID(payload["sub"]), str(payload.get("amr", "pwd"))
    except (jwt.PyJWTError, ValueError) as exc:
        raise InvalidTokenError(str(exc)) from exc


@dataclass(frozen=True)
class AccessClaims:
    user_id: uuid.UUID
    session_id: uuid.UUID | None


def decode_access_token(settings: Settings, token: str) -> AccessClaims:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["sub", "exp", "iat", "type"]},
        )
    except jwt.PyJWTError as exc:
        raise InvalidTokenError(str(exc)) from exc
    if payload.get("type") != "access":
        raise InvalidTokenError("wrong token type")
    try:
        sid = payload.get("sid")
        return AccessClaims(uuid.UUID(payload["sub"]), uuid.UUID(sid) if sid else None)
    except ValueError as exc:
        raise InvalidTokenError("bad subject") from exc


def new_refresh_token() -> str:
    """Opaque refresh token; only its SHA-256 hash is stored."""
    return secrets.token_urlsafe(48)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def new_reset_code() -> str:
    """Password-reset code typed by the user: 10 characters, ~50 bits, unambiguous alphabet."""
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(10))


def new_numeric_code(digits: int = 6) -> str:
    """Short code typed from an email (email verification)."""
    return "".join(secrets.choice("0123456789") for _ in range(digits))


def normalize_reset_code(code: str) -> str:
    return "".join(ch for ch in code.upper() if ch.isalnum())


def same_hash(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())
