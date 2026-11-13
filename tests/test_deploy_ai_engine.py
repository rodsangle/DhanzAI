"""scripts/server/deploy_ai_engine.py, and that its four files work with the live server's own providers."""

import asyncio
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import httpx

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("deploy_ai_engine", ROOT / "scripts/server/deploy_ai_engine.py")
dae = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dae)


def live_files(monkeypatch, contents: dict[str, bytes]):
    real_run = subprocess.run

    def fake_run(argv, **kwargs):
        if "exec" in argv and "cat" in argv:
            relative = argv[-1].split("dhanz_ai/", 1)[1]
            return SimpleNamespace(stdout=contents[relative], returncode=0)
        return real_run(argv, **kwargs)

    monkeypatch.setattr(dae.subprocess, "run", fake_run)


def repo_file(relative: str) -> bytes:
    return (ROOT / "ai_engine/dhanz_ai" / relative).read_bytes()


def test_windows_line_endings_are_not_a_difference(monkeypatch):
    crlf = {r: repo_file(r).replace(b"\n", b"\r\n") for r in dae.FILES}
    live_files(monkeypatch, crlf)
    assert dae.plan("api", "/pkg/dhanz_ai", set(dae.FILES)) == {r: "current" for r in dae.FILES}


def test_a_real_edit_is_still_unknown(monkeypatch):
    edited = {r: repo_file(r) for r in dae.FILES}
    edited["orchestrator.py"] += b"\n# a server-only change\n"
    live_files(monkeypatch, edited)
    assert dae.plan("api", "/pkg/dhanz_ai", set(dae.FILES))["orchestrator.py"] == "unknown"


def test_normalized_only_touches_crlf():
    assert dae.normalized(b"a\r\nb\nc\r") == b"a\nb\nc\r"


def test_only_the_four_gpt6_files_are_replaced(monkeypatch):
    # The live server runs its own prompts.py, ollama.py and lmstudio.py; those must never be touched.
    assert set(dae.FILES) == {"providers/base.py", "providers/openai.py", "orchestrator.py", "types.py"}
    live_files(monkeypatch, {r: repo_file(r) for r in dae.FILES})
    states = dae.plan("api", "/pkg/dhanz_ai", set(dae.FILES) | {"prompts.py", "providers/lmstudio.py"})
    assert set(states) == set(dae.FILES)


def test_smoke_test_imports_every_module_before_the_backend():
    assert "pkgutil.walk_packages(dhanz_ai.__path__" in dae.SMOKE_TEST
    assert dae.SMOKE_TEST.index("walk_packages") < dae.SMOKE_TEST.index("import app.main")


def gpt6_handler(seen):
    def handler(request):
        body = json.loads(request.content)
        seen.append(body)
        if "temperature" in body:
            return httpx.Response(
                400,
                json={
                    "error": {
                        "message": "Unsupported value: 'temperature' does not support 0.7. Only the default (1) value is supported."
                    }
                },
            )
        chunk = json.dumps({"choices": [{"delta": {"content": "ok"}}]})
        return httpx.Response(200, content=("data: " + chunk + "\n\ndata: [DONE]\n\n").encode())

    return handler


def test_the_servers_own_lmstudio_provider_works_with_the_new_openai_provider():
    sys.path.insert(0, str(ROOT / "tests/fixtures"))
    try:
        from live_lmstudio import LMStudioProvider
    finally:
        sys.path.pop(0)
    from dhanz_ai import ChatMessage, GenerationParams

    seen = []
    client = httpx.AsyncClient(transport=httpx.MockTransport(gpt6_handler(seen)))
    provider = LMStudioProvider(None, ["qwen3"], base_url="http://lmstudio:1234/v1", client=client)
    assert provider.is_configured() and provider.models()[0].model == "qwen3"

    async def run():
        return [c async for c in provider.stream("qwen3", [ChatMessage("user", "hi")], GenerationParams())]

    assert "".join(c.text for c in asyncio.run(run())) == "ok"
    assert seen[-1]["messages"][-1]["content"].endswith("/no_think")


def test_a_server_provider_written_for_the_old_base_still_constructs():
    # The live ollama.py calls super().__init__(client) and may use DEFAULT_TIMEOUT.
    from dhanz_ai.providers import base

    class OldStyle(base.Provider):
        name = "old"

        def __init__(self, client=None):
            super().__init__(client)

        def models(self):
            return []

        def is_configured(self):
            return True

        async def stream(self, model, messages, params, tools=()):
            yield None

    assert OldStyle()._client.timeout.read == base.DEFAULT_TIMEOUT.read == 120.0
