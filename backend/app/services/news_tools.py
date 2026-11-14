"""Live news headlines as an assistant tool, plus automatic use of live weather.

Plugs into the host's tool registry the same way the weather tool does (``register(globals())`` at
the end of ``app/services/assistant_tools.py``), so it also works on servers whose tool module has
its own changes. News comes from the server's configured search provider (SearXNG, Brave or Tavily,
in its news mode). Only the topic the user asked about is sent; results are links and short
snippets from the provider, newest first, never invented.

The user's question about news or weather is their consent to look it up: the tool descriptions tell
the model to call these tools right away instead of asking for permission first.
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime
from urllib.parse import urlsplit

from dhanz_knowledge.search import BraveSearch, SearchProvider, SearxngSearch, TavilySearch
from dhanz_knowledge.types import SearchError

NEWS_TOOL = "get_live_news"
MAX_RESULTS = 10
MAX_LOOKUPS_PER_REPLY = 3
SNIPPET_CHARS = 300

AUTOMATIC = (
    "Call it right away, without asking the user for permission or confirmation: their question is the "
    "approval. Never say you cannot access live information when this tool is available."
)

NEWS_DESCRIPTION = (
    "Get live news headlines from the web, newest first, with each article's source, link and publish time. "
    "Use it whenever the user asks about news, headlines, breaking stories, current events or what is happening "
    "now, about a topic, person, company, place or country (an empty topic gives top headlines). "
    + AUTOMATIC
    + " Answer only from the results, cite the sources with their links and times, and say when results are "
    "missing or old. Only the topic is sent to the server's search provider."
)

WEATHER_AUTOMATIC = (
    " Use it whenever the user asks about weather, temperature, rain or a forecast. "
    + AUTOMATIC
    + " Only ask a question when the place is missing or ambiguous."
)


def search_provider(settings) -> SearchProvider | None:
    """The server's configured web search provider, or None when web search is off."""
    if settings is None:
        return None
    provider = getattr(settings, "search_provider", "none")
    if provider == "brave" and getattr(settings, "brave_api_key", None):
        return BraveSearch(settings.brave_api_key)
    if provider == "tavily" and getattr(settings, "tavily_api_key", None):
        return TavilySearch(settings.tavily_api_key)
    if provider == "searxng" and getattr(settings, "searxng_url", None):
        return SearxngSearch(settings.searxng_url)
    return None


def _query(args: dict) -> tuple[str, int]:
    topic = args.get("topic", "")
    country = args.get("country", "")
    count = args.get("max_results", 8)
    if not isinstance(topic, str) or len(topic) > 200:
        raise ValueError("topic must be text up to 200 characters.")
    if not isinstance(country, str) or len(country) > 60:
        raise ValueError("country must be a country name up to 60 characters.")
    if type(count) is not int or not 1 <= count <= MAX_RESULTS:
        raise ValueError(f"max_results must be an integer from 1 to {MAX_RESULTS}.")
    parts = [p.strip() for p in (topic, country) if p.strip()]
    query = " ".join(parts) if parts else "top news headlines"
    if topic.strip() and "news" not in topic.lower():
        query += " news"
    return query, count


async def lookup_news(args: dict, provider: SearchProvider) -> dict:
    query, count = _query(args)
    results = await provider.search(query, count=MAX_RESULTS * 2, news=True)
    seen: set[str] = set()
    articles = []
    for r in results:
        if not r.url.startswith(("https://", "http://")) or r.url in seen:
            continue
        seen.add(r.url)
        articles.append(
            {
                "title": r.title.strip()[:300],
                "url": r.url,
                "source": urlsplit(r.url).hostname or "",
                "published_at": r.published_at.isoformat() if r.published_at else None,
                "snippet": " ".join(r.snippet.split())[:SNIPPET_CHARS],
            }
        )
    # Newest first; articles without a date keep the provider's order after the dated ones.
    dated = sorted((a for a in articles if a["published_at"]), key=lambda a: a["published_at"], reverse=True)
    undated = [a for a in articles if not a["published_at"]]
    articles = (dated + undated)[:count]
    return {
        "status": "ok" if articles else "no_results",
        "query": query,
        "retrieved_at_utc": datetime.now(UTC).isoformat(),
        "provider": provider.name,
        "articles": articles,
        "instructions": (
            "Summarise the main stories from these articles only, newest first. Link each story to its source and "
            "mention its publish time. If there are no results or they are old, say so; never invent news."
        ),
    }


def _automatic_weather(namespace) -> None:
    """Tell the model to use an installed get_weather tool without asking first."""
    tools, Tool, ToolSpec = namespace["TOOLS"], namespace["Tool"], namespace["ToolSpec"]
    weather = tools.get("get_weather")
    if weather is None or WEATHER_AUTOMATIC in weather.spec.description:
        return
    spec = ToolSpec(weather.spec.name, weather.spec.description + WEATHER_AUTOMATIC, weather.spec.parameters)
    tools["get_weather"] = (
        dataclasses.replace(weather, spec=spec)
        if dataclasses.is_dataclass(weather)
        else Tool(spec, weather.label, weather.run)
    )


def register(namespace) -> None:
    """Add get_live_news to the host's existing tool registry, without replacing anything else."""
    tools = namespace["TOOLS"]
    Tool, ToolSpec = namespace["Tool"], namespace["ToolSpec"]
    ToolOutcome, ToolInputError = namespace["ToolOutcome"], namespace["ToolInputError"]
    _automatic_weather(namespace)
    if NEWS_TOOL in tools:
        return

    async def run(ctx, args):
        report = getattr(ctx, "capability_report", None) or {}
        if report.get("ai_privacy_mode") == "local_only":
            raise ToolInputError("Live news sends the topic to a web search provider and is off in local-only mode.")
        count = getattr(ctx, "_news_requests", 0)
        if count >= MAX_LOOKUPS_PER_REPLY:
            raise ToolInputError("At most three news lookups per reply. Answer from the results you have.")
        settings = getattr(ctx, "settings", None)
        if settings is None:
            from app.core.config import get_settings

            settings = get_settings()
        provider = search_provider(settings)
        if provider is None:
            raise ToolInputError(
                "Live news is unavailable: web search is not configured on this DHANZ server. Tell the user so; "
                "do not invent news."
            )
        ctx._news_requests = count + 1
        try:
            result = await lookup_news(args, provider)
        except ValueError as exc:
            raise ToolInputError(str(exc)) from None
        except SearchError:
            raise ToolInputError(
                "The news search failed. Tell the user live news could not be retrieved right now; do not invent news."
            ) from None
        finally:
            await provider.aclose()
        found = len(result["articles"])
        return ToolOutcome(result, f"Live news: {found} {'article' if found == 1 else 'articles'}")

    tools[NEWS_TOOL] = Tool(
        ToolSpec(
            NEWS_TOOL,
            NEWS_DESCRIPTION,
            {
                "type": "object",
                "properties": {
                    "topic": {
                        "type": "string",
                        "description": "What the news is about, for example 'Philippines elections' or 'Nvidia'. "
                        "Leave empty for top headlines.",
                    },
                    "country": {
                        "type": "string",
                        "description": "Country or region to focus on, if the user named one.",
                    },
                    "max_results": {"type": "integer", "minimum": 1, "maximum": MAX_RESULTS},
                },
            },
        ),
        "Checking live news",
        run,
    )
