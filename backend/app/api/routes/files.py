"""File uploads (documents and images) for chat attachments and the knowledge library."""

from __future__ import annotations

from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import Response

from app.api.deps import CurrentUser, DbDep, KnowledgeDep, SettingsDep, parse_uuid
from app.core import rate_limit
from app.models import KnowledgeDocument, Project
from app.schemas import DocumentOut
from app.services import audit, files_service

router = APIRouter(prefix="/files", tags=["files"])


@router.post("", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
async def upload_file(
    request: Request,
    user: CurrentUser,
    db: DbDep,
    settings: SettingsDep,
    knowledge: KnowledgeDep,
    file: UploadFile,
    project_id: Annotated[str | None, Form()] = None,
) -> KnowledgeDocument:
    """Upload a document or image. It is scanned (if a scanner is configured), its text is
    extracted and indexed, and it can then be attached to messages or found in the library."""
    rate_limit.enforce(f"upload:{user.id}", settings.rate_limit_upload_per_minute)
    pid = None
    if project_id:
        pid = parse_uuid(project_id)
        project = await db.get(Project, pid)
        if project is None or project.user_id != user.id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
    limit = settings.max_upload_mb * 1024 * 1024
    data = await file.read(limit + 1)
    doc = await files_service.store_upload(
        db,
        settings,
        request.app.state.files,
        knowledge.embedder,
        user_id=user.id,
        filename=file.filename or "file",
        data=data,
        project_id=pid,
    )
    audit.record(db, "file.upload", user_id=user.id, detail={"document_id": str(doc.id), "type": doc.file_type})
    await db.commit()
    return doc


@router.get("/{document_id}/download")
async def download_file(document_id: str, request: Request, user: CurrentUser, db: DbDep) -> Response:
    doc = await db.get(KnowledgeDocument, parse_uuid(document_id))
    if doc is None or doc.user_id != user.id or not doc.storage_key:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File not found")
    data = await request.app.state.files.storage.get(doc.storage_key)
    ascii_name = "".join(c if c.isascii() and c.isprintable() and c != '"' else "_" for c in doc.title)
    return Response(
        data,
        # Always a download: never rendered inline, so a crafted file cannot run in a browser context.
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(doc.title)}",
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )
