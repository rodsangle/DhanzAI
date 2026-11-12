import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "enable_pdf_ocr", Path(__file__).resolve().parents[1] / "deploy/updaters/enable_pdf_ocr.py"
)
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)


def setup_docker(monkeypatch, tmp_path, *, tools=True, enabled=False):
    files = [tmp_path / name for name in ["prod.yml", "web.yml", "custom.yml"]]
    for path in files:
        path.write_text("DO_NOT_PRINT_PRIVATE_CONFIGURATION")
    metadata = {
        "image": "sha256:" + "a" * 64,
        "files": ",".join(str(p) for p in files),
        "directory": str(tmp_path),
        "project": "deploy",
        "service": "api",
    }
    calls = []
    applied = False

    def docker(*args, directory=None):
        nonlocal applied
        calls.append(args)
        if args[0] == "exec":
            return json.dumps({"supported": True, "enabled": enabled or applied, "tesseract": tools, "poppler": tools})
        if args[0] == "inspect":
            return "healthy" if args[-1] != helper._METADATA else json.dumps(metadata)
        if args[0] == "compose" and "up" in args:
            applied = True
        return ""

    monkeypatch.setattr(helper, "docker", docker)
    return calls, files


def test_prepare_preserves_all_overlays_and_never_recreates_api(monkeypatch, tmp_path, capsys):
    calls, files = setup_docker(monkeypatch, tmp_path)
    helper.enable()
    overlay = tmp_path / "docker-compose.ocr.json"
    config = json.loads(overlay.read_text())
    assert config["services"] == {
        "api": {"image": "dhanz-api:ocr-base-" + "a" * 16, "environment": {"OCR_ENABLED": "true"}}
    }
    assert not any("up" in args for args in calls)
    config_call = next(args for args in calls if args[0] == "compose")
    assert all(str(path) in config_call for path in files + [overlay])
    assert "DO_NOT_PRINT_PRIVATE_CONFIGURATION" not in capsys.readouterr().out


def test_apply_pins_current_image_and_recreates_only_api(monkeypatch, tmp_path):
    calls, files = setup_docker(monkeypatch, tmp_path)
    helper.enable(apply=True)
    assert ("tag", "sha256:" + "a" * 64, "dhanz-api:ocr-base-" + "a" * 16) in calls
    up = next(args for args in calls if args[0] == "compose" and "up" in args)
    assert up[up.index("up") :] == ("up", "-d", "--no-deps", "--no-build", "--pull", "never", "--force-recreate", "api")
    assert all(str(path) in up for path in files)
    assert up[-1] == "api" and "db" not in up and "redis" not in up


def test_missing_tools_cannot_mutate_configuration(monkeypatch, tmp_path):
    calls, _ = setup_docker(monkeypatch, tmp_path, tools=False)
    with pytest.raises(ValueError, match="Nothing was changed"):
        helper.enable(apply=True)
    assert len(calls) == 1
    assert not (tmp_path / "docker-compose.ocr.json").exists()


def test_already_enabled_does_not_recreate_api(monkeypatch, tmp_path, capsys):
    calls, _ = setup_docker(monkeypatch, tmp_path, enabled=True)
    helper.enable(apply=True)
    assert len(calls) == 1
    assert "Upload the PDF again" in capsys.readouterr().out


def test_unrelated_overlay_is_never_overwritten(monkeypatch, tmp_path):
    calls, _ = setup_docker(monkeypatch, tmp_path)
    overlay = tmp_path / "docker-compose.ocr.json"
    overlay.write_text('{"services":{"api":{"environment":{"CUSTOM":"keep"}}}}')
    with pytest.raises(ValueError, match="left unchanged"):
        helper.enable(apply=True)
    assert json.loads(overlay.read_text())["services"]["api"]["environment"]["CUSTOM"] == "keep"
    assert not any(args[0] == "tag" or "up" in args for args in calls)
