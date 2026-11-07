import asyncio
import json
import shutil
import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.assistant_studio import media_engine as engine
from app.assistant_studio import media_studio as studio


@pytest.fixture
def settings(tmp_path):
    return SimpleNamespace(storage_dir=str(tmp_path))


@pytest.mark.asyncio
async def test_queue_idempotency_and_owner_download_boundaries(settings):
    owner, other = uuid.uuid4(), uuid.uuid4()
    edit = engine.Edit(mode="sound", effect="chime")
    key = "same_render_request_1234"
    first = await studio.enqueue(settings, owner, edit, key)
    again = await studio.enqueue(settings, owner, edit, key)
    assert first == again and first["status"] == "queued"
    assert len(studio.jobs(settings, owner)) == 1
    assert studio.jobs(settings, other) == []
    with pytest.raises(HTTPException) as denied:
        await studio.download(uuid.UUID(first["id"]), SimpleNamespace(id=other), settings)
    assert denied.value.status_code == 404
    with pytest.raises(HTTPException) as conflict:
        await studio.enqueue(settings, owner, engine.Edit(mode="sound", effect="beep"), key)
    assert conflict.value.status_code == 409
    with pytest.raises(HTTPException) as pending:
        await studio.download(uuid.UUID(first["id"]), SimpleNamespace(id=owner), settings)
    assert pending.value.status_code == 409


@pytest.mark.asyncio
async def test_worker_keeps_exports_across_navigation_and_restart_marks_orphans(settings, monkeypatch):
    owner = uuid.uuid4()
    job = await studio.enqueue(settings, owner, engine.Edit(mode="sound", effect="beep"), "worker_test_request_1234")

    async def render(folder, edit):
        result = folder / "Sound_effect.wav"
        result.write_bytes(b"fake-output")
        return result

    monkeypatch.setattr(studio, "render", render)
    worker = asyncio.create_task(studio.worker(settings))
    for _ in range(30):
        await asyncio.sleep(0.02)
        if studio.jobs(settings, owner)[0]["status"] == "complete":
            break
    worker.cancel()
    with pytest.raises(asyncio.CancelledError):
        await worker
    folder, manifest = studio.owned(settings, owner, job["id"])
    assert manifest["status"] == "complete"
    response = await studio.download(uuid.UUID(job["id"]), SimpleNamespace(id=owner), settings)
    assert response.filename == "Sound_effect.wav"
    assert "no-store" in response.headers["cache-control"]
    manifest["status"] = "running"
    studio.write(folder, manifest)
    worker = asyncio.create_task(studio.worker(settings))
    await asyncio.sleep(0.05)
    worker.cancel()
    with pytest.raises(asyncio.CancelledError):
        await worker
    assert studio.read(folder)["status"] == "failed"
    await studio.delete(uuid.UUID(job["id"]), SimpleNamespace(id=owner), settings)
    assert not folder.exists()


@pytest.mark.parametrize(
    "options",
    [
        {"mode": "sound", "effect": "none"},
        {"mode": "narration"},
        {"duration": float("nan")},
        {"voice": "../../etc/passwd"},
        {"effect": "sine;movie=/etc/passwd"},
        {"duration": 61},
        {"command": "anything"},
    ],
)
def test_media_settings_are_bounded_and_reject_command_or_filter_injection(options):
    with pytest.raises(ValidationError):
        engine.Edit.model_validate(options)


@pytest.mark.asyncio
async def test_actual_ffmpeg_trim_mix_and_sound(tmp_path):
    if not shutil.which("ffmpeg"):
        pytest.skip("FFmpeg is required for this integration test")
    await engine.command(
        "ffmpeg",
        "-v",
        "error",
        "-y",
        "-f",
        "lavfi",
        "-i",
        "color=c=blue:s=320x240:r=12:d=3",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=440:duration=3",
        "-c:v",
        "libx264",
        "-threads",
        "1",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        str(tmp_path / "source.mp4"),
    )
    (tmp_path / "source.mp4").rename(tmp_path / "video.input")
    original = (tmp_path / "video.input").read_bytes()
    result = await engine.render(tmp_path, engine.Edit(start=0.5, duration=2, effect="chime", original_volume=0.5))
    info, duration = await engine.probe(result)
    assert abs(duration - 2) < 0.2
    assert {s["codec_type"] for s in info["streams"]} == {"video", "audio"}
    assert (tmp_path / "video.input").read_bytes() == original
    result = await engine.render(tmp_path, engine.Edit(mode="sound", effect="beep", duration=2))
    assert result.name == "Sound_effect.wav"
    assert abs((await engine.probe(result))[1] - 2) < 0.2
    with pytest.raises(ValueError):
        await engine.render(tmp_path, engine.Edit(start=2.5, duration=2))


@pytest.mark.asyncio
async def test_ffmpeg_rejects_playlist_and_remote_protocol(tmp_path):
    playlist = tmp_path / "audio.input"
    playlist.write_text("#EXTM3U\nhttp://127.0.0.1/private\n")
    with pytest.raises(ValueError):
        await engine.probe(playlist)


@pytest.mark.asyncio
async def test_actual_espeak_narration_and_video_mix(tmp_path):
    if not shutil.which("espeak-ng"):
        pytest.skip("eSpeak NG is required for this integration test")
    script = "Hello. This is Dhanz."
    result = await engine.render(tmp_path, engine.Edit(mode="narration", narration=script))
    assert result.name == "Narration.wav" and (await engine.probe(result))[1] > 0
    await engine.command(
        "ffmpeg",
        "-v",
        "error",
        "-y",
        "-f",
        "lavfi",
        "-i",
        "color=c=red:s=160x120:d=6",
        "-c:v",
        "libx264",
        "-threads",
        "1",
        str(tmp_path / "source.mp4"),
    )  # noqa: E501 - bounded fixed schema/filter or installer metadata
    (tmp_path / "source.mp4").rename(tmp_path / "video.input")
    result = await engine.render(tmp_path, engine.Edit(duration=6, narration=script, original_volume=0))
    info, _ = await engine.probe(result)
    assert any(s["codec_type"] == "audio" for s in info["streams"])


def test_installer_preserves_bootstrap_and_frozen_payloads():
    import ast
    import base64
    import gzip
    import runpy
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    backend = runpy.run_path(str(root / "deploy/updaters/install_media_backend.py"))
    for name, source in backend["payload"]().items():
        assert source == (root / "server_extensions/assistant_studio" / name).read_text()
    original = "def install(app):\n    existing_custom_feature(app)\n    _install_connected_operations(app)\n"
    patched = backend["patch_bootstrap"](original)
    assert "existing_custom_feature(app)" in patched
    assert backend["patch_bootstrap"](patched) == patched
    assert patched.count("    _install_media_studio(app)") == 1
    assert "COPY --chmod=0755" in backend["image_dockerfile"](
        "before", "/srv/backend/app/assistant_studio/bootstrap.py", backend["MODULES"]
    )
    tree = ast.parse((root / "deploy/updaters/install_media_backend.py").read_text())
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and "from app.main import create_app" in node.value
        ):
            compile(node.value, "<startup-check>", "exec")
    combined = runpy.run_path(str(root / "deploy/updaters/install_media_studio.py"))
    files = json.loads(gzip.decompress(base64.b64decode(combined["PAYLOAD"])))
    assert files["install_media_backend.py"] == (root / "deploy/updaters/install_media_backend.py").read_text()
