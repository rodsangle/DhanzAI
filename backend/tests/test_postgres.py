"""PostgreSQL + pgvector checks. Run with TEST_POSTGRES_URL=postgresql+asyncpg://... (CI does)."""

import os
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.db.session import make_engine, make_sessionmaker
from app.models import KnowledgeChunk, User
from app.services import knowledge_service
from dhanz_knowledge import Page
from tests.conftest import HashEmbedder, migrate

URL = os.environ.get("TEST_POSTGRES_URL")
pytestmark = pytest.mark.skipif(not URL, reason="TEST_POSTGRES_URL not set")


@pytest.fixture
def pg_url() -> str:
    migrate(URL)  # sync: Alembic runs its own event loop
    return URL


async def test_pgvector_ingest_and_hybrid_search(pg_url):
    engine = make_engine(pg_url)
    maker = make_sessionmaker(engine)
    embedder = HashEmbedder()
    try:
        async with maker() as db:
            owner = User(email=f"pg-{uuid.uuid4().hex[:8]}@example.com", password_hash="x", display_name="PG")
            other = User(email=f"pg-{uuid.uuid4().hex[:8]}@example.com", password_hash="x", display_name="PG2")
            db.add_all([owner, other])
            await db.flush()
            page = Page(
                url=f"https://garden.example/{uuid.uuid4().hex}",
                title="Growing tomatoes",
                text="Tomato plants need at least six hours of direct sunlight.\nWater tomato plants consistently.",
                retrieved_at=datetime.now(UTC),
            )
            doc = await knowledge_service.ingest_page(db, owner.id, page, embedder, added_via="manual")
            await db.commit()

            chunk = await db.scalar(select(KnowledgeChunk).where(KnowledgeChunk.document_id == doc.id))
            assert chunk is not None and len(chunk.embedding) == 64

            vector_hits = await knowledge_service._vector_search(
                db, owner.id, embedder.key, (await embedder.embed(["sunlight for tomato plants"]))[0]
            )
            assert vector_hits and vector_hits[0][1] > 0.35  # computed by pgvector's <=> operator

            hits = await knowledge_service.search_library(db, owner.id, "sunlight for tomato plants", embedder)
            assert hits[0].url == page.url and hits[0].origin == "library"
            assert await knowledge_service.search_library(db, other.id, "sunlight for tomato plants", embedder) == []

            await db.delete(owner)
            await db.delete(other)
            await db.commit()
    finally:
        await engine.dispose()
