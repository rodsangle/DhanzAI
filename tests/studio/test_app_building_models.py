import importlib.util
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from app.assistant_studio import app_building_models as feature
from app.assistant_studio import builder


def test_only_discovered_coding_models_are_ranked():
    ids = [
        "gpt-4.1-mini",
        "gpt-4o",
        "gpt-5.1",
        "gpt-5.1-codex-mini",
        "gpt-5.1-codex",
        "gpt-5-codex",
        "gpt-5.1-codex-2026-01-01",
        "gpt-image-1",
        "gpt-4o-audio-preview",
        "gpt-5.1-chat-latest",
        "whisper-1",
        None,
    ]
    chosen = feature.select_models(ids)
    assert chosen[:2] == ["gpt-5.1-codex", "gpt-5.1-codex-2026-01-01"]
    assert set(chosen) <= set(ids)
    assert "gpt-5.1" in chosen and "gpt-4o" in chosen
    assert not any("image" in name or "audio" in name or "chat-latest" in name for name in chosen)


@pytest.mark.asyncio
async def test_model_discovery_is_key_scoped_without_generating_or_redirecting(monkeypatch):
    feature._CACHE.clear()
    requests = []
    original = httpx.AsyncClient

    def handler(request):
        requests.append(request)
        assert request.method == "GET" and request.url.path == "/v1/models"
        names = (
            ["gpt-5.1-codex", "gpt-4.1-mini"] if request.headers["authorization"] == "Bearer key-one" else ["gpt-4.1"]
        )
        return httpx.Response(200, json={"data": [{"id": name} for name in names]})

    monkeypatch.setattr(
        feature.httpx, "AsyncClient", lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs)
    )
    one = SimpleNamespace(openai_api_key="key-one", openai_base_url="https://api.openai.com/v1")
    two = SimpleNamespace(openai_api_key="key-two", openai_base_url="https://api.openai.com/v1")
    first = await feature.models(one)
    first.clear()
    assert (await feature.models(one))[0] == "gpt-5.1-codex"
    assert await feature.models(two) == ["gpt-4.1"]
    assert len(requests) == 2
    assert "key-one" not in feature._CACHE and "key-two" not in feature._CACHE
    other = SimpleNamespace(openai_api_key="key-one", openai_base_url="https://other.example/v1")
    assert await feature.models(other) == []
    assert len(requests) == 2


@pytest.mark.asyncio
async def test_unavailable_discovery_does_not_invent_models_or_echo_provider_errors(monkeypatch):
    feature._CACHE.clear()
    original = httpx.AsyncClient
    transport = httpx.MockTransport(lambda request: httpx.Response(401, json={"error": {"message": "private-secret"}}))
    monkeypatch.setattr(feature.httpx, "AsyncClient", lambda **kwargs: original(transport=transport, **kwargs))
    with pytest.raises(builder.BuildError) as exc:
        await feature.models(SimpleNamespace(openai_api_key="key-failure", openai_base_url="https://api.openai.com/v1"))
    assert "private-secret" not in str(exc.value)
    assert not feature._CACHE


def test_additive_updater_preserves_custom_source_and_refuses_unknown_defaults():
    root = Path(__file__).resolve().parents[2]
    path = root / "deploy/updaters/install_app_building_model.py"
    spec = importlib.util.spec_from_file_location("app_model_updater", path)
    updater = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(updater)
    bootstrap = "def install(app):\n    app.include_router(router, prefix=app.state.settings.api_prefix)\n    custom_feature()\n"
    updated = updater.patch_bootstrap(bootstrap)
    assert "custom_feature()" in updated
    assert updater.patch_bootstrap(updated) == updated
    tools = (root / "server_extensions/assistant_studio/app_builder_tools.py").read_text()
    assert updater.patch_tools(tools) == tools
    old = tools.replace(
        'model = args.get("model") or (names[0] if names else "")',
        'model = args.get("model") or next(\n                            (name for name in ("gpt-4.1-mini", "gpt-4.1") if name in names), names[0] if names else ""\n                        )',
    )
    assert updater.patch_tools(old) == tools
    with pytest.raises(ValueError, match="customized"):
        updater.patch_tools('model = "custom"')
    assert (
        updater.payload()["module"] == (root / "server_extensions/assistant_studio/app_building_models.py").read_text()
    )
