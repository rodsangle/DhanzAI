"""Web search providers. Each returns ranked SearchResults; none of them scrape search pages."""

from __future__ import annotations

from abc import ABC, abstractmethod

import httpx

from dhanz_knowledge.extract import parse_date
from dhanz_knowledge.types import SearchError, SearchResult


class SearchProvider(ABC):
    name: str

    def __init__(self, client: httpx.AsyncClient | None = None):
        self._client = client or httpx.AsyncClient(timeout=15.0)

    @abstractmethod
    async def search(self, query: str, *, count: int = 6, news: bool = False) -> list[SearchResult]: ...

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _json(self, method: str, url: str, **kwargs) -> dict:
        try:
            response = await self._client.request(method, url, **kwargs)
        except httpx.HTTPError as exc:
            raise SearchError(f"{self.name}: network error ({type(exc).__name__})") from exc
        if response.status_code >= 400:
            raise SearchError(f"{self.name}: HTTP {response.status_code}")
        try:
            return response.json()
        except ValueError as exc:
            raise SearchError(f"{self.name}: invalid JSON") from exc


class BraveSearch(SearchProvider):
    """Brave Search API (https://brave.com/search/api/)."""

    name = "brave"

    def __init__(self, api_key: str, client: httpx.AsyncClient | None = None):
        super().__init__(client)
        self.api_key = api_key

    async def search(self, query: str, *, count: int = 6, news: bool = False) -> list[SearchResult]:
        endpoint = "news" if news else "web"
        data = await self._json(
            "GET",
            f"https://api.search.brave.com/res/v1/{endpoint}/search",
            params={"q": query, "count": count, "safesearch": "moderate", "text_decorations": "false"},
            headers={"X-Subscription-Token": self.api_key, "Accept": "application/json"},
        )
        items = data.get("results", []) if news else (data.get("web") or {}).get("results", [])
        return [
            SearchResult(
                title=i.get("title", ""),
                url=i["url"],
                snippet=i.get("description", ""),
                published_at=parse_date(i.get("page_age")),
                source=self.name,
            )
            for i in items
            if i.get("url")
        ][:count]


class TavilySearch(SearchProvider):
    """Tavily Search API (https://tavily.com)."""

    name = "tavily"

    def __init__(self, api_key: str, client: httpx.AsyncClient | None = None):
        super().__init__(client)
        self.api_key = api_key

    async def search(self, query: str, *, count: int = 6, news: bool = False) -> list[SearchResult]:
        data = await self._json(
            "POST",
            "https://api.tavily.com/search",
            json={"query": query, "max_results": count, "topic": "news" if news else "general"},
            headers={"Authorization": f"Bearer {self.api_key}"},
        )
        return [
            SearchResult(
                title=i.get("title", ""),
                url=i["url"],
                snippet=i.get("content", ""),
                published_at=parse_date(i.get("published_date")),
                source=self.name,
            )
            for i in data.get("results", [])
            if i.get("url")
        ][:count]


class SearxngSearch(SearchProvider):
    """Self-hosted SearXNG instance with the JSON output format enabled."""

    name = "searxng"

    def __init__(self, base_url: str, client: httpx.AsyncClient | None = None):
        super().__init__(client)
        self.base_url = base_url.rstrip("/")

    async def search(self, query: str, *, count: int = 6, news: bool = False) -> list[SearchResult]:
        data = await self._json(
            "GET",
            f"{self.base_url}/search",
            params={"q": query, "format": "json", "categories": "news" if news else "general", "safesearch": 1},
        )
        return [
            SearchResult(
                title=i.get("title", ""),
                url=i["url"],
                snippet=i.get("content", ""),
                published_at=parse_date(i.get("publishedDate")),
                source=self.name,
            )
            for i in data.get("results", [])
            if i.get("url")
        ][:count]
