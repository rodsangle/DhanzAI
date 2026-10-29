"""Phase 5: sessions, lockout, password change/reset, retention, temporary chats, admin, monitoring."""

import asyncio
from datetime import timedelta

import fakeredis
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update

from app.core.rate_limit import RateLimiter, limiter
from app.db.base import utcnow
from app.db.session import make_engine, make_sessionmaker
from app.main import create_app
from app.models import AuditLog, Conversation, Memory, RefreshToken, User
from app.services.maintenance import run_maintenance
from dhanz_ai import Orchestrator
from tests.conftest import EchoProvider, parse_sse

PASSWORD = "correct-horse-9"


class FakeMailer:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str, str]] = []

    async def send(self, to: str, subject: str, body: str) -> None:
        self.sent.append((to, subject, body))


def make_client(settings, knowledge, **kwargs) -> TestClient:
    limiter.reset()
    return TestClient(create_app(settings, Orchestrator([EchoProvider()]), knowledge, **kwargs))


def register(client, email, password=PASSWORD):
    r = client.post("/api/v1/auth/register", json={"email": email, "password": password, "display_name": "U"})
    assert r.status_code == 201, r.text
    return r.json()


def login(client, email, password=PASSWORD, agent="test-agent"):
    return client.post("/api/v1/auth/login", json={"email": email, "password": password}, headers={"User-Agent": agent})


def bearer(tokens) -> dict:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


def db_run(settings, fn):
    """Run fn(session) against the test database."""

    async def go():
        engine = make_engine(settings.database_url)
        try:
            async with make_sessionmaker(engine)() as db:
                result = await fn(db)
                await db.commit()
                return result
        finally:
            await engine.dispose()

    return asyncio.run(go())


# ---------------------------------------------------------------- registration & admin bootstrap


def test_first_account_is_admin_and_registration_can_be_closed(settings, knowledge):
    settings.allow_registration = False
    with make_client(settings, knowledge) as client:
        assert client.get("/api/v1/auth/options").json() == {"registration_open": True, "password_reset": False}
        admin = register(client, "owner@example.com")
        assert admin["user"]["role"] == "admin"
        assert client.get("/api/v1/auth/options").json()["registration_open"] is False
        r = client.post(
            "/api/v1/auth/register", json={"email": "x@example.com", "password": PASSWORD, "display_name": "X"}
        )
        assert r.status_code == 403 and "closed" in r.json()["detail"]


# ---------------------------------------------------------------- login lockout


def test_account_lockout_after_failed_logins(settings, knowledge):
    settings.rate_limit_auth_per_minute = 1000
    settings.login_lockout_attempts = 3
    with make_client(settings, knowledge) as client:
        register(client, "ada@example.com")
        register(client, "bob@example.com")
        for _ in range(3):
            assert login(client, "ada@example.com", "wrong-password-1").status_code == 401
        r = login(client, "ada@example.com")
        assert r.status_code == 429 and "Too many failed sign-in attempts" in r.json()["detail"]
        assert int(r.headers["Retry-After"]) > 60
        assert login(client, "bob@example.com").status_code == 200  # other accounts unaffected
        # Unknown emails lock the same way (no hint about which accounts exist).
        for _ in range(3):
            login(client, "ghost@example.com", "wrong-password-1")
        assert login(client, "ghost@example.com", "wrong-password-1").status_code == 429


def test_successful_login_resets_the_failure_count(settings, knowledge):
    settings.login_lockout_attempts = 3
    with make_client(settings, knowledge) as client:
        register(client, "ada@example.com")
        for _ in range(2):
            login(client, "ada@example.com", "wrong-password-1")
        assert login(client, "ada@example.com").status_code == 200
        for _ in range(2):
            login(client, "ada@example.com", "wrong-password-1")
        assert login(client, "ada@example.com").status_code == 200


# ---------------------------------------------------------------- sessions


def test_sessions_list_and_immediate_revocation(client):
    register(client, "ada@example.com")
    phone = login(client, "ada@example.com", agent="DhanzAI Android").json()
    laptop = login(client, "ada@example.com", agent="DhanzAI Windows").json()

    sessions = client.get("/api/v1/users/me/sessions", headers=bearer(laptop)).json()
    assert len(sessions) == 3  # registration + phone + laptop
    assert sessions[0]["current"] and sessions[0]["user_agent"] == "DhanzAI Windows"
    phone_session = next(s for s in sessions if s["user_agent"] == "DhanzAI Android")

    r = client.delete(f"/api/v1/users/me/sessions/{phone_session['id']}", headers=bearer(laptop))
    assert r.status_code == 204
    # The phone's access token stops working at once, and so does its refresh token.
    assert client.get("/api/v1/users/me", headers=bearer(phone)).status_code == 401
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": phone["refresh_token"]}).status_code == 401
    assert client.get("/api/v1/users/me", headers=bearer(laptop)).status_code == 200

    # Refreshing keeps the session (same id) alive.
    refreshed = client.post("/api/v1/auth/refresh", json={"refresh_token": laptop["refresh_token"]}).json()
    ids = [s["id"] for s in client.get("/api/v1/users/me/sessions", headers=bearer(refreshed)).json()]
    assert len(ids) == 2

    assert client.post("/api/v1/users/me/sessions/revoke-others", headers=bearer(refreshed)).json() == {"ended": 1}
    assert len(client.get("/api/v1/users/me/sessions", headers=bearer(refreshed)).json()) == 1


def test_cannot_revoke_someone_elses_session(client):
    ada = register(client, "ada@example.com")
    bob = register(client, "bob@example.com")
    ada_session = client.get("/api/v1/users/me/sessions", headers=bearer(ada)).json()[0]["id"]
    assert client.delete(f"/api/v1/users/me/sessions/{ada_session}", headers=bearer(bob)).status_code == 404
    assert client.get("/api/v1/users/me", headers=bearer(ada)).status_code == 200


# ---------------------------------------------------------------- password change & reset


def test_change_password_signs_out_other_devices(client):
    register(client, "ada@example.com")
    phone = login(client, "ada@example.com").json()
    laptop = login(client, "ada@example.com").json()
    url = "/api/v1/users/me/password"
    bad = {"current_password": "nope-nope-1", "new_password": "a-new-pass-42"}
    assert client.post(url, json=bad, headers=bearer(laptop)).status_code == 403
    weak = {"current_password": PASSWORD, "new_password": "aaaaaaaaaaaa"}
    assert client.post(url, json=weak, headers=bearer(laptop)).status_code == 422
    ok = {"current_password": PASSWORD, "new_password": "a-new-pass-42"}
    assert client.post(url, json=ok, headers=bearer(laptop)).status_code == 204
    assert client.get("/api/v1/users/me", headers=bearer(phone)).status_code == 401
    assert client.get("/api/v1/users/me", headers=bearer(laptop)).status_code == 200
    assert login(client, "ada@example.com").status_code == 401
    assert login(client, "ada@example.com", "a-new-pass-42").status_code == 200


def test_password_reset_by_email_code(settings, knowledge):
    mailer = FakeMailer()
    with make_client(settings, knowledge, mailer=mailer) as client:
        assert client.get("/api/v1/auth/options").json()["password_reset"] is True
        old = register(client, "ada@example.com")
        request = "/api/v1/auth/password-reset/request"
        confirm = "/api/v1/auth/password-reset/confirm"

        assert client.post(request, json={"email": "nobody@example.com"}).status_code == 202
        assert client.post(request, json={"email": "Ada@Example.com"}).status_code == 202
        client.get("/api/v1/health")  # let the background send run
        assert [m[0] for m in mailer.sent] == ["ada@example.com"]
        body = mailer.sent[0][2]
        code = body.split("code is: ")[1].split()[0]
        assert len(code.replace("-", "")) == 10

        new = {"email": "ada@example.com", "code": "WRONG-CODE1", "new_password": "fresh-pass-77"}
        assert client.post(confirm, json=new).status_code == 400
        new["code"] = code.lower()  # case and dash do not matter
        assert client.post(confirm, json=new).status_code == 204
        assert client.post(confirm, json=new).status_code == 400  # one use only
        assert client.get("/api/v1/users/me", headers=bearer(old)).status_code == 401  # signed out everywhere
        assert login(client, "ada@example.com", "fresh-pass-77").status_code == 200


def test_password_reset_code_is_burned_after_too_many_guesses(settings, knowledge):
    mailer = FakeMailer()
    settings.rate_limit_auth_per_minute = 1000
    with make_client(settings, knowledge, mailer=mailer) as client:
        register(client, "ada@example.com")
        client.post("/api/v1/auth/password-reset/request", json={"email": "ada@example.com"})
        client.get("/api/v1/health")
        code = mailer.sent[0][2].split("code is: ")[1].split()[0]
        guess = {"email": "ada@example.com", "code": "AAAAA-AAAAA", "new_password": "fresh-pass-77"}
        for _ in range(5):
            assert client.post("/api/v1/auth/password-reset/confirm", json=guess).status_code == 400
        guess["code"] = code
        assert client.post("/api/v1/auth/password-reset/confirm", json=guess).status_code == 400


def test_password_reset_not_configured(client):
    r = client.post("/api/v1/auth/password-reset/request", json={"email": "ada@example.com"})
    assert r.status_code == 501


# ---------------------------------------------------------------- privacy: retention & temporary chats


def test_retention_and_temporary_chats(settings, knowledge):
    with make_client(settings, knowledge) as client:
        ada = register(client, "ada@example.com")
        bob = register(client, "bob@example.com")
        h = bearer(ada)
        assert client.patch("/api/v1/users/me", json={"retention_days": 30}, headers=h).json()["retention_days"] == 30
        assert client.patch("/api/v1/users/me", json={"retention_days": 12}, headers=h).status_code == 422
        old = client.post("/api/v1/conversations", json={}, headers=h).json()["id"]
        recent = client.post("/api/v1/conversations", json={}, headers=h).json()["id"]
        bob_old = client.post("/api/v1/conversations", json={}, headers=bearer(bob)).json()["id"]

        # Memory on; "remember that" in a temporary chat is not saved.
        client.patch("/api/v1/users/me", json={"memory_enabled": True}, headers=h)
        temp = client.post("/api/v1/conversations", json={"temporary": True}, headers=h).json()
        assert temp["temporary"] is True
        r = client.post(
            f"/api/v1/conversations/{temp['id']}/messages", json={"content": "Remember that I like tea"}, headers=h
        )
        assert not [e for e in parse_sse(r.text) if e["type"] == "memory"]
        assert db_run(settings, lambda db: db.scalar(select(Memory.id))) is None

        async def backdate(db):
            past = utcnow() - timedelta(days=40)
            await db.execute(
                update(Conversation).where(Conversation.id.in_([_uuid(old), _uuid(bob_old)])).values(updated_at=past)
            )
            await db.execute(
                update(Conversation)
                .where(Conversation.id == _uuid(temp["id"]))
                .values(updated_at=utcnow() - timedelta(hours=25))
            )
            db.add(AuditLog(action="old.entry", created_at=utcnow() - timedelta(days=400)))

        db_run(settings, backdate)
        counts = db_run(settings, lambda db: run_maintenance(_maker_of(db), settings))
        assert counts["conversations"] == 2 and counts["audit_logs"] == 1
        ids = {c["id"] for c in client.get("/api/v1/conversations", headers=h).json()["items"]}
        assert ids == {recent}
        # Bob keeps everything: he did not choose a retention period.
        assert [c["id"] for c in client.get("/api/v1/conversations", headers=bearer(bob)).json()["items"]] == [bob_old]
        # 0 turns retention off again.
        assert client.patch("/api/v1/users/me", json={"retention_days": 0}, headers=h).json()["retention_days"] is None


def _uuid(value):
    import uuid

    return uuid.UUID(value)


def _maker_of(db):
    """A sessionmaker bound to the same engine as [db] (for run_maintenance)."""
    return make_sessionmaker(db.bind)


def test_maintenance_removes_expired_refresh_tokens(settings, knowledge):
    with make_client(settings, knowledge) as client:
        register(client, "ada@example.com")

    async def expire(db):
        await db.execute(update(RefreshToken).values(expires_at=utcnow() - timedelta(days=1)))

    db_run(settings, expire)
    counts = db_run(settings, lambda db: run_maintenance(_maker_of(db), settings))
    assert counts["refresh_tokens"] == 1


# ---------------------------------------------------------------- admin


def test_admin_endpoints(client):
    admin = register(client, "owner@example.com")
    ada = register(client, "ada@example.com")
    h = bearer(admin)
    assert client.get("/api/v1/admin/stats", headers=bearer(ada)).status_code == 403

    cid = client.post("/api/v1/conversations", json={}, headers=bearer(ada)).json()["id"]
    client.post(f"/api/v1/conversations/{cid}/messages", json={"content": "hello"}, headers=bearer(ada))

    stats = client.get("/api/v1/admin/stats", headers=h).json()
    assert stats["users"] == 2 and stats["messages_24h"] == 1 and stats["active_users_7d"] == 1
    assert stats["usage_30d"] == [{"provider": "echo", "replies": 1, "input_tokens": 10, "output_tokens": 5}]

    users = client.get("/api/v1/admin/users", params={"q": "ada"}, headers=h).json()
    assert users["total"] == 1 and users["items"][0]["messages_30d"] == 1
    ada_id = users["items"][0]["id"]

    r = client.patch(f"/api/v1/admin/users/{ada_id}", json={"is_active": False}, headers=h)
    assert r.status_code == 200 and r.json()["is_active"] is False
    assert client.get("/api/v1/users/me", headers=bearer(ada)).status_code == 401
    assert login(client, "ada@example.com").status_code == 401

    admin_id = admin["user"]["id"]
    assert client.patch(f"/api/v1/admin/users/{admin_id}", json={"role": "user"}, headers=h).status_code == 409
    assert client.patch(f"/api/v1/admin/users/{ada_id}", json={"role": "root"}, headers=h).status_code == 422

    audit = client.get("/api/v1/admin/audit", params={"action": "admin."}, headers=h).json()
    assert audit[0]["action"] == "admin.user_updated" and audit[0]["detail"]["is_active"] is False
    logins = client.get("/api/v1/admin/audit", params={"action": "auth.login_failed"}, headers=h).json()
    assert len(logins) == 1


def test_cli_promote(settings, knowledge, monkeypatch):
    from app import cli

    with make_client(settings, knowledge) as client:
        register(client, "owner@example.com")
        register(client, "ada@example.com")
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    assert cli.main(["promote", "ada@example.com"]) == 0
    assert db_run(settings, lambda db: db.scalar(select(User.role).where(User.email == "ada@example.com"))) == "admin"
    assert cli.main(["demote", "nobody@example.com"]) == 1


# ---------------------------------------------------------------- monitoring & limits


def test_request_ids_and_metrics(settings, knowledge):
    settings.metrics_token = "m" * 32
    with make_client(settings, knowledge) as client:
        r = client.get("/api/v1/health", headers={"X-Request-ID": "trace-123"})
        assert r.headers["X-Request-ID"] == "trace-123"
        generated = client.get("/api/v1/health", headers={"X-Request-ID": "bad id with spaces"})
        assert len(generated.headers["X-Request-ID"]) == 32
        ada = register(client, "ada@example.com")
        cid = client.post("/api/v1/conversations", json={}, headers=bearer(ada)).json()["id"]
        client.post(f"/api/v1/conversations/{cid}/messages", json={"content": "hi"}, headers=bearer(ada))

        assert client.get("/metrics").status_code == 404
        assert client.get("/metrics", headers={"Authorization": "Bearer wrong"}).status_code == 404
        text = client.get("/metrics", headers={"Authorization": f"Bearer {'m' * 32}"}).text
        assert 'dhanz_http_requests_total{method="GET",route="/api/v1/health",status="200"}' in text
        assert 'route="/api/v1/conversations/{conversation_id}/messages"' in text
        assert 'dhanz_chat_replies_total{outcome="done"}' in text
        assert 'dhanz_llm_tokens_total{direction="output",provider="echo"}' in text


def test_metrics_disabled_without_token(client):
    assert client.get("/metrics").status_code == 404


def test_oversized_bodies_are_refused(client, auth):
    cid = client.post("/api/v1/conversations", json={}, headers=auth["headers"]).json()["id"]
    huge = "x" * (600 * 1024)
    r = client.post(f"/api/v1/conversations/{cid}/messages", json={"content": huge}, headers=auth["headers"])
    assert r.status_code == 413 and "too large" in r.json()["detail"]


def test_security_headers_and_compression(client, auth):
    r = client.get("/api/v1/users/me/export", headers={**auth["headers"], "Accept-Encoding": "gzip"})
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["Cross-Origin-Resource-Policy"] == "same-origin"
    big = client.get("/openapi.json", headers={"Accept-Encoding": "gzip"})
    assert big.headers.get("content-encoding") == "gzip"


# ---------------------------------------------------------------- shared rate limiting


async def test_redis_rate_limiter_shares_counts_between_processes():
    server = fakeredis.FakeServer()
    a, b = RateLimiter(), RateLimiter()
    a.use_redis(fakeredis.aioredis.FakeRedis(server=server))
    b.use_redis(fakeredis.aioredis.FakeRedis(server=server))
    assert await a.hit("k", 2, 60) is None
    assert await b.hit("k", 2, 60) is None
    retry = await a.hit("k", 2, 60)
    assert retry is not None and 0 < retry <= 60
    assert await b.peek("k", 2, 60) is not None
    await b.clear("k")
    assert await a.peek("k", 2, 60) is None


async def test_rate_limiter_falls_back_when_redis_is_down():
    class Broken:
        def pipeline(self, *a, **k):
            raise ConnectionError("redis down")

    rl = RateLimiter()
    rl.use_redis(Broken())
    assert await rl.hit("k", 1, 60) is None
    assert await rl.hit("k", 1, 60) is not None  # still limited, per process


@pytest.mark.parametrize("days", [None, 7])
def test_settings_accept_retention_choices(client, auth, days):
    r = client.patch("/api/v1/users/me", json={"retention_days": days or 0}, headers=auth["headers"])
    assert r.json()["retention_days"] == days
