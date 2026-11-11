"""Start account-owned app/agent projects from ordinary chat."""

import functools
import sys
import uuid

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select

GUIDANCE = (
    "\nUse build_app for requests to create a new app or agent, rather than only describing how. "
    "Carry the user's requirements from the conversation into instructions. For mobile apps choose Flutter; "
    "for websites choose web; for Python agents choose python. Explain important choices with short options "
    "and tradeoffs in chat. If a compatible demo can be built now, start it while asking for integration details. "
    "When vehicle make/model/year or connected hardware is unknown, build a clearly labeled simulated prototype "
    "and ask for those details before real integration. Never claim vehicle actions or GPS are real in demo mode. "
    "Use actual tool status: queued is not complete. Completed source files are downloadable in the sidebar's "
    "App & agent builder. Do not claim an APK, tests, installation, deployment or an automatic follow-up message. "
    "Use the Simulator card to open the right sidebar; revise with project_id and instructions to update "
    "a completed app using its existing source. Keep unrelated features. A revision is a new project, "
    "and must not be claimed ready until complete. "
    "Check build_app status when the user asks about progress; do not repeatedly poll in one reply. "
    "Use github_workspace instead for changes to an existing repository. Provider API usage charges apply."
)


def build_instructions(instructions, runtime):
    if runtime == "flutter":
        return (
            "[DHANZ_RUNTIME:flutter]\n"
            "Create a Flutter mobile starter with pubspec.yaml, lib/main.dart, supporting Dart files, "
            "README.md and an interactive simulator/index.html browser companion. Include exact Flutter SDK setup, "
            "platform-scaffold and Android build instructions. "
            "Use a provider/service interface; external hardware or APIs unavailable to this project must use "
            "an explicitly labeled demo implementation. Demo state must never imply a real command succeeded. "
            "Vehicle commands must use an authorized compatible manufacturer or hardware API in a future "
            "real adapter; no immobilizer bypass or unverified engine commands. Vehicle GPS must not be "
            "confused with the phone's location. Use placeholders, never credentials. Do not claim an APK "
            "was compiled. User requirements:\n" + instructions
        )
    return instructions


def install(app=None):
    from app.services import assistant_tools as tools
    from dhanz_ai import ToolSpec

    if app is not None:
        from .app_simulator import router

        app.include_router(router, prefix=app.state.settings.api_prefix)

    async def run(ctx, args):
        from app.models import User

        from . import builder, routes
        from .models import BuilderProject
        from .operations_tools import request_key

        try:
            if ctx.settings is None:
                raise ValueError("The server's app builder is unavailable.")
            operation = args.get("operation")
            async with ctx.maker() as db:
                user = await db.get(User, ctx.user_id)
                if user is None or not user.is_active:
                    raise ValueError("Sign in with an active account.")
                if operation == "status":
                    row = await routes.owned_project(db, user, uuid.UUID(str(args.get("project_id", ""))))
                    project = routes.public(row)
                elif operation == "revise":
                    from .app_simulator import queue_revision

                    identifier = uuid.UUID(str(args.get("project_id", "")))
                    changes = args.get("instructions", "")
                    if not isinstance(changes, str) or not 5 <= len(changes) <= 8000:
                        raise ValueError("Describe the changes (5–8000 characters).")
                    project = await queue_revision(
                        identifier,
                        changes,
                        request_key(ctx, "app-builder-revise:" + str(identifier)),
                        user,
                        db,
                        ctx.settings,
                    )
                elif operation == "models":
                    names = [] if user.routing_policy == "local_only" else await builder.models(ctx.settings)
                    return tools.ToolOutcome({"models": names}, "Checked app-building models")
                elif operation == "start":
                    key = request_key(ctx, "app-builder")
                    row = await db.scalar(
                        select(BuilderProject).where(
                            BuilderProject.user_id == user.id, BuilderProject.request_key == key
                        )
                    )
                    if row is not None:
                        project = routes.public(row)
                    else:
                        if user.routing_policy == "local_only":
                            raise ValueError("External app generation is disabled in local-only mode.")
                        runtime = args.get("runtime", "web")
                        if runtime not in ("web", "flutter", "python"):
                            raise ValueError("Choose web, flutter or python.")
                        instructions = args.get("instructions", "")
                        if not isinstance(instructions, str) or not 5 <= len(instructions) <= 10000:
                            raise ValueError("Provide the requested app requirements (5–10000 characters).")
                        names = await builder.models(ctx.settings)
                        model = args.get("model") or (names[0] if names else "")
                        if model not in names:
                            raise ValueError(
                                "No matching app-building model is available; check models and API access."
                            )
                        body = routes.BuildRequest(
                            name=args.get("title", "New app"),
                            kind="agent" if runtime == "python" else "app",
                            prompt=build_instructions(instructions, runtime),
                            model=model,
                            request_key=key,
                        )
                        project = await routes.create_project(body, user, db, ctx.settings)
                else:
                    raise ValueError("Choose start, revise, status or models.")
                return tools.ToolOutcome(
                    {
                        "project": project,
                        "workspace": "App & agent builder",
                        "source_ready": project["status"] == "complete",
                        "note": "Open App & agent builder in the sidebar to view/download completed source. "
                        "Queued/running work is not finished. No APK was built or deployed.",
                    },
                    "App project: " + project["status"],
                    {"type": "app_project", "id": project["id"], "name": project["name"]}
                    if project["kind"] == "app"
                    else None,
                )
        except (ValueError, ValidationError, HTTPException, builder.BuildError) as exc:
            detail = str(exc.detail) if isinstance(exc, HTTPException) else str(exc)
            raise tools.ToolInputError(detail) from None

    tools.TOOLS["build_app"] = tools.Tool(
        ToolSpec(
            "build_app",
            GUIDANCE.strip(),
            {
                "type": "object",
                "required": ["operation"],
                "additionalProperties": False,
                "properties": {
                    "operation": {"type": "string", "enum": ["models", "start", "revise", "status"]},
                    "runtime": {"type": "string", "enum": ["web", "flutter", "python"]},
                    "instructions": {"type": "string", "maxLength": 10000},
                    "title": {"type": "string", "maxLength": 100},
                    "model": {"type": "string"},
                    "project_id": {"type": "string"},
                },
            },
        ),
        "Building an app",
        run,
    )
    chat = sys.modules.get("app.services.chat_service")
    original = getattr(chat, "build_system_prompt", None)
    if original and not getattr(original, "_app_builder_guidance", False):

        @functools.wraps(original)
        def prompt(*args, **kwargs):
            text = original(*args, **kwargs)
            if kwargs.get("tools"):
                text += GUIDANCE
            return text

        prompt._app_builder_guidance = True
        chat.build_system_prompt = prompt
