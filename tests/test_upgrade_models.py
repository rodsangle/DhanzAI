"""scripts/server/upgrade_models.py: picks only models that answer, keeps working ones, never prints keys."""

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("upgrade_models", ROOT / "scripts/server/upgrade_models.py")
um = importlib.util.module_from_spec(spec)
sys.modules["upgrade_models"] = um
spec.loader.exec_module(um)


class FakeProviders:
    def __init__(self, openai_ids, broken=(), images=()):
        self.openai_ids = openai_ids
        self.broken = set(broken)
        self.images = list(images)
        self.calls = []

    def __call__(self, method, url, headers, body):
        self.calls.append((method, url, body))
        if url.endswith("/models"):
            return 200, {"data": [{"id": i} for i in self.openai_ids + self.images]}
        if url.endswith("/chat/completions"):
            return (400, {"error": "unsupported"}) if body["model"] in self.broken else (200, "data: {}")
        return 404, {}


def test_newest_answering_models_first_and_current_kept_as_fallback():
    fake = FakeProviders(
        ["gpt-6.1-terra", "gpt-6-astra", "gpt-6-luna", "gpt-realtime-2", "gpt-6-cyber", "gpt-4.1", "gpt-4.1-mini"],
        broken={"gpt-6-astra"},
    )
    env = {"OPENAI_API_KEY": "sk-secret", "OPENAI_MODELS": "gpt-4.1-mini,gpt-4.1"}
    (result,) = um.plan(env, fake)
    assert result.proposed.split(",") == ["gpt-6.1-terra", "gpt-6-luna", "gpt-4.1-mini", "gpt-4.1"]
    assert any("gpt-6-astra: listed but the test request failed" in n for n in result.notes)
    probed = {body["model"] for _, url, body in fake.calls if body}
    assert not probed & {"gpt-realtime-2", "gpt-6-cyber"}
    probe = next(body for _, _, body in fake.calls if body)
    assert probe["stream"] is True and "temperature" in probe and "max_completion_tokens" in probe


def test_retired_model_removed_but_never_left_empty():
    fake = FakeProviders(["gpt-4.1"], broken={"gpt-4.1"})
    (result,) = um.plan({"OPENAI_API_KEY": "k", "OPENAI_MODELS": "gpt-4.1"}, fake)
    assert result.proposed == "gpt-4.1" and not result.changed
    assert "nothing answered; left unchanged" in result.notes


def test_image_model_moves_to_newer_version_of_same_variant():
    fake = FakeProviders([], images=["gpt-image-2.6-sunburst", "gpt-image-2.6-flare", "gpt-image-2.5-sunburst"])
    env = {"CREATIVE_ENABLED": "true", "CREATIVE_IMAGE_API_KEY": "k", "CREATIVE_IMAGE_MODEL": "gpt-image-2.5-sunburst"}
    (result,) = um.plan(env, fake)
    assert result.proposed == "gpt-image-2.6-sunburst"


def test_xai_image_model_upgrades_from_unversioned():
    fake = FakeProviders([], images=["grok-imagine-image", "grok-imagine-image-2.0", "grok-imagine-video-1.5"])
    env = {
        "CREATIVE_ENABLED": "true",
        "CREATIVE_IMAGE_API_KEY": "xai-k",
        "CREATIVE_IMAGE_BASE_URL": "https://api.x.ai/v1",
        "CREATIVE_IMAGE_MODEL": "grok-imagine-image",
    }
    (result,) = um.plan(env, fake)
    assert result.proposed == "grok-imagine-image-2.0"


def test_report_only_by_default_and_apply_keeps_backup(tmp_path, capsys, monkeypatch):
    env_file = tmp_path / ".env"
    original = "# comment\nOPENAI_API_KEY=sk-secret\nOPENAI_MODELS=gpt-4.1\nJWT_SECRET=x\n"
    env_file.write_text(original)
    monkeypatch.setattr(um, "http", FakeProviders(["gpt-6.1-terra", "gpt-4.1"]))
    monkeypatch.setattr(um.plan, "__defaults__", (um.http,))

    assert um.main(["--env", str(env_file)]) == 0
    out = capsys.readouterr().out
    assert "gpt-6.1-terra,gpt-4.1" in out and "sk-secret" not in out
    assert env_file.read_text() == original

    assert um.main(["--env", str(env_file), "--apply"]) == 0
    assert "OPENAI_MODELS=gpt-6.1-terra,gpt-4.1\n" in env_file.read_text()
    assert "JWT_SECRET=x" in env_file.read_text()
    (backup,) = tmp_path.glob(".env.bak-*")
    assert backup.read_text() == original
    assert oct(backup.stat().st_mode & 0o777) == "0o600"


def test_failed_models_show_the_providers_reason_without_keys():
    class Rejecting(FakeProviders):
        def __call__(self, method, url, headers, body):
            if body and body.get("model") == "gpt-6-astra":
                msg = "Unsupported value: 'temperature' does not support 0.7 with this model. Key sk-abcdefghijklmnop"
                return 400, {"error": {"message": msg}}
            return super().__call__(method, url, headers, body)

    (result,) = um.plan({"OPENAI_API_KEY": "k", "OPENAI_MODELS": "gpt-4.1"}, Rejecting(["gpt-6-astra", "gpt-4.1"]))
    note = next(n for n in result.notes if n.startswith("gpt-6-astra"))
    assert "HTTP 400: Unsupported value: 'temperature'" in note
    assert "sk-abcdefghijklmnop" not in note and "[key]" in note


class LiveLike(FakeProviders):
    """Mirrors the live server: GPT-6/5.5/5 accept only temperature 1; -pro is not a chat model."""

    temperature_one_only = {"gpt-6.1-sol", "gpt-6.1-terra", "gpt-6-astra", "gpt-6-luna", "gpt-5.5", "gpt-5"}

    def __call__(self, method, url, headers, body):
        if body and body["model"].endswith("-pro"):
            return 404, {"error": {"message": "This is not a chat model"}}
        if body and body["model"] in self.temperature_one_only and body["temperature"] != 1:
            msg = "Unsupported value: 'temperature' does not support 0.7 with this model. "
            return 400, {"error": {"message": msg + "Only the default (1) value is supported."}}
        return super().__call__(method, url, headers, body)


LIVE_IDS = [
    "gpt-6.1-sol", "gpt-6.1-terra", "gpt-6-astra", "gpt-6-luna", "gpt-5.5", "gpt-5.5-pro", "gpt-5.4",
    "gpt-5.4-mini", "gpt-5.4-nano", "gpt-5.2", "gpt-5.1", "gpt-5", "gpt-4.1-mini", "gpt-4.1",
]  # fmt: skip
LIVE_CURRENT = "gpt-5.4,gpt-5.4-mini,gpt-5.4-nano,gpt-4.1-mini,gpt-4.1"


def test_temperature_one_models_switch_default_temperature_and_older_models_are_not_added():
    fake = LiveLike(LIVE_IDS)
    chat, temperature = um.plan({"OPENAI_API_KEY": "k", "OPENAI_MODELS": LIVE_CURRENT}, fake)
    assert chat.proposed == "gpt-6.1-sol,gpt-6.1-terra,gpt-6-astra," + LIVE_CURRENT
    assert (temperature.setting, temperature.current, temperature.proposed) == ("DEFAULT_TEMPERATURE", "0.7", "1")
    assert not {"gpt-5.2", "gpt-5.1", "gpt-5.5-pro"} & set(chat.proposed.split(","))
    probed_pro = [body for _, _, body in fake.calls if body and body["model"].endswith("-pro")]
    assert probed_pro == []


def test_without_newer_models_nothing_changes_even_if_older_ones_answer():
    fake = LiveLike([m for m in LIVE_IDS if not m.startswith(("gpt-6", "gpt-5.5"))])
    (chat,) = um.plan({"OPENAI_API_KEY": "k", "OPENAI_MODELS": LIVE_CURRENT}, fake)
    assert not chat.changed


def test_temperature_stays_when_already_one():
    fake = LiveLike(LIVE_IDS)
    results = um.plan({"OPENAI_API_KEY": "k", "OPENAI_MODELS": LIVE_CURRENT, "DEFAULT_TEMPERATURE": "1"}, fake)
    assert [r.setting for r in results] == ["OPENAI_MODELS"]
    assert results[0].proposed.startswith("gpt-6.1-sol,gpt-6.1-terra,gpt-6-astra,")


def test_models_that_reject_tools_are_not_chosen():
    class ToolRejecting(LiveLike):
        def __call__(self, method, url, headers, body):
            if body and body["model"].startswith("gpt-6") and body.get("tools"):
                msg = "Function tools with reasoning_effort are not supported for this model in /v1/chat/completions."
                return 400, {"error": {"message": msg}}
            return super().__call__(method, url, headers, body)

    fake = ToolRejecting(LIVE_IDS)
    results = um.plan({"OPENAI_API_KEY": "k", "OPENAI_MODELS": LIVE_CURRENT}, fake)
    chat = results[0]
    assert not any(m.startswith("gpt-6") for m in chat.proposed.split(","))
    assert any("Function tools" in n for n in chat.notes)
    assert all(body.get("tools") for _, url, body in fake.calls if body)
