"""OpenAI (and OpenAI-compatible) Chat Completions provider."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Sequence

import httpx

from dhanz_ai.providers.base import CLOUD_READ_TIMEOUT_SECONDS, Provider, iter_sse_data, parse_json, tool_arguments
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


class OpenAIProvider(Provider):
    name = "openai"

    def __init__(
        self,
        api_key: str | None,
        models: Sequence[str],
        base_url: str = "https://api.openai.com/v1",
        client: httpx.AsyncClient | None = None,
        name: str | None = None,
        *,
        read_timeout: float = CLOUD_READ_TIMEOUT_SECONDS,
    ):
        super().__init__(client, read_timeout=read_timeout)
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
            caps = {Capability.CHAT, Capability.CODE, Capability.TOOLS}
            if "4o" in m or "gpt-4.1" in m or "gpt-5" in m:
                caps.add(Capability.VISION)
            tier = CostTier.LOW if "mini" in m or "nano" in m else CostTier.MEDIUM
            infos.append(ModelInfo(self.name, m, m, frozenset(caps), tier))
        return infos

    async def stream(
        self, model: str, messages: Sequence[ChatMessage], params: GenerationParams, tools: Sequence[ToolSpec] = ()
    ) -> AsyncIterator[StreamChunk]:
        payload: dict = {
            "model": model,
            "messages": [_to_openai(m) for m in messages],
            "stream": True,
            "stream_options": {"include_usage": True},
            "temperature": params.temperature,
            "max_completion_tokens": params.max_tokens,
        }
        if tools:
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {"name": t.name, "description": t.description, "parameters": t.parameters},
                }
                for t in tools
            ]
        headers = {"Authorization": f"Bearer {self.api_key}"}
        input_tokens = output_tokens = None
        calls: dict[int, dict] = {}  # tool-call fragments by index
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
                        delta = choice.get("delta") or {}
                        if delta.get("content"):
                            yield StreamChunk(text=delta["content"])
                        for frag in delta.get("tool_calls") or []:
                            call = calls.setdefault(frag.get("index", 0), {"id": "", "name": "", "arguments": ""})
                            call["id"] = frag.get("id") or call["id"]
                            fn = frag.get("function") or {}
                            call["name"] = fn.get("name") or call["name"]
                            call["arguments"] += fn.get("arguments") or ""
        except httpx.HTTPError as exc:
            raise ProviderError(self.name, f"Network error: {exc}") from exc
        if calls:
            yield StreamChunk(
                tool_calls=tuple(
                    ToolCall(c["id"] or f"call_{i}", c["name"], tool_arguments(self.name, c["arguments"]))
                    for i, c in sorted(calls.items())
                )
            )
        yield StreamChunk(done=True, input_tokens=input_tokens, output_tokens=output_tokens)


def _to_openai(m: ChatMessage) -> dict:
    if m.role == "tool" and m.tool_result is not None:
        return {"role": "tool", "tool_call_id": m.tool_result.call_id, "content": m.tool_result.content}
    if m.tool_calls:
        return {
            "role": "assistant",
            "content": m.content or None,
            "tool_calls": [
                {"id": c.id, "type": "function", "function": {"name": c.name, "arguments": json.dumps(c.arguments)}}
                for c in m.tool_calls
            ],
        }
    if not m.images:
        return {"role": m.role, "content": m.content}
    parts: list[dict] = [{"type": "text", "text": m.content}]
    parts += [
        {"type": "image_url", "image_url": {"url": f"data:{img.mime_type};base64,{img.data_b64}"}} for img in m.images
    ]
    return {"role": m.role, "content": parts}
