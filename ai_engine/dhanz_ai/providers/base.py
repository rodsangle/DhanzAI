"""Provider interface and shared HTTP/SSE helpers."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Sequence

import httpx

from dhanz_ai.types import ChatMessage, GenerationParams, ModelInfo, ProviderError, StreamChunk, ToolSpec

# Cloud providers wait this long for the next byte. Ollama's own default is longer.
CLOUD_READ_TIMEOUT_SECONDS = 120.0
OLLAMA_READ_TIMEOUT_SECONDS = 300.0


def http_timeout(read_seconds: float) -> httpx.Timeout:
    return httpx.Timeout(connect=10.0, read=read_seconds, write=30.0, pool=10.0)


DEFAULT_TIMEOUT = http_timeout(CLOUD_READ_TIMEOUT_SECONDS)


class Provider(ABC):
    """A chat-completion backend. Implementations must stream deltas."""

    name: str

    def __init__(self, client: httpx.AsyncClient | None = None, *, read_timeout: float = CLOUD_READ_TIMEOUT_SECONDS):
        # A client may be injected (tests use httpx.MockTransport).
        self._client = client or httpx.AsyncClient(timeout=http_timeout(read_timeout))

    @abstractmethod
    def models(self) -> list[ModelInfo]:
        """Models this provider exposes to users."""

    @abstractmethod
    def is_configured(self) -> bool:
        """True when credentials/endpoint are present so the provider can be used."""

    @abstractmethod
    def stream(
        self,
        model: str,
        messages: Sequence[ChatMessage],
        params: GenerationParams,
        tools: Sequence[ToolSpec] = (),
    ) -> AsyncIterator[StreamChunk]:
        """Yield text deltas; the final chunk has done=True.

        When `tools` are given and the model decides to call some, one chunk carries `tool_calls`
        (before the final chunk). Only pass tools to models with Capability.TOOLS.
        """

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _raise_for_status(self, response: httpx.Response) -> None:
        if response.status_code < 400:
            return
        body = (await response.aread()).decode("utf-8", errors="replace")[:500]
        retryable = response.status_code in (408, 409, 429) or response.status_code >= 500
        raise ProviderError(
            self.name,
            f"HTTP {response.status_code}: {body}",
            status_code=response.status_code,
            retryable=retryable,
        )


async def iter_sse_data(response: httpx.Response) -> AsyncIterator[tuple[str | None, str]]:
    """Yield (event, data) pairs from a text/event-stream response."""
    event: str | None = None
    data_lines: list[str] = []
    async for line in response.aiter_lines():
        if line == "":
            if data_lines:
                yield event, "\n".join(data_lines)
            event, data_lines = None, []
            continue
        if line.startswith(":"):
            continue
        field, _, value = line.partition(":")
        value = value[1:] if value.startswith(" ") else value
        if field == "event":
            event = value
        elif field == "data":
            data_lines.append(value)
    if data_lines:
        yield event, "\n".join(data_lines)


def parse_json(provider: str, raw: str) -> dict:
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ProviderError(provider, f"Malformed stream payload: {raw[:200]}", retryable=False) from exc


def tool_arguments(provider: str, raw: str | dict | None) -> dict:
    """Arguments of a tool call, which providers send as a JSON string or an object."""
    if raw is None or raw == "":
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        # Let the tool report the problem to the model instead of failing the whole reply.
        return {"_invalid_arguments": raw[:500]}
    return value if isinstance(value, dict) else {"_invalid_arguments": raw[:500]}
