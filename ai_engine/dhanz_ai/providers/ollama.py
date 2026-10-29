"""Ollama provider for locally hosted models."""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence

import httpx

from dhanz_ai.providers.base import Provider, parse_json, tool_arguments
from dhanz_ai.types import (
    Capability,
    ChatMessage,
    CostTier,
    GenerationParams,
    ModelInfo,
    ProviderError,
    StreamChunk,
    ToolCall,
    ToolSpec,
)

# Model families whose Ollama templates support function calling.
_TOOL_FAMILIES = (
    "llama3.1",
    "llama3.2",
    "llama3.3",
    "llama4",
    "qwen2.5",
    "qwen3",
    "mistral",
    "mixtral",
    "command-r",
    "granite3",
    "hermes3",
    "firefunction",
    "gpt-oss",
    "phi4-mini",
    "smollm2",
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
        infos = []
        for m in self._models:
            caps = {Capability.CHAT, Capability.CODE, Capability.LOCAL}
            if any(v in m for v in ("llava", "vision", "gemma3", "qwen2.5vl", "minicpm-v", "moondream")):
                caps.add(Capability.VISION)
            if any(m.startswith(f) for f in _TOOL_FAMILIES):
                caps.add(Capability.TOOLS)
            infos.append(ModelInfo(self.name, m, f"{m} (local)", frozenset(caps), CostTier.FREE, context_window=8_192))
        return infos

    async def stream(
        self, model: str, messages: Sequence[ChatMessage], params: GenerationParams, tools: Sequence[ToolSpec] = ()
    ) -> AsyncIterator[StreamChunk]:
        payload: dict = {
            "model": model,
            "messages": [_to_ollama(m) for m in messages],
            "stream": True,
            "options": {"temperature": params.temperature, "num_predict": params.max_tokens},
        }
        if tools:
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {"name": t.name, "description": t.description, "parameters": t.parameters},
                }
                for t in tools
            ]
        input_tokens = output_tokens = None
        calls: list[ToolCall] = []
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
                    message = obj.get("message") or {}
                    if message.get("content"):
                        yield StreamChunk(text=message["content"])
                    for tc in message.get("tool_calls") or []:
                        fn = tc.get("function") or {}
                        name = fn.get("name", "")
                        calls.append(
                            ToolCall(
                                tc.get("id") or f"{name}_{len(calls)}",
                                name,
                                tool_arguments(self.name, fn.get("arguments")),
                            )
                        )
                    if obj.get("done"):
                        input_tokens = obj.get("prompt_eval_count")
                        output_tokens = obj.get("eval_count")
                        break
        except httpx.HTTPError as exc:
            raise ProviderError(self.name, f"Network error (is Ollama running at {self.base_url}?): {exc}") from exc
        if calls:
            yield StreamChunk(tool_calls=tuple(calls))
        yield StreamChunk(done=True, input_tokens=input_tokens, output_tokens=output_tokens)


def _to_ollama(m: ChatMessage) -> dict:
    if m.role == "tool" and m.tool_result is not None:
        return {"role": "tool", "content": m.tool_result.content, "tool_name": m.tool_result.name}
    out: dict = {"role": m.role, "content": m.content}
    if m.images:
        out["images"] = [i.data_b64 for i in m.images]
    if m.tool_calls:
        out["tool_calls"] = [{"function": {"name": c.name, "arguments": c.arguments}} for c in m.tool_calls]
    return out
