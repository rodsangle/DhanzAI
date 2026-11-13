"""scripts/server/deploy_ai_engine.py: a CRLF copy of a repository file is the same file."""

import importlib.util
import subprocess
from pathlib import Path
from types import SimpleNamespace

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
    assert dae.plan("api", "/pkg/dhanz_ai") == {r: "current" for r in dae.FILES}


def test_a_real_edit_is_still_unknown(monkeypatch):
    edited = {r: repo_file(r) for r in dae.FILES}
    edited["orchestrator.py"] += b"\n# a server-only change\n"
    live_files(monkeypatch, edited)
    assert dae.plan("api", "/pkg/dhanz_ai")["orchestrator.py"] == "unknown"


def test_normalized_only_touches_crlf():
    assert dae.normalized(b"a\r\nb\nc\r") == b"a\nb\nc\r"
