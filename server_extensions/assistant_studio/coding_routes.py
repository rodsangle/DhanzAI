import uuid
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.deps import CurrentUser, DbDep, SettingsDep
from app.core import rate_limit
from app.services import github_service as gh

from . import builder
from . import coding_service as service
from .coding_models import CodingDraft

router = APIRouter(prefix="/coding", tags=["coding-workspace"])


class DraftInput(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    instructions: str = Field(min_length=5, max_length=12000)
    model: str = Field(min_length=1, max_length=200)
    request_key: str = Field(min_length=16, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    repository: str = Field(default="", max_length=140)
    base_branch: str = Field(default="", max_length=200)
    paths: list[str] = Field(default_factory=list, max_length=12)
    project_id: uuid.UUID | None = None
    kind: Literal["app", "agent"] = "app"
    workdir: str = Field(default="", max_length=200)
    runtime: Literal["python", "web", "flutter"] = "web"
    auto_repair: bool = False


class CodeFile(BaseModel):
    path: str = Field(max_length=160)
    content: str = Field(max_length=150000)


class ReviewInput(BaseModel):
    files: list[CodeFile] | None = Field(default=None, min_length=1, max_length=32)


class PublishInput(BaseModel):
    review_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


@router.get("/repositories")
async def repositories(user: CurrentUser, db: DbDep, settings: SettingsDep):
    try:
        return await gh.read(db, settings, user.id, "repositories")
    except gh.GitHubError as exc:
        raise HTTPException(exc.status, str(exc)) from None


@router.get("/source")
async def source(
    user: CurrentUser,
    db: DbDep,
    settings: SettingsDep,
    repository: str = Query(max_length=140),
    path: str = Query(default="", max_length=1000),
    ref: str = Query(default="", max_length=200),
    operation: Literal["directory", "file"] = "directory",
):
    try:
        return await gh.read(db, settings, user.id, operation, repository, path, ref)
    except gh.GitHubError as exc:
        raise HTTPException(exc.status, str(exc)) from None


@router.post("/drafts", status_code=201)
async def create(body: DraftInput, user: CurrentUser, db: DbDep, settings: SettingsDep):
    await rate_limit.enforce("coding:" + str(user.id), 5)
    try:
        row = await service.queue_draft(db, settings, user, body)
        return await service.public(db, row, True)
    except gh.GitHubError as exc:
        raise HTTPException(exc.status, str(exc)) from None
    except builder.BuildError as exc:
        raise HTTPException(400, builder.failure_message(exc)) from None
    except IntegrityError:
        await db.rollback()
        row = await db.scalar(
            select(CodingDraft).where(CodingDraft.user_id == user.id, CodingDraft.request_key == body.request_key)
        )
        if row is None:
            raise HTTPException(409, "Another coding request is being handled; refresh before retrying.") from None
        return await service.public(db, row, True)


@router.get("/drafts")
async def drafts(user: CurrentUser, db: DbDep):
    rows = list(
        await db.scalars(
            select(CodingDraft).where(CodingDraft.user_id == user.id).order_by(CodingDraft.created_at.desc()).limit(50)
        )
    )
    return {"drafts": [await service.public(db, row) for row in rows]}


@router.get("/drafts/{identifier}")
async def detail(identifier: uuid.UUID, user: CurrentUser, db: DbDep):
    try:
        return await service.public(db, await service.owned(db, user.id, identifier), True)
    except gh.GitHubError as exc:
        raise HTTPException(exc.status, str(exc)) from None


@router.post("/drafts/{identifier}/review")
async def review(identifier: uuid.UUID, body: ReviewInput, user: CurrentUser, db: DbDep, settings: SettingsDep):
    try:
        row = await service.owned(db, user.id, identifier)
        return await service.prepare_review(
            db, settings, user.id, row, [f.model_dump() for f in body.files] if body.files else None
        )
    except gh.GitHubError as exc:
        raise HTTPException(exc.status, str(exc)) from None
    except builder.BuildError as exc:
        raise HTTPException(400, builder.failure_message(exc)) from None


@router.post("/drafts/{identifier}/publish")
async def publish(identifier: uuid.UUID, body: PublishInput, user: CurrentUser, db: DbDep, settings: SettingsDep):
    try:
        await gh.limit(user.id)
        return await service.publish(
            db, settings, user.id, await service.owned(db, user.id, identifier), body.review_hash
        )
    except gh.GitHubError as exc:
        raise HTTPException(exc.status, str(exc)) from None


@router.post("/drafts/{identifier}/checks")
async def checks(identifier: uuid.UUID, user: CurrentUser, db: DbDep, settings: SettingsDep):
    try:
        await gh.limit(user.id)
        row = await service.owned(db, user.id, identifier)
        result = await service.refresh_checks(db, settings, user.id, row)
        if row.auto_repair and row.repair_count == 0 and (row.check_result or {}).get("conclusion") == "failure":
            await service.repair_once(db, user, row, True)
            result = await service.public(db, row, True)
        return result
    except gh.GitHubError as exc:
        raise HTTPException(exc.status, str(exc)) from None


@router.post("/drafts/{identifier}/repair")
async def repair(identifier: uuid.UUID, user: CurrentUser, db: DbDep):
    try:
        await rate_limit.enforce("coding-repair:" + str(user.id), 3)
        row = await service.owned(db, user.id, identifier)
        await service.repair_once(db, user, row)
        return await service.public(db, row, True)
    except gh.GitHubError as exc:
        raise HTTPException(exc.status, str(exc)) from None
