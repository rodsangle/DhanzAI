"""Provider stream-parsing tests against recorded wire formats (no network)."""

import json

import httpx
import pytest

from dhanz_ai import (
    AnthropicProvider,
    ChatMessage,
    GeminiProvider,
    GenerationParams,
    OllamaProvider,
    OpenAIProvider,
    ProviderError,
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
