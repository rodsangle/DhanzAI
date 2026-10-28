"""Phase 4: background replies, stop, push notifications, device registration, app updates."""

import asyncio
import json
import threading
import time

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from fastapi.testclient import TestClient

from app.core.rate_limit import limiter
from app.main import create_app
from app.services import chat_service
from app.services.push import ApnsSender, FcmSender, InvalidToken, Notification, PushService
from app.services.turns import TurnManager
from dhanz_ai import Orchestrator, StreamChunk
from tests.conftest import EchoProvider, parse_sse


class SlowProvider(EchoProvider):
    """Streams many words slowly so a reply is still running while the test acts on it."""

    def __init__(self, words: int = 200, delay: float = 0.02) -> None:
        super().__init__("slow")
        self.words, self.delay = words, delay

    async def stream(self, model, messages, params):
        self.last_messages = list(messages)
        for i in range(self.words):
            await asyncio.sleep(self.delay)
            yield StreamChunk(text=f"w{i} ")
        yield StreamChunk(done=True, input_tokens=1, output_tokens=self.words)


class FakePush(PushService):
    def __init__(self) -> None:
        super().__init__([])
        self.sent: list[tuple] = []

    @property
    def enabled(self) -> bool:
        return True

    async def notify_user(self, maker, user_id, notification) -> int:
        self.sent.append((user_id, notification))
        return 1


def make_client(settings, knowledge, provider, push=None):
    limiter.reset()
    app = create_app(settings, Orchestrator([provider]), knowledge, push=push)
    return TestClient(app)


def signup(client, email="ada@example.com"):
    r = client.post(
        "/api/v1/auth/register", json={"email": email, "password": "correct-horse-9", "display_name": "Ada"}
    )
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}, r.json()["access_token"]


def wait_for(predicate, timeout=10.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError("condition not met in time")


def assistant(client, h, cid):
    return client.get(f"/api/v1/conversations/{cid}", headers=h).json()["messages"][-1]


# ---------------------------------------------------------------- turn manager


async def test_turn_survives_subscriber_leaving_and_reports_unattended_finish():
    finished = []

    async def on_finish(handle):
        finished.append(handle.final_event)

    async def events():
        for i in range(5):
            await asyncio.sleep(0.01)
            yield {"type": "delta", "text": str(i)}
        yield {"type": "done", "message": None}

    import uuid

    turns = TurnManager(on_unattended_finish=on_finish)
    handle = turns.start(events(), message_id=uuid.uuid4(), user_id=uuid.uuid4(), conversation_id=uuid.uuid4())
    sub = turns.subscribe(handle)
    assert (await anext(sub))["text"] == "0"
    await sub.aclose()  # the client went away
    await turns.wait_idle()
    await asyncio.sleep(0)
    assert [e["type"] for e in handle.events] == ["delta"] * 5 + ["done"]
    assert finished == [{"type": "done", "message": None}]

    # A late subscriber replays the whole reply.
    replay = [e async for e in turns.subscribe(handle)]
    assert replay == handle.events


async def test_watched_turn_does_not_notify_and_cancel_marks_stopped():
    import uuid

    finished = []

    async def on_finish(handle):
        finished.append(handle)

    async def forever():
        yield {"type": "meta"}
        await asyncio.sleep(60)
        yield {"type": "done"}

    turns = TurnManager(on_unattended_finish=on_finish)
    mid = uuid.uuid4()
    handle = turns.start(forever(), message_id=mid, user_id=uuid.uuid4(), conversation_id=uuid.uuid4())
    seen = []

    async def watch():
        async for e in turns.subscribe(handle):
            seen.append(e["type"])

    watcher = asyncio.create_task(watch())
    await asyncio.sleep(0.05)
    assert turns.cancel(mid)
    await watcher
    assert seen == ["meta", "stopped"]
    assert finished == [] and turns.get(mid) is None
    assert not turns.cancel(mid)


# ---------------------------------------------------------------- stop / background replies over HTTP


def test_stop_endpoint_cancels_running_reply(settings, knowledge):
    with make_client(settings, knowledge, SlowProvider()) as client:
        h, _ = signup(client)
        cid = client.post("/api/v1/conversations", headers=h, json={}).json()["id"]
        result = {}

        def send():
            r = client.post(f"/api/v1/conversations/{cid}/messages", headers=h, json={"content": "long please"})
            result["events"] = parse_sse(r.text)

        t = threading.Thread(target=send)
        t.start()
        wait_for(lambda: len(client.get(f"/api/v1/conversations/{cid}", headers=h).json()["messages"]) == 2)
        time.sleep(0.2)
        r = client.post(f"/api/v1/conversations/{cid}/stop", headers=h)
        assert r.status_code == 202 and r.json()["stopping"]
        t.join(10)
        assert result["events"][-1]["type"] == "stopped"
        msg = assistant(client, h, cid)
        assert msg["status"] == "stopped" and msg["content"].startswith("w0 ")
        assert len(msg["content"].split()) < 200
        # Nothing is running now.
        assert client.post(f"/api/v1/conversations/{cid}/stop", headers=h).json() == {"stopping": None}


def test_stop_from_another_worker_uses_the_database_flag(settings, knowledge, monkeypatch):
    monkeypatch.setattr(chat_service, "STOP_POLL_SECONDS", 0.05)
    with make_client(settings, knowledge, SlowProvider()) as client:
        h, _ = signup(client)
        cid = client.post("/api/v1/conversations", headers=h, json={}).json()["id"]
        # Simulate the reply running in a different worker: the local cancel finds nothing.
        monkeypatch.setattr(client.app.state.turns, "cancel", lambda _id: False)
        result = {}

        def send():
            r = client.post(f"/api/v1/conversations/{cid}/messages", headers=h, json={"content": "long"})
            result["events"] = parse_sse(r.text)

        t = threading.Thread(target=send)
        t.start()
        wait_for(lambda: len(client.get(f"/api/v1/conversations/{cid}", headers=h).json()["messages"]) == 2)
        time.sleep(0.2)
        assert client.post(f"/api/v1/conversations/{cid}/stop", headers=h).json()["stopping"]
        t.join(10)
        assert result["events"][-1]["type"] == "stopped"
        assert result["events"][-1]["message"]["status"] == "stopped"
        assert assistant(client, h, cid)["status"] == "stopped"


def test_other_users_cannot_stop_my_reply(client, auth):
    other, _ = signup(client, "bob@example.com")
    cid = client.post("/api/v1/conversations", headers=auth["headers"], json={}).json()["id"]
    assert client.post(f"/api/v1/conversations/{cid}/stop", headers=other).status_code == 404


def test_reply_continues_after_disconnect_and_pushes(settings, knowledge):
    push = FakePush()
    with make_client(settings, knowledge, SlowProvider(words=30, delay=0.01), push=push) as client:
        h, token = signup(client)
        cid = client.post("/api/v1/conversations", headers=h, json={}).json()["id"]
        with client.websocket_connect("/api/v1/ws/chat") as ws:
            ws.send_json({"type": "auth", "token": token})
            assert ws.receive_json()["type"] == "ready"
            ws.send_json({"type": "send", "request_id": "r1", "conversation_id": cid, "content": "hi"})
            assert ws.receive_json()["type"] == "meta"
        # The socket is gone (app backgrounded); the reply still completes and is saved.
        wait_for(lambda: assistant(client, h, cid)["status"] == "complete")
        assert len(assistant(client, h, cid)["content"].split()) == 30
        wait_for(lambda: len(push.sent) == 1)
        user_id, note = push.sent[0]
        assert note.title == "Dhanz finished your answer" and "hi" not in note.body
        assert note.data["conversation_id"] == cid

        # A reply the user watched to the end sends no notification.
        r = client.post(f"/api/v1/conversations/{cid}/messages", headers=h, json={"content": "again"})
        assert parse_sse(r.text)[-1]["type"] == "done"
        time.sleep(0.1)
        assert len(push.sent) == 1


# ---------------------------------------------------------------- devices


def test_device_register_upsert_and_unregister(client, auth):
    h = auth["headers"]
    body = {"platform": "android", "token": "device-token-1", "app_version": "0.4.0"}
    assert client.post("/api/v1/devices", headers=h, json=body).status_code == 204
    assert client.post("/api/v1/devices", headers=h, json=body).status_code == 204  # idempotent
    assert client.post("/api/v1/devices", headers=h, json={**body, "platform": "web"}).status_code == 422
    other, _ = signup(client, "bob@example.com")
    # Bob cannot remove Ada's token, but registering it on his phone moves it to him.
    assert client.post("/api/v1/devices/unregister", headers=other, json={"token": "device-token-1"}).status_code == 204
    assert client.post("/api/v1/devices", headers=other, json=body).status_code == 204
    assert client.post("/api/v1/devices", json=body).status_code == 401
    assert client.post("/api/v1/devices", headers=h, json={**body, "token": "short"}).status_code == 422
    assert client.get("/api/v1/models", headers=h).json()["features"]["push_notifications"] is False


async def test_push_service_deletes_invalid_tokens(settings):
    from sqlalchemy import select

    from app.db.session import make_engine, make_sessionmaker
    from app.models import Device, User

    engine = make_engine(settings.database_url)
    maker = make_sessionmaker(engine)
    async with maker() as db:
        user = User(email="p@example.com", password_hash="x", display_name="P")
        db.add(user)
        await db.flush()
        db.add_all(
            [
                Device(user_id=user.id, platform="android", token="good"),
                Device(user_id=user.id, platform="android", token="dead"),
                Device(user_id=user.id, platform="ios", token="no-sender"),
            ]
        )
        await db.commit()
        uid = user.id

    class Sender:
        platform = "android"

        def __init__(self):
            self.tokens = []

        async def send(self, token, n):
            self.tokens.append(token)
            if token == "dead":
                raise InvalidToken(token)

    sender = Sender()
    delivered = await PushService([sender]).notify_user(maker, uid, Notification("t", "b", {}))
    assert delivered == 1 and sorted(sender.tokens) == ["dead", "good"]
    async with maker() as db:
        assert sorted(await db.scalars(select(Device.token))) == ["good", "no-sender"]
    await engine.dispose()


# ---------------------------------------------------------------- FCM / APNs senders


def _rsa_pem() -> tuple[str, object]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ).decode()
    return pem, key.public_key()


async def test_fcm_sender_authenticates_and_detects_dead_tokens():
    pem, public = _rsa_pem()
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.host == "oauth2.googleapis.com":
            form = dict(x.split("=", 1) for x in request.content.decode().split("&"))
            claims = jwt.decode(form["assertion"], public, algorithms=["RS256"], audience=str(request.url))
            assert claims["iss"] == "svc@proj.iam.gserviceaccount.com"
            return httpx.Response(200, json={"access_token": "ya29.x", "expires_in": 3600})
        assert request.headers["authorization"] == "Bearer ya29.x"
        msg = json.loads(request.content)["message"]
        if msg["token"] == "dead":
            return httpx.Response(404, json={"error": {"status": "NOT_FOUND", "details": ["UNREGISTERED"]}})
        assert msg["notification"]["title"] == "Hi" and msg["data"] == {"conversation_id": "c1"}
        return httpx.Response(200, json={"name": "projects/proj/messages/1"})

    sender = FcmSender(
        {"project_id": "proj", "client_email": "svc@proj.iam.gserviceaccount.com", "private_key": pem},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    n = Notification("Hi", "Tap", {"conversation_id": "c1"})
    await sender.send("good", n)
    await sender.send("good", n)
    with pytest.raises(InvalidToken):
        await sender.send("dead", n)
    assert sum(r.url.host == "oauth2.googleapis.com" for r in calls) == 1  # access token cached
    assert str(calls[1].url) == "https://fcm.googleapis.com/v1/projects/proj/messages:send"


async def test_apns_sender_signs_provider_token():
    key = ec.generate_private_key(ec.SECP256R1())
    pem = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ).decode()

    def handler(request: httpx.Request) -> httpx.Response:
        token = request.headers["authorization"].removeprefix("bearer ")
        assert jwt.get_unverified_header(token)["kid"] == "KEY123"
        assert jwt.decode(token, key.public_key(), algorithms=["ES256"])["iss"] == "TEAM123"
        assert request.headers["apns-topic"] == "ai.dhanz.app"
        assert request.url.host == "api.sandbox.push.apple.com"
        if request.url.path.endswith("/dead"):
            return httpx.Response(410, json={"reason": "Unregistered"})
        if request.url.path.endswith("/bad"):
            return httpx.Response(400, json={"reason": "BadDeviceToken"})
        body = json.loads(request.content)
        assert body["aps"]["alert"]["title"] == "Hi" and body["conversation_id"] == "c1"
        return httpx.Response(200)

    sender = ApnsSender(
        "TEAM123",
        "KEY123",
        pem,
        "ai.dhanz.app",
        sandbox=True,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    n = Notification("Hi", "Tap", {"conversation_id": "c1"})
    await sender.send("good", n)
    for token in ("dead", "bad"):
        with pytest.raises(InvalidToken):
            await sender.send(token, n)


# ---------------------------------------------------------------- app updates


def test_update_check(settings, knowledge, provider, tmp_path):
    manifest = tmp_path / "latest.json"
    manifest.write_text(
        json.dumps(
            {
                "version": "0.4.0",
                "notes": "Push notifications",
                "minimum_version": "0.3.0",
                "platforms": {
                    "windows": {"url": "https://example.com/DhanzAI-0.4.0-setup.exe", "sha256": "ab" * 32},
                    "android": {"url": "http://insecure.example/app.apk"},
                },
            }
        )
    )
    settings.update_manifest_file = str(manifest)
    with make_client(settings, knowledge, provider) as client:

        def check(platform, version):
            r = client.get("/api/v1/app/updates", params={"platform": platform, "version": version})
            assert r.status_code == 200, r.text
            return r.json()

        newer = check("windows", "0.3.5+12")
        assert newer["update_available"] and not newer["mandatory"]
        assert newer["sha256"] == "ab" * 32 and newer["notes"] == "Push notifications"
        assert check("windows", "0.2.9")["mandatory"] is True
        same = check("windows", "v0.4.0")
        assert not same["update_available"] and same["url"] is None
        assert not check("android", "0.1.0")["update_available"]  # http:// URLs are never offered
        assert not check("ios", "0.1.0")["update_available"]
        assert client.get("/api/v1/app/updates", params={"platform": "linux", "version": "1"}).status_code == 422


def test_update_check_without_manifest(client):
    r = client.get("/api/v1/app/updates", params={"platform": "windows", "version": "0.1.0"})
    assert r.json()["update_available"] is False
