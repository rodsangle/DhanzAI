"""A manual Update click authorizes one named task on the user's paired server."""

import asyncio
import uuid
from datetime import timedelta

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import CurrentUser, DbDep
from app.core import rate_limit
from app.db.base import utcnow

from . import operations_service as operations
from .operations_models import OperationGrant, OperationJob, OperationServer
from .web_release import fetch_release

router = APIRouter(prefix="/operations/web-updates", tags=["web-updates"])
TASK = "update_web"


async def latest():
    try:
        return await asyncio.to_thread(fetch_release)
    except Exception:
        raise HTTPException(503, "GitHub web-release check failed. Your installed app was not changed.") from None


def recipe(server):
    return next((t for t in server.tasks if t["name"] == TASK), None)


@router.get("")
async def check(user: CurrentUser, db: DbDep):
    await rate_limit.enforce("web-update-check:" + str(user.id), 30)
    release = await latest()
    servers = list(
        await db.scalars(
            select(OperationServer).where(OperationServer.user_id == user.id, OperationServer.revoked.is_(False))
        )
    )
    available = [
        {
            "id": str(server.id),
            "name": server.name,
            "online": bool(server.last_seen and server.last_seen > utcnow() - timedelta(minutes=2)),
        }
        for server in servers
        if recipe(server)
    ]
    return {
        "release": release,
        "servers": available,
        "detail": "Update installs the latest GitHub web build on your paired host, then refreshes this app.",
    }


class Start(BaseModel):
    server_id: uuid.UUID
    request_key: str = Field(pattern=r"^[A-Za-z0-9_-]{16,64}$")


@router.post("", status_code=202)
async def start(body: Start, user: CurrentUser, db: DbDep):
    await rate_limit.enforce("web-update-start:" + str(user.id), 10)
    # Lock the owned host so two devices cannot enqueue concurrent web replacements.
    server = await db.scalar(
        select(OperationServer)
        .where(
            OperationServer.id == body.server_id, OperationServer.user_id == user.id, OperationServer.revoked.is_(False)
        )
        .with_for_update()
    )
    if server is None:
        raise HTTPException(404, "Paired update server not found.")
    task = recipe(server)
    if not task:
        raise HTTPException(409, "Enable the web-update recipe on this server first.")
    key = "web_update_" + body.request_key
    previous = await db.scalar(
        select(OperationJob).where(OperationJob.user_id == user.id, OperationJob.request_key == key)
    )
    if previous:
        if previous.server_id != server.id or previous.task != TASK:
            raise HTTPException(409, "This request key belongs to a different task.")
        return operations.public(previous)
    pending = await db.scalar(
        select(OperationJob)
        .where(
            OperationJob.server_id == server.id,
            OperationJob.task == TASK,
            OperationJob.status.in_(["queued", "executing"]),
        )
        .order_by(OperationJob.created_at.desc())
    )
    if pending:
        return operations.public(pending)
    # The authenticated manual button click is the one-shot authorization. Models
    # have no tool for this endpoint and no permanent grant is silently enabled.
    grant = OperationGrant(
        user_id=user.id,
        kind="server_task",
        target=str(server.id),
        scope={"task": TASK, "manifest_hash": task["manifest_hash"], "description": task["description"]},
        remaining=1,
        expires_at=utcnow() + timedelta(minutes=5),
    )
    db.add(grant)
    await db.flush()
    return operations.public(await operations.enqueue(db, user.id, grant.id, key))


@router.get("/jobs/{identifier}")
async def status(identifier: uuid.UUID, user: CurrentUser, db: DbDep):
    job = await operations.owned(db, OperationJob, user.id, identifier)
    if job.task != TASK:
        raise HTTPException(404, "Web update task not found.")
    return operations.public(job)


def install(app):
    app.include_router(router, prefix=app.state.settings.api_prefix)
