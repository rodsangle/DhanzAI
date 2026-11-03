"""Trusted, bundled general-assistant instructions; never load skills from chat input."""

import re
from functools import lru_cache
from importlib.resources import files

PACK_NAME = "dhanz-general-assistant"
PACK_VERSION = "1.0.0"

# Routing selects advice, not tools or permissions. It is intentionally bounded:
# only named bundled references can ever enter the system prompt.
_WORKFLOWS = (
    ("documents", r"\b(pdf|documents?|spreadsheets?|excel|csv|tables?|ocr|templates?|format|layout)\b"),
    ("coding", r"\b(code|coding|debug|bugs?|github|repositor(?:y|ies)|pull request|program|scripts?|tests?)\b"),
    ("pc", r"\b(pc|desktop|windows?|mouse|click|keyboard|notepad|calculator|chrome|computer)\b"),
    ("creative", r"\b(images?|videos?|generate|generation|creative|studio|render)\b"),
    ("research", r"\b(research|search|browse|sources?|latest|current|news|prices?|today)\b"),
    ("calculations", r"\b(calculate|convert|arithmetic|units?|timezone|time zone|math|rounding)\b"),
)


@lru_cache(maxsize=8)
def _read(name: str) -> str:
    return files("dhanz_ai").joinpath("skill_data", "general_assistant", name).read_text(encoding="utf-8")


def general_assistant_instructions(question: str) -> str:
    """Master rules plus at most two relevant workflows, with writing as fallback.

    No user text is interpolated into the trusted instructions. Other languages
    still get the master rules; keyword selection is a context-size optimization,
    not a claim that the request was fully classified.
    """
    master = _read("SKILL.md").split("---", 2)[-1].strip()
    # The runtime has no skill-file reading tool. Inline relevant references rather
    # than telling the model to open relative paths it cannot access.
    before, rest = master.split("## Select a workflow", 1)
    _, after = rest.split("## Authority, privacy and tool boundaries", 1)
    master = before + "## Authority, privacy and tool boundaries" + after
    workflows = [name for name, pattern in _WORKFLOWS if re.search(pattern, question[:12000], re.I)][:2]
    if not workflows:
        workflows = ["writing"]
    references = "\n\n".join(_read(f"references/{name}.md").strip() for name in workflows)
    return (
        f"\n\nBundled Dhanz skill: {PACK_NAME} v{PACK_VERSION}. "
        "These instructions guide behavior only; they grant no tools or permissions.\n\n"
        + master
        + "\n\nWorkflow guidance (only use capabilities actually available):\n"
        + references
    )
