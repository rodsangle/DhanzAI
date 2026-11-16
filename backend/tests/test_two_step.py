"""Two-step verification by emailed code, "remember this device", and security alert emails.

The authenticator-app (TOTP) flow itself is covered in test_accounts.py.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core import mfa
from app.core.rate_limit import limiter
from app.core.security import create_mfa_token, decode_mfa_token
from app.main import create_app
from app.services import accounts
from dhanz_ai import Orchestrator
from tests.conftest import EchoProvider
from tests.test_accounts import API, PASSWORD, FakeMailer, bearer, enable_mfa, login, register


@pytest.fixture
def mailer() -> FakeMailer:
    return FakeMailer()


@pytest.fixture
def mail_client(settings, knowledge, mailer):
    limiter.reset()
    with TestClient(create_app(settings, Orchestrator([EchoProvider()]), knowledge, mailer=mailer)) as client:
        yield client


def last_code(client, mailer: FakeMailer, subject_part: str = "code") -> str:
    client.get(f"{API}/health")  # let the background send run
    for _to, subject, body in reversed(mailer.sent):
        if subject_part in subject:
            return body.split("code is: ")[1].split()[0] if "code is: " in body else subject.split()[0]
    raise AssertionError(f"no email about {subject_part!r}: {[m[1] for m in mailer.sent]}")


def subjects(client, mailer: FakeMailer) -> list[str]:
    client.get(f"{API}/health")
    return [m[1] for m in mailer.sent]


def verified(client, mailer) -> dict:
    tokens = register(client)
    code = last_code(client, mailer, "Confirm your email")
    r = client.post(f"{API}/users/me/email-verification/confirm", json={"code": code}, headers=bearer(tokens))
    assert r.json()["email_verified"] is True
    return tokens


def enable_email_mfa(client, mailer, tokens) -> list[str]:
    r = client.post(f"{API}/users/me/mfa/email/setup", json={"password": PASSWORD}, headers=bearer(tokens))
    assert r.status_code == 202, r.text
    assert "a*" in r.json()["detail"]  # masked address
    code = last_code(client, mailer, "security code")
    r = client.post(f"{API}/users/me/mfa/email/enable", json={"code": code}, headers=bearer(tokens))
    assert r.status_code == 200, r.text
    return r.json()["recovery_codes"]


# --- pure helpers ---------------------------------------------------------------------------------


def test_masked_email_and_device_labels():
    assert accounts.mask_email("ada.lovelace@example.com") == "a**********e@example.com"
    assert accounts.mask_email("al@example.com") == "a*@example.com"
    assert accounts.device_label("Mozilla/5.0 (Windows NT 10.0) Chrome/130.0") == "Chrome on Windows"
    assert accounts.device_label("Dart/3.9 (dart:io)") == "DHANZ app"
    assert accounts.device_label(None) == "Unknown device"


def test_challenge_tokens_carry_a_unique_id(settings):
    one, _ = create_mfa_token(settings, __import__("uuid").uuid4(), "password")
    two, _ = create_mfa_token(settings, __import__("uuid").uuid4(), "password")
    a, b = decode_mfa_token(settings, one), decode_mfa_token(settings, two)
    assert a.challenge_id and a.challenge_id != b.challenge_id
    assert len(accounts.login_code_purpose(a.challenge_id)) <= 20  # fits verification_codes.purpose


# --- email codes ------------------------------------------------------------------------------------


def test_email_code_setup_needs_mail_a_confirmed_address_and_the_password(client, mailer):
    plain = register(client)  # server without email
    assert (
        client.post(f"{API}/users/me/mfa/email/setup", json={"password": PASSWORD}, headers=bearer(plain)).status_code
        == 501
    )


def test_email_code_setup_needs_a_confirmed_address_and_the_password(mail_client, mailer):
    options = mail_client.get(f"{API}/auth/options").json()
    assert options["mfa_email"] is True and options["trusted_device_days"] == 30
    unconfirmed = register(mail_client, email="bo@example.com")
    r = mail_client.post(f"{API}/users/me/mfa/email/setup", json={"password": PASSWORD}, headers=bearer(unconfirmed))
    assert r.status_code == 400 and "Confirm your email" in r.json()["detail"]
    tokens = verified(mail_client, mailer)
    wrong = mail_client.post(
        f"{API}/users/me/mfa/email/setup", json={"password": "nope-nope-1"}, headers=bearer(tokens)
    )
    assert wrong.status_code == 403


def test_email_codes_turn_on_and_sign_in_with_the_code_for_that_sign_in(mail_client, mailer):
    tokens = verified(mail_client, mailer)
    other_device = login(mail_client).json()
    codes = enable_email_mfa(mail_client, mailer, tokens)
    assert len(codes) == mfa.RECOVERY_CODE_COUNT
    me = mail_client.get(f"{API}/users/me", headers=bearer(tokens)).json()
    assert me["mfa_enabled"] is True and me["mfa_method"] == "email"
    assert "DHANZ AI security: two-step verification is on" in subjects(mail_client, mailer)
    # The other device signed in with the password only, so it was signed out.
    assert (
        mail_client.post(f"{API}/auth/refresh", json={"refresh_token": other_device["refresh_token"]}).status_code
        == 401
    )

    first = login(mail_client).json()
    assert first["mfa_required"] is True and first["method"] == "email" and first["code_sent"] is True
    assert first["email_hint"] == "a*a@example.com"
    first_code = last_code(mail_client, mailer, "sign-in code")
    second = login(mail_client).json()
    second_code = last_code(mail_client, mailer, "sign-in code")

    # A code only works for the sign-in it was sent for.
    if first_code != second_code:
        crossed = mail_client.post(
            f"{API}/auth/mfa/verify", json={"mfa_token": second["mfa_token"], "code": first_code}
        )
        assert crossed.status_code == 401 and "newest code" in crossed.json()["detail"]
    ok = mail_client.post(f"{API}/auth/mfa/verify", json={"mfa_token": second["mfa_token"], "code": second_code})
    assert ok.status_code == 200 and ok.json()["trusted_device_token"] is None
    # ... and only once.
    again = mail_client.post(f"{API}/auth/mfa/verify", json={"mfa_token": second["mfa_token"], "code": second_code})
    assert again.status_code == 401
    # An authenticator-style code means nothing for an email account.
    assert (
        mail_client.post(f"{API}/users/me/mfa/setup", json={"password": PASSWORD}, headers=bearer(tokens)).status_code
        == 409
    )


def test_resend_replaces_the_code_and_is_rate_limited(mail_client, mailer):
    tokens = verified(mail_client, mailer)
    enable_email_mfa(mail_client, mailer, tokens)
    challenge = login(mail_client).json()
    old = last_code(mail_client, mailer, "sign-in code")
    r = mail_client.post(f"{API}/auth/mfa/resend", json={"mfa_token": challenge["mfa_token"]})
    assert r.status_code == 202
    new = last_code(mail_client, mailer, "sign-in code")
    assert mail_client.post(f"{API}/auth/mfa/resend", json={"mfa_token": challenge["mfa_token"]}).status_code == 429
    if old != new:
        stale = mail_client.post(f"{API}/auth/mfa/verify", json={"mfa_token": challenge["mfa_token"], "code": old})
        assert stale.status_code == 401
    good = mail_client.post(f"{API}/auth/mfa/verify", json={"mfa_token": challenge["mfa_token"], "code": new})
    assert good.status_code == 200


def test_resend_is_refused_for_authenticator_accounts_and_forged_challenges(mail_client, mailer):
    tokens = register(mail_client)
    enable_mfa(mail_client, tokens)
    challenge = login(mail_client).json()
    assert challenge["method"] == "totp" and challenge["email_hint"] is None
    assert mail_client.post(f"{API}/auth/mfa/resend", json={"mfa_token": challenge["mfa_token"]}).status_code == 400
    assert mail_client.post(f"{API}/auth/mfa/resend", json={"mfa_token": "x" * 40}).status_code == 401


def test_a_code_burns_after_five_wrong_tries(mail_client, mailer):
    tokens = verified(mail_client, mailer)
    enable_email_mfa(mail_client, mailer, tokens)
    challenge = login(mail_client).json()
    code = last_code(mail_client, mailer, "sign-in code")
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(5):
        r = mail_client.post(f"{API}/auth/mfa/verify", json={"mfa_token": challenge["mfa_token"], "code": wrong})
        assert r.status_code == 401
    # The per-account limit on wrong second-factor codes now applies, and the code itself is burnt.
    r = mail_client.post(f"{API}/auth/mfa/verify", json={"mfa_token": challenge["mfa_token"], "code": code})
    assert r.status_code in (401, 429)


def test_recovery_code_signs_in_and_alerts_the_owner(mail_client, mailer):
    tokens = verified(mail_client, mailer)
    codes = enable_email_mfa(mail_client, mailer, tokens)
    challenge = login(mail_client).json()
    r = mail_client.post(f"{API}/auth/mfa/verify", json={"mfa_token": challenge["mfa_token"], "code": codes[0].lower()})
    assert r.status_code == 200
    assert "DHANZ AI security: a recovery code was used" in subjects(mail_client, mailer)
    reuse = login(mail_client).json()
    assert (
        mail_client.post(f"{API}/auth/mfa/verify", json={"mfa_token": reuse["mfa_token"], "code": codes[0]}).status_code
        == 401
    )


def test_managing_email_codes_needs_an_emailed_code(mail_client, mailer):
    tokens = verified(mail_client, mailer)
    enable_email_mfa(mail_client, mailer, tokens)
    off = f"{API}/users/me/mfa/disable"
    assert mail_client.post(off, json={"code": "123456"}, headers=bearer(tokens)).status_code == 403
    assert mail_client.post(f"{API}/users/me/mfa/email/code", headers=bearer(tokens)).status_code == 202
    code = last_code(mail_client, mailer, "security code")
    # A sign-in code cannot be used for account changes, and vice versa (different purposes).
    r = mail_client.post(f"{API}/users/me/mfa/recovery-codes", json={"code": code}, headers=bearer(tokens))
    assert r.status_code == 200 and "DHANZ AI security: new recovery codes" in subjects(mail_client, mailer)
    assert mail_client.post(off, json={"code": code}, headers=bearer(tokens)).status_code == 403  # used up
    limiter.reset()  # 30 seconds later
    assert mail_client.post(f"{API}/users/me/mfa/email/code", headers=bearer(tokens)).status_code == 202
    # Too soon for another code.
    assert mail_client.post(f"{API}/users/me/mfa/email/code", headers=bearer(tokens)).status_code == 429
    code = last_code(mail_client, mailer, "security code")
    r = mail_client.post(off, json={"code": code}, headers=bearer(tokens))
    assert r.status_code == 200 and r.json()["mfa_enabled"] is False and r.json()["mfa_method"] is None
    assert "DHANZ AI security: two-step verification is off" in subjects(mail_client, mailer)
    assert "access_token" in login(mail_client).json()


def test_switching_email_codes_off_on_the_server_keeps_existing_accounts_working(settings, knowledge, mailer):
    limiter.reset()
    with TestClient(create_app(settings, Orchestrator([EchoProvider()]), knowledge, mailer=mailer)) as client:
        tokens = verified(client, mailer)
        enable_email_mfa(client, mailer, tokens)
    off = settings.model_copy(update={"mfa_email_enabled": False})
    limiter.reset()
    with TestClient(create_app(off, Orchestrator([EchoProvider()]), knowledge, mailer=mailer)) as client:
        assert client.get(f"{API}/auth/options").json()["mfa_email"] is False
        challenge = login(client).json()
        code = last_code(client, mailer, "sign-in code")
        assert (
            client.post(f"{API}/auth/mfa/verify", json={"mfa_token": challenge["mfa_token"], "code": code}).status_code
            == 200
        )
        other = register(client, email="cy@example.com")
        r = client.post(f"{API}/users/me/mfa/email/setup", json={"password": PASSWORD}, headers=bearer(other))
        assert r.status_code == 501


# --- remember this device --------------------------------------------------------------------------


def test_remembered_device_skips_the_second_step_until_forgotten(client):
    tokens = register(client)
    secret, _codes = enable_mfa(client, tokens)
    challenge = login(client).json()
    r = client.post(
        f"{API}/auth/mfa/verify",
        json={
            "mfa_token": challenge["mfa_token"],
            "code": mfa.code_at(secret, mfa.current_step()),
            "remember_device": True,
        },
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0) Chrome/130.0"},
    )
    assert r.status_code == 200
    device_token = r.json()["trusted_device_token"]
    assert device_token and len(device_token) >= 40
    session = r.json()

    skip = client.post(
        f"{API}/auth/login",
        json={"email": "ada@example.com", "password": PASSWORD, "trusted_device_token": device_token},
    )
    assert "access_token" in skip.json()
    # The token alone is not a password: a wrong password still fails.
    bad = client.post(
        f"{API}/auth/login",
        json={"email": "ada@example.com", "password": "wrong-pass-9", "trusted_device_token": device_token},
    )
    assert bad.status_code == 401
    # A made-up token still gets the challenge.
    guess = client.post(
        f"{API}/auth/login", json={"email": "ada@example.com", "password": PASSWORD, "trusted_device_token": "x" * 43}
    )
    assert guess.json()["mfa_required"] is True

    devices = client.get(f"{API}/users/me/trusted-devices", headers=bearer(session)).json()
    assert [d["label"] for d in devices] == ["Chrome on Windows"]
    r = client.delete(f"{API}/users/me/trusted-devices/{devices[0]['id']}", headers=bearer(session))
    assert r.status_code == 204
    again = client.post(
        f"{API}/auth/login",
        json={"email": "ada@example.com", "password": PASSWORD, "trusted_device_token": device_token},
    )
    assert again.json()["mfa_required"] is True


def test_remembered_devices_are_tied_to_one_account(client):
    ada = register(client)
    secret, _ = enable_mfa(client, ada)
    challenge = login(client).json()
    token = client.post(
        f"{API}/auth/mfa/verify",
        json={
            "mfa_token": challenge["mfa_token"],
            "code": mfa.code_at(secret, mfa.current_step()),
            "remember_device": True,
        },
    ).json()["trusted_device_token"]
    bo = register(client, email="bo@example.com")
    secret_bo, _ = enable_mfa_for(client, bo, "bo@example.com")
    r = client.post(
        f"{API}/auth/login", json={"email": "bo@example.com", "password": PASSWORD, "trusted_device_token": token}
    )
    assert r.json()["mfa_required"] is True


def enable_mfa_for(client, tokens, email):
    setup = client.post(f"{API}/users/me/mfa/setup", json={"password": PASSWORD}, headers=bearer(tokens)).json()
    code = mfa.code_at(setup["secret"], mfa.current_step() - 1)
    r = client.post(f"{API}/users/me/mfa/enable", json={"code": code}, headers=bearer(tokens))
    assert r.status_code == 200, (email, r.text)
    return setup["secret"], r.json()["recovery_codes"]


def test_security_changes_forget_every_remembered_device(client):
    tokens = register(client)
    secret, codes = enable_mfa(client, tokens)

    def remembered() -> tuple[dict, str]:
        challenge = login(client).json()
        r = client.post(
            f"{API}/auth/mfa/verify",
            json={"mfa_token": challenge["mfa_token"], "code": codes.pop(), "remember_device": True},
        )
        assert r.status_code == 200, r.text
        return r.json(), r.json()["trusted_device_token"]

    def skips(token: str) -> bool:
        r = client.post(
            f"{API}/auth/login", json={"email": "ada@example.com", "password": PASSWORD, "trusted_device_token": token}
        )
        return "access_token" in r.json()

    session, token = remembered()
    assert skips(token)
    assert client.delete(f"{API}/users/me/trusted-devices", headers=bearer(session)).status_code == 204
    assert not skips(token)

    session, token = remembered()
    r = client.post(
        f"{API}/users/me/password",
        json={"current_password": PASSWORD, "new_password": "brand-new-horse-7"},
        headers=bearer(session),
    )
    assert r.status_code in (200, 204), r.text
    r = client.post(
        f"{API}/auth/login",
        json={"email": "ada@example.com", "password": "brand-new-horse-7", "trusted_device_token": token},
    )
    assert r.json()["mfa_required"] is True


def test_turning_off_or_admin_reset_forgets_devices(client):
    admin = register(client)  # first account is the admin
    bo = register(client, email="bo@example.com")
    secret, codes = enable_mfa_for(client, bo, "bo@example.com")
    challenge = client.post(f"{API}/auth/login", json={"email": "bo@example.com", "password": PASSWORD}).json()
    token = client.post(
        f"{API}/auth/mfa/verify",
        json={"mfa_token": challenge["mfa_token"], "code": codes[0], "remember_device": True},
    ).json()["trusted_device_token"]
    users = client.get(f"{API}/admin/users", headers=bearer(admin)).json()
    bo_id = next(
        u["id"] for u in (users["items"] if isinstance(users, dict) else users) if u["email"] == "bo@example.com"
    )
    r = client.patch(f"{API}/admin/users/{bo_id}", json={"reset_mfa": True}, headers=bearer(admin))
    assert r.status_code == 200, r.text
    r = client.post(
        f"{API}/auth/login", json={"email": "bo@example.com", "password": PASSWORD, "trusted_device_token": token}
    )
    assert "access_token" in r.json()  # no second step any more: it was reset
    from app.models import TrustedDevice  # noqa: F401 - the table is empty for bo now (checked via the list)

    assert client.get(f"{API}/users/me/trusted-devices", headers=bearer(r.json())).json() == []


def test_remember_device_can_be_switched_off(settings, knowledge):
    limiter.reset()
    off = settings.model_copy(update={"trusted_device_days": 0})
    with TestClient(create_app(off, Orchestrator([EchoProvider()]), knowledge)) as client:
        tokens = register(client)
        secret, codes = enable_mfa(client, tokens)
        challenge = login(client).json()
        r = client.post(
            f"{API}/auth/mfa/verify",
            json={"mfa_token": challenge["mfa_token"], "code": codes[0], "remember_device": True},
        )
        assert r.status_code == 200 and r.json()["trusted_device_token"] is None
        assert client.get(f"{API}/auth/options").json()["trusted_device_days"] == 0
