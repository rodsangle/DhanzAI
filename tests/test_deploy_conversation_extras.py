"""scripts/server/deploy_conversation_extras.py: hooks go in the right place and only once."""

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/server"))
spec = importlib.util.spec_from_file_location(
    "deploy_conversation_extras", ROOT / "scripts/server/deploy_conversation_extras.py"
)
dce = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dce)

LIVE_STYLE = """def create_app(settings=None):
    app = FastAPI()
    app.include_router(web_routes.router)
    if settings is None:
        return app
    return app


def helper():
    return 1


app = create_app()
"""


def test_main_hook_goes_before_create_apps_final_return_once():
    out = dce.hook_main(LIVE_STYLE)
    body = out.split("def helper")[0]
    assert body.rstrip().endswith("_install_conversation_extras(app)\n    return app".rstrip())
    assert body.count("_install_conversation_extras(app)") == 1
    assert "        return app" in body  # the early return is left alone
    assert dce.hook_main(out) == out  # running again changes nothing


def test_main_without_create_app_or_return_is_refused():
    with pytest.raises(SystemExit, match="no create_app"):
        dce.hook_main("app = FastAPI()\n")
    with pytest.raises(SystemExit, match="no final `return app`"):
        dce.hook_main("def create_app():\n    pass\n\n\nx = 1\n")


def test_models_hook_is_appended_once():
    out = dce.hook_models("from app.db.base import Base\n")
    assert out.endswith("ConversationArchive, SharedConversation  # noqa: E402,F401\n")
    assert dce.hook_models(out) == out


def test_repository_main_already_installs_the_package():
    main = (ROOT / "backend/app/main.py").read_text()
    assert "install_conversation_extras(app)" in main
