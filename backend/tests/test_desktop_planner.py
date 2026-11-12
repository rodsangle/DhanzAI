import base64
import io
import json
from types import SimpleNamespace

import pytest
from PIL import Image

from dhanz_ai import Capability, CostTier, ModelInfo, Provider, StreamChunk
from tests.test_tools import make_client, signup


def test_environment_switch_supports_existing_custom_settings(monkeypatch):
    from app.api.routes.desktop import planner_enabled

    monkeypatch.delenv("DESKTOP_PLANNER_ENABLED", raising=False)
    assert not planner_enabled(SimpleNamespace())
    monkeypatch.setenv("DESKTOP_PLANNER_ENABLED", "true")
    assert planner_enabled(SimpleNamespace())
    monkeypatch.setenv("DESKTOP_PLANNER_ENABLED", "false")
    assert not planner_enabled(SimpleNamespace(desktop_planner_enabled=True))


class Planner(Provider):
    name = "planner"

    def __init__(self, plan):
        super().__init__()
        self.plan, self.requests = plan, []

    def is_configured(self):
        return True

    def models(self):
        return [ModelInfo(self.name, "vision", "Vision", frozenset({Capability.CHAT, Capability.VISION}), CostTier.LOW)]

    async def stream(self, model, messages, params, tools=()):
        assert not tools
        self.requests.append(messages)
        yield StreamChunk(text=json.dumps(self.plan))
        yield StreamChunk(done=True)


def observation(**overrides):
    stream = io.BytesIO()
    Image.new("RGB", (64, 32), "white").save(stream, "JPEG")
    return {
        "goal": "Open documentation",
        "screenshot": base64.b64encode(stream.getvalue()).decode(),
        "width": 64,
        "height": 32,
        "step": 0,
        "screen_sharing_consent": True,
        **overrides,
    }


def test_disabled_by_default(settings, knowledge):
    provider = Planner({})
    with make_client(settings, knowledge, provider=provider) as client:
        headers, _ = signup(client)
        assert client.get("/api/v1/desktop/status", headers=headers).json() == {"enabled": False}
        assert client.post("/api/v1/desktop/next", headers=headers, json=observation()).status_code == 404
        assert not provider.requests


def test_vision_plan_is_bounded_stateless_and_has_no_tools(settings, knowledge):
    settings.desktop_planner_enabled = True
    provider = Planner({"operation": "click", "risk": "navigation", "reason": "Open tab", "x": 10, "y": 20})
    with make_client(settings, knowledge, provider=provider) as client:
        headers, _ = signup(client)
        response = client.post("/api/v1/desktop/next", headers=headers, json=observation())
        assert response.status_code == 200, response.text
        assert response.json()["x"] == 10
        assert provider.requests[0][-1].images[0].mime_type == "image/jpeg"
        assert "untrusted" in provider.requests[0][0].content
        assert client.get("/api/v1/conversations", headers=headers).json()["total"] == 0


@pytest.mark.parametrize(
    "changes",
    [
        {"screen_sharing_consent": False},
        {"screenshot": "not-base64-data"},
        {"width": 65},
        {"step": 20},
        {"width": 2000},
    ],
)
def test_invalid_observation_never_reaches_model(settings, knowledge, changes):
    settings.desktop_planner_enabled = True
    provider = Planner({})
    with make_client(settings, knowledge, provider=provider) as client:
        headers, _ = signup(client)
        response = client.post("/api/v1/desktop/next", headers=headers, json=observation(**changes))
        assert response.status_code == 422
        assert not provider.requests


@pytest.mark.parametrize(
    "plan",
    [
        {"operation": "shell", "risk": "navigation", "reason": "Run code"},
        {"operation": "click", "risk": "navigation", "reason": "Outside", "x": 100, "y": 10},
        {"operation": "scroll", "risk": "navigation", "reason": "Scroll", "scroll_delta": 17},
        {"operation": "type_text", "risk": "uncertain", "reason": "Enter", "text": "line\nbreak"},
        {"operation": "press_key", "risk": "uncertain", "reason": "Shell", "key": "WIN+R"},
    ],
)
def test_invalid_model_output_never_becomes_an_action(settings, knowledge, plan):
    settings.desktop_planner_enabled = True
    provider = Planner(plan)
    with make_client(settings, knowledge, provider=provider) as client:
        headers, _ = signup(client)
        assert client.post("/api/v1/desktop/next", headers=headers, json=observation()).status_code == 502


def test_local_privacy_mode_does_not_use_cloud_vision(settings, knowledge, monkeypatch):
    from app.models import User

    monkeypatch.setattr(User, "ai_privacy_mode", "local_only", raising=False)
    settings.desktop_planner_enabled = True
    provider = Planner({"operation": "done", "risk": "navigation", "reason": "Visible"})
    with make_client(settings, knowledge, provider=provider) as client:
        headers, _ = signup(client)
        assert client.post("/api/v1/desktop/next", headers=headers, json=observation()).status_code == 502
        assert not provider.requests


def test_email_verification_gate_applies_to_desktop_planning(settings, knowledge):
    import uuid

    from app.models import User

    settings.desktop_planner_enabled = True
    provider = Planner({})
    with make_client(settings, knowledge, provider=provider) as client:
        headers, _ = signup(client)
        user_id = client.get("/api/v1/users/me", headers=headers).json()["id"]

        async def unverify():
            async with client.app.state.sessionmaker() as db:
                account = await db.get(User, uuid.UUID(user_id))
                account.email_verified_at = None
                await db.commit()

        client.portal.call(unverify)
        settings.require_email_verification = True
        client.app.state.mailer = object()
        assert client.post("/api/v1/desktop/next", headers=headers, json=observation()).status_code == 403
        assert not provider.requests
