"""Speech-to-text through an OpenAI-compatible /audio/transcriptions endpoint."""

from __future__ import annotations

import httpx

from app.core.config import Settings


class TranscriptionError(Exception):
    pass


class SpeechToText:
    def __init__(self, base_url: str, api_key: str | None, model: str, client: httpx.AsyncClient | None = None):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self._client = client or httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0))

    async def transcribe(self, audio: bytes, filename: str, mime_type: str, language: str | None = None) -> str:
        data = {"model": self.model, "response_format": "json"}
        if language:
            data["language"] = language
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        try:
            r = await self._client.post(
                f"{self.base_url}/audio/transcriptions",
                data=data,
                files={"file": (filename, audio, mime_type)},
                headers=headers,
            )
        except httpx.HTTPError as exc:
            raise TranscriptionError(f"network error ({type(exc).__name__})") from exc
        if r.status_code >= 400:
            raise TranscriptionError(f"HTTP {r.status_code}: {r.text[:200]}")
        return (r.json().get("text") or "").strip()

    async def aclose(self) -> None:
        await self._client.aclose()


def build_stt(settings: Settings) -> SpeechToText | None:
    if settings.stt_provider != "openai":
        return None
    api_key = settings.stt_api_key or settings.openai_api_key
    base_url = settings.stt_base_url or settings.openai_base_url
    if not api_key and not settings.stt_base_url:
        return None  # the OpenAI cloud endpoint needs a key; self-hosted Whisper servers may not
    return SpeechToText(base_url, api_key, settings.stt_model)
