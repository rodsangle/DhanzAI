"""scripts/server/deploy_live_news.py: the hook is appended once and needs the host's tool registry."""

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/server"))
spec = importlib.util.spec_from_file_location("deploy_live_news", ROOT / "scripts/server/deploy_live_news.py")
dln = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dln)

REGISTRY = """
from dhanz_ai import ToolSpec
class ToolInputError(Exception): ...
class ToolOutcome: ...
class Tool: ...
class ToolBox: ...
TOOLS: dict = {}
"""


def test_the_live_shaped_tool_module_is_accepted():
    weather_patched = REGISTRY + "\nfrom app.services.weather_tools import register as r\nr(globals())\n"
    assert dln.registry_ok(weather_patched)
    assert not dln.registry_ok("TOOLS = {}\n")


def test_the_hook_is_appended_once_after_everything_else():
    once = dln.hook(REGISTRY)
    assert once.startswith(REGISTRY.rstrip("\n"))
    assert once.rstrip().endswith("_register_dhanz_news(globals())")
    assert dln.hook(once) == once


def test_a_broken_module_is_refused_before_building():
    with pytest.raises(SyntaxError):
        dln.hook("def broken(:\n")


def test_the_repository_tool_module_carries_the_same_hook():
    source = (ROOT / "backend/app/services/assistant_tools.py").read_text()
    assert dln.registry_ok(source)
    assert source.rstrip().endswith("_register_dhanz_news(globals())")
    assert dln.hook(source) == source
