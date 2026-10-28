from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class SearchResult:
    title: str
    url: str
    snippet: str = ""
    published_at: datetime | None = None
    source: str = ""  # search provider name


@dataclass(frozen=True)
class Page:
    """Main content extracted from a fetched web page."""

    url: str  # final URL after redirects
    title: str
    text: str
    site_name: str | None = None
    author: str | None = None
    published_at: datetime | None = None
    retrieved_at: datetime | None = None
    language: str | None = None


@dataclass
class Passage:
    """A piece of text that may be shown to the model as evidence."""

    text: str
    url: str
    title: str
    site_name: str | None = None
    published_at: datetime | None = None
    retrieved_at: datetime | None = None
    origin: str = "web"  # web | library
    score: float = 0.0
    document_id: str | None = None


@dataclass
class Citation:
    """A numbered source shown to the user and referenced as [n] by the model."""

    n: int
    title: str
    url: str
    site_name: str | None = None
    published_at: datetime | None = None
    retrieved_at: datetime | None = None
    origin: str = "web"
    passages: list[str] = field(default_factory=list)

    def to_json(self) -> dict:
        return {
            "n": self.n,
            "title": self.title,
            "url": self.url,
            "site_name": self.site_name,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "retrieved_at": self.retrieved_at.isoformat() if self.retrieved_at else None,
            "origin": self.origin,
        }


class FetchError(Exception):
    """A page could not (or must not) be fetched. `reason` is safe to show users."""

    def __init__(self, url: str, reason: str):
        super().__init__(f"{url}: {reason}")
        self.url = url
        self.reason = reason


class SearchError(Exception):
    pass
