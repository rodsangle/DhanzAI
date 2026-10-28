"""Project workspaces: group conversations and documents and give Dhanz standing instructions."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import func, select

from app.api.deps import CurrentUser, DbDep, parse_uuid
from app.db.base import utcnow
from app.models import Conversation, KnowledgeDocument, Project
from app.schemas import ProjectCreate, ProjectDetail, ProjectOut, ProjectUpdate

router = APIRouter(prefix="/projects", tags=["projects"])


async def get_owned_project(db, user, project_id) -> Project:
    project = await db.get(Project, project_id)
    if project is None or project.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
    return project


def _clean(text: str | None) -> str | None:
    return (text or "").strip() or None


@router.get("", response_model=list[ProjectOut])
async def list_projects(user: CurrentUser, db: DbDep) -> list[Project]:
    return list(await db.scalars(select(Project).where(Project.user_id == user.id).order_by(Project.name)))


@router.post("", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
async def create_project(body: ProjectCreate, user: CurrentUser, db: DbDep) -> Project:
    project = Project(
        user_id=user.id,
        name=body.name.strip(),
        description=_clean(body.description),
        instructions=_clean(body.instructions),
    )
    db.add(project)
    await db.commit()
    return project


@router.get("/{project_id}", response_model=ProjectDetail)
async def get_project(project_id: str, user: CurrentUser, db: DbDep) -> ProjectDetail:
    project = await get_owned_project(db, user, parse_uuid(project_id))
    convs = await db.scalar(select(func.count()).where(Conversation.project_id == project.id))
    docs = await db.scalar(select(func.count()).where(KnowledgeDocument.project_id == project.id))
    return ProjectDetail(
        **ProjectOut.model_validate(project).model_dump(), conversation_count=convs or 0, document_count=docs or 0
    )


@router.patch("/{project_id}", response_model=ProjectOut)
async def update_project(project_id: str, body: ProjectUpdate, user: CurrentUser, db: DbDep) -> Project:
    project = await get_owned_project(db, user, parse_uuid(project_id))
    fields = body.model_fields_set
    if "name" in fields and body.name:
        project.name = body.name.strip()
    if "description" in fields:
        project.description = _clean(body.description)
    if "instructions" in fields:
        project.instructions = _clean(body.instructions)
    project.updated_at = utcnow()
    await db.commit()
    return project


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(project_id: str, user: CurrentUser, db: DbDep) -> Response:
    """Delete the project. Its conversations and documents are kept and become unassigned."""
    project = await get_owned_project(db, user, parse_uuid(project_id))
    await db.delete(project)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
