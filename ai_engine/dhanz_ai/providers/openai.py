"""OpenAI (and OpenAI-compatible) Chat Completions provider."""

from __future__ import annotations

import json
import logging
import re
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

log = logging.getLogger(__name__)

# Read by scripts/server/upgrade_models.py to know the server adapts per-model request settings.
ADAPTIVE_PARAMS = True
# Request settings some models refuse, learned from the provider's own HTTP 400 replies:
NO_TEMPERATURE = "no_temperature"  # "Only the default (1) value is supported" (GPT-5.5/5.6/6.x)
REASONING_NONE_WITH_TOOLS = "reasoning_none_with_tools"  # "Function tools with reasoning_effort ... set 'none'"


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
        # Per model: settings to change, learned from a rejected request and kept for the process lifetime.
        self._adjustments: dict[str, set[str]] = {}
        if name:
            # Allows registering OpenAI-compatible endpoints (e.g. Groq, Together) under another name.
            self.name = name

    def is_configured(self) -> bool:
        return bool(self.api_key) and bool(self._models)

    def models(self) -> list[ModelInfo]:
        infos = []
        for m in self._models:
            caps = {Capability.CHAT, Capability.CODE, Capability.TOOLS}
            if "4o" in m or "gpt-4.1" in m or _gpt_major(m) >= 5:
                caps.add(Capability.VISION)
            tier = CostTier.LOW if any(word in m for word in ("mini", "nano", "luna")) else CostTier.MEDIUM
            infos.append(ModelInfo(self.name, m, m, frozenset(caps), tier))
        return infos

    def _payload(
        self, model: str, messages: Sequence[ChatMessage], params: GenerationParams, tools: Sequence[ToolSpec]
    ) -> dict:
        adjust = self._adjustments.get(model, set())
        payload: dict = {
            "model": model,
            "messages": [_to_openai(m) for m in messages],
            "stream": True,
            "stream_options": {"include_usage": True},
            "max_completion_tokens": params.max_tokens,
        }
        if NO_TEMPERATURE not in adjust:
            payload["temperature"] = params.temperature
        if tools:
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {"name": t.name, "description": t.description, "parameters": t.parameters},
                }
                for t in tools
            ]
            if REASONING_NONE_WITH_TOOLS in adjust:
                payload["reasoning_effort"] = "none"
        return payload

    def _learn(self, model: str, exc: ProviderError, with_tools: bool) -> bool:
        """Record a setting this model refused. True when the request is worth sending again."""
        if exc.status_code != 400:
            return False
        text = str(exc).lower()
        adjust = self._adjustments.setdefault(model, set())
        if "temperature" in text and ("only the default" in text or "unsupported value" in text):
            change = NO_TEMPERATURE
        elif with_tools and "reasoning_effort" in text and "'none'" in text:
            change = REASONING_NONE_WITH_TOOLS
        else:
            return False
        if change in adjust:
            return False
        adjust.add(change)
        log.info("Model %s refused a request setting; sending again with %s", model, change)
        return True

    async def stream(
        self, model: str, messages: Sequence[ChatMessage], params: GenerationParams, tools: Sequence[ToolSpec] = ()
    ) -> AsyncIterator[StreamChunk]:
        # A refused setting is reported (HTTP 400) before any output, so the request can be sent again.
        for attempt in range(3):
            chunks = self._stream_once(self._payload(model, messages, params, tools))
            try:
                first = await anext(chunks)
            except ProviderError as exc:
                if attempt < 2 and self._learn(model, exc, bool(tools)):
                    continue
                raise
            yield first
            async for chunk in chunks:
                yield chunk
            return

    async def _stream_once(self, payload: dict) -> AsyncIterator[StreamChunk]:
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


def _gpt_major(model: str) -> int:
    """Major version of a GPT model id ("gpt-6.1-terra" -> 6); 0 when it is not one."""
    match = re.match(r"gpt-(\d+)", model)
    return int(match.group(1)) if match else 0
