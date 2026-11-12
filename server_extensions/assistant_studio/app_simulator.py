"""Create a revised copy of a completed owned app; never overwrite the source."""

import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import CurrentUser, DbDep, SettingsDep

from . import builder, routes

router = APIRouter(prefix="/assistant-studio", tags=["assistant-studio"])


class Revision(BaseModel):
    changes: str = Field(min_length=5, max_length=8000)
    request_key: str = Field(min_length=16, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")


async def queue_revision(identifier, changes, key, user, db, settings):
    from .app_builder_tools import build_instructions

    parent = await routes.owned_project(db, user, identifier)
    if parent.status != "complete" or parent.kind != "app":
        raise HTTPException(409, "Choose a completed app project to revise.")
    runtime = "flutter" if parent.prompt.startswith("[DHANZ_RUNTIME:flutter]\n") else "web"
    instructions = f"[DHANZ_REVISION:{parent.id}]\nRequested changes:\n{changes}"
    prompt = build_instructions(instructions, runtime)
    body = routes.BuildRequest(
        name=(parent.name[:85] + " · revised"), kind="app", prompt=prompt, model=parent.model, request_key=key
    )
    return await routes.create_project(body, user, db, settings)


@router.post("/projects/{identifier}/revise", status_code=201)
async def revise(identifier: uuid.UUID, body: Revision, user: CurrentUser, db: DbDep, settings: SettingsDep):
    try:
        return await queue_revision(identifier, body.changes, body.request_key, user, db, settings)
    except builder.BuildError as exc:
        raise HTTPException(400, builder.failure_message(exc)) from None
