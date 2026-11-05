"""Expose existing grants to chat; never expose permission-creation tools."""

import uuid

from fastapi import HTTPException
from sqlalchemy import select

from . import operations_service as service
from .operations_models import OperationGrant, OperationJob

_DHANZ_OPERATIONS_CHAT_VERSION = 2


def request_key(ctx, grant_id):
    """One execution per grant per assistant reply, independent of model arguments.

    The persisted reply ID survives context reconstruction. Older contexts without
    that field share a random key on the same context object for the reply.
    """
    reply = getattr(ctx, "assistant_message_id", None)
    if reply is not None:
        identity = f"dhanz-operation:{ctx.user_id}:{ctx.conversation_id}:{reply}:{grant_id}"
        return "chat_" + uuid.uuid5(uuid.NAMESPACE_URL, identity).hex
    keys = getattr(ctx, "_dhanz_operation_keys", None)
    if keys is None:
        keys = {}
        ctx._dhanz_operation_keys = keys
    identity = (str(ctx.user_id), str(ctx.conversation_id), str(grant_id))
    return keys.setdefault(identity, "chat_" + uuid.uuid4().hex)


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
            key = request_key(ctx, identifier)
            async with ctx.maker() as db:
                row = await service.enqueue(db, ctx.user_id, identifier, key)
                return tools.ToolOutcome(service.public(row), "Queued authorized server task")
        except (HTTPException, ValueError) as exc:
            raise tools.ToolInputError(str(exc.detail) if isinstance(exc, HTTPException) else str(exc)) from None

    tools.TOOLS["connected_operations"] = tools.Tool(
        ToolSpec(
            "connected_operations",
            "List this user's standing permissions and actual server task results. "
            "For AWS/server health, restart or approved deployment requests, check these connections before "
            "asking for instance IDs or AWS CLI details. "
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
            "No extra approval is needed within that grant. The server generates internal request keys; "
            "never ask the user for one. Repeated calls for this grant in the same reply return the same task. "
            "If an outcome is uncertain, inspect connected_operations; do not start another reply to retry it. "
            "No arbitrary commands or arguments are accepted.",
            {
                "type": "object",
                "properties": {"grant_id": {"type": "string"}},
                "required": ["grant_id"],
                "additionalProperties": False,
            },
        ),
        "Running authorized server task",
        run,
    )
