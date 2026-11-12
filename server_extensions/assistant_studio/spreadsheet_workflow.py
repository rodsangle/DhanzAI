"""Extend only successful Excel workflows, retaining the live orchestrator implementation."""

import inspect
import textwrap


def install():
    import dhanz_ai.orchestrator as runtime

    original = runtime.Orchestrator.stream_chat
    if getattr(original, "_dhanz_workbook_rounds", False):
        return
    source = textwrap.dedent(inspect.getsource(original))
    replacements = {
        "for round_no in range(MAX_TOOL_ROUNDS + 1):": "tool_round_limit = MAX_TOOL_ROUNDS\n"
        "for round_no in range(max(MAX_TOOL_ROUNDS, 12) + 1):",
        "if round_no == MAX_TOOL_ROUNDS:": "if round_no >= tool_round_limit:",
        "results = tuple([await _run(run_tool, c) for c in calls])": (
            "results = tuple([await _run(run_tool, c) for c in calls])\n"
            'if any(c.name == "excel_workbook" and not r.is_error for c, r in zip(calls, results)):\n'
            "    tool_round_limit = max(MAX_TOOL_ROUNDS, 12)"
        ),
        "yield RoutedChunk(info, StreamChunk(text=note))": "if tool_round_limit > MAX_TOOL_ROUNDS:\n"
        '    note = ("\\n\\nThe workbook workflow reached its tool-step limit. "\n'
        '            "Use a workbook download already attached to this reply, if present. "\n'
        '            "If none is attached, the workbook task is unfinished.")\n'
        "yield RoutedChunk(info, StreamChunk(text=note))",
    }
    for anchor, replacement in replacements.items():
        if source.count(anchor) != 1:
            raise ValueError("Unsupported live workbook tool-loop interface. No orchestrator was replaced.")
        prefix = source[: source.index(anchor)].rsplit("\n", 1)[-1]
        if prefix.strip():
            raise ValueError("Unexpected inline orchestrator statement. Nothing replaced.")
        source = source.replace(anchor, replacement.replace("\n", "\n" + prefix))
    namespace = {}
    # Compile only trusted, locally installed Python source with exact interface guards.
    # Keep its existing globals/providers/fallback/cancellation behavior; no user code is evaluated.
    exec(compile(source, "<dhanz-workbook-rounds>", "exec"), original.__globals__, namespace)  # noqa: S102
    updated = namespace["stream_chat"]
    updated._dhanz_workbook_rounds = True
    runtime.Orchestrator.stream_chat = updated
