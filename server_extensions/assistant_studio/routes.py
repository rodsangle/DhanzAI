import uuid
from typing import Literal

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError

from app.api.deps import CurrentUser, DbDep, SettingsDep
from app.db.base import utcnow
from app.models import Conversation, Message

from . import builder
from .models import BuilderProject, ResponseFeedback

router = APIRouter(prefix="/assistant-studio", tags=["assistant-studio"])


async def owned_message(db, user, identifier):
    message = await db.scalar(
        select(Message).join(Conversation).where(Message.id == identifier, Conversation.user_id == user.id)
    )
    if message is None:
        raise HTTPException(404, "Reply not found")
    if message.role != "assistant" or message.status == "streaming":
        raise HTTPException(409, "Rate a finished assistant reply.")
    return message


class Feedback(BaseModel):
    rating: Literal["up", "down"] | None = None
    note: str = Field(default="", max_length=1000)


@router.get("/feedback/{message_id}")
async def get_feedback(message_id: uuid.UUID, user: CurrentUser, db: DbDep):
    await owned_message(db, user, message_id)
    row = await db.get(ResponseFeedback, (message_id, user.id))
    return {"rating": row.rating if row else None, "note": row.note if row else ""}


@router.put("/feedback/{message_id}")
async def save_feedback(message_id: uuid.UUID, body: Feedback, user: CurrentUser, db: DbDep):
    await owned_message(db, user, message_id)
    row = await db.get(ResponseFeedback, (message_id, user.id))
    if body.rating is None:
        await db.execute(
            delete(ResponseFeedback).where(
                ResponseFeedback.message_id == message_id, ResponseFeedback.user_id == user.id
            )
        )
    elif row is None:
        db.add(ResponseFeedback(message_id=message_id, user_id=user.id, rating=body.rating, note=body.note))
    else:
        row.rating = body.rating
        row.note = body.note
        row.updated_at = utcnow()
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, "Feedback changed concurrently. Refresh and retry.") from None
    return {"rating": body.rating, "note": body.note if body.rating else ""}


@router.get("/models")
async def builder_models(user: CurrentUser, settings: SettingsDep):
    if user.routing_policy == "local_only":
        return {
            "models": [],
            "codex_available": False,
            "detail": "External project generation is disabled in local-only mode.",
        }
    try:
        ids = await builder.models(settings)
    except builder.BuildError as exc:
        raise HTTPException(503, str(exc)) from None
    return {
        "models": ids,
        "codex_available": any("codex" in name for name in ids),
        "detail": "Uses your configured OpenAI API connection. Provider usage charges apply. Generated code is not executed or deployed.",
    }


class BuildRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    kind: Literal["app", "agent"]
    prompt: str = Field(min_length=5, max_length=12000)
    model: str = Field(min_length=1, max_length=200)
    request_key: str = Field(min_length=16, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")


def public(row, include_files=False):
    result = {
        "id": str(row.id),
        "name": row.name,
        "kind": row.kind,
        "model": row.model,
        "status": row.status,
        "summary": row.summary,
        "error": row.error,
        "created_at": row.created_at.isoformat(),
        "file_count": len(row.files or []),
    }
    if include_files:
        result["files"] = row.files or []
    return result


@router.post("/projects", status_code=201)
async def create_project(body: BuildRequest, user: CurrentUser, db: DbDep, settings: SettingsDep):
    from app.core import rate_limit

    await rate_limit.enforce(f"builder:{user.id}", 5)
    if user.routing_policy == "local_only":
        raise HTTPException(403, "External code generation is disabled in local-only mode.")
    if __import__("re").search(r"sk-(?:proj-|ant-)[A-Za-z0-9_-]{20,}|BEGIN [A-Z ]{0,40}PRIVATE KEY", body.prompt):
        raise HTTPException(422, "Use placeholders for credentials, not actual keys, in project instructions.")
    existing = await db.scalar(
        select(BuilderProject).where(BuilderProject.user_id == user.id, BuilderProject.request_key == body.request_key)
    )
    if existing:
        return public(existing)
    pending = await db.scalar(
        select(func.count())
        .select_from(BuilderProject)
        .where(BuilderProject.user_id == user.id, BuilderProject.status.in_(["queued", "running"]))
    )
    if pending >= 2:
        raise HTTPException(429, "Wait for your existing builds to finish.")
    total = await db.scalar(select(func.count()).select_from(BuilderProject).where(BuilderProject.user_id == user.id))
    if total >= 30:
        raise HTTPException(409, "Delete an old project before creating another.")
    try:
        ids = await builder.models(settings)
    except builder.BuildError as exc:
        raise HTTPException(503, str(exc)) from None
    if body.model not in ids:
        raise HTTPException(422, "Choose an available model from the project builder.")
    row = BuilderProject(user_id=user.id, **body.model_dump())
    db.add(row)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        row = await db.scalar(
            select(BuilderProject).where(
                BuilderProject.user_id == user.id, BuilderProject.request_key == body.request_key
            )
        )
        if row is None:
            raise HTTPException(409, "The build could not be queued.") from None
    return public(row)


@router.get("/projects")
async def list_projects(user: CurrentUser, db: DbDep):
    rows = await db.scalars(
        select(BuilderProject)
        .where(BuilderProject.user_id == user.id)
        .order_by(BuilderProject.created_at.desc())
        .limit(30)
    )
    return {"projects": [public(row) for row in rows]}


async def owned_project(db, user, identifier):
    row = await db.get(BuilderProject, identifier)
    if row is None or row.user_id != user.id:
        raise HTTPException(404, "Project not found")
    return row


@router.get("/projects/{project_id}")
async def get_project(project_id: uuid.UUID, user: CurrentUser, db: DbDep):
    return public(await owned_project(db, user, project_id), True)


@router.delete("/projects/{project_id}")
async def delete_project(project_id: uuid.UUID, user: CurrentUser, db: DbDep):
    row = await owned_project(db, user, project_id)
    if row.status in {"queued", "running"}:
        raise HTTPException(409, "Wait for the build to finish before deleting it.")
    await db.delete(row)
    await db.commit()
    return {"deleted": True}


@router.get("/projects/{project_id}/download")
async def download_project(project_id: uuid.UUID, user: CurrentUser, db: DbDep):
    row = await owned_project(db, user, project_id)
    if row.status != "complete" or not row.files:
        raise HTTPException(409, "The project files are not ready.")
    data = builder.archive(row.files)
    return Response(
        data,
        media_type="application/zip",
        headers={
            "Content-Disposition": 'attachment; filename="Dhanz_Project.zip"',
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )
