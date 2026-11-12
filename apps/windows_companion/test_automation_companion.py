"""Portable tests: no real credentials, Windows actions, or remote side effects."""

import copy
import importlib.util
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "automation_companion", Path(__file__).with_name("automation_companion.py")
)
companion = importlib.util.module_from_spec(spec)
spec.loader.exec_module(companion)
sys.modules["automation_companion"] = companion


def action(**overrides):
    return {
        "id": str(uuid.uuid4()),
        "provider": "windows",
        "status": "pending",
        "payload": {"provider": "windows", "operation": "open_app", "app": "notepad"},
        "expires_at": (datetime.now(UTC) + timedelta(minutes=15)).isoformat(),
        **overrides,
    }


class Api:
    def __init__(self, proposed):
        self.proposed = proposed
        self.calls = []

    def call(self, method, path, body=None):
        self.calls.append((method, path, body))
        if path.endswith("/windows-claim"):
            claimed = copy.deepcopy(self.proposed)
            claimed["status"] = "executing"
            return claimed
        return {}


def test_approval_precedes_claim_and_execution():
    proposed = action()
    api = Api(proposed)
    executed = []

    def approve(payload, remaining):
        assert api.calls == [] and not executed
        assert payload == proposed["payload"] and remaining > 0
        return True

    def execute(payload):
        assert api.calls[-1][1] == "/users/me"
        executed.append(payload)

    assert companion.process_action(api, proposed, approve, execute) == "completed"
    assert executed == [proposed["payload"]]
    assert api.calls[-1][2] == {"success": True}


def test_denial_never_claims_or_executes():
    proposed = action()
    api = Api(proposed)
    assert companion.process_action(api, proposed, lambda *a: False, lambda p: pytest.fail("Executed")) == "denied"
    assert len(api.calls) == 1 and api.calls[0][1].endswith("/reject")


def test_expired_action_never_prompts():
    proposed = action(expires_at=(datetime.now(UTC) - timedelta(seconds=1)).isoformat())
    api = Api(proposed)
    assert companion.process_action(api, proposed, lambda *a: pytest.fail("Prompted")) == "expired"
    assert not api.calls


def test_changed_payload_never_executes():
    proposed = action()
    api = Api(proposed)
    original = api.call

    def changed(method, path, body=None):
        result = original(method, path, body)
        if path.endswith("/windows-claim"):
            result["payload"]["app"] = "calculator"
        return result

    api.call = changed
    assert companion.process_action(api, proposed, lambda *a: True, lambda p: pytest.fail("Executed")) == "mismatch"


def test_uncertain_claim_is_not_retried():
    proposed = action()
    api = Api(proposed)

    def uncertain(method, path, body=None):
        api.calls.append((method, path, body))
        raise companion.ApiError(0)

    api.call = uncertain
    with pytest.raises(companion.ApiError):
        companion.process_action(api, proposed, lambda *a: True, lambda p: pytest.fail("Executed"))
    assert len(api.calls) == 1


def test_revoked_session_prevents_execution():
    proposed = action()
    api = Api(proposed)
    original = api.call

    def revoked(method, path, body=None):
        if path == "/users/me":
            raise companion.SignInRequired("revoked")
        return original(method, path, body)

    api.call = revoked
    with pytest.raises(companion.SignInRequired):
        companion.process_action(api, proposed, lambda *a: True, lambda p: pytest.fail("Executed"))


@pytest.mark.parametrize(
    "payload",
    [
        {"provider": "windows", "operation": "open_app", "app": "powershell"},
        {"provider": "windows", "operation": "open_app", "app": "notepad", "args": "secret"},
        {"provider": "windows", "operation": "capture_window"},
        {"provider": "windows", "operation": "click", "x": -1, "y": 2, "clicks": 1},
        {"provider": "windows", "operation": "open_url", "url": "file:///C:/secret"},
        {"provider": "windows", "operation": "open_url", "url": "https://user:pass@example.com"},
        {"provider": "windows", "operation": "open_url", "url": "https://example.com\n"},
        {"provider": "github", "operation": "open_app", "app": "notepad"},
    ],
)
def test_unsupported_actions_are_ignored(payload):
    proposed = action(payload=payload)
    api = Api(proposed)
    assert companion.process_action(api, proposed, lambda *a: pytest.fail("Prompted")) == "ignored"
    assert not api.calls


def test_https_website_can_be_approved():
    proposed = action(
        payload={"provider": "windows", "operation": "open_url", "url": "https://github.com/rodsangle/DhanzAI"}
    )
    api = Api(proposed)
    executed = []
    assert companion.process_action(api, proposed, lambda *a: True, executed.append) == "completed"
    assert executed == [proposed["payload"]]


def test_explicit_401_refreshes_once_and_saves_rotated_tokens(monkeypatch):
    calls, saved = [], []

    def request(server, method, path, token=None, body=None):
        calls.append((path, token, body))
        if len(calls) == 1:
            raise companion.ApiError(401)
        if path == "/auth/refresh":
            assert token is None
            assert body == {"refresh_token": "old-refresh"}
            return {"access_token": "new-access", "refresh_token": "new-refresh"}
        assert token == "new-access"  # noqa: S105 - dummy test credential
        return {"actions": []}

    monkeypatch.setattr(companion, "raw_request", request)
    api = companion.Api(
        "https://dhanzai.com",
        {"access_token": "old-access", "refresh_token": "old-refresh"},
        lambda c: saved.append(dict(c)),
    )
    assert api.call("GET", "/automation/actions") == {"actions": []}
    assert len(calls) == 3 and saved[0]["refresh_token"] == "new-refresh"  # noqa: S105 - dummy test credential


@pytest.mark.parametrize("code", [0, 403, 409, 429, 500])
def test_other_errors_never_retry_or_refresh(monkeypatch, code):
    calls = []

    def fail(*args, **kwargs):
        calls.append(args)
        raise companion.ApiError(code)

    monkeypatch.setattr(companion, "raw_request", fail)
    api = companion.Api(
        "https://dhanzai.com", {"access_token": "test", "refresh_token": "test"}, lambda c: pytest.fail("Saved")
    )
    with pytest.raises(companion.ApiError):
        api.call("POST", "/automation/actions/test/windows-claim", {})
    assert len(calls) == 1


def test_credentials_saved_encrypted_atomically(monkeypatch, tmp_path):
    monkeypatch.setattr(companion, "protect", lambda raw: b"encrypted-test")
    path = tmp_path / "credentials.bin"
    companion.save_credentials(path, {"access_token": "must-not-be-plaintext"})
    assert path.read_bytes() == b"encrypted-test"
    assert list(tmp_path.iterdir()) == [path]


@pytest.mark.parametrize(
    "server", ["http://dhanzai.com", "https://user:pass@example.com", "https://example.com/path", "file:///tmp/x"]
)
def test_invalid_origins_rejected_before_request(server):
    with pytest.raises(ValueError):
        companion.raw_request(server, "GET", "/automation/actions", token="secret")  # noqa: S106 - dummy test credential


def test_redirect_refused():
    with pytest.raises(ValueError):
        companion.NoRedirects().redirect_request(None, None, 302, "redirect", {}, "https://evil.example")


@pytest.mark.skipif(sys.platform != "win32", reason="Requires native Windows DPAPI")
def test_native_windows_dpapi_roundtrip():
    plaintext = b"test-session-data-not-a-real-credential"
    encrypted = companion.protect(plaintext)
    assert encrypted != plaintext
    assert companion.protect(encrypted, decrypt=True) == plaintext
