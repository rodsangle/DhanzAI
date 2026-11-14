"""Live news tool: newest first, sources kept, automatic (no permission question), safe failures."""

import asyncio
import json
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.services import assistant_tools, news_tools
from app.services.assistant_tools import TOOLS, Tool, ToolBox, ToolContext, ToolInputError, ToolOutcome
from dhanz_ai import ToolCall, ToolSpec
from dhanz_knowledge.types import SearchError, SearchResult


class FakeSearch:
    name = "fake"

    def __init__(self, results=None, error=None):
        self.results, self.error, self.calls, self.closed = results or [], error, [], False

    async def search(self, query, *, count=6, news=False):
        self.calls.append((query, count, news))
        if self.error:
            raise self.error
        return self.results

    async def aclose(self):
        self.closed = True


def result(title, url, day=None, snippet="text"):
    when = datetime(2026, 11, day, 8, 0, tzinfo=UTC) if day else None
    return SearchResult(title=title, url=url, snippet=snippet, published_at=when, source="fake")


def ctx(**extra):
    settings = SimpleNamespace(
        search_provider="searxng", searxng_url="http://searxng:8080", github_allowed_repositories=""
    )
    context = ToolContext(maker=None, user_id=uuid.uuid4(), conversation_id=None, settings=settings)
    for key, value in extra.items():
        setattr(context, key, value)
    return context


def run(context, args):
    return asyncio.run(TOOLS[news_tools.NEWS_TOOL].run(context, args))


def test_registered_and_described_as_automatic():
    tool = TOOLS["get_live_news"]
    assert "without asking the user for permission" in tool.spec.description
    assert tool.label == "Checking live news"
    assert tool.spec.name in [s.name for s in ToolBox(ctx()).specs]


def test_headlines_are_newest_first_deduplicated_and_cited(monkeypatch):
    fake = FakeSearch(
        [
            result("Older", "https://a.example/old", day=10),
            result("Undated", "https://b.example/undated"),
            result("Newest", "https://c.example/new", day=13, snippet="  many   spaces  "),
            result("Duplicate", "https://c.example/new", day=13),
            result("Not a web page", "javascript:alert(1)", day=12),
        ]
    )
    monkeypatch.setattr(news_tools, "search_provider", lambda settings: fake)
    outcome = run(ctx(), {"topic": "Philippines elections", "country": "Philippines", "max_results": 5})

    assert fake.calls == [("Philippines elections Philippines news", 20, True)]
    assert fake.closed
    articles = outcome.data["articles"]
    assert [a["title"] for a in articles] == ["Newest", "Older", "Undated"]
    assert articles[0]["source"] == "c.example"
    assert articles[0]["snippet"] == "many spaces"
    assert articles[0]["published_at"].startswith("2026-11-13")
    assert outcome.data["status"] == "ok"
    assert outcome.summary == "Live news: 3 articles"
    json.dumps(outcome.data)  # what the model receives


def test_empty_topic_asks_for_top_headlines(monkeypatch):
    fake = FakeSearch([])
    monkeypatch.setattr(news_tools, "search_provider", lambda settings: fake)
    outcome = run(ctx(), {})
    assert fake.calls[0][0] == "top news headlines"
    assert outcome.data["status"] == "no_results"
    assert outcome.summary == "Live news: 0 articles"


def test_without_web_search_the_model_is_told_not_to_invent_news(monkeypatch):
    monkeypatch.setattr(news_tools, "search_provider", lambda settings: None)
    with pytest.raises(ToolInputError, match="not configured"):
        run(ctx(), {"topic": "markets"})


def test_search_failure_and_bad_input_are_tool_errors(monkeypatch):
    fake = FakeSearch(error=SearchError("searxng: HTTP 502"))
    monkeypatch.setattr(news_tools, "search_provider", lambda settings: fake)
    with pytest.raises(ToolInputError, match="could not be retrieved"):
        run(ctx(), {"topic": "markets"})
    assert fake.closed
    monkeypatch.setattr(news_tools, "search_provider", lambda settings: FakeSearch())
    with pytest.raises(ToolInputError, match="max_results"):
        run(ctx(), {"max_results": 50})


def test_lookups_are_limited_per_reply_and_off_in_local_only_mode(monkeypatch):
    monkeypatch.setattr(news_tools, "search_provider", lambda settings: FakeSearch())
    context = ctx()
    for _ in range(3):
        run(context, {"topic": "x"})
    with pytest.raises(ToolInputError, match="At most three"):
        run(context, {"topic": "x"})
    with pytest.raises(ToolInputError, match="local-only"):
        run(ctx(capability_report={"ai_privacy_mode": "local_only"}), {"topic": "x"})


def test_toolbox_logs_the_lookup(monkeypatch):
    monkeypatch.setattr(
        news_tools, "search_provider", lambda settings: FakeSearch([result("A", "https://a.example/1", 1)])
    )
    box = ToolBox(ctx())
    out = asyncio.run(box.run(ToolCall("c1", "get_live_news", {"topic": "rain"})))
    assert not out.is_error
    assert box.activity == [
        {"tool": "get_live_news", "summary": "Live news: 1 article", "error": False, "action": None}
    ]


def test_search_provider_follows_server_settings():
    assert news_tools.search_provider(None) is None
    assert news_tools.search_provider(SimpleNamespace(search_provider="none")) is None
    assert news_tools.search_provider(SimpleNamespace(search_provider="brave", brave_api_key=None)) is None
    assert (
        news_tools.search_provider(SimpleNamespace(search_provider="searxng", searxng_url="http://s")).name == "searxng"
    )


def test_an_installed_weather_tool_becomes_automatic_and_registering_again_changes_nothing():
    async def weather(ctx, args):
        return ToolOutcome({}, "Weather: ok")

    tools = {"get_weather": Tool(ToolSpec("get_weather", "Look up live weather.", {"type": "object"}), "W", weather)}
    namespace = {
        "TOOLS": tools,
        "Tool": Tool,
        "ToolSpec": ToolSpec,
        "ToolOutcome": ToolOutcome,
        "ToolInputError": ToolInputError,
    }
    news_tools.register(namespace)
    description = tools["get_weather"].spec.description
    assert description.startswith("Look up live weather.")
    assert "without asking the user for permission" in description
    assert tools["get_weather"].run is weather
    assert "get_live_news" in tools

    news_tools.register(namespace)
    assert tools["get_weather"].spec.description == description  # added once only


def test_the_registry_hook_is_at_the_end_of_the_tool_module():
    assert assistant_tools._register_dhanz_news is news_tools.register
