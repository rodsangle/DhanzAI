import json
import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.assistant_studio import media_engine as engine
from app.assistant_studio import reference_video as reference


@pytest.mark.asyncio
async def test_actual_video_sampling_preserves_order_and_discards_source(tmp_path):
    await engine.command(
        "ffmpeg",
        "-v",
        "error",
        "-y",
        "-f",
        "lavfi",
        "-i",
        "testsrc=size=160x120:rate=10:duration=2",
        "-c:v",
        "libx264",
        "-threads",
        "1",
        "-pix_fmt",
        "yuv420p",
        str(tmp_path / "clip.mp4"),
    )
    content = (tmp_path / "clip.mp4").read_bytes()
    length, times = await reference.frames(tmp_path, content)
    assert abs(length - 2) < 0.2 and times == sorted(times) and times[0] == 0
    assert not (tmp_path / "source.input").exists()
    assert all((tmp_path / f"frame-{i}.png").read_bytes().startswith(b"\x89PNG") for i in range(4))
    assert (tmp_path / "frame-0.png").read_bytes() != (tmp_path / "frame-3.png").read_bytes()


@pytest.mark.asyncio
async def test_owned_analysis_cached_and_explicit_retry_required(tmp_path, monkeypatch):
    settings = SimpleNamespace(storage_dir=str(tmp_path))
    user = SimpleNamespace(id=uuid.uuid4(), routing_policy="cloud_allowed")
    identifier, document_id = uuid.uuid4(), uuid.uuid4()
    folder = reference.root(settings) / str(identifier)
    folder.mkdir()
    reference.save(
        folder,
        {
            "id": str(identifier),
            "owner": str(user.id),
            "created": reference.time.time(),
            "reference_id": str(document_id),
            "analysis_started": False,
            "brief": None,
        },
    )

    class DB:
        async def get(self, model, key):
            return SimpleNamespace(user_id=user.id)

    calls = []

    async def fail(*args):
        calls.append("attempt")
        raise HTTPException(502, "Failed")

    monkeypatch.setattr(reference, "describe", fail)
    with pytest.raises(HTTPException):
        await reference.analyze(identifier, reference.Analysis(), user, DB(), settings)
    with pytest.raises(HTTPException) as repeated:
        await reference.analyze(identifier, reference.Analysis(), user, DB(), settings)
    assert repeated.value.status_code == 409 and len(calls) == 1

    async def succeed(*args):
        calls.append("retry")
        return "A blue scene with a slow camera pan."

    monkeypatch.setattr(reference, "describe", succeed)
    result = await reference.analyze(identifier, reference.Analysis(retry=True), user, DB(), settings)
    assert "slow camera" in result["brief"]
    assert (await reference.analyze(identifier, reference.Analysis(), user, DB(), settings))["cached"]
    assert calls == ["attempt", "retry"]
    with pytest.raises(HTTPException) as denied:
        reference.owned(settings, uuid.uuid4(), identifier)
    assert denied.value.status_code == 404
    user.routing_policy = "local_only"
    with pytest.raises(HTTPException) as local:
        await reference.analyze(identifier, reference.Analysis(), user, DB(), settings)
    assert local.value.status_code == 403


def test_installer_payload_and_existing_hook_preserved():
    import base64
    import gzip
    import runpy
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    updater = runpy.run_path(str(root / "deploy/updaters/install_reference_backend.py"))
    assert (
        updater["payload"]()["module"] == (root / "server_extensions/assistant_studio/reference_video.py").read_text()
    )
    source = "def install(app):\n    _install_media_studio(app)\n    _install_autonomy(app)\n"
    updated = updater["patch_bootstrap"](source)
    assert "_install_autonomy(app)" in updated and updated.count("    _install_reference_video(app)") == 1
    assert updater["patch_bootstrap"](updated) == updated
    combined = runpy.run_path(str(root / "deploy/updaters/install_reference_video.py"))
    packet = json.loads(gzip.decompress(base64.b64decode(combined["PAYLOAD"])))
    assert packet["install_reference_backend.py"] == (root / "deploy/updaters/install_reference_backend.py").read_text()


@pytest.mark.asyncio
async def test_vision_request_uses_four_frames_and_configured_official_endpoint(tmp_path, monkeypatch):
    import httpx

    for i in range(4):
        (tmp_path / f"frame-{i}.png").write_bytes(b"fake-png-for-mocked-provider")
    settings = SimpleNamespace(
        openai_api_key="test-only-key",
        openai_base_url="https://api.openai.com/v1",
        openai_models="gpt-4.1-mini,gpt-4.1",
    )
    received = []

    def respond(request):
        received.append(request)
        payload = json.loads(request.content)
        parts = payload["messages"][0]["content"]
        assert len([part for part in parts if part["type"] == "image_url"]) == 4
        assert "inferred motion" in parts[0]["text"]
        return httpx.Response(
            200, json={"choices": [{"message": {"content": "A steady opening shot, followed by a gentle pan."}}]}
        )

    original = httpx.AsyncClient
    monkeypatch.setattr(
        reference.httpx, "AsyncClient", lambda **kwargs: original(transport=httpx.MockTransport(respond), **kwargs)
    )
    brief = await reference.describe(settings, tmp_path, {"duration": 2, "timestamps": [0, 0.6, 1.2, 1.8]})
    assert "gentle pan" in brief and len(received) == 1
    assert str(received[0].url) == "https://api.openai.com/v1/chat/completions"
    settings.openai_base_url = "https://other.example/v1"
    with pytest.raises(HTTPException) as unavailable:
        await reference.describe(settings, tmp_path, {"duration": 2, "timestamps": []})
    assert unavailable.value.status_code == 503 and len(received) == 1


def test_expired_frames_are_purged_without_waiting_for_another_upload(tmp_path):
    settings = SimpleNamespace(storage_dir=str(tmp_path))
    base = reference.root(settings)
    folder = base / str(uuid.uuid4())
    folder.mkdir()
    reference.save(folder, {"owner": str(uuid.uuid4()), "created": reference.time.time() - reference.RETENTION - 10})
    (folder / "frame-0.png").write_bytes(b"expired")
    reference.prune_locked(base)
    assert not folder.exists()
