"""Knowledge library and web-research wiring for the API."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import Float, bindparam, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.db.base import utcnow
from app.models import KnowledgeChunk, KnowledgeDocument
from dhanz_knowledge import (
    BraveSearch,
    Embedder,
    EmbeddingError,
    Fetcher,
    GeminiEmbedder,
    OllamaEmbedder,
    OpenAIEmbedder,
    Page,
    Passage,
    ResearchPipeline,
    SearchProvider,
    SearxngSearch,
    TavilySearch,
    bm25_scores,
    chunk_text,
    cosine,
    reciprocal_rank_fusion,
)
from dhanz_knowledge.ranking import tokenize

log = logging.getLogger(__name__)

MIN_COSINE = 0.35  # below this a library chunk is treated as unrelated
# A keyword hit must contain at least half of the query's meaningful words. (BM25 scores alone
# are not comparable across library sizes: with only a few documents every score is tiny.)
MIN_TERM_COVERAGE = 0.5


@dataclass
class KnowledgeRuntime:
    fetcher: Fetcher
    search: SearchProvider | None
    embedder: Embedder | None
    max_results: int = 6
    max_pages: int = 4

    def pipeline(self) -> ResearchPipeline:
        return ResearchPipeline(self.search, self.fetcher, max_results=self.max_results, max_pages=self.max_pages)

    async def aclose(self) -> None:
        await self.fetcher.aclose()
        if self.search:
            await self.search.aclose()
        if self.embedder:
            await self.embedder.aclose()


def build_knowledge_runtime(settings: Settings) -> KnowledgeRuntime:
    search: SearchProvider | None = None
    if settings.search_provider == "brave" and settings.brave_api_key:
        search = BraveSearch(settings.brave_api_key)
    elif settings.search_provider == "tavily" and settings.tavily_api_key:
        search = TavilySearch(settings.tavily_api_key)
    elif settings.search_provider == "searxng" and settings.searxng_url:
        search = SearxngSearch(settings.searxng_url)
    elif settings.search_provider != "none":
        log.warning("SEARCH_PROVIDER=%s is missing its key/URL; web search disabled", settings.search_provider)

    embedder: Embedder | None = None
    model = settings.embedding_model
    if settings.embedding_provider == "openai" and settings.openai_api_key:
        embedder = OpenAIEmbedder(
            settings.openai_api_key, model or "text-embedding-3-small", base_url=settings.openai_base_url
        )
    elif settings.embedding_provider == "gemini" and settings.gemini_api_key:
        embedder = GeminiEmbedder(settings.gemini_api_key, model or "gemini-embedding-001")
    elif settings.embedding_provider == "ollama" and settings.ollama_base_url:
        embedder = OllamaEmbedder(settings.ollama_base_url, model or "nomic-embed-text")

    return KnowledgeRuntime(
        fetcher=Fetcher(user_agent=settings.fetch_user_agent),
        search=search,
        embedder=embedder,
        max_results=settings.research_max_results,
        max_pages=settings.research_max_pages,
    )


# ---------------------------------------------------------------- ingestion


async def ingest_page(
    db: AsyncSession, user_id: uuid.UUID, page: Page, embedder: Embedder | None, *, added_via: str
) -> KnowledgeDocument:
    """Insert or refresh a page in the user's library (caller commits)."""
    content_hash = hashlib.sha256(page.text.encode()).hexdigest()
    doc = await db.scalar(
        select(KnowledgeDocument).where(KnowledgeDocument.user_id == user_id, KnowledgeDocument.url == page.url)
    )
    now = utcnow()
    if doc is not None and doc.content_hash == content_hash:
        doc.retrieved_at = page.retrieved_at or now
        if added_via == "manual":
            doc.added_via = "manual"
        return doc
    if doc is None:
        doc = KnowledgeDocument(user_id=user_id, url=page.url, added_via=added_via)
        db.add(doc)
    else:
        await db.execute(delete(KnowledgeChunk).where(KnowledgeChunk.document_id == doc.id))
    doc.title = (page.title or page.url)[:300]
    doc.site_name = (page.site_name or None) and page.site_name[:200]
    doc.author = (page.author or None) and page.author[:200]
    doc.published_at = page.published_at
    doc.retrieved_at = page.retrieved_at or now
    doc.content = page.text
    doc.content_hash = content_hash
    await db.flush()

    chunks = chunk_text(page.text)
    vectors: list[list[float]] | None = None
    if embedder and chunks:
        try:
            vectors = await embedder.embed(chunks)
        except EmbeddingError as exc:
            log.warning("Embedding failed for %s; stored for keyword search only: %s", page.url, exc)
    for i, text in enumerate(chunks):
        db.add(
            KnowledgeChunk(
                document_id=doc.id,
                user_id=user_id,
                ordinal=i,
                text=text,
                embedding=vectors[i] if vectors else None,
                embedding_model=embedder.key if vectors and embedder else None,
            )
        )
    return doc


_background: set[asyncio.Task] = set()


def index_in_background(
    maker: async_sessionmaker[AsyncSession], user_id: uuid.UUID, pages: Sequence[Page], embedder: Embedder | None
) -> None:
    """Save research pages to the user's library without delaying the chat response."""

    async def run() -> None:
        async with maker() as db:
            for page in pages:
                try:
                    await ingest_page(db, user_id, page, embedder, added_via="research")
                    await db.commit()
                except Exception:  # noqa: BLE001 - indexing is best effort
                    await db.rollback()
                    log.exception("Auto-indexing %s failed", page.url)

    task = asyncio.create_task(run())
    _background.add(task)
    task.add_done_callback(_background.discard)


async def wait_for_background_indexing() -> None:
    """Used by tests and graceful shutdown."""
    if _background:
        await asyncio.gather(*list(_background), return_exceptions=True)


# ---------------------------------------------------------------- retrieval


async def search_library(
    db: AsyncSession, user_id: uuid.UUID, query: str, embedder: Embedder | None, *, limit: int = 4
) -> list[Passage]:
    """Hybrid (keyword + semantic) search over one user's library. Never sees other users' chunks."""
    terms = tokenize(query)[:8]
    keyword_hits: list[tuple[KnowledgeChunk, float]] = []
    if terms:
        rows = list(
            await db.scalars(
                select(KnowledgeChunk)
                .where(
                    KnowledgeChunk.user_id == user_id,
                    or_(*[func.lower(KnowledgeChunk.text).contains(t, autoescape=True) for t in terms]),
                )
                .limit(400)
            )
        )
        scores = bm25_scores(query, [r.text for r in rows])
        wanted = set(terms)

        def coverage(text: str) -> float:
            return len(wanted & set(tokenize(text))) / len(wanted)

        keyword_hits = sorted(
            ((r, s) for r, s in zip(rows, scores, strict=True) if coverage(r.text) >= MIN_TERM_COVERAGE),
            key=lambda x: x[1],
            reverse=True,
        )[:20]

    vector_hits: list[tuple[KnowledgeChunk, float]] = []
    if embedder is not None:
        try:
            [qv] = await embedder.embed([query])
        except EmbeddingError as exc:
            log.warning("Query embedding failed: %s", exc)
            qv = None
        if qv is not None:
            vector_hits = await _vector_search(db, user_id, embedder.key, qv)

    by_id: dict[uuid.UUID, KnowledgeChunk] = {}
    rankings = []
    for hits in (keyword_hits, vector_hits):
        rankings.append([])
        for chunk, _ in hits:
            by_id[chunk.id] = chunk
            rankings[-1].append(chunk.id)
    if not by_id:
        return []
    ids = list(by_id)
    fused = reciprocal_rank_fusion([[ids.index(i) for i in r] for r in rankings])
    best = sorted(fused, key=fused.get, reverse=True)[:limit]

    doc_ids = {by_id[ids[i]].document_id for i in best}
    docs = {d.id: d for d in await db.scalars(select(KnowledgeDocument).where(KnowledgeDocument.id.in_(doc_ids)))}
    passages = []
    for i in best:
        chunk = by_id[ids[i]]
        doc = docs[chunk.document_id]
        passages.append(
            Passage(
                text=chunk.text,
                url=doc.url,
                title=doc.title,
                site_name=doc.site_name,
                published_at=doc.published_at,
                retrieved_at=doc.retrieved_at,
                origin="library",
                score=fused[i],
                document_id=str(doc.id),
            )
        )
    return passages


async def _vector_search(
    db: AsyncSession, user_id: uuid.UUID, model_key: str, qv: list[float], k: int = 20
) -> list[tuple[KnowledgeChunk, float]]:
    base = select(KnowledgeChunk).where(
        KnowledgeChunk.user_id == user_id,
        KnowledgeChunk.embedding_model == model_key,
        KnowledgeChunk.embedding.is_not(None),
    )
    if db.get_bind().dialect.name == "postgresql":
        from pgvector.sqlalchemy import Vector

        distance = KnowledgeChunk.embedding.op("<=>", return_type=Float)(bindparam("qv", qv, type_=Vector()))
        rows = (await db.execute(base.add_columns(distance.label("d")).order_by("d").limit(k))).all()
        hits = [(chunk, 1 - d) for chunk, d in rows]
    else:  # portable fallback: exact cosine in Python
        hits = [(c, cosine(qv, c.embedding or [])) for c in await db.scalars(base.limit(5000))]
        hits.sort(key=lambda x: x[1], reverse=True)
    return [(c, s) for c, s in hits[:k] if s >= MIN_COSINE]


async def has_library(db: AsyncSession, user_id: uuid.UUID) -> bool:
    return (
        await db.scalar(select(KnowledgeDocument.id).where(KnowledgeDocument.user_id == user_id).limit(1))
    ) is not None
