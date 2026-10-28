"""Ollama provider for locally hosted models."""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence

import httpx

from dhanz_ai.providers.base import Provider, parse_json
from dhanz_ai.types import (
    Capability,
    ChatMessage,
    CostTier,
    GenerationParams,
    ModelInfo,
    ProviderError,
    StreamChunk,
)


class OllamaProvider(Provider):
    name = "ollama"

    def __init__(self, base_url: str | None, models: Sequence[str], client: httpx.AsyncClient | None = None):
        super().__init__(client)
        self.base_url = (base_url or "").rstrip("/")
        self._models = list(models)

    def is_configured(self) -> bool:
        return bool(self.base_url) and bool(self._models)

    def models(self) -> list[ModelInfo]:
        caps = frozenset({Capability.CHAT, Capability.CODE, Capability.LOCAL})
        return [
            ModelInfo(self.name, m, f"{m} (local)", caps, CostTier.FREE, context_window=8_192) for m in self._models
        ]

    async def stream(
        self, model: str, messages: Sequence[ChatMessage], params: GenerationParams
    ) -> AsyncIterator[StreamChunk]:
        payload = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": True,
            "options": {"temperature": params.temperature, "num_predict": params.max_tokens},
        }
        input_tokens = output_tokens = None
        try:
            async with self._client.stream("POST", f"{self.base_url}/api/chat", json=payload) as response:
                await self._raise_for_status(response)
                # Ollama streams newline-delimited JSON rather than SSE.
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    obj = parse_json(self.name, line)
                    if obj.get("error"):
                        raise ProviderError(self.name, str(obj["error"]), retryable=False)
                    text = (obj.get("message") or {}).get("content")
                    if text:
                        yield StreamChunk(text=text)
                    if obj.get("done"):
                        input_tokens = obj.get("prompt_eval_count")
                        output_tokens = obj.get("eval_count")
                        break
        except httpx.HTTPError as exc:
            raise ProviderError(self.name, f"Network error (is Ollama running at {self.base_url}?): {exc}") from exc
        yield StreamChunk(done=True, input_tokens=input_tokens, output_tokens=output_tokens)
