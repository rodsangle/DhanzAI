from app.core.config import Settings


def test_register_login_me(client, auth):
    assert auth["user"]["email"] == "ada@example.com"
    r = client.get("/api/v1/users/me", headers=auth["headers"])
    assert r.status_code == 200 and r.json()["display_name"] == "Ada"

    r = client.post("/api/v1/auth/login", json={"email": "ADA@example.com", "password": "correct-horse-9"})
    assert r.status_code == 200
    assert r.json()["access_token"]


def test_duplicate_email(client, auth):
    r = client.post(
        "/api/v1/auth/register", json={"email": "ada@example.com", "password": "another-pass-1", "display_name": "X"}
    )
    assert r.status_code == 409


def test_weak_password_rejected(client):
    for pw in ("short1", "aaaaaaaaaaaa", "123456789012"):
        r = client.post("/api/v1/auth/register", json={"email": "b@example.com", "password": pw, "display_name": "B"})
        assert r.status_code == 422, pw


def test_bad_login_is_generic(client, auth):
    wrong_pw = client.post("/api/v1/auth/login", json={"email": "ada@example.com", "password": "nope"})
    no_user = client.post("/api/v1/auth/login", json={"email": "ghost@example.com", "password": "nope"})
    assert wrong_pw.status_code == no_user.status_code == 401
    assert wrong_pw.json() == no_user.json()


def test_requires_auth(client):
    assert client.get("/api/v1/users/me").status_code == 401
    assert client.get("/api/v1/users/me", headers={"Authorization": "Bearer garbage"}).status_code == 401
    assert client.get("/api/v1/conversations").status_code == 401


def test_refresh_rotation_and_reuse_detection(client, auth):
    first = auth["refresh_token"]
    r = client.post("/api/v1/auth/refresh", json={"refresh_token": first})
    assert r.status_code == 200
    second = r.json()["refresh_token"]
    assert second != first

    # Replaying the rotated token is treated as theft: it fails and kills the newer token too.
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": first}).status_code == 401
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": second}).status_code == 401


def test_logout_revokes_refresh(client, auth):
    assert client.post("/api/v1/auth/logout", json={"refresh_token": auth["refresh_token"]}).status_code == 204
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": auth["refresh_token"]}).status_code == 401


def test_login_rate_limited(settings, provider):
    from fastapi.testclient import TestClient

    from app.core.rate_limit import limiter
    from app.main import create_app
    from dhanz_ai import Orchestrator

    limiter.reset()
    strict = Settings(**{**settings.model_dump(), "rate_limit_auth_per_minute": 3})
    with TestClient(create_app(strict, Orchestrator([provider]))) as c:
        codes = [
            c.post("/api/v1/auth/login", json={"email": "x@example.com", "password": "p"}).status_code for _ in range(4)
        ]
    assert codes == [401, 401, 401, 429]


def test_production_requires_strong_secret(monkeypatch):
    import pytest

    # CI exports a real JWT_SECRET; this test is about the built-in default.
    monkeypatch.delenv("JWT_SECRET", raising=False)
    with pytest.raises(ValueError):
        Settings(_env_file=None, app_env="production", database_url="postgresql+asyncpg://u:p@h/db")
    with pytest.raises(ValueError):
        Settings(app_env="production", jwt_secret="x" * 40, database_url="sqlite+aiosqlite:///x.db")
    Settings(app_env="production", jwt_secret="x" * 40, database_url="postgresql+asyncpg://u:p@h/db")


def test_update_profile_and_preferences(client, auth):
    h = auth["headers"]
    r = client.patch("/api/v1/users/me", headers=h, json={"display_name": "Ada L", "routing_policy": "cheapest"})
    assert r.status_code == 200 and r.json()["routing_policy"] == "cheapest"
    assert client.patch("/api/v1/users/me", headers=h, json={"preferred_model": "nope:x"}).status_code == 422
    r = client.patch("/api/v1/users/me", headers=h, json={"preferred_model": "echo:echo-1"})
    assert r.json()["preferred_model"] == "echo:echo-1"
    r = client.patch("/api/v1/users/me", headers=h, json={"preferred_model": ""})
    assert r.json()["preferred_model"] is None


def test_delete_account_removes_data(client, auth):
    h = auth["headers"]
    conv = client.post("/api/v1/conversations", headers=h, json={}).json()
    assert client.request("DELETE", "/api/v1/users/me", headers=h, json={"password": "wrong"}).status_code == 403
    assert (
        client.request("DELETE", "/api/v1/users/me", headers=h, json={"password": "correct-horse-9"}).status_code == 204
    )
    assert client.get("/api/v1/users/me", headers=h).status_code == 401
    # Re-registering the same email works and cannot see old data.
    r = client.post(
        "/api/v1/auth/register", json={"email": "ada@example.com", "password": "correct-horse-9", "display_name": "A"}
    )
    h2 = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert client.get(f"/api/v1/conversations/{conv['id']}", headers=h2).status_code == 404
