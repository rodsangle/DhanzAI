from __future__ import annotations

from typing import Literal

from app.models import Conversation, Message


def render_conversation(conv: Conversation, messages: list[Message], fmt: Literal["markdown", "txt"]) -> str:
    shown = [m for m in messages if m.content.strip()]
    if fmt == "markdown":
        lines = [f"# {conv.title}", "", f"_Exported from DHANZ AI · created {conv.created_at:%Y-%m-%d %H:%M} UTC_", ""]
        for m in shown:
            who = "You" if m.role == "user" else "Dhanz"
            meta = f" · {m.model}" if m.role == "assistant" and m.model else ""
            lines += [f"### {who}{meta}", "", m.content, ""]
        return "\n".join(lines)
    lines = [conv.title, "=" * len(conv.title), ""]
    for m in shown:
        lines += [f"[{m.created_at:%Y-%m-%d %H:%M}] {'You' if m.role == 'user' else 'Dhanz'}:", m.content, ""]
    return "\n".join(lines)
