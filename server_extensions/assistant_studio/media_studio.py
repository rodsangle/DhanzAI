"""Private durable local render queue; one CPU renderer across API processes."""

import asyncio
import contextlib
import fcntl
import hashlib
import json
import shutil
import tempfile
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import ValidationError

from app.api.deps import CurrentUser, SettingsDep

from .media_engine import Edit, render

router = APIRouter(prefix="/media-studio", tags=["media-studio"])
LIMIT = 100 * 1024 * 1024
RETENTION = 7 * 86400


def root(settings):
    path = Path(settings.storage_dir) / "media-studio"
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    return path


def write(folder, data):
    temp = folder / ("manifest-" + uuid.uuid4().hex + ".tmp")
    temp.write_text(json.dumps(data))
    temp.replace(folder / "manifest.json")


def read(folder):
    return json.loads((folder / "manifest.json").read_text())


def public(data):
    return {key: data.get(key) for key in ("id", "status", "mode", "created", "filename", "error", "source_name")}


def owned(settings, user_id, identifier):
    folder = root(settings) / str(uuid.UUID(str(identifier)))
    try:
        data = read(folder)
    except (FileNotFoundError, ValueError):
        raise HTTPException(404, "Media job not found.") from None
    if data["owner"] != str(user_id):
        raise HTTPException(404, "Media job not found.")
    return folder, data


def jobs(settings, user_id):
    entries = []
    for path in root(settings).glob("????????-????-????-????-????????????/manifest.json"):
        try:
            data = read(path.parent)
            if data["owner"] == str(user_id):
                entries.append(public(data))
        except (OSError, ValueError):
            continue
    return sorted(entries, key=lambda d: d["created"], reverse=True)[:30]


@contextlib.contextmanager
def lock(path, *, blocking=True):
    with path.open("a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
        except BlockingIOError:
            yield False
            return
        try:
            yield True
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


async def enqueue(settings, user_id, edit, key, video=None, audio=None):
    if (
        not isinstance(key, str)
        or not 16 <= len(key) <= 80
        or not all(c.isascii() and (c.isalnum() or c in "_-") for c in key)
    ):
        raise HTTPException(422, "Use a unique request key of 16–80 letters, digits, underscores or hyphens.")
    for upload in (video, audio):
        if upload and (not upload[1] or len(upload[1]) > LIMIT):
            raise HTTPException(413, "Each media file must be nonempty and at most 100 MB.")
    if edit.mode == "video" and video is None:
        raise HTTPException(422, "Upload a video to edit.")
    fingerprint = hashlib.sha256(edit.model_dump_json().encode())
    for upload in (video, audio):
        fingerprint.update(upload[1] if upload else b"")
    digest = fingerprint.hexdigest()
    identifier = str(uuid.uuid5(uuid.NAMESPACE_URL, f"dhanz-media:{user_id}:{key}"))
    base = root(settings)
    folder = base / identifier
    with lock(base / "queue.lock"):
        if folder.exists():
            previous = read(folder)
            if previous["fingerprint"] != digest:
                raise HTTPException(409, "This request key was used for different media settings.")
            return public(previous)
        entries = jobs(settings, user_id)
        if sum(d["status"] in ("queued", "running") for d in entries) >= 3 or len(entries) >= 30:
            raise HTTPException(429, "Finish queued jobs or delete old media jobs before adding more.")
        incoming = sum(len(upload[1]) for upload in (video, audio) if upload)
        if shutil.disk_usage(base).free < incoming + 1024 * 1024 * 1024:
            raise HTTPException(507, "Media storage is low. Delete old exports before adding more.")
        active = sum(
            read(path.parent)["status"] in ("queued", "running")
            for path in base.glob("????????-????-????-????-????????????/manifest.json")
        )
        if active >= 10:
            raise HTTPException(429, "The local render queue is full. Wait for exports to finish.")
        stage = Path(tempfile.mkdtemp(prefix="stage-", dir=base))
        stage.chmod(0o700)
        try:
            for name, upload in (("video.input", video), ("audio.input", audio)):
                if upload:
                    (stage / name).write_bytes(upload[1])
            data = {
                "id": identifier,
                "owner": str(user_id),
                "fingerprint": digest,
                "settings": edit.model_dump(),
                "mode": edit.mode,
                "status": "queued",
                "created": time.time(),
                "filename": None,
                "error": None,
                "source_name": Path(video[0]).name[:150] if video else "",
            }
            write(stage, data)
            stage.rename(folder)
        finally:
            if stage.exists():
                shutil.rmtree(stage)
    return public(data)


@router.get("/jobs")
async def listing(user: CurrentUser, settings: SettingsDep):
    return {
        "jobs": jobs(settings, user.id),
        "retention_days": 7,
        "local_rendering": True,
        "narration_engine": "eSpeak NG (synthetic voice, no API key)",
    }


@router.post("/jobs", status_code=202)
async def create(
    user: CurrentUser,
    settings: SettingsDep,
    options: str = Form(max_length=12000),
    request_key: str = Form(min_length=16, max_length=80),
    video: UploadFile | None = File(default=None),
    audio: UploadFile | None = File(default=None),
):
    try:
        edit = Edit.model_validate_json(options)
    except ValidationError:
        raise HTTPException(422, "Invalid media settings. Check duration, volumes and narration text.") from None

    async def take(upload):
        if upload is None:
            return None
        data = await upload.read(LIMIT + 1)
        if len(data) > LIMIT:
            raise HTTPException(413, "Each media file must be at most 100 MB.")
        if settings.clamav_host:
            from app.services.scanner import ClamAVScanner, MalwareFound, ScanError

            try:
                await ClamAVScanner(settings.clamav_host, settings.clamav_port).scan(data)
            except (MalwareFound, ScanError):
                raise HTTPException(422, "The file did not pass the configured malware scan.") from None
        return (upload.filename or "upload", data)

    return await enqueue(settings, user.id, edit, request_key, await take(video), await take(audio))


@router.get("/jobs/{identifier}/download")
async def download(identifier: uuid.UUID, user: CurrentUser, settings: SettingsDep):
    folder, data = owned(settings, user.id, identifier)
    if data["status"] != "complete":
        raise HTTPException(409, "The media export is not complete.")
    name = data["filename"]
    if name not in ("Edited_video.mp4", "Narration.wav", "Sound_effect.wav") or not (folder / name).is_file():
        raise HTTPException(404, "Export unavailable.")
    return FileResponse(
        folder / name,
        filename=name,
        media_type="video/mp4" if name.endswith("mp4") else "audio/wav",
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
    )


@router.delete("/jobs/{identifier}")
async def delete(identifier: uuid.UUID, user: CurrentUser, settings: SettingsDep):
    base = root(settings)
    # The renderer holds this lock throughout a job. Never remove its files mid-render.
    with lock(base / "renderer.lock", blocking=False) as acquired:
        if not acquired:
            raise HTTPException(409, "A render is active. Try deleting after it finishes.")
        with lock(base / "queue.lock"):
            folder, _ = owned(settings, user.id, identifier)
            shutil.rmtree(folder)
    return {"deleted": True}


async def worker(settings):
    base = root(settings)
    while True:
        with lock(base / "renderer.lock", blocking=False) as acquired:
            if acquired:
                for manifest in sorted(
                    base.glob("????????-????-????-????-????????????/manifest.json"), key=lambda p: p.stat().st_mtime
                ):  # noqa: E501 - bounded fixed schema/filter or installer metadata
                    folder = manifest.parent
                    data = read(folder)
                    if data["created"] < time.time() - RETENTION:
                        shutil.rmtree(folder)
                        continue
                    if data["status"] == "running":
                        data.update(status="failed", error="Render interrupted by server restart. Create a new export.")
                        write(folder, data)
                    if data["status"] != "queued":
                        continue
                    data["status"] = "running"
                    write(folder, data)
                    try:
                        output = await render(folder, Edit.model_validate(data["settings"]))
                        data.update(status="complete", filename=output.name)
                    except asyncio.CancelledError:
                        data.update(status="failed", error="Render interrupted. Create a new export.")
                        write(folder, data)
                        raise
                    except (ValueError, OSError, TimeoutError):
                        # Decoder diagnostics may contain private metadata. Keep them out of receipts/logs.
                        data.update(
                            status="failed",
                            error="Could not render. Check the clip length and audio, shorten narration, or try MP4/WAV inputs.",  # noqa: E501 - bounded fixed schema/filter or installer metadata
                        )
                    write(folder, data)
                    break
        await asyncio.sleep(1)


def install_tools():
    from app.services import assistant_tools as tools
    from dhanz_ai import ToolSpec

    async def run(ctx, args):
        try:
            if ctx.settings is None:
                raise ValueError("Media storage is unavailable.")
            operation = args.get("operation", "list")
            if operation == "list":
                return tools.ToolOutcome({"jobs": jobs(ctx.settings, ctx.user_id)}, "Listed local media exports")
            if operation == "status":
                _, data = owned(ctx.settings, ctx.user_id, args.get("job_id"))
                return tools.ToolOutcome(public(data), "Checked local media export")
            if operation != "create" or args.get("mode") not in ("narration", "sound"):
                raise ValueError(
                    "Use the Media editor for video uploads, trim and soundtrack mixing. "
                    "This chat tool creates narration or sound effects."
                )
            edit = Edit.model_validate(
                {k: v for k, v in args.items() if k not in ("operation", "request_key", "job_id")}
            )
            result = await enqueue(ctx.settings, ctx.user_id, edit, args.get("request_key"))
            return tools.ToolOutcome(
                {
                    **result,
                    "open": "/media-editor",
                    "note": "Queued, not yet complete. Download in Media editor after completion.",
                },
                "Queued local audio export",
            )
        except (ValueError, HTTPException) as exc:
            raise tools.ToolInputError(exc.detail if isinstance(exc, HTTPException) else str(exc)) from None

    schema = Edit.model_json_schema()
    properties = {
        k: v for k, v in schema["properties"].items() if k not in ("start", "original_volume", "music_volume")
    }
    properties.update(
        operation={"type": "string", "enum": ["list", "status", "create"]},
        job_id={"type": "string"},
        request_key={"type": "string", "minLength": 16, "maxLength": 80},
    )
    tools.TOOLS["local_media"] = tools.Tool(
        ToolSpec(
            "local_media",
            "Create downloadable synthetic narration or simple chime/beep/tone WAV files locally without API credits; list/check owned exports. Video trimming and mixing are available in the Media editor sidebar. Never claim completion until status is complete. Supply a unique 16–80 character request_key for create. Generated audio is eSpeak NG/synth tones, not natural AI music or a cloned voice.",  # noqa: E501 - bounded fixed schema/filter or installer metadata
            {"type": "object", "properties": properties, "required": ["operation"]},
        ),
        "Local media",
        run,
    )


def install(app):
    if getattr(app.state, "_local_media_installed", False):
        return
    app.state._local_media_installed = True
    app.include_router(router, prefix=app.state.settings.api_prefix)
    install_tools()
    original = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(application):
        async with original(application):
            task = asyncio.create_task(worker(application.state.settings))
            try:
                yield
            finally:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task

    app.router.lifespan_context = lifespan
