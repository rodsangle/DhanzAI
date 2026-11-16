"""scripts/server/deploy_two_step.py: the two hooks are placed exactly, once, or not at all."""

import ast
import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/server"))
spec = importlib.util.spec_from_file_location("deploy_two_step", ROOT / "scripts/server/deploy_two_step.py")
dts = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dts)

# The live server's auth.py and main.py are this repository's versions from before the built-in
# two-step verification (commit 954776d); its login() matched the server's line for line.
LIVE_AUTH = (ROOT / "tests/fixtures/live_auth.py.txt").read_text()
LIVE_MAIN = (ROOT / "tests/fixtures/live_main.py.txt").read_text()


def login_source(source: str) -> str:
    start, end = dts._function(source, "async def login(")
    return source[start:end]


def test_login_hook_goes_right_before_the_tokens_and_once():
    patched = dts.hook_login(LIVE_AUTH)
    ast.parse(patched)
    login = login_source(patched)
    assert login.index("_two_step_login_hook(db, settings, request, user)") < login.index(
        "tokens = await issue_tokens("
    )
    assert login.index("verify_password_async") < login.index("_two_step_login_hook")  # password first
    assert dts.hook_login(patched) == patched
    assert patched.replace(dts.LOGIN_HOOK, "") == LIVE_AUTH  # nothing else changes


def test_main_hook_goes_before_create_app_returns():
    patched = dts.hook_main(LIVE_MAIN)
    ast.parse(patched)
    start, end = dts._function(patched, "def create_app(")
    body = patched[start:end]
    assert body.rstrip().endswith("return app") and "_install_two_step(app)" in body
    assert dts.hook_main(patched) == patched


def test_unexpected_login_code_is_refused():
    login = login_source(LIVE_AUTH)
    doubled = login.replace(
        "    tokens = await issue_tokens(", "    tokens = await issue_tokens(\n    tokens = await issue_tokens("
    )
    twice = LIVE_AUTH.replace(login, doubled)
    with pytest.raises(SystemExit, match="exactly once"):
        dts.hook_login(twice)
    renamed = LIVE_AUTH.replace(
        "async def login(body: LoginRequest, request: Request, db",
        "async def login(body: LoginRequest, req: Request, db",
    )
    with pytest.raises(SystemExit, match="`request`"):
        dts.hook_login(renamed)
    with pytest.raises(SystemExit, match="Expected one"):
        dts.hook_login("def other():\n    pass\n")


def test_the_package_ships_every_module():
    names = {p.name for p in dts.PACKAGE.glob("*.py")}
    assert {"__init__.py", "core.py", "models.py", "service.py", "routes.py"} <= names
