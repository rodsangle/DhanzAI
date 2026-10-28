"""Google Gemini (Generative Language API) provider."""

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


class GeminiProvider(Provider):
    name = "gemini"

    def __init__(
        self,
        api_key: str | None,
        models: Sequence[str],
        base_url: str = "https://generativelanguage.googleapis.com/v1beta",
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
            tier = CostTier.LOW if "flash" in m else CostTier.MEDIUM
            if "pro" in m:
                caps.add(Capability.REASONING)
            infos.append(ModelInfo(self.name, m, m, frozenset(caps), tier, context_window=1_000_000))
        return infos

    async def stream(
        self, model: str, messages: Sequence[ChatMessage], params: GenerationParams
    ) -> AsyncIterator[StreamChunk]:
        system = "\n\n".join(m.content for m in messages if m.role == "system")
        contents = [
            {
                "role": "model" if m.role == "assistant" else "user",
                "parts": [{"inline_data": {"mime_type": i.mime_type, "data": i.data_b64}} for i in m.images]
                + [{"text": m.content}],
            }
            for m in messages
            if m.role != "system"
        ]
        payload: dict = {
            "contents": contents,
            "generationConfig": {"temperature": params.temperature, "maxOutputTokens": params.max_tokens},
        }
        if system:
            payload["systemInstruction"] = {"parts": [{"text": system}]}
        url = f"{self.base_url}/models/{model}:streamGenerateContent"
        headers = {"x-goog-api-key": self.api_key or ""}
        input_tokens = output_tokens = None
        try:
            async with self._client.stream(
                "POST", url, params={"alt": "sse"}, json=payload, headers=headers
            ) as response:
                await self._raise_for_status(response)
                async for _event, data in iter_sse_data(response):
                    obj = parse_json(self.name, data)
                    if obj.get("error"):
                        raise ProviderError(self.name, str(obj["error"]), retryable=False)
                    usage = obj.get("usageMetadata") or {}
                    input_tokens = usage.get("promptTokenCount", input_tokens)
                    output_tokens = usage.get("candidatesTokenCount", output_tokens)
                    for cand in obj.get("candidates") or []:
                        for part in (cand.get("content") or {}).get("parts") or []:
                            if part.get("text") and not part.get("thought"):
                                yield StreamChunk(text=part["text"])
                        if cand.get("finishReason") == "SAFETY":
                            raise ProviderError(self.name, "Response blocked by safety filters", retryable=False)
        except httpx.HTTPError as exc:
            raise ProviderError(self.name, f"Network error: {exc}") from exc
        yield StreamChunk(done=True, input_tokens=input_tokens, output_tokens=output_tokens)
