"""Narrow, side-effect-free commands that do not need a model to interpret them."""

import re

from app.services.assistant_tools import ToolInputError, convert, evaluate

_CALCULATE = re.compile(r"(?:calculate|what is)\s+(.+?)\??", re.I)
_CONVERT = re.compile(r"convert\s+(-?\d+(?:\.\d+)?)\s+([\w°]+)\s+to\s+([\w°]+)\??", re.I)


def direct_answer(text: str) -> tuple[str, str] | None:
    """Return a tool name and answer only for a complete, independently valid command.

    No history-dependent interpretation, arbitrary code, external actions or writes.
    Invalid or ambiguous input remains on the normal model path.
    """
    text = text.strip()
    if len(text) > 300:
        return None
    try:
        if match := _CALCULATE.fullmatch(text):
            expression = match[1]
            return "calculate", f"{expression} = {evaluate(expression)}"
        if match := _CONVERT.fullmatch(text):
            value, source, target = float(match[1]), match[2], match[3]
            result = convert(value, source, target)
            return "convert_units", f"{value:g} {source} = {result:.10g} {target}"
    except (ToolInputError, TypeError, RecursionError):
        return None
    return None
