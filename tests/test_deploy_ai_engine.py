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
    assert dae.plan("api", "/pkg/dhanz_ai", set(dae.FILES)) == {r: "current" for r in dae.FILES}


def test_a_real_edit_is_still_unknown(monkeypatch):
    edited = {r: repo_file(r) for r in dae.FILES}
    edited["orchestrator.py"] += b"\n# a server-only change\n"
    live_files(monkeypatch, edited)
    assert dae.plan("api", "/pkg/dhanz_ai", set(dae.FILES))["orchestrator.py"] == "unknown"


def test_normalized_only_touches_crlf():
    assert dae.normalized(b"a\r\nb\nc\r") == b"a\nb\nc\r"


def test_the_whole_package_is_checked_and_missing_files_are_new(monkeypatch):
    assert {"providers/base.py", "providers/openai.py", "orchestrator.py", "types.py", "__init__.py"} <= set(dae.FILES)
    present = {r: repo_file(r) for r in dae.FILES if r != "skill_pack.py"}
    live_files(monkeypatch, present)
    states = dae.plan("api", "/pkg/dhanz_ai", set(present))
    assert states["skill_pack.py"] == "new"
    assert all(state == "current" for r, state in states.items() if r != "skill_pack.py")


def test_smoke_test_imports_every_module_before_the_backend():
    assert "pkgutil.walk_packages(dhanz_ai.__path__" in dae.SMOKE_TEST
    assert dae.SMOKE_TEST.index("walk_packages") < dae.SMOKE_TEST.index("import app.main")
