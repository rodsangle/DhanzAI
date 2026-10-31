"""Public accounts: email verification, two-factor authentication, Google / Apple sign-in."""

from __future__ import annotations

import time
import uuid

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from app.core import mfa
from app.core.rate_limit import limiter
from app.main import create_app
from app.services.oauth import IdTokenVerifier
from dhanz_ai import Orchestrator
from tests.conftest import EchoProvider

PASSWORD = "correct-horse-9"
API = "/api/v1"


class FakeMailer:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str, str]] = []

    async def send(self, to: str, subject: str, body: str) -> None:
        self.sent.append((to, subject, body))


def bearer(tokens: dict) -> dict:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


def register(client, email="ada@example.com", password=PASSWORD) -> dict:
    r = client.post(f"{API}/auth/register", json={"email": email, "password": password, "display_name": "Ada"})
    assert r.status_code == 201, r.text
    return r.json()


def login(client, email="ada@example.com", password=PASSWORD):
    return client.post(f"{API}/auth/login", json={"email": email, "password": password})


# --- TOTP ------------------------------------------------------------------------------------------


def test_totp_matches_rfc_6238_and_rejects_replays():
    secret = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"  # ASCII "12345678901234567890", the RFC test key
    assert mfa.code_at(secret, 59 // 30) == "287082"  # RFC 6238 SHA-1 vector, last 6 digits
    assert mfa.code_at(secret, 1111111109 // 30) == "081804"
    now = 1_700_000_000.0
    code = mfa.code_at(secret, mfa.current_step(now))
    step = mfa.match_step(secret, code, now=now)
    assert step == mfa.current_step(now)
    assert mfa.match_step(secret, code, now=now + 30) == step  # one step of clock drift is fine
    assert mfa.match_step(secret, code, now=now + 90) is None
    assert mfa.match_step(secret, code, now=now, after=step) is None  # already used
    assert mfa.match_step(secret, "12345", now=now) is None
    assert mfa.match_step(secret, code[:3] + " " + code[3:], now=now) == step  # spaces are ignored


def test_totp_secret_is_encrypted_at_rest(settings):
    secret = mfa.new_secret()
    sealed = mfa.encrypt_secret(settings, secret)
    assert secret not in sealed and sealed.startswith("v1:")
    assert mfa.decrypt_secret(settings, sealed) == secret
    other = settings.model_copy(update={"data_encryption_key": "another-key-entirely-0123456789"})
    with pytest.raises(Exception):  # noqa: B017 - InvalidTag: a different key cannot read it
        mfa.decrypt_secret(other, sealed)
    assert len(mfa.new_recovery_codes()) == 10


# --- email verification ----------------------------------------------------------------------------


def test_email_verification_unlocks_chats_when_required(settings, knowledge):
    limiter.reset()
    mailer = FakeMailer()
    strict = settings.model_copy(update={"require_email_verification": True})
    with TestClient(create_app(strict, Orchestrator([EchoProvider()]), knowledge, mailer=mailer)) as client:
        options = client.get(f"{API}/auth/options").json()
        assert options["email_verification"] is True and options["email_verification_required"] is True
        tokens = register(client)
        assert tokens["user"]["email_verified"] is False
        client.get(f"{API}/health")  # let the background send run
        assert [m[1] for m in mailer.sent] == ["Confirm your email for DHANZ AI"]
        code = mailer.sent[0][2].split("code is: ")[1].split()[0]
        assert len(code) == 6 and code.isdigit()

        locked = client.post(f"{API}/conversations", json={"title": "x"}, headers=bearer(tokens))
        assert locked.status_code == 403 and "Confirm your email" in locked.json()["detail"]
        locked_studio = client.get(f"{API}/creative/capabilities", headers=bearer(tokens))
        assert locked_studio.status_code == 403 and "Confirm your email" in locked_studio.json()["detail"]
        assert client.get(f"{API}/users/me", headers=bearer(tokens)).status_code == 200  # account stays usable

        confirm = f"{API}/users/me/email-verification/confirm"
        wrong = "000000" if code != "000000" else "111111"
        assert client.post(confirm, json={"code": wrong}, headers=bearer(tokens)).status_code == 400
        r = client.post(confirm, json={"code": code}, headers=bearer(tokens))
        assert r.status_code == 200 and r.json()["email_verified"] is True
        assert client.post(f"{API}/conversations", json={"title": "x"}, headers=bearer(tokens)).status_code == 201
        assert client.get(f"{API}/creative/capabilities", headers=bearer(tokens)).status_code == 200
        resend = client.post(f"{API}/users/me/email-verification", headers=bearer(tokens))
        assert resend.status_code == 202 and "already" in resend.json()["detail"]


def test_email_codes_burn_after_five_wrong_guesses(settings, knowledge):
    limiter.reset()
    mailer = FakeMailer()
    with TestClient(create_app(settings, Orchestrator([EchoProvider()]), knowledge, mailer=mailer)) as client:
        tokens = register(client)
        client.get(f"{API}/health")
        code = mailer.sent[0][2].split("code is: ")[1].split()[0]
        wrong = "000000" if code != "000000" else "111111"
        confirm = f"{API}/users/me/email-verification/confirm"
        for _ in range(5):
            assert client.post(confirm, json={"code": wrong}, headers=bearer(tokens)).status_code == 400
        assert client.post(confirm, json={"code": code}, headers=bearer(tokens)).status_code == 400
        # A new code works.
        assert client.post(f"{API}/users/me/email-verification", headers=bearer(tokens)).status_code == 202
        client.get(f"{API}/health")
        fresh = mailer.sent[-1][2].split("code is: ")[1].split()[0]
        assert client.post(confirm, json={"code": fresh}, headers=bearer(tokens)).json()["email_verified"] is True


def test_without_email_nothing_is_locked(client):
    tokens = register(client)
    assert tokens["user"]["email_verified"] is False
    assert client.get(f"{API}/auth/options").json()["email_verification"] is False
    assert client.post(f"{API}/conversations", json={"title": "x"}, headers=bearer(tokens)).status_code == 201
    assert client.post(f"{API}/users/me/email-verification", headers=bearer(tokens)).status_code == 501


# --- two-factor authentication ---------------------------------------------------------------------


def _code(secret: str, offset: int = 0) -> str:
    return mfa.code_at(secret, mfa.current_step() + offset)


def enable_mfa(client, tokens) -> tuple[str, list[str]]:
    setup = client.post(f"{API}/users/me/mfa/setup", json={"password": PASSWORD}, headers=bearer(tokens))
    assert setup.status_code == 200, setup.text
    secret = setup.json()["secret"]
    assert setup.json()["otpauth_uri"].startswith("otpauth://totp/DHANZ%20AI%3Aada%40example.com?secret=")
    r = client.post(f"{API}/users/me/mfa/enable", json={"code": _code(secret, -1)}, headers=bearer(tokens))
    assert r.status_code == 200, r.text
    return secret, r.json()["recovery_codes"]


def test_two_factor_sign_in(client):
    tokens = register(client)
    other_device = login(client).json()
    assert (
        client.post(
            f"{API}/users/me/mfa/setup", json={"password": "wrong-password-1"}, headers=bearer(tokens)
        ).status_code
        == 403
    )
    secret, recovery = enable_mfa(client, tokens)
    assert len(recovery) == 10 and len(set(recovery)) == 10
    me = client.get(f"{API}/users/me", headers=bearer(tokens)).json()
    assert me["mfa_enabled"] is True
    # Sessions opened with the password alone were signed out; this one stays.
    assert client.get(f"{API}/users/me", headers=bearer(other_device)).status_code == 401

    challenge = login(client).json()
    assert challenge["mfa_required"] is True and "access_token" not in challenge
    verify = f"{API}/auth/mfa/verify"
    assert client.post(verify, json={"mfa_token": challenge["mfa_token"], "code": "000000"}).status_code == 401
    # The code used to enable is spent; the current one works once.
    r = client.post(verify, json={"mfa_token": challenge["mfa_token"], "code": _code(secret)})
    assert r.status_code == 200, r.text
    assert client.get(f"{API}/users/me", headers=bearer(r.json())).status_code == 200
    replay = client.post(verify, json={"mfa_token": login(client).json()["mfa_token"], "code": _code(secret)})
    assert replay.status_code == 401

    # A recovery code works exactly once, in any case and with or without dashes.
    code = recovery[0].lower().replace("-", "")
    assert client.post(verify, json={"mfa_token": login(client).json()["mfa_token"], "code": code}).status_code == 200
    assert client.post(verify, json={"mfa_token": login(client).json()["mfa_token"], "code": code}).status_code == 401
    left = client.get(f"{API}/users/me/mfa/recovery-codes/remaining", headers=bearer(tokens)).json()
    assert left == {"remaining": 9}

    # The challenge token is not an access token.
    assert (
        client.get(f"{API}/users/me", headers={"Authorization": f"Bearer {challenge['mfa_token']}"}).status_code == 401
    )

    fresh = client.post(f"{API}/users/me/mfa/recovery-codes", json={"code": recovery[1]}, headers=bearer(tokens))
    assert fresh.status_code == 200 and recovery[2] not in fresh.json()["recovery_codes"]
    assert (
        client.post(verify, json={"mfa_token": login(client).json()["mfa_token"], "code": recovery[2]}).status_code
        == 401
    )  # replaced codes stop working

    off = client.post(
        f"{API}/users/me/mfa/disable", json={"code": fresh.json()["recovery_codes"][0]}, headers=bearer(tokens)
    )
    assert off.status_code == 200 and off.json()["mfa_enabled"] is False
    assert "access_token" in login(client).json()


def test_wrong_two_factor_codes_are_limited(client):
    tokens = register(client)
    enable_mfa(client, tokens)
    challenge = login(client).json()["mfa_token"]
    statuses = [
        client.post(f"{API}/auth/mfa/verify", json={"mfa_token": challenge, "code": "000000"}).status_code
        for _ in range(6)
    ]
    assert statuses[:5] == [401] * 5 and statuses[5] == 429


def test_admin_can_reset_a_lost_authenticator(client):
    admin = register(client, "boss@example.com")
    tokens = register(client)
    enable_mfa(client, tokens)
    users = client.get(f"{API}/admin/users", headers=bearer(admin)).json()["items"]
    target = next(u for u in users if u["email"] == "ada@example.com")
    assert target["mfa_enabled"] is True
    r = client.patch(f"{API}/admin/users/{target['id']}", json={"reset_mfa": True}, headers=bearer(admin))
    assert r.status_code == 200 and r.json()["mfa_enabled"] is False
    assert "access_token" in login(client).json()
    audit = client.get(f"{API}/admin/audit", headers=bearer(admin)).json()
    assert any(e["action"] == "admin.user_updated" and e["detail"].get("mfa_reset") for e in audit)


def test_expired_or_forged_challenge_is_refused(client, settings):
    register(client)
    forged = jwt.encode(
        {"sub": str(uuid.uuid4()), "type": "mfa", "iat": int(time.time()), "exp": int(time.time()) + 60},
        "not-the-server-secret-at-all-0123456789",
        algorithm="HS256",
    )
    r = client.post(f"{API}/auth/mfa/verify", json={"mfa_token": forged, "code": "123456"})
    assert r.status_code == 401


def test_account_deletion_needs_the_second_factor(client):
    tokens = register(client)
    secret, _ = enable_mfa(client, tokens)
    delete = lambda body: client.request("DELETE", f"{API}/users/me", json=body, headers=bearer(tokens))  # noqa: E731
    assert delete({"password": PASSWORD}).status_code == 403
    assert delete({"password": PASSWORD, "mfa_code": _code(secret)}).status_code == 204


# --- Google / Apple --------------------------------------------------------------------------------


class FakeIssuer:
    """Signs ID tokens like Google/Apple and serves the matching JWKS."""

    def __init__(self) -> None:
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        jwk = jwt.algorithms.RSAAlgorithm.to_jwk(self.key.public_key(), as_dict=True)
        self.jwks = {"keys": [{**jwk, "kid": "k1", "alg": "RS256", "use": "sig"}]}
        self.fetches = 0

    def transport(self) -> httpx.MockTransport:
        def handler(request: httpx.Request) -> httpx.Response:
            self.fetches += 1
            return httpx.Response(200, json=self.jwks)

        return httpx.MockTransport(handler)

    def token(self, provider="google", sub="g-123", email="ada@example.com", **extra) -> str:
        now = int(time.time())
        claims = {
            "iss": "https://accounts.google.com" if provider == "google" else "https://appleid.apple.com",
            "aud": "web-client.apps.googleusercontent.com" if provider == "google" else "ai.dhanz.app",
            "sub": sub,
            "email": email,
            "email_verified": True if provider == "google" else "true",
            "iat": now,
            "exp": now + 600,
            "name": "Ada Lovelace",
        }
        claims.update(extra)
        claims = {k: v for k, v in claims.items() if v is not None}
        return jwt.encode(claims, self.key, algorithm="RS256", headers={"kid": "k1"})


@pytest.fixture
def issuer() -> FakeIssuer:
    return FakeIssuer()


@pytest.fixture
def social(settings, knowledge, issuer):
    limiter.reset()
    configured = settings.model_copy(
        update={"google_client_ids": "web-client.apps.googleusercontent.com", "apple_client_ids": "ai.dhanz.app"}
    )
    verifier = IdTokenVerifier(configured, http=httpx.AsyncClient(transport=issuer.transport()))
    app = create_app(configured, Orchestrator([EchoProvider()]), knowledge, id_tokens=verifier)
    with TestClient(app) as c:
        yield c


def oauth(client, provider, token, **body):
    return client.post(f"{API}/auth/oauth/{provider}", json={"id_token": token, **body})


def test_google_sign_up_then_sign_in(social, issuer):
    options = social.get(f"{API}/auth/options").json()
    assert options["google_client_id"] == "web-client.apps.googleusercontent.com" and options["apple_sign_in"]
    first = oauth(social, "google", issuer.token())
    assert first.status_code == 200, first.text
    user = first.json()["user"]
    assert user["email"] == "ada@example.com" and user["display_name"] == "Ada Lovelace"
    assert user["email_verified"] is True and user["has_password"] is False and user["role"] == "admin"
    again = oauth(social, "google", issuer.token())
    assert again.json()["user"]["id"] == user["id"]
    assert issuer.fetches == 1  # signing keys are cached
    links = social.get(f"{API}/users/me/identities", headers=bearer(again.json())).json()
    assert [link["provider"] for link in links] == ["google"]
    # No password: password sign-in is impossible, and the only sign-in method cannot be unlinked.
    assert login(social).status_code == 401
    assert social.delete(f"{API}/users/me/identities/google", headers=bearer(again.json())).status_code == 409


def test_bad_id_tokens_are_refused(social, issuer):
    assert oauth(social, "google", issuer.token(aud="someone-elses-app")).status_code == 401
    assert oauth(social, "google", issuer.token(iss="https://evil.example")).status_code == 401
    assert oauth(social, "google", issuer.token(exp=int(time.time()) - 3600)).status_code == 401
    assert oauth(social, "google", issuer.token(nonce="abc"), nonce="different").status_code == 401
    assert oauth(social, "google", issuer.token(nonce="abc"), nonce="abc").status_code == 200
    other_key = FakeIssuer()  # right claims, wrong signature
    assert oauth(social, "google", other_key.token(sub="g-999")).status_code == 401
    unverified = oauth(social, "google", issuer.token(sub="g-2", email="bob@example.com", email_verified=False))
    assert unverified.status_code == 400
    assert oauth(social, "github", issuer.token()).status_code == 422


def test_apple_sign_in_with_hashed_nonce_and_first_time_name(social, issuer):
    import hashlib

    raw = "random-nonce-123"
    token = issuer.token(
        "apple",
        sub="001234.abcd",
        email="x7k2@privaterelay.appleid.com",
        name=None,
        nonce=hashlib.sha256(raw.encode()).hexdigest(),
    )
    r = oauth(social, "apple", token, nonce=raw, display_name="Ada")
    assert r.status_code == 200, r.text
    assert r.json()["user"]["display_name"] == "Ada"


def test_google_links_to_existing_verified_account(social, issuer, settings):
    tokens = register(social)
    # Mark the address as confirmed (as the emailed code would).
    import asyncio

    from sqlalchemy import update

    from app.db.session import make_engine, make_sessionmaker
    from app.models import User

    async def verify() -> None:
        engine = make_engine(settings.database_url)
        async with make_sessionmaker(engine)() as db:
            await db.execute(update(User).values(email_verified_at=User.created_at))
            await db.commit()
        await engine.dispose()

    asyncio.run(verify())
    r = oauth(social, "google", issuer.token())
    assert r.json()["user"]["id"] == tokens["user"]["id"] and r.json()["user"]["has_password"] is True
    assert login(social).status_code == 200  # the password still works
    assert social.get(f"{API}/users/me", headers=bearer(tokens)).status_code == 200


def test_google_takes_over_unverified_squatted_address(social, issuer):
    squatter = register(social)  # someone registered ada@example.com without proving they own it
    r = oauth(social, "google", issuer.token())
    assert r.status_code == 200
    assert r.json()["user"]["id"] == squatter["user"]["id"]
    assert r.json()["user"]["has_password"] is False and r.json()["user"]["email_verified"] is True
    assert login(social).status_code == 401  # the squatter's password is gone
    assert social.get(f"{API}/users/me", headers=bearer(squatter)).status_code == 401  # and their sessions


def test_social_sign_in_respects_two_factor_and_closed_registration(social, issuer, settings):
    tokens = oauth(social, "google", issuer.token()).json()
    setup = social.post(f"{API}/users/me/mfa/setup", json={}, headers=bearer(tokens)).json()
    social.post(f"{API}/users/me/mfa/enable", json={"code": _code(setup["secret"], -1)}, headers=bearer(tokens))
    challenge = oauth(social, "google", issuer.token()).json()
    assert challenge["mfa_required"] is True
    ok = social.post(
        f"{API}/auth/mfa/verify", json={"mfa_token": challenge["mfa_token"], "code": _code(setup["secret"])}
    )
    assert ok.status_code == 200

    social.app.state.settings.allow_registration = False
    assert oauth(social, "google", issuer.token(sub="g-new", email="eve@example.com")).status_code == 403


def test_social_only_account_deletes_by_retyping_email(social, issuer):
    tokens = oauth(social, "google", issuer.token()).json()
    delete = lambda body: social.request("DELETE", f"{API}/users/me", json=body, headers=bearer(tokens))  # noqa: E731
    assert delete({}).status_code == 403
    assert delete({"confirm_email": "someone@example.com"}).status_code == 403
    assert delete({"confirm_email": "ADA@example.com"}).status_code == 204
