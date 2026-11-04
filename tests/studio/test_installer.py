import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("studio_installer", ROOT / "deploy/updaters/install_assistant_studio.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_installer_only_adds_hooks_and_preserves_custom_code():
    main = "def create_app():\n    app.include_router(web_routes.router)\n    return app\n"
    chat = "async def run_turn():\n    research = _Research()\n    custom_weather_question = 1\n"
    main, models, chat = module.patch_sources(main, "# existing models\n", chat)
    assert "_install_assistant_studio(app)" in main
    assert "ResponseFeedback" in models
    assert "custom_weather_question = 1" in chat
    assert chat.index("_run_pdf_excel") < chat.index("research = _Research()")
    with pytest.raises(ValueError, match="already installed"):
        module.patch_sources(main, models, chat)


def test_installer_refuses_unknown_chat_shape():
    with pytest.raises(ValueError):
        module.patch_sources(
            "def create_app():\n    app.include_router(web_routes.router)\n", "", "async def other(): pass"
        )
