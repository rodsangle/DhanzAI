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
