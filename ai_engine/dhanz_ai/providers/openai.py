"""OpenAI (and OpenAI-compatible) Chat Completions provider."""

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


class OpenAIProvider(Provider):
    name = "openai"

    def __init__(
        self,
        api_key: str | None,
        models: Sequence[str],
        base_url: str = "https://api.openai.com/v1",
        client: httpx.AsyncClient | None = None,
        name: str | None = None,
    ):
        super().__init__(client)
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self._models = list(models)
        if name:
            # Allows registering OpenAI-compatible endpoints (e.g. Groq, Together) under another name.
            self.name = name

    def is_configured(self) -> bool:
        return bool(self.api_key) and bool(self._models)

    def models(self) -> list[ModelInfo]:
        infos = []
        for m in self._models:
            caps = {Capability.CHAT, Capability.CODE}
            if "4o" in m or "gpt-4.1" in m or "gpt-5" in m:
                caps.add(Capability.VISION)
            tier = CostTier.LOW if "mini" in m or "nano" in m else CostTier.MEDIUM
            infos.append(ModelInfo(self.name, m, m, frozenset(caps), tier))
        return infos

    async def stream(
        self, model: str, messages: Sequence[ChatMessage], params: GenerationParams
    ) -> AsyncIterator[StreamChunk]:
        payload = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": True,
            "stream_options": {"include_usage": True},
            "temperature": params.temperature,
            "max_completion_tokens": params.max_tokens,
        }
        headers = {"Authorization": f"Bearer {self.api_key}"}
        input_tokens = output_tokens = None
        try:
            async with self._client.stream(
                "POST", f"{self.base_url}/chat/completions", json=payload, headers=headers
            ) as response:
                await self._raise_for_status(response)
                async for _event, data in iter_sse_data(response):
                    if data.strip() == "[DONE]":
                        break
                    obj = parse_json(self.name, data)
                    if obj.get("error"):
                        raise ProviderError(self.name, str(obj["error"]), retryable=False)
                    usage = obj.get("usage")
                    if usage:
                        input_tokens = usage.get("prompt_tokens")
                        output_tokens = usage.get("completion_tokens")
                    for choice in obj.get("choices") or []:
                        text = (choice.get("delta") or {}).get("content")
                        if text:
                            yield StreamChunk(text=text)
        except httpx.HTTPError as exc:
            raise ProviderError(self.name, f"Network error: {exc}") from exc
        yield StreamChunk(done=True, input_tokens=input_tokens, output_tokens=output_tokens)
