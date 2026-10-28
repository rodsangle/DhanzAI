"""Anthropic Claude Messages API provider."""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence

import httpx

from dhanz_ai.providers.base import Provider, iter_sse_data, parse_json
from dhanz_ai.types import (
    Capability,
    ChatMessage,
    CostTier,
    GenerationParams,
    ModelInfo,
    ProviderError,
    StreamChunk,
)

ANTHROPIC_VERSION = "2023-06-01"


class AnthropicProvider(Provider):
    name = "anthropic"

    def __init__(
        self,
        api_key: str | None,
        models: Sequence[str],
        base_url: str = "https://api.anthropic.com/v1",
        client: httpx.AsyncClient | None = None,
    ):
        super().__init__(client)
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self._models = list(models)

    def is_configured(self) -> bool:
        return bool(self.api_key) and bool(self._models)

    def models(self) -> list[ModelInfo]:
        infos = []
        for m in self._models:
            caps = {Capability.CHAT, Capability.CODE, Capability.VISION, Capability.LONG_CONTEXT}
            if "haiku" in m:
                tier = CostTier.LOW
            elif "opus" in m:
                tier = CostTier.HIGH
                caps.add(Capability.REASONING)
            else:
                tier = CostTier.MEDIUM
                caps.add(Capability.REASONING)
            infos.append(ModelInfo(self.name, m, m, frozenset(caps), tier, context_window=200_000))
        return infos

    async def stream(
        self, model: str, messages: Sequence[ChatMessage], params: GenerationParams
    ) -> AsyncIterator[StreamChunk]:
        # Claude takes the system prompt as a top-level field, not as a message.
        system = "\n\n".join(m.content for m in messages if m.role == "system")
        payload: dict = {
            "model": model,
            "max_tokens": params.max_tokens,
            "temperature": params.temperature,
            "stream": True,
            "messages": [_to_anthropic(m) for m in messages if m.role != "system"],
        }
        if system:
            payload["system"] = system
        headers = {"x-api-key": self.api_key or "", "anthropic-version": ANTHROPIC_VERSION}
        input_tokens = output_tokens = None
        try:
            async with self._client.stream(
                "POST", f"{self.base_url}/messages", json=payload, headers=headers
            ) as response:
                await self._raise_for_status(response)
                async for event, data in iter_sse_data(response):
                    obj = parse_json(self.name, data)
                    kind = obj.get("type", event)
                    if kind == "message_start":
                        usage = (obj.get("message") or {}).get("usage") or {}
                        input_tokens = usage.get("input_tokens")
                    elif kind == "content_block_delta":
                        delta = obj.get("delta") or {}
                        if delta.get("type") == "text_delta" and delta.get("text"):
                            yield StreamChunk(text=delta["text"])
                    elif kind == "message_delta":
                        output_tokens = (obj.get("usage") or {}).get("output_tokens", output_tokens)
                    elif kind == "error":
                        err = obj.get("error") or {}
                        retryable = err.get("type") in ("overloaded_error", "api_error", "rate_limit_error")
                        raise ProviderError(self.name, err.get("message", "stream error"), retryable=retryable)
                    elif kind == "message_stop":
                        break
        except httpx.HTTPError as exc:
            raise ProviderError(self.name, f"Network error: {exc}") from exc
        yield StreamChunk(done=True, input_tokens=input_tokens, output_tokens=output_tokens)


def _to_anthropic(m: ChatMessage) -> dict:
    if not m.images:
        return {"role": m.role, "content": m.content}
    parts: list[dict] = [
        {"type": "image", "source": {"type": "base64", "media_type": img.mime_type, "data": img.data_b64}}
        for img in m.images
    ]
    parts.append({"type": "text", "text": m.content})
    return {"role": m.role, "content": parts}
