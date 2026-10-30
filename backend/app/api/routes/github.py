"""Account-owned GitHub connection and bounded read-only repository operations."""

from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel, Field, SecretStr

from app.api.deps import CurrentUser, DbDep, SettingsDep
from app.models import GitHubConnection
from app.services import github_service as github

router = APIRouter(prefix="/github", tags=["github"])


class ConnectionInput(BaseModel):
    token: SecretStr
    repositories: list[str] = Field(min_length=1, max_length=20)


@router.get("/connection")
async def connection(user: CurrentUser, db: DbDep, settings: SettingsDep, response: Response):
    response.headers["Cache-Control"] = "no-store"
    return github.public_connection(await db.get(GitHubConnection, user.id), settings)


@router.put("/connection")
async def connect(body: ConnectionInput, user: CurrentUser, db: DbDep, settings: SettingsDep, response: Response):
    response.headers["Cache-Control"] = "no-store"
    try:
        return await github.connect(db, settings, user.id, body.token.get_secret_value(), body.repositories)
    except github.GitHubError as exc:
        raise HTTPException(exc.status, str(exc)) from None


@router.delete("/connection", status_code=204)
async def disconnect(user: CurrentUser, db: DbDep):
    stored = await db.get(GitHubConnection, user.id)
    if stored:
        await db.delete(stored)
        await db.commit()
    return Response(status_code=204)


@router.get("/read")
async def read(
    user: CurrentUser,
    db: DbDep,
    settings: SettingsDep,
    response: Response,
    operation: Literal["repositories", "directory", "file", "issues", "pulls", "pull"],
    repository: str = Query(default="", max_length=140),
    path: str = Query(default="", max_length=1000),
    ref: str = Query(default="", max_length=200),
    page: int = Query(default=1, ge=1, le=100),
    number: int = Query(default=0, ge=0, le=1_000_000_000),
    start_line: int = Query(default=1, ge=1, le=128000),
):
    response.headers["Cache-Control"] = "no-store"
    try:
        return await github.read(db, settings, user.id, operation, repository, path, ref, page, number, start_line)
    except github.GitHubError as exc:
        raise HTTPException(exc.status, str(exc)) from None
