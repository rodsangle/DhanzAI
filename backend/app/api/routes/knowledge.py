"""The user's private knowledge library: add web pages, browse, search, delete."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import func, or_, select

from app.api.deps import CurrentUser, DbDep, KnowledgeDep, SettingsDep, parse_uuid
from app.core import rate_limit
from app.models import KnowledgeChunk, KnowledgeDocument
from app.schemas import AddDocumentRequest, DocumentDetail, DocumentList, DocumentOut, LibraryHit
from app.services import audit, knowledge_service
from dhanz_knowledge import FetchError

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


async def _owned(db, user, document_id: str) -> KnowledgeDocument:
    doc = await db.get(KnowledgeDocument, parse_uuid(document_id))
    if doc is None or doc.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    return doc


@router.get("/documents", response_model=DocumentList)
async def list_documents(
    user: CurrentUser,
    db: DbDep,
    q: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> DocumentList:
    stmt = select(KnowledgeDocument).where(KnowledgeDocument.user_id == user.id)
    if q:
        needle = q.strip().lower()
        stmt = stmt.where(
            or_(
                func.lower(KnowledgeDocument.title).contains(needle, autoescape=True),
                func.lower(KnowledgeDocument.url).contains(needle, autoescape=True),
            )
        )
    total = await db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = await db.scalars(stmt.order_by(KnowledgeDocument.retrieved_at.desc()).limit(limit).offset(offset))
    return DocumentList(items=[DocumentOut.model_validate(d) for d in rows], total=total or 0)


@router.post("/documents", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
async def add_document(
    body: AddDocumentRequest, user: CurrentUser, db: DbDep, settings: SettingsDep, knowledge: KnowledgeDep
) -> KnowledgeDocument:
    """Read a public web page (respecting robots.txt and access controls) and add it to the library."""
    rate_limit.enforce(f"ingest:{user.id}", settings.rate_limit_ingest_per_minute)
    try:
        page = await knowledge.fetcher.fetch(body.url)
    except FetchError as exc:
        raise HTTPException(422, f"Could not add this page: {exc.reason}") from None
    doc = await knowledge_service.ingest_page(db, user.id, page, knowledge.embedder, added_via="manual")
    audit.record(db, "knowledge.add", user_id=user.id, detail={"url": page.url})
    await db.commit()
    return doc


@router.get("/documents/{document_id}", response_model=DocumentDetail)
async def get_document(document_id: str, user: CurrentUser, db: DbDep) -> DocumentDetail:
    doc = await _owned(db, user, document_id)
    count = await db.scalar(select(func.count()).where(KnowledgeChunk.document_id == doc.id))
    return DocumentDetail(**DocumentOut.model_validate(doc).model_dump(), content=doc.content, chunk_count=count or 0)


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(document_id: str, user: CurrentUser, db: DbDep) -> Response:
    doc = await _owned(db, user, document_id)
    await db.delete(doc)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/search", response_model=list[LibraryHit])
async def search(
    user: CurrentUser,
    db: DbDep,
    knowledge: KnowledgeDep,
    q: str = Query(min_length=1, max_length=500),
    limit: int = Query(default=8, ge=1, le=20),
) -> list[LibraryHit]:
    passages = await knowledge_service.search_library(db, user.id, q, knowledge.embedder, limit=limit)
    return [
        LibraryHit(
            document_id=p.document_id,
            title=p.title,
            url=p.url,
            site_name=p.site_name,
            snippet=p.text[:400],
        )
        for p in passages
    ]
