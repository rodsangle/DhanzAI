"""Two-factor authentication: TOTP codes (RFC 6238, as used by authenticator apps) and secret encryption."""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import struct
import time
from urllib.parse import quote, urlencode

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.core.config import Settings

STEP_SECONDS = 30
DIGITS = 6
# Accept the previous and next 30-second code too: phone clocks drift.
WINDOW = 1
ISSUER = "DHANZ AI"
RECOVERY_CODE_COUNT = 10


def new_secret() -> str:
    """160-bit secret, base32 without padding (what authenticator apps expect)."""
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def _key(secret: str) -> bytes:
    return base64.b32decode(secret + "=" * (-len(secret) % 8))


def code_at(secret: str, step: int) -> str:
    digest = hmac.new(_key(secret), struct.pack(">Q", step), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(value % 10**DIGITS).zfill(DIGITS)


def current_step(now: float | None = None) -> int:
    return int((time.time() if now is None else now) // STEP_SECONDS)


def match_step(secret: str, code: str, *, now: float | None = None, after: int | None = None) -> int | None:
    """The time step `code` belongs to, or None. Steps at or before `after` (already used) never match."""
    code = "".join(ch for ch in code if ch.isdigit())
    if len(code) != DIGITS:
        return None
    step = current_step(now)
    for candidate in range(step - WINDOW, step + WINDOW + 1):
        if after is not None and candidate <= after:
            continue
        if hmac.compare_digest(code_at(secret, candidate), code):
            return candidate
    return None


def provisioning_uri(secret: str, account: str) -> str:
    """otpauth:// link shown as a QR code (Google Authenticator, Microsoft Authenticator, 1Password, ...)."""
    label = quote(f"{ISSUER}:{account}")
    params = urlencode({"secret": secret, "issuer": ISSUER, "digits": DIGITS, "period": STEP_SECONDS})
    return f"otpauth://totp/{label}?{params}"


def new_recovery_codes() -> list[str]:
    """Ten single-use codes like `7KQ4-M2XD-9PRT` (~60 bits each)."""
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    codes = []
    for _ in range(RECOVERY_CODE_COUNT):
        raw = "".join(secrets.choice(alphabet) for _ in range(12))
        codes.append(f"{raw[:4]}-{raw[4:8]}-{raw[8:]}")
    return codes


def normalize_recovery_code(code: str) -> str:
    return "".join(ch for ch in code.upper() if ch.isalnum())


# --- secrets at rest -------------------------------------------------------------------------------
# TOTP secrets must be readable by the server (to compute codes), so they are encrypted rather than
# hashed: AES-256-GCM with a key derived from DATA_ENCRYPTION_KEY (falling back to JWT_SECRET).


def _aead(settings: Settings) -> AESGCM:
    material = (settings.data_encryption_key or settings.jwt_secret).encode()
    key = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=b"dhanz-ai/mfa-secret/v1").derive(material)
    return AESGCM(key)


def encrypt_secret(settings: Settings, secret: str) -> str:
    nonce = os.urandom(12)
    sealed = _aead(settings).encrypt(nonce, secret.encode(), b"mfa")
    return "v1:" + base64.urlsafe_b64encode(nonce + sealed).decode()


def decrypt_secret(settings: Settings, stored: str) -> str:
    if not stored.startswith("v1:"):
        raise ValueError("unknown secret format")
    raw = base64.urlsafe_b64decode(stored[3:])
    return _aead(settings).decrypt(raw[:12], raw[12:], b"mfa").decode()
