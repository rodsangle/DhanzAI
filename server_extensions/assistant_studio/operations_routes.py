import secrets
import uuid
from datetime import timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.api.deps import CurrentUser, DbDep, SettingsDep
from app.db.base import utcnow
from app.services import github_service as gh

from . import coding_service as coding
from . import operations_service as service
from .operations_models import OperationGrant, OperationJob, OperationServer

router = APIRouter(prefix="/operations", tags=["connected-operations"])
ServerToken = Annotated[str, Header(alias="X-Dhanz-Server-Token", min_length=40, max_length=200)]


class PairInput(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class Recipe(BaseModel):
    name: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,59}$")
    description: str = Field(min_length=1, max_length=300)
    manifest_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class Heartbeat(BaseModel):
    tasks: list[Recipe] = Field(max_length=12)


class GrantInput(BaseModel):
    kind: Literal["github_publish", "server_task"]
    target: str = Field(min_length=1, max_length=200)
    task: str = Field(default="", max_length=60)
    branch: str = Field(default="", max_length=200)
    hours: int = Field(default=24, ge=1, le=168)
    uses: int = Field(default=10, ge=1, le=100)
    authorize: Literal[True]


class RunInput(BaseModel):
    grant_id: uuid.UUID
    request_key: str = Field(pattern=r"^[A-Za-z0-9_-]{16,100}$")


class ResultInput(BaseModel):
    status: Literal["completed", "failed", "uncertain"]


@router.get("")
async def overview(user: CurrentUser, db: DbDep):
    result = {}
    for name, model in (("servers", OperationServer), ("grants", OperationGrant), ("jobs", OperationJob)):
        rows = await db.scalars(
            select(model).where(model.user_id == user.id).order_by(model.created_at.desc()).limit(100)
        )
        result[name] = [service.public(row) for row in rows]
    return result


@router.post("/servers", status_code=201)
async def pair(body: PairInput, user: CurrentUser, db: DbDep):
    count = len(
        list(
            await db.scalars(
                select(OperationServer.id).where(OperationServer.user_id == user.id, OperationServer.revoked.is_(False))
            )
        )
    )
    if count >= 5:
        raise HTTPException(409, "Disconnect an old server before pairing another.")
    token = secrets.token_urlsafe(48)
    row = OperationServer(user_id=user.id, name=body.name.strip(), token_hash=service.token_hash(token))
    db.add(row)
    await db.commit()
    return {"server": service.public(row), "token": token}


@router.post("/servers/{identifier}/revoke")
async def disconnect(identifier: uuid.UUID, user: CurrentUser, db: DbDep):
    row = await service.owned(db, OperationServer, user.id, identifier)
    row.revoked = True
    await db.execute(
        update(OperationJob)
        .where(
            OperationJob.server_id == row.id,
            OperationJob.status == "queued",
        )
        .values(status="cancelled", detail="Server disconnected before execution.", finished_at=utcnow())
    )
    await db.commit()
    return {"status": "revoked"}


@router.post("/grants", status_code=201)
async def grant(body: GrantInput, user: CurrentUser, db: DbDep, settings: SettingsDep):
    if body.kind == "server_task":
        try:
            identifier = uuid.UUID(body.target)
        except ValueError:
            raise HTTPException(422, "Select a paired server.") from None
        server = await service.owned(db, OperationServer, user.id, identifier)
        recipe = next((t for t in server.tasks if t["name"] == body.task), None)
        if server.revoked or recipe is None:
            raise HTTPException(409, "Connect the server companion and select an advertised task.")
        target = str(server.id)
        scope = {"task": recipe["name"], "manifest_hash": recipe["manifest_hash"], "description": recipe["description"]}
    else:
        try:
            target = gh.repository_name(body.target)
            _, metadata, reader = await coding.context(db, settings, user.id, target)
            branch = body.branch or metadata["default_branch"]
            from urllib.parse import quote

            await reader.get("/repos/" + target + "/commits/" + quote(branch, safe=""))
            scope = {"branch": branch, "repository_id": metadata["id"], "draft_pr_only": True}
        except gh.GitHubError as exc:
            raise HTTPException(exc.status, str(exc)) from None
    row = OperationGrant(
        user_id=user.id,
        kind=body.kind,
        target=target,
        scope=scope,
        remaining=body.uses,
        expires_at=utcnow() + timedelta(hours=body.hours),
    )
    db.add(row)
    await db.commit()
    return service.public(row)


@router.post("/grants/{identifier}/revoke")
async def revoke(identifier: uuid.UUID, user: CurrentUser, db: DbDep):
    row = await service.owned(db, OperationGrant, user.id, identifier)
    row.revoked = True
    await db.execute(
        update(OperationJob)
        .where(
            OperationJob.grant_id == row.id,
            OperationJob.status == "queued",
        )
        .values(status="cancelled", detail="Permission revoked before execution.", finished_at=utcnow())
    )
    await db.commit()
    return service.public(row)


@router.post("/run", status_code=202)
async def run(body: RunInput, user: CurrentUser, db: DbDep):
    try:
        return service.public(await service.enqueue(db, user.id, body.grant_id, body.request_key))
    except IntegrityError:
        await db.rollback()
        existing = await db.scalar(
            select(OperationJob).where(OperationJob.user_id == user.id, OperationJob.request_key == body.request_key)
        )
        if existing and existing.grant_id == body.grant_id:
            return service.public(existing)
        raise HTTPException(409, "Another task is being queued. Refresh before retrying.") from None


@router.post("/companion/heartbeat")
async def heartbeat(body: Heartbeat, token: ServerToken, db: DbDep):
    server = await service.server_auth(db, token)
    if len({t.name for t in body.tasks}) != len(body.tasks):
        raise HTTPException(422, "Recipe names must be unique.")
    server.tasks = [t.model_dump() for t in body.tasks]
    server.last_seen = utcnow()
    await db.commit()
    return {"status": "ok"}


@router.post("/companion/claim")
async def claim(token: ServerToken, db: DbDep):
    return {"job": await service.claim(db, await service.server_auth(db, token))}


@router.post("/companion/jobs/{identifier}/result")
async def report(identifier: uuid.UUID, body: ResultInput, token: ServerToken, db: DbDep):
    server = await service.server_auth(db, token)
    job = await db.scalar(
        select(OperationJob).where(OperationJob.id == identifier, OperationJob.server_id == server.id)
    )
    if job is None:
        raise HTTPException(404, "Task not found")
    if job.status == body.status:
        return service.public(job)
    if job.status not in {"executing", "uncertain"}:
        raise HTTPException(409, "Task is not awaiting a result.")
    job.status = body.status
    job.detail = "Companion reported " + body.status + ". Command output was kept on the server."
    job.finished_at = utcnow()
    await db.commit()
    return service.public(job)
