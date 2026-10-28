"""Voice assistant support: server-side speech-to-text (text-to-speech runs on the device)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, Request, UploadFile, status

from app.api.deps import CurrentUser, SettingsDep
from app.core import rate_limit
from app.schemas import TranscriptionOut
from app.services.stt import TranscriptionError

router = APIRouter(prefix="/voice", tags=["voice"])

AUDIO_TYPES = {"audio/mp4", "audio/m4a", "audio/x-m4a", "audio/aac", "audio/mpeg", "audio/wav", "audio/x-wav",
               "audio/webm", "audio/ogg", "audio/flac", "application/octet-stream"}  # fmt: skip


@router.post("/transcribe", response_model=TranscriptionOut)
async def transcribe(
    request: Request,
    user: CurrentUser,
    settings: SettingsDep,
    audio: UploadFile,
    language: Annotated[str | None, Form(max_length=10)] = None,
) -> TranscriptionOut:
    stt = request.app.state.stt
    if stt is None:
        raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "Speech-to-text is not configured on this server.")
    rate_limit.enforce(f"voice:{user.id}", settings.rate_limit_chat_per_minute)
    mime = (audio.content_type or "application/octet-stream").split(";")[0].lower()
    if mime not in AUDIO_TYPES:
        raise HTTPException(415, f"Unsupported audio type: {mime}")
    limit = settings.max_audio_mb * 1024 * 1024
    data = await audio.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(413, f"Recordings larger than {settings.max_audio_mb} MB are not accepted.")
    if not data:
        raise HTTPException(422, "The recording is empty.")
    try:
        text = await stt.transcribe(data, audio.filename or "speech.m4a", mime, language)
    except TranscriptionError:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Speech recognition failed. Please try again.") from None
    return TranscriptionOut(text=text)
