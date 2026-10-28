from __future__ import annotations

import hashlib
from collections.abc import AsyncIterator, Sequence

import httpx
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.rate_limit import limiter
from app.main import create_app
from app.services.knowledge_service import KnowledgeRuntime
from dhanz_ai import (
    Capability,
    ChatMessage,
    CostTier,
    GenerationParams,
    ModelInfo,
    Orchestrator,
    Provider,
    ProviderError,
    StreamChunk,
)
from dhanz_knowledge import Embedder, Fetcher, SearchProvider, SearchResult
from dhanz_knowledge.ranking import tokenize

BACKEND_DIR = __import__("pathlib").Path(__file__).resolve().parents[1]


class EchoProvider(Provider):
    """Test double: streams a deterministic reply that echoes the last user message."""

    name = "echo"

    def __init__(self) -> None:
        super().__init__()
        self.fail_with: ProviderError | None = None
        self.last_messages: list[ChatMessage] = []

    def is_configured(self) -> bool:
        return True

    def models(self) -> list[ModelInfo]:
        return [ModelInfo("echo", "echo-1", "Echo", frozenset({Capability.CHAT}), CostTier.FREE)]

    async def stream(
        self, model: str, messages: Sequence[ChatMessage], params: GenerationParams
    ) -> AsyncIterator[StreamChunk]:
        self.last_messages = list(messages)
        if self.fail_with:
            raise self.fail_with
        last = next(m.content for m in reversed(messages) if m.role == "user")
        for word in f"You said: {last}".split(" "):
            yield StreamChunk(text=word + " ")
        yield StreamChunk(done=True, input_tokens=10, output_tokens=5)


def migrate(database_url: str) -> None:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.attributes["database_url"] = database_url
    cfg.attributes["configure_logger"] = False
    command.upgrade(cfg, "head")


@pytest.fixture
def settings(tmp_path) -> Settings:
    url = f"sqlite+aiosqlite:///{tmp_path / 'test.db'}"
    migrate(url)
    return Settings(app_env="test", database_url=url, jwt_secret="t" * 40, rate_limit_auth_per_minute=1000)


@pytest.fixture
def provider() -> EchoProvider:
    return EchoProvider()


CHIP_ARTICLE = """<html><head><title>2nm chips arrive</title>
<meta property="og:site_name" content="Chip Times">
<meta property="article:published_time" content="2026-10-20T09:00:00Z"></head>
<body><article><p>Foundries started volume production of 2nm semiconductor chips with gate-all-around transistors.</p>
<p>Power efficiency improves by about 25 percent compared with 3nm.</p></article></body></html>"""

GARDEN_ARTICLE = """<html><head><title>Growing tomatoes</title></head><body><main>
<p>Tomato plants need at least six hours of direct sunlight and consistent watering.</p>
<p>Prune the suckers of indeterminate tomato varieties for bigger fruit.</p></main></body></html>"""


def _html(body: str, status: int = 200) -> httpx.Response:
    return httpx.Response(status, text=body, headers={"content-type": "text/html"})


WEB = {
    "https://chips.example/robots.txt": httpx.Response(404),
    "https://chips.example/2nm": _html(CHIP_ARTICLE),
    "https://garden.example/robots.txt": httpx.Response(404),
    "https://garden.example/tomatoes": _html(GARDEN_ARTICLE),
    "https://private.example/robots.txt": httpx.Response(200, text="User-agent: *\nDisallow: /"),
    "https://private.example/page": _html(GARDEN_ARTICLE),
}


async def _public(host: str) -> list[str]:
    return ["10.1.2.3"] if host == "intranet.example" else ["93.184.216.34"]


class FakeSearch(SearchProvider):
    name = "fake"

    def __init__(self) -> None:
        super().__init__()
        self.queries: list[str] = []

    async def search(self, query: str, *, count: int = 6, news: bool = False) -> list[SearchResult]:
        self.queries.append(query)
        return [SearchResult("2nm chips arrive", "https://chips.example/2nm", "2nm chips enter production")]


class HashEmbedder(Embedder):
    """Deterministic bag-of-words embedding for tests (similar words -> similar vectors)."""

    provider = "test"

    def __init__(self) -> None:
        super().__init__("hash-64")

    async def embed(self, texts):
        out = []
        for t in texts:
            v = [0.0] * 64
            for tok in tokenize(t):
                v[int(hashlib.md5(tok.encode()).hexdigest(), 16) % 64] += 1.0  # noqa: S324 - not security
            out.append(v)
        return out


@pytest.fixture
def search() -> FakeSearch:
    return FakeSearch()


@pytest.fixture
def knowledge(search) -> KnowledgeRuntime:
    fetcher = Fetcher(
        httpx.AsyncClient(transport=httpx.MockTransport(lambda r: WEB.get(str(r.url), httpx.Response(404)))),
        resolver=_public,
        min_host_interval=0,
    )
    return KnowledgeRuntime(fetcher=fetcher, search=search, embedder=HashEmbedder())


@pytest.fixture
def client(settings, provider, knowledge) -> TestClient:
    limiter.reset()
    app = create_app(settings, Orchestrator([provider]), knowledge)
    with TestClient(app) as c:
        yield c


@pytest.fixture
def auth(client) -> dict:
    r = client.post(
        "/api/v1/auth/register",
        json={"email": "Ada@Example.com", "password": "correct-horse-9", "display_name": "Ada"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    return {"headers": {"Authorization": f"Bearer {body['access_token']}"}, **body}


def parse_sse(text: str) -> list[dict]:
    import json

    events = []
    for block in text.strip().split("\n\n"):
        data = [line[6:] for line in block.splitlines() if line.startswith("data: ")]
        if data:
            events.append(json.loads("\n".join(data)))
    return events
