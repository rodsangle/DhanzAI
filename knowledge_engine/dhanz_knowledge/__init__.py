"""DHANZ AI knowledge engine: web search, polite fetching, extraction, embeddings and ranking."""

from dhanz_knowledge.embeddings import Embedder, EmbeddingError, GeminiEmbedder, OllamaEmbedder, OpenAIEmbedder
from dhanz_knowledge.extract import extract_page
from dhanz_knowledge.fetcher import Fetcher
from dhanz_knowledge.ranking import bm25_scores, chunk_text, cosine, reciprocal_rank_fusion
from dhanz_knowledge.research import (
    ResearchOutcome,
    ResearchPipeline,
    ResearchProgress,
    build_context,
    build_query,
    extract_urls,
    needs_search,
    wants_web,
)
from dhanz_knowledge.safety import check_url
from dhanz_knowledge.search import BraveSearch, SearchProvider, SearxngSearch, TavilySearch
from dhanz_knowledge.types import Citation, FetchError, Page, Passage, SearchError, SearchResult

__all__ = [
    "BraveSearch",
    "Citation",
    "Embedder",
    "EmbeddingError",
    "FetchError",
    "Fetcher",
    "GeminiEmbedder",
    "OllamaEmbedder",
    "OpenAIEmbedder",
    "Page",
    "Passage",
    "ResearchOutcome",
    "ResearchPipeline",
    "ResearchProgress",
    "SearchError",
    "SearchProvider",
    "SearchResult",
    "SearxngSearch",
    "TavilySearch",
    "bm25_scores",
    "build_context",
    "build_query",
    "check_url",
    "chunk_text",
    "cosine",
    "extract_page",
    "extract_urls",
    "needs_search",
    "reciprocal_rank_fusion",
    "wants_web",
]
