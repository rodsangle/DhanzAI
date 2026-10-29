"""Google Gemini (Generative Language API) provider."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Sequence

import httpx

from dhanz_ai.providers.base import Provider, iter_sse_data, parse_json, tool_arguments
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
            caps = {Capability.CHAT, Capability.CODE, Capability.VISION, Capability.LONG_CONTEXT, Capability.TOOLS}
            tier = CostTier.LOW if "flash" in m else CostTier.MEDIUM
            if "pro" in m:
                caps.add(Capability.REASONING)
            infos.append(ModelInfo(self.name, m, m, frozenset(caps), tier, context_window=1_000_000))
        return infos

    async def stream(
        self, model: str, messages: Sequence[ChatMessage], params: GenerationParams, tools: Sequence[ToolSpec] = ()
    ) -> AsyncIterator[StreamChunk]:
        system = "\n\n".join(m.content for m in messages if m.role == "system")
        payload: dict = {
            "contents": _to_gemini_contents([m for m in messages if m.role != "system"]),
            "generationConfig": {"temperature": params.temperature, "maxOutputTokens": params.max_tokens},
        }
        if system:
            payload["systemInstruction"] = {"parts": [{"text": system}]}
        if tools:
            payload["tools"] = [
                {
                    "functionDeclarations": [
                        {"name": t.name, "description": t.description, "parameters": t.parameters} for t in tools
                    ]
                }
            ]
        url = f"{self.base_url}/models/{model}:streamGenerateContent"
        headers = {"x-goog-api-key": self.api_key or ""}
        input_tokens = output_tokens = None
        calls: list[ToolCall] = []
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
                            elif fc := part.get("functionCall"):
                                calls.append(
                                    ToolCall(
                                        fc.get("id") or f"{fc.get('name', 'call')}_{len(calls)}",
                                        fc.get("name", ""),
                                        tool_arguments(self.name, fc.get("args")),
                                        # Thinking models require the signature to be sent back with the call.
                                        {"thoughtSignature": part["thoughtSignature"]}
                                        if part.get("thoughtSignature")
                                        else {},
                                    )
                                )
                        if cand.get("finishReason") == "SAFETY":
                            raise ProviderError(self.name, "Response blocked by safety filters", retryable=False)
        except httpx.HTTPError as exc:
            raise ProviderError(self.name, f"Network error: {exc}") from exc
        if calls:
            yield StreamChunk(tool_calls=tuple(calls))
        yield StreamChunk(done=True, input_tokens=input_tokens, output_tokens=output_tokens)


def _to_gemini_contents(messages: Sequence[ChatMessage]) -> list[dict]:
    contents: list[dict] = []
    for m in messages:
        if m.role == "tool" and m.tool_result is not None:
            r = m.tool_result
            try:
                response = json.loads(r.content)
            except json.JSONDecodeError:
                response = r.content
            if not isinstance(response, dict):
                response = {"result": response}  # functionResponse.response must be an object
            part = {"functionResponse": {"name": r.name, "response": response}}
            if not r.call_id.startswith(f"{r.name}_"):  # a real id from the API, not one we made up
                part["functionResponse"]["id"] = r.call_id
            if contents and contents[-1].get("_tool_results"):
                contents[-1]["parts"].append(part)
            else:
                contents.append({"role": "user", "parts": [part], "_tool_results": True})
            continue
        parts: list[dict] = [{"inline_data": {"mime_type": i.mime_type, "data": i.data_b64}} for i in m.images]
        if m.content or not m.tool_calls:
            parts.append({"text": m.content})
        for c in m.tool_calls:
            call: dict = {"name": c.name, "args": c.arguments}
            if not c.id.startswith(f"{c.name}_"):
                call["id"] = c.id
            parts.append({"functionCall": call, **c.extra})
        contents.append({"role": "model" if m.role == "assistant" else "user", "parts": parts})
    for c in contents:
        c.pop("_tool_results", None)
    return contents
