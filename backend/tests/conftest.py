from __future__ import annotations

from collections.abc import AsyncIterator, Sequence

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.rate_limit import limiter
from app.main import create_app
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


@pytest.fixture
def client(settings, provider) -> TestClient:
    limiter.reset()
    app = create_app(settings, Orchestrator([provider]))
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
