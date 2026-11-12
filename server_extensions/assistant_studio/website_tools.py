"""Resolve explicitly requested websites without guessing domains or opening popups."""

import functools
import re
import sys
from urllib.parse import urlsplit, urlunsplit

SITES = {
    "sortly": "https://www.sortly.com/",
    "google": "https://www.google.com/",
    "github": "https://github.com/",
    "youtube": "https://www.youtube.com/",
}


def destination(value):
    value = str(value).strip()
    if value.lower() in SITES:
        return SITES[value.lower()]
    if any(c.isspace() or ord(c) < 32 for c in value) or "\\" in value:
        raise ValueError("Provide the website name or its exact HTTPS address.")
    if "://" not in value:
        if "." not in value:
            raise ValueError("Unknown website name. Ask for its exact address instead of guessing a domain.")
        value = "https://" + value
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Use an HTTPS website address without embedded credentials.")
    if parsed.port not in (None, 443):
        raise ValueError("Use the public HTTPS website address.")
    return urlunsplit(parsed)


def install():
    from app.services import assistant_tools as tools
    from dhanz_ai import ToolSpec

    async def prepare(ctx, args):
        try:
            url = destination(args.get("website", ""))
        except ValueError as exc:
            raise tools.ToolInputError(str(exc)) from None
        return tools.ToolOutcome(
            {
                "url": url,
                "opened": False,
                "note": "A real Open website button is attached. The user clicks it on their current device; do not claim the website has opened or been read.",  # noqa: E501 - tool descriptions and prompt guidance
            },
            "Website ready to open",
            {"type": "open_website", "url": url},
        )

    tools.TOOLS["open_website"] = tools.Tool(
        ToolSpec(
            "open_website",
            "Prepare an Open website button on the current device for an explicit user request such as open Sortly. Accept a known website name or exact HTTPS URL. Does not browse, sign in, click inside websites, or control a paired PC.",  # noqa: E501 - tool descriptions and prompt guidance
            {
                "type": "object",
                "properties": {"website": {"type": "string"}},
                "required": ["website"],
                "additionalProperties": False,
            },
        ),
        "Preparing website",
        prepare,
    )
    chat = sys.modules.get("app.services.chat_service")
    pc_parser = getattr(chat, "requested_pc_action", None)
    if pc_parser and not getattr(pc_parser, "_website_default_device", False):

        @functools.wraps(pc_parser)
        def pc_action(question):
            action = pc_parser(question)
            explicit_pc = re.search(r"\b(?:my|paired|windows|rog)\s+(?:pc|computer|laptop)\b", question, re.I)
            if action and action.get("operation") == "open_url" and not explicit_pc:
                return None
            return action

        pc_action._website_default_device = True
        chat.requested_pc_action = pc_action
    original = getattr(chat, "build_system_prompt", None)
    if original and not getattr(original, "_website_opening", False):

        @functools.wraps(original)
        def prompt(*args, **kwargs):
            text = original(*args, **kwargs)
            if kwargs.get("tools"):
                text += "\nFor an explicit request to open a website on this device, call open_website. Sortly resolves to https://www.sortly.com/. Include its exact HTTPS address as a clickable link too. Tell the user to tap the attached Open website button; browser popup policies require that click. Do not give a blanket refusal or claim a site opened/read before it did. If the user explicitly asks for the paired Windows PC instead, use propose_action provider=windows operation=open_url and its existing review/local approval workflow. Never infer login, browsing or editing permissions from a request merely to open a website."  # noqa: E501 - tool descriptions and prompt guidance
            return text

        prompt._website_opening = True
        chat.build_system_prompt = prompt
