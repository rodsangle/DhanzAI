"""Sign in with Google / Apple: verify the ID token the app received from the provider.

The apps run the provider's own sign-in UI and send the resulting OpenID Connect ID token here. The
server checks its signature against the provider's published keys (JWKS), the issuer, the audience
(one of our OAuth client IDs), the expiry and, when the app sent one, the nonce. Nothing else from
the client is trusted: the account is identified by the provider's stable `sub`.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import time
from dataclasses import dataclass
from typing import Literal

import httpx
import jwt

from app.core.config import Settings

log = logging.getLogger(__name__)

ProviderName = Literal["google", "apple"]


@dataclass(frozen=True)
class ProviderSpec:
    jwks_url: str
    issuers: tuple[str, ...]


PROVIDERS: dict[str, ProviderSpec] = {
    "google": ProviderSpec(
        "https://www.googleapis.com/oauth2/v3/certs", ("https://accounts.google.com", "accounts.google.com")
    ),
    "apple": ProviderSpec("https://appleid.apple.com/auth/keys", ("https://appleid.apple.com",)),
}

JWKS_TTL_SECONDS = 3600
# An unknown key id triggers a refetch (providers rotate keys), but not more often than this.
JWKS_REFRESH_MIN_SECONDS = 60


class IdTokenError(Exception):
    """The token is not a valid sign-in for this server (message is safe to show)."""


@dataclass(frozen=True)
class VerifiedIdentity:
    provider: str
    subject: str
    email: str | None
    email_verified: bool
    name: str | None


def _truthy(value: object) -> bool:
    return value is True or (isinstance(value, str) and value.lower() == "true")


class IdTokenVerifier:
    def __init__(self, settings: Settings, http: httpx.AsyncClient | None = None) -> None:
        self.audiences: dict[str, list[str]] = {
            "google": settings.google_client_id_list,
            "apple": settings.apple_client_id_list,
        }
        self._http = http
        self._keys: dict[str, tuple[float, dict[str, jwt.PyJWK]]] = {}
        self._lock = asyncio.Lock()

    def enabled(self, provider: str) -> bool:
        return bool(self.audiences.get(provider))

    async def _client(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(timeout=10)
        return self._http

    async def _fetch(self, provider: str) -> dict[str, jwt.PyJWK]:
        client = await self._client()
        try:
            resp = await client.get(PROVIDERS[provider].jwks_url)
            resp.raise_for_status()
            keys = {}
            for data in resp.json().get("keys", []):
                try:
                    keys[data["kid"]] = jwt.PyJWK(data)
                except (KeyError, jwt.PyJWTError):
                    continue
            return keys
        except (httpx.HTTPError, ValueError) as exc:
            log.warning("Could not fetch %s signing keys: %s", provider, exc)
            raise IdTokenError(f"Could not reach {provider.title()} to check the sign-in. Try again.") from exc

    async def _key(self, provider: str, kid: str) -> jwt.PyJWK:
        async with self._lock:
            fetched_at, keys = self._keys.get(provider, (0.0, {}))
            age = time.monotonic() - fetched_at
            if age > JWKS_TTL_SECONDS or (kid not in keys and age > JWKS_REFRESH_MIN_SECONDS):
                keys = await self._fetch(provider)
                self._keys[provider] = (time.monotonic(), keys)
        if kid not in keys:
            raise IdTokenError("The sign-in token is not valid.")
        return keys[kid]

    async def verify(self, provider: str, token: str, nonce: str | None = None) -> VerifiedIdentity:
        if provider not in PROVIDERS or not self.enabled(provider):
            raise IdTokenError(f"Sign in with {provider.title()} is not enabled on this server.")
        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError as exc:
            raise IdTokenError("The sign-in token is not valid.") from exc
        if header.get("alg") != "RS256" or not header.get("kid"):
            raise IdTokenError("The sign-in token is not valid.")
        key = await self._key(provider, header["kid"])
        try:
            claims = jwt.decode(
                token,
                key.key,
                algorithms=["RS256"],
                audience=self.audiences[provider],
                issuer=list(PROVIDERS[provider].issuers),
                options={"require": ["iss", "aud", "sub", "exp", "iat"]},
                leeway=60,
            )
        except jwt.ExpiredSignatureError as exc:
            raise IdTokenError("The sign-in expired. Please try again.") from exc
        except jwt.PyJWTError as exc:
            raise IdTokenError("The sign-in token is not valid.") from exc
        if nonce is not None:
            # Google echoes the nonce; Sign in with Apple stores its SHA-256 (hex).
            got = str(claims.get("nonce", ""))
            hashed = hashlib.sha256(nonce.encode()).hexdigest()
            if not (hmac.compare_digest(got, nonce) or hmac.compare_digest(got, hashed)):
                raise IdTokenError("The sign-in token is not valid.")
        email = claims.get("email")
        return VerifiedIdentity(
            provider=provider,
            subject=str(claims["sub"]),
            email=email.lower() if isinstance(email, str) else None,
            email_verified=_truthy(claims.get("email_verified")),
            name=claims.get("name") if isinstance(claims.get("name"), str) else None,
        )

    async def aclose(self) -> None:
        if self._http is not None:
            await self._http.aclose()
