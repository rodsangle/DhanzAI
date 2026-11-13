"""Provider stream-parsing tests against recorded wire formats (no network)."""

import json

import httpx
import pytest

from dhanz_ai import (
    AnthropicProvider,
    ChatMessage,
    GeminiProvider,
    GenerationParams,
    ImagePart,
    OllamaProvider,
    OpenAIProvider,
    ProviderError,
    ToolSpec,
)

MESSAGES = [ChatMessage("system", "be brief"), ChatMessage("user", "hi")]


def sse(*events: tuple[str | None, dict | str]) -> bytes:
    out = []
    for event, data in events:
        if event:
            out.append(f"event: {event}")
        out.append("data: " + (data if isinstance(data, str) else json.dumps(data)))
        out.append("")
    return ("\n".join(out) + "\n").encode()


def client_returning(body: bytes, status: int = 200, captured: dict | None = None) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        if captured is not None:
            captured["url"] = str(request.url)
            captured["headers"] = dict(request.headers)
            captured["json"] = json.loads(request.content)
        return httpx.Response(status, content=body)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def collect(provider, model):
    chunks = [c async for c in provider.stream(model, MESSAGES, GenerationParams(max_tokens=50))]
    return "".join(c.text for c in chunks), chunks[-1]


async def test_openai_stream():
    body = sse(
        (None, {"choices": [{"delta": {"role": "assistant"}}]}),
        (None, {"choices": [{"delta": {"content": "Hel"}}]}),
        (None, {"choices": [{"delta": {"content": "lo"}}]}),
        (None, {"choices": [], "usage": {"prompt_tokens": 7, "completion_tokens": 2}}),
        (None, "[DONE]"),
    )
    captured: dict = {}
    p = OpenAIProvider("sk-test", ["gpt-test"], client=client_returning(body, captured=captured))
    text, last = await collect(p, "gpt-test")
    assert text == "Hello"
    assert last.done and last.input_tokens == 7 and last.output_tokens == 2
    assert captured["headers"]["authorization"] == "Bearer sk-test"
    assert captured["json"]["messages"][0] == {"role": "system", "content": "be brief"}
    assert captured["url"].endswith("/chat/completions")


async def test_anthropic_stream_moves_system_prompt():
    body = sse(
        ("message_start", {"type": "message_start", "message": {"usage": {"input_tokens": 11}}}),
        ("content_block_start", {"type": "content_block_start", "index": 0}),
        ("ping", {"type": "ping"}),
        ("content_block_delta", {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "Hi "}}),
        ("content_block_delta", {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "there"}}),
        ("message_delta", {"type": "message_delta", "usage": {"output_tokens": 3}}),
        ("message_stop", {"type": "message_stop"}),
    )
    captured: dict = {}
    p = AnthropicProvider("ak", ["claude-test"], client=client_returning(body, captured=captured))
    text, last = await collect(p, "claude-test")
    assert text == "Hi there"
    assert last.input_tokens == 11 and last.output_tokens == 3
    assert captured["json"]["system"] == "be brief"
    assert all(m["role"] != "system" for m in captured["json"]["messages"])
    assert captured["headers"]["x-api-key"] == "ak"
    assert captured["headers"]["anthropic-version"]


async def test_anthropic_stream_error_event():
    body = sse(("error", {"type": "error", "error": {"type": "overloaded_error", "message": "Overloaded"}}))
    p = AnthropicProvider("ak", ["claude-test"], client=client_returning(body))
    with pytest.raises(ProviderError) as info:
        await collect(p, "claude-test")
    assert info.value.retryable


async def test_gemini_stream():
    body = sse(
        (None, {"candidates": [{"content": {"parts": [{"text": "Bon"}], "role": "model"}}]}),
        (
            None,
            {
                "candidates": [{"content": {"parts": [{"text": "jour"}]}, "finishReason": "STOP"}],
                "usageMetadata": {"promptTokenCount": 4, "candidatesTokenCount": 2},
            },
        ),
    )
    captured: dict = {}
    p = GeminiProvider("gk", ["gemini-test"], client=client_returning(body, captured=captured))
    text, last = await collect(p, "gemini-test")
    assert text == "Bonjour"
    assert last.output_tokens == 2
    assert "gemini-test:streamGenerateContent" in captured["url"] and "alt=sse" in captured["url"]
    assert captured["json"]["systemInstruction"]["parts"][0]["text"] == "be brief"
    assert captured["json"]["contents"] == [{"role": "user", "parts": [{"text": "hi"}]}]


async def test_ollama_requests_num_ctx_and_reports_it_as_the_context_window():
    captured: dict = {}
    provider = OllamaProvider(
        "http://ollama:11434",
        ["qwen3"],
        num_ctx=16_384,
        client=client_returning(b'{"done": true}\n', captured=captured),
    )
    assert provider.models()[0].context_window == 16_384
    chunks = [chunk async for chunk in provider.stream("qwen3", MESSAGES, GenerationParams())]
    assert captured["json"]["options"]["num_ctx"] == 16_384
    assert chunks[-1].done


async def test_read_timeout_defaults():
    local = OllamaProvider("http://127.0.0.1:11434", ["llama3.1"])
    cloud = OpenAIProvider("key", ["gpt-4.1"])
    try:
        assert local._client.timeout.read == 300
        assert local.num_ctx == 16_384
        assert cloud._client.timeout.read == 120
    finally:
        await local.aclose()
        await cloud.aclose()


async def test_ollama_ndjson_stream():
    lines = [
        {"message": {"role": "assistant", "content": "Lo"}, "done": False},
        {"message": {"role": "assistant", "content": "cal"}, "done": False},
        {"message": {"role": "assistant", "content": ""}, "done": True, "prompt_eval_count": 5, "eval_count": 2},
    ]
    body = ("\n".join(json.dumps(x) for x in lines) + "\n").encode()
    p = OllamaProvider("http://ollama:11434", ["llama3"], client=client_returning(body))
    text, last = await collect(p, "llama3")
    assert text == "Local"
    assert last.done and last.output_tokens == 2


@pytest.mark.parametrize("status,retryable", [(429, True), (503, True), (401, False), (400, False)])
async def test_http_errors_map_to_provider_error(status, retryable):
    p = OpenAIProvider("k", ["m"], client=client_returning(b'{"error":"x"}', status=status))
    with pytest.raises(ProviderError) as info:
        await collect(p, "m")
    assert info.value.status_code == status
    assert info.value.retryable is retryable


def test_is_configured():
    assert not OpenAIProvider(None, ["m"]).is_configured()
    assert not AnthropicProvider("k", []).is_configured()
    assert OllamaProvider("http://x", ["m"]).is_configured()
    assert not OllamaProvider("", ["m"]).is_configured()


IMG = ImagePart("image/png", "iVBORw0KGgo=")
VISION_MESSAGES = [ChatMessage("user", "what is this?", images=(IMG,))]


async def test_images_are_sent_in_each_provider_format():
    body = sse((None, "[DONE]"))
    cap: dict = {}
    p = OpenAIProvider("k", ["gpt-4.1"], client=client_returning(body, captured=cap))
    [c async for c in p.stream("gpt-4.1", VISION_MESSAGES, GenerationParams())]
    content = cap["json"]["messages"][0]["content"]
    assert content[0] == {"type": "text", "text": "what is this?"}
    assert content[1]["image_url"]["url"] == "data:image/png;base64,iVBORw0KGgo="

    cap = {}
    p = AnthropicProvider(
        "k", ["claude"], client=client_returning(sse(("message_stop", {"type": "message_stop"})), captured=cap)
    )
    [c async for c in p.stream("claude", VISION_MESSAGES, GenerationParams())]
    content = cap["json"]["messages"][0]["content"]
    assert content[0]["source"] == {"type": "base64", "media_type": "image/png", "data": "iVBORw0KGgo="}

    cap = {}
    p = GeminiProvider("k", ["g"], client=client_returning(sse((None, {"candidates": []})), captured=cap))
    [c async for c in p.stream("g", VISION_MESSAGES, GenerationParams())]
    assert cap["json"]["contents"][0]["parts"][0]["inline_data"]["mime_type"] == "image/png"

    cap = {}
    p = OllamaProvider("http://o", ["llava"], client=client_returning(b'{"done": true}\n', captured=cap))
    [c async for c in p.stream("llava", VISION_MESSAGES, GenerationParams())]
    assert cap["json"]["messages"][0]["images"] == ["iVBORw0KGgo="]
    assert any("vision" == c.value for c in p.models()[0].capabilities)


def test_newer_gpt_models_read_images_and_luna_is_low_cost():
    from dhanz_ai.providers.openai import OpenAIProvider
    from dhanz_ai.types import Capability, CostTier

    infos = {m.model: m for m in OpenAIProvider("k", ["gpt-6.1-terra", "gpt-6-luna", "gpt-3.5-turbo"]).models()}
    assert Capability.VISION in infos["gpt-6.1-terra"].capabilities
    assert Capability.VISION not in infos["gpt-3.5-turbo"].capabilities
    assert infos["gpt-6-luna"].cost_tier == CostTier.LOW


def openai_rejecting(rejections: dict[str, str], seen: list[dict]) -> httpx.AsyncClient:
    """Answer with HTTP 400 while the request still contains a refused setting; otherwise stream 'ok'."""

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen.append(body)
        for setting, message in rejections.items():
            if setting in body and not (setting == "reasoning_effort" and body[setting] == "none"):
                return httpx.Response(400, json={"error": {"message": message, "param": setting}})
            if setting == "reasoning_effort" and body.get("tools") and body.get(setting) != "none":
                return httpx.Response(400, json={"error": {"message": message, "param": setting}})
        chunk = {"choices": [{"delta": {"content": "ok"}}]}
        return httpx.Response(200, content=sse((None, chunk), (None, "[DONE]")))

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


TEMPERATURE_REFUSED = (
    "Unsupported value: 'temperature' does not support 0.7 with this model. Only the default (1) value is supported."
)
TOOLS_REFUSED = (
    "Function tools with reasoning_effort are not supported for gpt-6.1-sol in /v1/chat/completions. "
    "To use function tools, use /v1/responses or set reasoning_effort to 'none'."
)
TOOL = ToolSpec("get_time", "Current time", {"type": "object", "properties": {}})


async def test_openai_adapts_to_refused_temperature_and_reasoning_settings():
    seen: list[dict] = []
    client = openai_rejecting({"temperature": TEMPERATURE_REFUSED, "reasoning_effort": TOOLS_REFUSED}, seen)
    p = OpenAIProvider("k", ["gpt-6.1-sol"], client=client)
    text = "".join(c.text for c in [c async for c in p.stream("gpt-6.1-sol", MESSAGES, GenerationParams(), [TOOL])])
    assert text == "ok"
    assert len(seen) == 3  # temperature refused, then tools/reasoning refused, then accepted
    assert "temperature" not in seen[-1] and seen[-1]["reasoning_effort"] == "none" and seen[-1]["tools"]

    seen.clear()  # learned: the next request is right the first time
    [c async for c in p.stream("gpt-6.1-sol", MESSAGES, GenerationParams(temperature=0), [TOOL])]
    assert len(seen) == 1 and "temperature" not in seen[0] and seen[0]["reasoning_effort"] == "none"

    seen.clear()  # without tools no reasoning setting is sent
    [c async for c in p.stream("gpt-6.1-sol", MESSAGES, GenerationParams())]
    assert len(seen) == 1 and "reasoning_effort" not in seen[0]


async def test_openai_other_models_keep_their_settings_and_unknown_400_is_raised():
    seen: list[dict] = []
    client = openai_rejecting({"temperature": TEMPERATURE_REFUSED}, seen)
    p = OpenAIProvider("k", ["gpt-6-luna", "gpt-4.1"], client=client)
    [c async for c in p.stream("gpt-6-luna", MESSAGES, GenerationParams())]
    assert "temperature" not in seen[-1]

    ok_client = openai_rejecting({}, seen)
    p2 = OpenAIProvider("k", ["gpt-4.1"], client=ok_client)
    seen.clear()
    [c async for c in p2.stream("gpt-4.1", MESSAGES, GenerationParams(temperature=0.7))]
    assert seen[0]["temperature"] == 0.7 and "reasoning_effort" not in seen[0]

    other = OpenAIProvider(
        "k", ["gpt-4.1"], client=client_returning(b'{"error": {"message": "context length exceeded"}}', status=400)
    )
    with pytest.raises(ProviderError, match="context length") as caught:
        [c async for c in other.stream("gpt-4.1", MESSAGES, GenerationParams())]
    assert caught.value.status_code == 400 and caught.value.model_rejected
