"""Push notifications: Firebase Cloud Messaging (Android) and Apple Push Notification service (iOS).

Both use their official HTTP APIs directly (FCM HTTP v1 with a service account, APNs with
token-based .p8 authentication), so no vendor SDK is needed on the server.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

import httpx
import jwt
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.observability import PUSH_SENT
from app.models import Device

log = logging.getLogger(__name__)


class InvalidToken(Exception):
    """The device token is no longer valid and should be forgotten."""


@dataclass(frozen=True)
class Notification:
    title: str
    body: str
    data: dict[str, str]


class FcmSender:
    platform = "android"
    SCOPE = "https://www.googleapis.com/auth/firebase.messaging"

    def __init__(self, service_account: dict, client: httpx.AsyncClient | None = None):
        self.account = service_account
        self.project_id = service_account["project_id"]
        self._client = client or httpx.AsyncClient(timeout=15.0)
        self._token: tuple[str, float] | None = None

    async def _access_token(self) -> str:
        if self._token and self._token[1] - 60 > time.time():
            return self._token[0]
        now = int(time.time())
        token_uri = self.account.get("token_uri", "https://oauth2.googleapis.com/token")
        assertion = jwt.encode(
            {"iss": self.account["client_email"], "scope": self.SCOPE, "aud": token_uri, "iat": now, "exp": now + 3600},
            self.account["private_key"],
            algorithm="RS256",
        )
        r = await self._client.post(
            token_uri,
            data={"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": assertion},
        )
        r.raise_for_status()
        body = r.json()
        self._token = (body["access_token"], time.time() + int(body.get("expires_in", 3600)))
        return self._token[0]

    async def send(self, token: str, n: Notification) -> None:
        message = {
            "message": {
                "token": token,
                "notification": {"title": n.title, "body": n.body},
                "data": n.data,
                "android": {"priority": "high", "notification": {"channel_id": "dhanz_replies"}},
            }
        }
        r = await self._client.post(
            f"https://fcm.googleapis.com/v1/projects/{self.project_id}/messages:send",
            json=message,
            headers={"Authorization": f"Bearer {await self._access_token()}"},
        )
        if r.status_code == 404 or (r.status_code == 400 and "registration token" in r.text.lower()):
            raise InvalidToken(token)
        if "UNREGISTERED" in r.text:
            raise InvalidToken(token)
        r.raise_for_status()


class ApnsSender:
    platform = "ios"

    def __init__(
        self,
        team_id: str,
        key_id: str,
        private_key: str,
        bundle_id: str,
        *,
        sandbox: bool = False,
        client: httpx.AsyncClient | None = None,
    ):
        self.team_id, self.key_id, self.private_key, self.bundle_id = team_id, key_id, private_key, bundle_id
        self.host = "https://api.sandbox.push.apple.com" if sandbox else "https://api.push.apple.com"
        self._client = client or httpx.AsyncClient(http2=True, timeout=15.0)  # APNs requires HTTP/2
        self._jwt: tuple[str, float] | None = None

    def _provider_token(self) -> str:
        # Apple rejects tokens older than an hour and throttles refreshes more often than every 20 minutes.
        if self._jwt and time.time() - self._jwt[1] < 45 * 60:
            return self._jwt[0]
        token = jwt.encode(
            {"iss": self.team_id, "iat": int(time.time())},
            self.private_key,
            algorithm="ES256",
            headers={"kid": self.key_id},
        )
        self._jwt = (token, time.time())
        return token

    async def send(self, token: str, n: Notification) -> None:
        payload = {"aps": {"alert": {"title": n.title, "body": n.body}, "sound": "default"}, **n.data}
        r = await self._client.post(
            f"{self.host}/3/device/{token}",
            json=payload,
            headers={
                "authorization": f"bearer {self._provider_token()}",
                "apns-topic": self.bundle_id,
                "apns-push-type": "alert",
                "apns-priority": "10",
            },
        )
        if r.status_code == 410 or (
            r.status_code == 400 and any(k in r.text for k in ("BadDeviceToken", "DeviceTokenNotForTopic"))
        ):
            raise InvalidToken(token)
        r.raise_for_status()


class PushService:
    def __init__(self, senders: list):
        self.senders = {s.platform: s for s in senders}

    @property
    def enabled(self) -> bool:
        return bool(self.senders)

    async def notify_user(
        self, maker: async_sessionmaker[AsyncSession], user_id: uuid.UUID, notification: Notification
    ) -> int:
        """Send to all the user's registered devices. Returns how many were delivered."""
        async with maker() as db:
            devices = list(await db.scalars(select(Device).where(Device.user_id == user_id)))
        delivered, invalid = 0, []
        for device in devices:
            sender = self.senders.get(device.platform)
            if sender is None:
                continue
            try:
                await sender.send(device.token, notification)
                delivered += 1
                PUSH_SENT.labels(device.platform, "delivered").inc()
            except InvalidToken:
                invalid.append(device.id)
                PUSH_SENT.labels(device.platform, "invalid_token").inc()
            except httpx.HTTPError as exc:
                log.warning("Push to %s device failed: %s", device.platform, exc)
                PUSH_SENT.labels(device.platform, "failed").inc()
        if invalid:
            async with maker() as db:
                await db.execute(delete(Device).where(Device.id.in_(invalid)))
                await db.commit()
        return delivered

    async def aclose(self) -> None:
        for sender in self.senders.values():
            await sender._client.aclose()


def _read_secret(inline: str | None, path: str | None) -> str | None:
    if inline:
        return inline
    if path:
        return Path(path).read_text(encoding="utf-8")
    return None


def build_push(settings: Settings) -> PushService:
    senders: list = []
    fcm = _read_secret(settings.fcm_service_account_json, settings.fcm_service_account_file)
    if fcm:
        senders.append(FcmSender(json.loads(fcm)))
    apns_key = _read_secret(settings.apns_private_key, settings.apns_private_key_file)
    if apns_key and settings.apns_team_id and settings.apns_key_id and settings.apns_bundle_id:
        senders.append(
            ApnsSender(
                settings.apns_team_id,
                settings.apns_key_id,
                apns_key,
                settings.apns_bundle_id,
                sandbox=settings.apns_use_sandbox,
            )
        )
    return PushService(senders)
