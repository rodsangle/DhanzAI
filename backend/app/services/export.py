from __future__ import annotations

import re
from pathlib import Path
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


_FONTS = Path(__file__).resolve().parent.parent / "assets" / "fonts"


def render_pdf(conv: Conversation, messages: list[Message]) -> bytes:
    """Render a conversation as a PDF (code blocks in monospace).

    The bundled DejaVu fonts cover Latin, Greek, Cyrillic, Arabic, Hebrew and many symbols; Chinese,
    Japanese and Korean characters need an extra font and are currently left blank.
    """
    from fpdf import FPDF

    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_font("DejaVu", "", str(_FONTS / "DejaVuSans.ttf"))
    pdf.add_font("DejaVu", "B", str(_FONTS / "DejaVuSans-Bold.ttf"))
    pdf.add_font("DejaVuMono", "", str(_FONTS / "DejaVuSansMono.ttf"))
    pdf.set_title(conv.title)
    pdf.set_creator("DHANZ AI")
    pdf.add_page()
    width = pdf.epw

    pdf.set_font("DejaVu", "B", 16)
    pdf.multi_cell(width, 8, conv.title, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("DejaVu", "", 9)
    pdf.set_text_color(110, 110, 110)
    pdf.multi_cell(
        width,
        5,
        f"Exported from DHANZ AI · created {conv.created_at:%Y-%m-%d %H:%M} UTC",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.ln(4)

    for m in messages:
        if not m.content.strip():
            continue
        who = "You" if m.role == "user" else "Dhanz"
        meta = f" · {m.model}" if m.role == "assistant" and m.model else ""
        pdf.set_font("DejaVu", "B", 11)
        pdf.set_text_color(11, 26, 51) if m.role == "user" else pdf.set_text_color(160, 120, 20)
        pdf.multi_cell(width, 6, f"{who}{meta}", new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(0, 0, 0)
        for is_code, block in _split_code(m.content):
            if is_code:
                pdf.set_font("DejaVuMono", "", 8.5)
                pdf.set_fill_color(242, 244, 248)
                pdf.multi_cell(width, 4.5, block, fill=True, new_x="LMARGIN", new_y="NEXT")
            else:
                pdf.set_font("DejaVu", "", 10)
                pdf.multi_cell(width, 5.2, _plain(block), new_x="LMARGIN", new_y="NEXT")
        for c in m.citations or []:
            pdf.set_font("DejaVu", "", 8)
            pdf.set_text_color(90, 90, 90)
            pdf.multi_cell(
                width, 4.2, f"[{c.get('n')}] {c.get('title')} — {c.get('url')}", new_x="LMARGIN", new_y="NEXT"
            )
            pdf.set_text_color(0, 0, 0)
        pdf.ln(3)
    return bytes(pdf.output())


def _split_code(text: str) -> list[tuple[bool, str]]:
    parts: list[tuple[bool, str]] = []
    for i, block in enumerate(text.split("```")):
        if i % 2 == 1:  # inside a fence: drop the language tag line
            first, _, rest = block.partition("\n")
            block = rest if first.strip() and " " not in first.strip() else block
        block = block.strip("\n")
        if block.strip():
            parts.append((i % 2 == 1, block))
    return parts


_EMPHASIS = re.compile(r"(\*\*|__)(.+?)\1")


def _plain(text: str) -> str:
    """Drop Markdown emphasis markers that would otherwise print literally."""
    return _EMPHASIS.sub(r"\2", text)
