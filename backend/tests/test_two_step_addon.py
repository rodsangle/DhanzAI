"""server_extensions/two_step: the two-step verification add-on for servers that predate the
built-in one (the live server). Run against this backend's real sign-in routes, with the built-in
two-step routes removed and the add-on's sign-in hook in place, the way the deploy script wires it.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.rate_limit import limiter
from app.db.base import Base
from app.main import create_app
from app.services import accounts
from app.services.auth_service import issue_tokens
from dhanz_ai import Orchestrator
from tests.conftest import EchoProvider

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "server_extensions"))
import two_step  # noqa: E402
from two_step import core, service  # noqa: E402
from two_step.models import TABLES  # noqa: E402

API = "/api/v1"
PASSWORD = "correct-horse-9"


async def _tables(url: str, create: bool) -> None:
    engine = create_async_engine(url)
    async with engine.begin() as conn:
        if create:
            await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=list(TABLES), checkfirst=True))
        else:
            await conn.run_sync(lambda c: Base.metadata.drop_all(c, tables=list(reversed(TABLES)), checkfirst=True))
    await engine.dispose()


@pytest.fixture
def addon(settings, knowledge, monkeypatch):
    """This backend shaped like the live one: no built-in two-step routes, the add-on installed."""
    asyncio.run(_tables(settings.database_url, True))
    limiter.reset()

    async def finish_sign_in(db, settings, request, user, method, **_):
        challenge = await two_step.login_hook(db, settings, request, user)  # the hook the deploy inserts
        if challenge is not None:
            return challenge
        return await issue_tokens(db, settings, user, user_agent=request.headers.get("user-agent"))

    monkeypatch.setattr(accounts, "finish_sign_in", finish_sign_in)
    app = create_app(settings, Orchestrator([EchoProvider()]), knowledge)
    two_step.install(app)  # its routes come first, ahead of this backend's built-in two-step routes
    two_step.install(app)  # installing twice must not wrap twice
    with TestClient(app) as client:
        yield client
    asyncio.run(_tables(settings.database_url, False))


def bearer(tokens: dict) -> dict:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


def register(client, email="ada@example.com") -> dict:
    r = client.post(f"{API}/auth/register", json={"email": email, "password": PASSWORD, "display_name": "Ada"})
    assert r.status_code == 201, r.text
    return r.json()


def login(client, email="ada@example.com", password=PASSWORD, **extra):
    return client.post(f"{API}/auth/login", json={"email": email, "password": password, **extra})


def now_code(secret: str, offset: int = 0) -> str:
    return core.code_at(secret, core.current_step() + offset)


def turn_on(client, tokens) -> tuple[str, list[str]]:
    setup = client.post(f"{API}/users/me/mfa/setup", json={"password": PASSWORD}, headers=bearer(tokens))
    assert setup.status_code == 200, setup.text
    secret = setup.json()["secret"]
    assert setup.json()["otpauth_uri"].startswith("otpauth://totp/DHANZ%20AI%3A")
    r = client.post(f"{API}/users/me/mfa/enable", json={"code": now_code(secret, -1)}, headers=bearer(tokens))
    assert r.status_code == 200, r.text
    return secret, r.json()["recovery_codes"]


def test_status_is_reported_in_the_servers_own_replies(addon):
    tokens = register(addon)
    assert tokens["user"]["mfa_enabled"] is False  # register reply carries the status
    me = addon.get(f"{API}/users/me", headers=bearer(tokens)).json()
    assert me["mfa_enabled"] is False and me["mfa_method"] is None and me["email"] == "ada@example.com"
    options = addon.get(f"{API}/auth/options").json()
    assert options["mfa_email"] is False and options["trusted_device_days"] == 30
    assert "registration_open" in options  # the original fields stay


def test_turn_on_then_sign_in_needs_the_code(addon):
    tokens = register(addon)
    other = login(addon).json()
    wrong = addon.post(f"{API}/users/me/mfa/setup", json={"password": "wrong-pass-1"}, headers=bearer(tokens))
    assert wrong.status_code == 403
    secret, codes = turn_on(addon, tokens)
    assert len(codes) == 10
    assert addon.get(f"{API}/users/me", headers=bearer(tokens)).json()["mfa_enabled"] is True
    # Sessions opened with the password only were ended; this one stays.
    assert addon.post(f"{API}/auth/refresh", json={"refresh_token": other["refresh_token"]}).status_code == 401
    assert addon.get(f"{API}/users/me", headers=bearer(tokens)).status_code == 200

    challenge = login(addon).json()
    assert challenge["mfa_required"] is True and challenge["method"] == "totp" and "access_token" not in challenge
    assert login(addon, password="wrong-pass-1").status_code == 401  # the password still comes first

    bad = addon.post(f"{API}/auth/mfa/verify", json={"mfa_token": challenge["mfa_token"], "code": "000000"})
    assert bad.status_code == 401
    good_code = now_code(secret)
    ok = addon.post(f"{API}/auth/mfa/verify", json={"mfa_token": challenge["mfa_token"], "code": good_code})
    assert ok.status_code == 200, ok.text
    assert ok.json()["user"]["mfa_enabled"] is True and ok.json()["trusted_device_token"] is None
    # The same 30-second code never works twice.
    again = login(addon).json()
    replay = addon.post(f"{API}/auth/mfa/verify", json={"mfa_token": again["mfa_token"], "code": good_code})
    assert replay.status_code == 401


def test_recovery_codes_are_single_use_and_can_be_replaced(addon):
    tokens = register(addon)
    secret, codes = turn_on(addon, tokens)
    challenge = login(addon).json()
    first = addon.post(f"{API}/auth/mfa/verify", json={"mfa_token": challenge["mfa_token"], "code": codes[0].lower()})
    assert first.status_code == 200
    again = login(addon).json()
    reuse = addon.post(f"{API}/auth/mfa/verify", json={"mfa_token": again["mfa_token"], "code": codes[0]})
    assert reuse.status_code == 401
    assert addon.get(f"{API}/users/me/mfa/recovery-codes/remaining", headers=bearer(tokens)).json() == {"remaining": 9}
    new = addon.post(f"{API}/users/me/mfa/recovery-codes", json={"code": codes[1]}, headers=bearer(tokens))
    assert new.status_code == 200 and new.json()["recovery_codes"] != codes
    old = login(addon).json()
    assert (
        addon.post(f"{API}/auth/mfa/verify", json={"mfa_token": old["mfa_token"], "code": codes[2]}).status_code == 401
    )


def test_wrong_codes_are_limited_and_forged_challenges_refused(addon, settings):
    tokens = register(addon)
    turn_on(addon, tokens)
    challenge = login(addon).json()
    statuses = [
        addon.post(f"{API}/auth/mfa/verify", json={"mfa_token": challenge["mfa_token"], "code": "000000"}).status_code
        for _ in range(6)
    ]
    assert statuses[:5] == [401] * 5 and statuses[5] == 429
    assert addon.post(f"{API}/auth/mfa/verify", json={"mfa_token": "x" * 40, "code": "123456"}).status_code == 401
    forged = settings.model_copy(update={"jwt_secret": "another-secret-" * 4})
    token, _ = service.create_challenge(forged, __import__("uuid").uuid4())
    assert addon.post(f"{API}/auth/mfa/verify", json={"mfa_token": token, "code": "123456"}).status_code == 401


def test_remember_this_device_until_the_password_changes(addon):
    tokens = register(addon)
    secret, codes = turn_on(addon, tokens)
    challenge = login(addon).json()
    r = addon.post(
        f"{API}/auth/mfa/verify",
        json={"mfa_token": challenge["mfa_token"], "code": codes[0], "remember_device": True},
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0) Chrome/130.0"},
    )
    device = r.json()["trusted_device_token"]
    session = r.json()
    assert device and "access_token" in login(addon, trusted_device_token=device).json()
    assert login(addon, trusted_device_token="x" * 43).json()["mfa_required"] is True
    listed = addon.get(f"{API}/users/me/trusted-devices", headers=bearer(session)).json()
    assert [d["label"] for d in listed] == ["Chrome on Windows"]

    changed = addon.post(
        f"{API}/users/me/password",
        json={"current_password": PASSWORD, "new_password": "brand-new-horse-7"},
        headers=bearer(session),
    )
    assert changed.status_code in (200, 204), changed.text
    after = login(addon, password="brand-new-horse-7", trusted_device_token=device).json()
    assert after["mfa_required"] is True
    fresh = addon.post(f"{API}/auth/login", json={"email": "ada@example.com", "password": "brand-new-horse-7"}).json()
    ok = addon.post(f"{API}/auth/mfa/verify", json={"mfa_token": fresh["mfa_token"], "code": codes[1]}).json()
    assert addon.get(f"{API}/users/me/trusted-devices", headers=bearer(ok)).json() == []


def test_devices_are_per_account_and_can_be_forgotten(addon):
    ada = register(addon)
    _, ada_codes = turn_on(addon, ada)
    challenge = login(addon).json()
    r = addon.post(
        f"{API}/auth/mfa/verify",
        json={"mfa_token": challenge["mfa_token"], "code": ada_codes[0], "remember_device": True},
    ).json()
    device, session = r["trusted_device_token"], r
    bo = register(addon, email="bo@example.com")
    turn_on(addon, bo)
    assert login(addon, email="bo@example.com", trusted_device_token=device).json()["mfa_required"] is True

    listed = addon.get(f"{API}/users/me/trusted-devices", headers=bearer(session)).json()
    assert addon.delete(f"{API}/users/me/trusted-devices/{listed[0]['id']}", headers=bearer(bo)).status_code == 404
    assert addon.delete(f"{API}/users/me/trusted-devices/{listed[0]['id']}", headers=bearer(session)).status_code == 204
    assert login(addon, trusted_device_token=device).json()["mfa_required"] is True


def test_turning_off_needs_a_code_and_forgets_devices(addon):
    tokens = register(addon)
    secret, codes = turn_on(addon, tokens)
    challenge = login(addon).json()
    r = addon.post(
        f"{API}/auth/mfa/verify",
        json={"mfa_token": challenge["mfa_token"], "code": codes[0], "remember_device": True},
    ).json()
    device = r["trusted_device_token"]
    assert addon.post(f"{API}/users/me/mfa/disable", json={"code": "000000"}, headers=bearer(r)).status_code == 403
    off = addon.post(f"{API}/users/me/mfa/disable", json={"code": codes[1]}, headers=bearer(r))
    assert off.status_code == 200 and off.json()["mfa_enabled"] is False
    assert "access_token" in login(addon).json()
    # Turned on again: the old remembered device does not skip the step.
    turn_on(addon, r)
    assert login(addon, trusted_device_token=device).json()["mfa_required"] is True


def test_device_days_come_from_settings_or_the_environment(monkeypatch):
    from types import SimpleNamespace

    live = SimpleNamespace(jwt_secret="x" * 40)  # the live server's settings have no such field
    assert service.trusted_device_days(live) == 30
    monkeypatch.setenv("TRUSTED_DEVICE_DAYS", "7")
    assert service.trusted_device_days(live) == 7
    monkeypatch.setenv("TRUSTED_DEVICE_DAYS", "999")
    assert service.trusted_device_days(live) == 90
    assert service.trusted_device_days(SimpleNamespace(trusted_device_days=0)) == 0


def test_remember_device_can_be_switched_off(addon, settings, monkeypatch):
    monkeypatch.setattr(settings, "trusted_device_days", 0)
    tokens = register(addon)
    _, codes = turn_on(addon, tokens)
    challenge = login(addon).json()
    r = addon.post(
        f"{API}/auth/mfa/verify",
        json={"mfa_token": challenge["mfa_token"], "code": codes[0], "remember_device": True},
    )
    assert r.status_code == 200 and r.json()["trusted_device_token"] is None
    assert addon.get(f"{API}/auth/options").json()["trusted_device_days"] == 0


def test_secrets_are_encrypted_and_labels_readable(settings):
    sealed = core.encrypt_secret(settings, "JBSWY3DPEHPK3PXP")
    assert sealed.startswith("v1:") and "JBSWY3DPEHPK3PXP" not in sealed
    assert core.decrypt_secret(settings, sealed) == "JBSWY3DPEHPK3PXP"
    assert service.device_label("Dart/3.9 (dart:io)") == "DHANZ app"
    assert service.device_label(None) == "Unknown device"
