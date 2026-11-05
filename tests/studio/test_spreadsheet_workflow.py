import pytest

from app.assistant_studio import spreadsheet_workflow
from dhanz_ai import (
    Capability,
    ChatMessage,
    CostTier,
    ModelInfo,
    Orchestrator,
    Provider,
    StreamChunk,
    ToolCall,
    ToolResult,
    ToolSpec,
)


class Script(Provider):
    name = "workbook-script"

    def __init__(self, tool, finish_after=None):
        super().__init__()
        self.tool = tool
        self.finish_after = finish_after
        self.seen = 0

    def is_configured(self):
        return True

    def models(self):
        return [ModelInfo(self.name, "test", "Test", frozenset({Capability.CHAT, Capability.TOOLS}), CostTier.LOW)]

    async def stream(self, model, messages, params, tools=()):
        self.seen += 1
        if self.finish_after is not None and self.seen > self.finish_after:
            yield StreamChunk(text="Workbook download is attached.")
        else:
            yield StreamChunk(tool_calls=(ToolCall(str(self.seen), self.tool, {}),))
        yield StreamChunk(done=True, input_tokens=2, output_tokens=1)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "tool,error,finish,expected_calls,expected_runs",
    [
        ("excel_workbook", False, 8, 9, 8),
        ("excel_workbook", False, None, 13, 12),
        ("excel_workbook", True, None, 6, 5),
        ("calculate", False, None, 6, 5),
    ],
)
async def test_workbook_extension_is_bounded_and_other_workflows_unchanged(
    monkeypatch, tool, error, finish, expected_calls, expected_runs
):
    original = Orchestrator.stream_chat
    monkeypatch.setattr(Orchestrator, "stream_chat", original)
    spreadsheet_workflow.install()
    installed = Orchestrator.stream_chat
    spreadsheet_workflow.install()
    assert Orchestrator.stream_chat is installed
    provider = Script(tool, finish)
    executed = []

    async def runner(call):
        executed.append(call.id)
        return ToolResult(call.id, call.name, "{}", is_error=error)

    chunks = [
        chunk
        async for chunk in Orchestrator([provider]).stream_chat(
            [ChatMessage("user", "Format this workbook")],
            tools=[ToolSpec(tool, "Tool", {"type": "object", "properties": {}})],
            run_tool=runner,
        )
    ]
    assert provider.seen == expected_calls and len(executed) == expected_runs
    assert len(executed) == len(set(executed))
    assert sum(chunk.chunk.done for chunk in chunks) == 1
    assert chunks[-1].chunk.input_tokens == 2 * expected_calls
    text = "".join(chunk.chunk.text for chunk in chunks)
    if finish:
        assert "download is attached" in text and "limit" not in text
    elif tool == "excel_workbook" and not error:
        assert "workbook task is unfinished" in text
    else:
        assert "stopped after several tool steps" in text


def test_unknown_orchestrator_is_not_silently_replaced(monkeypatch):
    async def unsupported(self):
        yield None

    monkeypatch.setattr(Orchestrator, "stream_chat", unsupported)
    with pytest.raises(ValueError, match="Unsupported live"):
        spreadsheet_workflow.install()
    assert Orchestrator.stream_chat is unsupported
