"""Text embedding providers used for semantic search over the knowledge library."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

import httpx


class EmbeddingError(Exception):
    pass


class Embedder(ABC):
    provider: str

    def __init__(self, model: str, client: httpx.AsyncClient | None = None):
        self.model = model
        self._client = client or httpx.AsyncClient(timeout=60.0)

    @property
    def key(self) -> str:
        """Identifies the vector space; vectors from different keys are never compared."""
        return f"{self.provider}:{self.model}"

    @abstractmethod
    async def embed(self, texts: Sequence[str]) -> list[list[float]]: ...

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _post(self, url: str, **kwargs) -> dict:
        try:
            r = await self._client.post(url, **kwargs)
        except httpx.HTTPError as exc:
            raise EmbeddingError(f"{self.provider}: network error ({type(exc).__name__})") from exc
        if r.status_code >= 400:
            raise EmbeddingError(f"{self.provider}: HTTP {r.status_code}: {r.text[:200]}")
        return r.json()


class OpenAIEmbedder(Embedder):
    provider = "openai"

    def __init__(self, api_key: str, model: str = "text-embedding-3-small", base_url: str = "https://api.openai.com/v1",
                 client: httpx.AsyncClient | None = None):  # fmt: skip
        super().__init__(model, client)
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for start in range(0, len(texts), 64):
            data = await self._post(
                f"{self.base_url}/embeddings",
                json={"model": self.model, "input": list(texts[start : start + 64])},
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
            out += [d["embedding"] for d in sorted(data["data"], key=lambda d: d["index"])]
        return out


class GeminiEmbedder(Embedder):
    provider = "gemini"

    def __init__(self, api_key: str, model: str = "gemini-embedding-001", client: httpx.AsyncClient | None = None):
        super().__init__(model, client)
        self.api_key = api_key

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for start in range(0, len(texts), 100):
            batch = texts[start : start + 100]
            data = await self._post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:batchEmbedContents",
                json={
                    "requests": [{"model": f"models/{self.model}", "content": {"parts": [{"text": t}]}} for t in batch]
                },
                headers={"x-goog-api-key": self.api_key},
            )
            out += [e["values"] for e in data["embeddings"]]
        return out


class OllamaEmbedder(Embedder):
    provider = "ollama"

    def __init__(self, base_url: str, model: str = "nomic-embed-text", client: httpx.AsyncClient | None = None):
        super().__init__(model, client)
        self.base_url = base_url.rstrip("/")

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        data = await self._post(f"{self.base_url}/api/embed", json={"model": self.model, "input": list(texts)})
        return data["embeddings"]
