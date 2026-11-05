"""Expose existing grants to chat; never expose permission-creation tools."""

import uuid

from fastapi import HTTPException
from sqlalchemy import select

from . import operations_service as service
from .operations_models import OperationGrant, OperationJob


def install_tools():
    from app.services import assistant_tools as tools
    from dhanz_ai import ToolSpec

    async def catalog(ctx, args):
        async with ctx.maker() as db:
            grants = list(await db.scalars(select(OperationGrant).where(OperationGrant.user_id == ctx.user_id)))
            jobs = list(
                await db.scalars(
                    select(OperationJob)
                    .where(OperationJob.user_id == ctx.user_id)
                    .order_by(OperationJob.created_at.desc())
                    .limit(10)
                )
            )
            return tools.ToolOutcome(
                {
                    "permissions": [service.public(g) for g in grants if service.active(g)],
                    "recent_tasks": [service.public(j) for j in jobs],
                },
                "Checked connected operations",
            )

    async def run(ctx, args):
        try:
            identifier = uuid.UUID(str(args.get("grant_id", "")))
            key = str(args.get("request_key", ""))
            import re

            if not re.fullmatch(r"[A-Za-z0-9_-]{16,100}", key):
                raise ValueError("Use a unique request key of 16–100 letters, digits, underscores or hyphens.")
            async with ctx.maker() as db:
                row = await service.enqueue(db, ctx.user_id, identifier, key)
                return tools.ToolOutcome(service.public(row), "Queued authorized server task")
        except (HTTPException, ValueError) as exc:
            raise tools.ToolInputError(str(exc.detail) if isinstance(exc, HTTPException) else str(exc)) from None

    tools.TOOLS["connected_operations"] = tools.Tool(
        ToolSpec(
            "connected_operations",
            "List this user's standing permissions and actual server task results. "
            "Never claim a queued task completed. Permissions are configured by the user in Connected operations.",
            {"type": "object", "properties": {}, "additionalProperties": False},
        ),
        "Checking connected operations",
        catalog,
    )
    tools.TOOLS["run_connected_task"] = tools.Tool(
        ToolSpec(
            "run_connected_task",
            "Run a named server recipe under an existing user-approved standing permission. "
            "First list connected_operations. Choose only a matching active server_task grant for the user's task. "
            "No extra approval is needed within that grant. Reuse the request_key if the outcome is uncertain; "
            "never submit a new key to retry the same action. No arbitrary commands or arguments are accepted.",
            {
                "type": "object",
                "properties": {"grant_id": {"type": "string"}, "request_key": {"type": "string"}},
                "required": ["grant_id", "request_key"],
                "additionalProperties": False,
            },
        ),
        "Running authorized server task",
        run,
    )
