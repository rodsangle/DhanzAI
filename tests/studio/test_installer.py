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


def test_frozen_builder_protocol_payload_matches_reviewed_source_and_rejects_unknown_versions():
    spec = importlib.util.spec_from_file_location(
        "builder_protocol_installer", ROOT / "deploy/updaters/install_builder_protocol.py"
    )
    installer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(installer)
    import hashlib

    assert (
        hashlib.sha256(installer.source().encode()).hexdigest()
        == "31ec2687edf2e6e0d334878b580636f6adedce0b64fdf389359933dd2794c9bc"
    )
    assert installer.supported(installer.source()) is False
    with pytest.raises(ValueError, match="differs"):
        installer.supported("unrecognized builder implementation")
