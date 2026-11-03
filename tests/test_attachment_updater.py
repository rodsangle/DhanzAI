import ast
import base64
import gzip
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("attachment_updater", ROOT / "deploy/updaters/prepare_attachment_fix.py")
updater = importlib.util.module_from_spec(spec)
spec.loader.exec_module(updater)


def baseline():
    reader = (ROOT / "tests/fixtures/attachment_reader_before.txt").read_text()
    return (
        "from __future__ import annotations\nATTACHMENT_CONTEXT_BUDGET = 40000\n" + reader + "\n\n"
        "async def _research(maker, orchestrator, turn, notes):\n"
        "    async with maker() as db:\n"
        "        attached, images = await _attachment_passages(db, turn, notes)\n"
        "    if attached:\n"
        "        window = 8192\n"
        "        budget = attachment_context_budget(window)\n"
        "    return attached, images\n\n"
        "def custom_automation_0010():\n    return 'KEEP CUSTOM GITHUB AND PC FEATURES'\n"
    )


def test_patch_preserves_custom_features_and_adds_full_document_context():
    original = baseline()
    patched = updater.patch_source(original)
    before = next(n for n in ast.parse(original).body if isinstance(n, ast.FunctionDef))
    after = next(n for n in ast.parse(patched).body if isinstance(n, ast.FunctionDef) and n.name == before.name)
    assert ast.dump(before) == ast.dump(after)
    assert "budget_chars=_attachment_budget_for_turn(orchestrator, turn)" in patched
    assert "_attachment_budget_for_turn(orchestrator, turn, window=window)" in patched
    assert "FULL_ATTACHMENT_CONTEXT_BUDGET = 160_000" in patched
    compile(patched, "chat_service.py", "exec")
    assert updater.patch_source(patched) == patched


def test_changed_custom_reader_is_never_overwritten():
    changed = baseline().replace("if not doc.content:", "if doc.content is None:")
    with pytest.raises(ValueError, match="differs from the supported baseline"):
        updater.patch_source(changed)


def test_changed_research_budget_is_never_overwritten():
    changed = baseline().replace("attachment_context_budget(window)", "custom_budget(window)")
    with pytest.raises(ValueError, match="custom context budget"):
        updater.patch_source(changed)


def test_installer_bundles_the_actual_tested_backend_functions():
    payload = ast.parse(gzip.decompress(base64.b64decode(updater._BUNDLED_SOURCE)).decode())
    current = ast.parse((ROOT / "backend/app/services/chat_service.py").read_text())
    names = {"_attachment_passages", "_complete_attachment_requested", "_attachment_budget_for_turn"}

    def functions(tree):
        return {
            n.name: ast.dump(n)
            for n in tree.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in names
        }

    assert functions(payload) == functions(current)
