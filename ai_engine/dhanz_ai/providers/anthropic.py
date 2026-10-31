"""Anthropic Claude Messages API provider."""

from __future__ import annotations

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

ANTHROPIC_VERSION = "2023-06-01"


class AnthropicProvider(Provider):
    name = "anthropic"

    def __init__(
        self,
        api_key: str | None,
        models: Sequence[str],
        base_url: str = "https://api.anthropic.com/v1",
        client: httpx.AsyncClient | None = None,
        *,
        read_timeout: float = CLOUD_READ_TIMEOUT_SECONDS,
    ):
        super().__init__(client, read_timeout=read_timeout)
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self._models = list(models)

    def is_configured(self) -> bool:
        return bool(self.api_key) and bool(self._models)

    def models(self) -> list[ModelInfo]:
        infos = []
        for m in self._models:
            caps = {Capability.CHAT, Capability.CODE, Capability.VISION, Capability.LONG_CONTEXT, Capability.TOOLS}
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
        self, model: str, messages: Sequence[ChatMessage], params: GenerationParams, tools: Sequence[ToolSpec] = ()
    ) -> AsyncIterator[StreamChunk]:
        # Claude takes the system prompt as a top-level field, not as a message.
        system = "\n\n".join(m.content for m in messages if m.role == "system")
        payload: dict = {
            "model": model,
            "max_tokens": params.max_tokens,
            "temperature": params.temperature,
            "stream": True,
            "messages": _to_anthropic_messages([m for m in messages if m.role != "system"]),
        }
        if system:
            payload["system"] = system
        if tools:
            payload["tools"] = [
                {"name": t.name, "description": t.description, "input_schema": t.parameters} for t in tools
            ]
        headers = {"x-api-key": self.api_key or "", "anthropic-version": ANTHROPIC_VERSION}
        input_tokens = output_tokens = None
        tool_blocks: dict[int, dict] = {}  # tool_use blocks being streamed, by content index
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
                    elif kind == "content_block_start":
                        block = obj.get("content_block") or {}
                        if block.get("type") == "tool_use":
                            tool_blocks[obj.get("index", 0)] = {
                                "id": block.get("id", ""),
                                "name": block.get("name", ""),
                                "json": "",
                            }
                    elif kind == "content_block_delta":
                        delta = obj.get("delta") or {}
                        if delta.get("type") == "text_delta" and delta.get("text"):
                            yield StreamChunk(text=delta["text"])
                        elif delta.get("type") == "input_json_delta" and obj.get("index", 0) in tool_blocks:
                            tool_blocks[obj.get("index", 0)]["json"] += delta.get("partial_json") or ""
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
        if tool_blocks:
            yield StreamChunk(
                tool_calls=tuple(
                    ToolCall(b["id"], b["name"], tool_arguments(self.name, b["json"]))
                    for _, b in sorted(tool_blocks.items())
                )
            )
        yield StreamChunk(done=True, input_tokens=input_tokens, output_tokens=output_tokens)


def _to_anthropic_messages(messages: Sequence[ChatMessage]) -> list[dict]:
    """Claude wants tool results as `tool_result` blocks in a user turn, all results of one round together."""
    out: list[dict] = []
    for m in messages:
        if m.role == "tool" and m.tool_result is not None:
            block = {
                "type": "tool_result",
                "tool_use_id": m.tool_result.call_id,
                "content": m.tool_result.content,
                **({"is_error": True} if m.tool_result.is_error else {}),
            }
            if (
                out
                and out[-1]["role"] == "user"
                and isinstance(out[-1]["content"], list)
                and all(b.get("type") == "tool_result" for b in out[-1]["content"])
            ):
                out[-1]["content"].append(block)
            else:
                out.append({"role": "user", "content": [block]})
            continue
        out.append(_to_anthropic(m))
    return out


def _to_anthropic(m: ChatMessage) -> dict:
    if m.tool_calls:
        blocks: list[dict] = [{"type": "text", "text": m.content}] if m.content else []
        blocks += [{"type": "tool_use", "id": c.id, "name": c.name, "input": c.arguments} for c in m.tool_calls]
        return {"role": "assistant", "content": blocks}
    if not m.images:
        return {"role": m.role, "content": m.content}
    parts: list[dict] = [
        {"type": "image", "source": {"type": "base64", "media_type": img.mime_type, "data": img.data_b64}}
        for img in m.images
    ]
    parts.append({"type": "text", "text": m.content})
    return {"role": m.role, "content": parts}
