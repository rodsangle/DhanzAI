"""Web research pipeline: decide → search → read → rank → cite."""

from __future__ import annotations

import asyncio
import re
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field

from dhanz_knowledge.fetcher import Fetcher
from dhanz_knowledge.ranking import bm25_scores, chunk_text
from dhanz_knowledge.search import SearchProvider
from dhanz_knowledge.types import Citation, FetchError, Page, Passage, SearchError, SearchResult

_URL = re.compile(r"https?://[^\s<>()\"'\]]+", re.IGNORECASE)
_WEB_HINTS = re.compile(
    r"\b(latest|newest|recent(ly)?|current(ly)?|today|tonight|yesterday|this (week|month|year)|right now|"
    r"news|headlines?|breaking|price|prices|cost of|stock|exchange rate|weather|forecast|score|results?|"
    r"released?|release date|announced?|launch(ed)?|update[sd]?|version|who (won|is the current)|"
    r"search|look up|lookup|google|browse|on the (web|internet)|online|sources?|citations?|20[2-9]\d)\b",
    re.IGNORECASE,
)
_NEWS_HINTS = re.compile(r"\b(news|headlines?|breaking|today|this week|announced?|latest)\b", re.IGNORECASE)
_LEADING = re.compile(
    r"^\s*(hey|hi|ok(ay)?)?\s*,?\s*(dhanz)?\s*[,:]?\s*"
    r"(please\s+)?((can|could|would) you\s+)?(please\s+)?"
    r"((do a\s+)?(web\s+)?search|look\s*up|find|google|browse|research)?\s*"
    r"((on|in|the)\s+)*(the\s+)?(internet|web|online)?\s*(for|about)?\s*",
    re.IGNORECASE,
)


def extract_urls(text: str) -> list[str]:
    seen, out = set(), []
    for url in _URL.findall(text):
        url = url.rstrip(".,;:!?")
        if url not in seen:
            seen.add(url)
            out.append(url)
    return out[:5]


def needs_search(text: str) -> bool:
    """Heuristic: does this message ask for current information that needs a web search?"""
    return bool(_WEB_HINTS.search(_URL.sub(" ", text)))


def wants_web(text: str) -> bool:
    """Does answering need the web at all (a search, or reading links the user pasted)?"""
    return bool(extract_urls(text)) or needs_search(text)


def build_query(text: str) -> str:
    """Turn a chat message into a search query ("Hey Dhanz, search the internet for X" -> "X")."""
    text = _URL.sub(" ", text)
    first = text.strip().split("\n")[0]
    query = _LEADING.sub("", first, count=1).strip(" ?.!") or first.strip()
    return query[:200]


@dataclass
class ResearchProgress:
    stage: str  # searching | reading | ranking | done | error
    detail: dict = field(default_factory=dict)


@dataclass
class ResearchOutcome:
    query: str | None
    passages: list[Passage]
    pages: list[Page]
    failures: list[dict]


class ResearchPipeline:
    def __init__(
        self,
        search: SearchProvider | None,
        fetcher: Fetcher,
        *,
        max_results: int = 6,
        max_pages: int = 4,
        max_passages: int = 8,
    ):
        self.search = search
        self.fetcher = fetcher
        self.max_results = max_results
        self.max_pages = max_pages
        self.max_passages = max_passages

    async def run(self, message: str, *, use_search: bool) -> AsyncIterator[ResearchProgress | ResearchOutcome]:
        urls = extract_urls(message)
        query = build_query(message) if use_search and self.search else None
        results: list[SearchResult] = []
        failures: list[dict] = []

        if query:
            yield ResearchProgress("searching", {"query": query})
            try:
                results = await self.search.search(
                    query, count=self.max_results, news=bool(_NEWS_HINTS.search(message))
                )
            except SearchError as exc:
                failures.append({"url": None, "reason": f"web search failed ({exc})"})

        targets = urls + [r.url for r in results if r.url not in urls]
        targets = targets[: max(self.max_pages, len(urls))]
        if targets:
            yield ResearchProgress("reading", {"urls": targets})
        pages: list[Page] = []
        fetched = await asyncio.gather(*(self._fetch(u) for u in targets))
        for url, outcome in zip(targets, fetched, strict=True):
            if isinstance(outcome, Page):
                pages.append(outcome)
            else:
                failures.append({"url": url, "reason": outcome})

        passages = rank_pages(query or message, pages, limit=self.max_passages)
        # Pages we could not read can still contribute the search engine's own snippet.
        read = {p.url for p in pages} | {f["url"] for f in failures if f["url"] in urls}
        for r in results:
            if r.snippet and r.url not in read and all(p.url != r.url for p in passages):
                passages.append(Passage(text=r.snippet, url=r.url, title=r.title, published_at=r.published_at))
        yield ResearchProgress("done", {"pages": len(pages), "failures": len(failures)})
        yield ResearchOutcome(query=query, passages=passages, pages=pages, failures=failures)

    async def _fetch(self, url: str) -> Page | str:
        try:
            return await self.fetcher.fetch(url)
        except FetchError as exc:
            return exc.reason


def rank_pages(query: str, pages: Sequence[Page], *, limit: int) -> list[Passage]:
    candidates: list[Passage] = []
    for page in pages:
        for chunk in chunk_text(page.text):
            candidates.append(
                Passage(
                    text=chunk,
                    url=page.url,
                    title=page.title,
                    site_name=page.site_name,
                    published_at=page.published_at,
                    retrieved_at=page.retrieved_at,
                )
            )
    scores = bm25_scores(query, [c.text for c in candidates])
    for c, s in zip(candidates, scores, strict=True):
        c.score = s
    best: list[Passage] = []
    per_page: dict[str, int] = {}
    for c in sorted(candidates, key=lambda c: c.score, reverse=True):
        if per_page.get(c.url, 0) >= 3:
            continue  # keep several sources represented
        best.append(c)
        per_page[c.url] = per_page.get(c.url, 0) + 1
        if len(best) >= limit:
            break
    # Every readable page gets at least its best passage even if the keyword score is 0.
    for page in pages:
        if not any(p.url == page.url for p in best):
            first = next((c for c in candidates if c.url == page.url), None)
            if first:
                best.append(first)
    return best


def build_context(passages: Sequence[Passage], *, budget_chars: int = 14_000) -> tuple[str, list[Citation]]:
    """Number sources [1]..[n] and render them as a prompt block for the model."""
    citations: dict[str, Citation] = {}
    used = 0
    for p in passages:
        if used + len(p.text) > budget_chars:
            continue
        cit = citations.get(p.url)
        if cit is None:
            cit = Citation(
                n=len(citations) + 1,
                title=p.title or p.url,
                url=p.url,
                site_name=p.site_name,
                published_at=p.published_at,
                retrieved_at=p.retrieved_at,
                origin=p.origin,
            )
            citations[p.url] = cit
        cit.passages.append(p.text)
        used += len(p.text)
    blocks = []
    for c in citations.values():
        meta = [c.site_name or "", "your library" if c.origin == "library" else ""]
        if c.published_at:
            meta.append(f"published {c.published_at:%Y-%m-%d}")
        if c.retrieved_at:
            meta.append(f"retrieved {c.retrieved_at:%Y-%m-%d}")
        header = f"[{c.n}] {c.title}" + (f" ({'; '.join(m for m in meta if m)})" if any(meta) else "")
        blocks.append(header + f"\nURL: {c.url}\n" + "\n…\n".join(c.passages))
    return "\n\n".join(blocks), list(citations.values())
