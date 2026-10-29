"""Function calling: each provider's wire format (recorded, no network) and the orchestrator's tool loop."""

import json
from collections.abc import AsyncIterator, Sequence

import pytest
from test_providers import client_returning, sse

from dhanz_ai import (
    AnthropicProvider,
    Capability,
    ChatMessage,
    CostTier,
    GeminiProvider,
    GenerationParams,
    ModelInfo,
    OllamaProvider,
    OpenAIProvider,
    Orchestrator,
    Provider,
    StreamChunk,
    ToolCall,
    ToolResult,
    ToolSpec,
)

CALC = ToolSpec(
    "calculate",
    "Evaluate an arithmetic expression.",
    {"type": "object", "properties": {"expression": {"type": "string"}}, "required": ["expression"]},
)

# A conversation that already contains one tool round, to check how each provider encodes it.
HISTORY = [
    ChatMessage("system", "be brief"),
    ChatMessage("user", "What is 12*7 and 3+4?"),
    ChatMessage(
        "assistant",
        "Let me calculate.",
        tool_calls=(
            ToolCall("c1", "calculate", {"expression": "12*7"}),
            ToolCall("c2", "calculate", {"expression": "3+4"}),
        ),
    ),
    ChatMessage.from_tool_result(ToolResult("c1", "calculate", '{"result": 84}')),
    ChatMessage.from_tool_result(ToolResult("c2", "calculate", '{"result": 7}')),
]


async def run(provider, model, messages=HISTORY):
    return [c async for c in provider.stream(model, messages, GenerationParams(), tools=[CALC])]


async def test_openai_tool_calls():
    body = sse(
        (None, {"choices": [{"delta": {"role": "assistant", "content": "Sure. "}}]}),
        (
            None,
            {
                "choices": [
                    {
                        "delta": {
                            "tool_calls": [
                                {
                                    "index": 0,
                                    "id": "call_A",
                                    "type": "function",
                                    "function": {"name": "calculate", "arguments": ""},
                                }
                            ]
                        }
                    }
                ]
            },
        ),
        (None, {"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": '{"expres'}}]}}]}),
        (None, {"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": 'sion": "2+2"}'}}]}}]}),
        (None, {"choices": [{"delta": {}, "finish_reason": "tool_calls"}]}),
        (None, {"choices": [], "usage": {"prompt_tokens": 30, "completion_tokens": 9}}),
        (None, "[DONE]"),
    )
    captured: dict = {}
    chunks = await run(OpenAIProvider("k", ["gpt-4.1"], client=client_returning(body, captured=captured)), "gpt-4.1")
    assert chunks[0].text == "Sure. "
    assert chunks[-2].tool_calls == (ToolCall("call_A", "calculate", {"expression": "2+2"}),)
    assert chunks[-1].done and chunks[-1].output_tokens == 9

    sent = captured["json"]
    assert sent["tools"][0] == {"type": "function", "function": {"name": "calculate", **_desc_params()}}
    assistant, first_result = sent["messages"][2], sent["messages"][3]
    assert assistant["tool_calls"][1] == {
        "id": "c2",
        "type": "function",
        "function": {"name": "calculate", "arguments": '{"expression": "3+4"}'},
    }
    assert first_result == {"role": "tool", "tool_call_id": "c1", "content": '{"result": 84}'}


async def test_anthropic_tool_use():
    body = sse(
        ("message_start", {"type": "message_start", "message": {"usage": {"input_tokens": 40}}}),
        (
            "content_block_start",
            {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
        ),
        (
            "content_block_delta",
            {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "Ok."}},
        ),
        ("content_block_stop", {"type": "content_block_stop", "index": 0}),
        (
            "content_block_start",
            {
                "type": "content_block_start",
                "index": 1,
                "content_block": {"type": "tool_use", "id": "toolu_1", "name": "calculate", "input": {}},
            },
        ),
        (
            "content_block_delta",
            {
                "type": "content_block_delta",
                "index": 1,
                "delta": {"type": "input_json_delta", "partial_json": '{"expr'},
            },
        ),
        (
            "content_block_delta",
            {
                "type": "content_block_delta",
                "index": 1,
                "delta": {"type": "input_json_delta", "partial_json": 'ession": "6*7"}'},
            },
        ),
        ("content_block_stop", {"type": "content_block_stop", "index": 1}),
        (
            "message_delta",
            {"type": "message_delta", "delta": {"stop_reason": "tool_use"}, "usage": {"output_tokens": 12}},
        ),
        ("message_stop", {"type": "message_stop"}),
    )
    captured: dict = {}
    p = AnthropicProvider("k", ["claude-x"], client=client_returning(body, captured=captured))
    chunks = await run(p, "claude-x")
    assert chunks[0].text == "Ok."
    assert chunks[-2].tool_calls == (ToolCall("toolu_1", "calculate", {"expression": "6*7"}),)
    assert chunks[-1].input_tokens == 40 and chunks[-1].output_tokens == 12

    sent = captured["json"]
    assert sent["tools"] == [{"name": "calculate", **_desc(), "input_schema": CALC.parameters}]
    assistant, results = sent["messages"][1], sent["messages"][2]
    assert assistant["content"][0] == {"type": "text", "text": "Let me calculate."}
    assert assistant["content"][2] == {
        "type": "tool_use",
        "id": "c2",
        "name": "calculate",
        "input": {"expression": "3+4"},
    }
    # Both results of the round travel in ONE user turn.
    assert len(sent["messages"]) == 3
    assert results["role"] == "user"
    assert [b["tool_use_id"] for b in results["content"]] == ["c1", "c2"]


async def test_gemini_function_call_keeps_thought_signature():
    body = sse(
        (
            None,
            {
                "candidates": [
                    {
                        "content": {
                            "role": "model",
                            "parts": [
                                {
                                    "functionCall": {"name": "calculate", "args": {"expression": "9/3"}},
                                    "thoughtSignature": "SIG",
                                }
                            ],
                        }
                    }
                ],
                "usageMetadata": {"promptTokenCount": 20, "candidatesTokenCount": 5},
            },
        ),
    )
    captured: dict = {}
    p = GeminiProvider("k", ["gemini-x"], client=client_returning(body, captured=captured))
    chunks = await run(p, "gemini-x")
    call = chunks[-2].tool_calls[0]
    assert (call.name, call.arguments, call.extra) == ("calculate", {"expression": "9/3"}, {"thoughtSignature": "SIG"})

    # Sending the call back includes the signature; results become functionResponse parts in one turn.
    follow_up = [
        *HISTORY[:2],
        ChatMessage("assistant", "", tool_calls=(call,)),
        ChatMessage.from_tool_result(ToolResult(call.id, "calculate", '{"result": 3}')),
    ]
    captured.clear()
    p2 = GeminiProvider("k", ["gemini-x"], client=client_returning(sse((None, {"candidates": []})), captured=captured))
    await run(p2, "gemini-x", follow_up)
    contents = captured["json"]["contents"]
    assert contents[1] == {
        "role": "model",
        "parts": [{"functionCall": {"name": "calculate", "args": {"expression": "9/3"}}, "thoughtSignature": "SIG"}],
    }
    assert contents[2] == {
        "role": "user",
        "parts": [{"functionResponse": {"name": "calculate", "response": {"result": 3}}}],
    }
    assert captured["json"]["tools"][0]["functionDeclarations"][0]["name"] == "calculate"

    # Earlier history: two results in one round are merged; ids from the API are passed back.
    captured.clear()
    await run(
        GeminiProvider("k", ["gemini-x"], client=client_returning(sse((None, {"candidates": []})), captured=captured)),
        "gemini-x",
    )
    contents = captured["json"]["contents"]
    assert [p["functionResponse"]["id"] for p in contents[2]["parts"]] == ["c1", "c2"]


async def test_ollama_tool_calls():
    lines = [
        {
            "message": {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"function": {"name": "calculate", "arguments": {"expression": "1+1"}}}],
            },
            "done": False,
        },
        {"message": {"role": "assistant", "content": ""}, "done": True, "prompt_eval_count": 11, "eval_count": 4},
    ]
    body = ("\n".join(json.dumps(x) for x in lines) + "\n").encode()
    captured: dict = {}
    p = OllamaProvider("http://ollama:11434", ["llama3.1"], client=client_returning(body, captured=captured))
    assert Capability.TOOLS in p.models()[0].capabilities
    assert Capability.TOOLS not in OllamaProvider("http://x", ["llava"]).models()[0].capabilities
    chunks = await run(p, "llama3.1")
    assert chunks[-2].tool_calls[0].arguments == {"expression": "1+1"}
    sent = captured["json"]
    assert sent["messages"][2]["tool_calls"][0] == {
        "function": {"name": "calculate", "arguments": {"expression": "12*7"}}
    }
    assert sent["messages"][3] == {"role": "tool", "content": '{"result": 84}', "tool_name": "calculate"}


def _desc():
    return {"description": CALC.description}


def _desc_params():
    return {"description": CALC.description, "parameters": CALC.parameters}


# ------------------------------------------------------------------------- orchestrator loop


class ToolScriptProvider(Provider):
    """Round 1 asks for tools; round 2 answers using the results it was given."""

    name = "scripted"

    def __init__(self, rounds: list[list[StreamChunk]], tools: bool = True):
        super().__init__()
        self.rounds = rounds
        self.tools = tools
        self.seen: list[list[ChatMessage]] = []
        self.offered: list[tuple] = []

    def is_configured(self) -> bool:
        return True

    def models(self) -> list[ModelInfo]:
        caps = {Capability.CHAT, *([Capability.TOOLS] if self.tools else [])}
        return [ModelInfo(self.name, "m", "M", frozenset(caps), CostTier.LOW)]

    async def stream(
        self, model: str, messages: Sequence[ChatMessage], params: GenerationParams, tools=()
    ) -> AsyncIterator[StreamChunk]:
        self.seen.append(list(messages))
        self.offered.append(tuple(tools))
        for chunk in self.rounds[min(len(self.seen) - 1, len(self.rounds) - 1)]:
            yield chunk


async def test_orchestrator_runs_tools_and_feeds_results_back():
    p = ToolScriptProvider(
        [
            [
                StreamChunk(text="Checking. "),
                StreamChunk(tool_calls=(ToolCall("a", "calculate", {"expression": "2+3"}),)),
                StreamChunk(done=True, input_tokens=10, output_tokens=3),
            ],
            [StreamChunk(text="It is 5."), StreamChunk(done=True, input_tokens=15, output_tokens=4)],
        ]
    )
    ran = []

    async def runner(call: ToolCall) -> ToolResult:
        ran.append(call)
        return ToolResult(call.id, call.name, json.dumps({"result": 5}))

    out = [
        rc async for rc in Orchestrator([p]).stream_chat([ChatMessage("user", "2+3?")], tools=[CALC], run_tool=runner)
    ]
    assert "".join(rc.chunk.text for rc in out) == "Checking. It is 5."
    assert [c.name for c in ran] == ["calculate"]
    assert [r.content for rc in out for r in rc.tool_results] == ['{"result": 5}']
    final = out[-1].chunk
    assert final.done and final.input_tokens == 25 and final.output_tokens == 7
    assert sum(rc.chunk.done for rc in out) == 1
    second = p.seen[1]
    assert second[-2].tool_calls[0].id == "a" and second[-2].content == "Checking. "
    assert second[-1].role == "tool" and second[-1].tool_result.call_id == "a"
    assert p.offered[0] == (CALC,)


async def test_failing_tool_is_reported_to_the_model():
    p = ToolScriptProvider(
        [
            [StreamChunk(tool_calls=(ToolCall("a", "calculate", {}),)), StreamChunk(done=True)],
            [StreamChunk(text="Sorry, that failed."), StreamChunk(done=True)],
        ]
    )

    async def runner(call):
        raise RuntimeError("boom")

    out = [rc async for rc in Orchestrator([p]).stream_chat([ChatMessage("user", "x")], tools=[CALC], run_tool=runner)]
    result = next(r for rc in out for r in rc.tool_results)
    assert result.is_error and "boom" in result.content
    assert out[-2].chunk.text == "Sorry, that failed."


async def test_tool_rounds_are_capped():
    loop = [StreamChunk(tool_calls=(ToolCall("a", "calculate", {"expression": "1"}),)), StreamChunk(done=True)]
    p = ToolScriptProvider([loop])

    async def runner(call):
        return ToolResult(call.id, call.name, "{}")

    out = [rc async for rc in Orchestrator([p]).stream_chat([ChatMessage("user", "x")], tools=[CALC], run_tool=runner)]
    assert len(p.seen) == 6  # MAX_TOOL_ROUNDS + 1 model calls
    assert "stopped after several tool steps" in "".join(rc.chunk.text for rc in out)


@pytest.mark.parametrize("supports_tools", [False, True])
async def test_tools_only_offered_to_capable_models(supports_tools):
    p = ToolScriptProvider([[StreamChunk(text="hi"), StreamChunk(done=True)]], tools=supports_tools)

    async def runner(call):  # pragma: no cover - never called
        raise AssertionError

    [rc async for rc in Orchestrator([p]).stream_chat([ChatMessage("user", "x")], tools=[CALC], run_tool=runner)]
    assert p.offered[0] == ((CALC,) if supports_tools else ())
