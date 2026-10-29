import json

import httpx
import pytest

from dhanz_knowledge import (
    BraveSearch,
    Fetcher,
    FetchError,
    GeminiEmbedder,
    OllamaEmbedder,
    OpenAIEmbedder,
    Page,
    ResearchOutcome,
    ResearchPipeline,
    SearxngSearch,
    TavilySearch,
    bm25_scores,
    build_context,
    build_query,
    check_url,
    chunk_text,
    extract_page,
    extract_urls,
    needs_search,
    reciprocal_rank_fusion,
    wants_web,
)

ARTICLE = """<html lang="en"><head><title>Chip news - Example</title>
<meta property="og:site_name" content="Example Tech">
<meta property="article:published_time" content="2026-10-20T09:00:00Z">
<meta name="author" content="R. Writer">
<script>var tracking = 1;</script></head>
<body><nav><a href="/">Home</a> <a href="/news">News</a></nav>
<div class="cookie-banner">We use cookies</div>
<article><h1>New 2nm semiconductor process</h1>
<p>Foundries began volume production of 2 nanometre chips using gate-all-around transistors.</p>
<p>The new process improves power efficiency by about 25 percent compared with 3 nanometre nodes.</p>
<ul><li>Backside power delivery</li><li>High-NA EUV lithography</li></ul></article>
<footer>Copyright</footer></body></html>"""


async def public_resolver(host: str) -> list[str]:
    return {"internal.test": ["10.0.0.5"], "metadata.test": ["169.254.169.254"]}.get(host, ["93.184.216.34"])


# ---------------------------------------------------------------- safety


@pytest.mark.parametrize(
    "url",
    [
        "ftp://example.com/x",
        "http://127.0.0.1/admin",
        "http://[::1]/",
        "http://internal.test/",
        "http://metadata.test/latest/meta-data",
        "http://example.com:8080/",
        "http://user:pw@example.com/",
        "file:///etc/passwd",
    ],
)
async def test_unsafe_urls_rejected(url):
    with pytest.raises(FetchError):
        await check_url(url, public_resolver)


async def test_public_url_ok():
    assert await check_url("https://example.com/a?b=1", public_resolver) == "https://example.com/a?b=1"


# ---------------------------------------------------------------- extraction


def test_extract_article_main_content_and_metadata():
    page = extract_page(ARTICLE, "https://example.com/chips")
    assert page.title == "Chip news - Example"
    assert page.site_name == "Example Tech"
    assert page.author == "R. Writer"
    assert page.published_at.isoformat().startswith("2026-10-20")
    assert "gate-all-around" in page.text and "- Backside power delivery" in page.text
    assert "cookies" not in page.text and "Home" not in page.text and "tracking" not in page.text


# ---------------------------------------------------------------- fetcher


def site(routes: dict[str, httpx.Response], log: list[str] | None = None) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        if log is not None:
            log.append(f"{request.url} UA={request.headers.get('user-agent')} cookie={request.headers.get('cookie')}")
        return routes.get(str(request.url), httpx.Response(404))

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def html(body: str, status: int = 200) -> httpx.Response:
    return httpx.Response(status, text=body, headers={"content-type": "text/html; charset=utf-8"})


def make_fetcher(routes, log=None) -> Fetcher:
    return Fetcher(site(routes, log), resolver=public_resolver, min_host_interval=0)


async def test_fetch_reads_page_and_identifies_itself():
    log: list[str] = []
    f = make_fetcher(
        {"https://example.com/robots.txt": httpx.Response(404), "https://example.com/chips": html(ARTICLE)}, log
    )
    page = await f.fetch("https://example.com/chips")
    assert "2 nanometre" in page.text and page.retrieved_at is not None
    assert all("DhanzAI-Research" in line and "cookie=None" in line for line in log)


async def test_robots_disallow_is_respected():
    robots = httpx.Response(200, text="User-agent: *\nDisallow: /private/\n")
    f = make_fetcher({"https://example.com/robots.txt": robots, "https://example.com/private/x": html(ARTICLE)})
    with pytest.raises(FetchError, match="robots.txt"):
        await f.fetch("https://example.com/private/x")


async def test_robots_server_error_means_disallow():
    f = make_fetcher({"https://example.com/robots.txt": httpx.Response(503), "https://example.com/a": html(ARTICLE)})
    with pytest.raises(FetchError, match="robots.txt"):
        await f.fetch("https://example.com/a")


@pytest.mark.parametrize("status", [401, 402, 403])
async def test_paywalls_and_logins_are_not_bypassed(status):
    f = make_fetcher(
        {"https://example.com/robots.txt": httpx.Response(404), "https://example.com/a": html("x", status)}
    )
    with pytest.raises(FetchError, match="login or subscription"):
        await f.fetch("https://example.com/a")


async def test_redirect_to_private_address_blocked():
    f = make_fetcher(
        {
            "https://example.com/robots.txt": httpx.Response(404),
            "https://example.com/go": httpx.Response(302, headers={"location": "http://internal.test/secret"}),
        }
    )
    with pytest.raises(FetchError, match="private"):
        await f.fetch("https://example.com/go")


async def test_non_html_rejected():
    pdf = httpx.Response(200, content=b"%PDF", headers={"content-type": "application/pdf"})
    f = make_fetcher({"https://example.com/robots.txt": httpx.Response(404), "https://example.com/a.pdf": pdf})
    with pytest.raises(FetchError, match="unsupported content type"):
        await f.fetch("https://example.com/a.pdf")


# ---------------------------------------------------------------- search providers


def json_client(payload: dict, captured: dict) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        captured["body"] = json.loads(request.content) if request.content else None
        return httpx.Response(200, json=payload)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_brave():
    cap: dict = {}
    payload = {
        "web": {"results": [{"title": "T", "url": "https://a.com", "description": "d", "page_age": "2026-10-01"}]}
    }
    results = await BraveSearch("bk", json_client(payload, cap)).search("chips", count=3)
    assert results[0].url == "https://a.com" and results[0].published_at.year == 2026
    assert cap["headers"]["x-subscription-token"] == "bk" and "q=chips" in cap["url"]


async def test_tavily_and_searxng():
    cap: dict = {}
    r = await TavilySearch(
        "tk", json_client({"results": [{"title": "T", "url": "https://b.com", "content": "c"}]}, cap)
    ).search("q", news=True)
    assert r[0].snippet == "c" and cap["body"]["topic"] == "news"
    r = await SearxngSearch(
        "http://sx", json_client({"results": [{"title": "S", "url": "https://c.com"}]}, cap)
    ).search("q")
    assert r[0].url == "https://c.com" and "format=json" in cap["url"]


# ---------------------------------------------------------------- embeddings


async def test_embedders_parse_responses():
    cap: dict = {}
    oa = OpenAIEmbedder(
        "k", client=json_client({"data": [{"index": 1, "embedding": [0, 1]}, {"index": 0, "embedding": [1, 0]}]}, cap)
    )
    assert await oa.embed(["a", "b"]) == [[1, 0], [0, 1]]
    assert oa.key == "openai:text-embedding-3-small"
    gm = GeminiEmbedder("k", client=json_client({"embeddings": [{"values": [0.5]}]}, cap))
    assert await gm.embed(["a"]) == [[0.5]]
    ol = OllamaEmbedder("http://o", client=json_client({"embeddings": [[0.1, 0.2]]}, cap))
    assert await ol.embed(["a"]) == [[0.1, 0.2]]


# ---------------------------------------------------------------- ranking & research


def test_chunking_and_bm25():
    text = "\n".join(f"Paragraph {i} " + "word " * 60 for i in range(20))
    chunks = chunk_text(text, target_chars=800, overlap_chars=100)
    assert len(chunks) > 3 and all(len(c) <= 900 for c in chunks)
    scores = bm25_scores("solar panel efficiency", ["cats and dogs", "solar panel efficiency is 22 percent"])
    assert scores[1] > scores[0] == 0
    fused = reciprocal_rank_fusion([[2, 0, 1], [0, 2]])
    assert max(fused, key=fused.get) in (0, 2)


def test_query_and_intent_helpers():
    assert build_query("Hey Dhanz, search the internet for the latest semiconductor technology") == (
        "the latest semiconductor technology"
    )
    assert build_query("What is the price of gold today?") == "What is the price of gold today"
    assert wants_web("latest semiconductor news") and wants_web("summarise https://example.com/x")
    assert not wants_web("write a poem about cats")
    assert not needs_search("summarise https://example.com/x") and needs_search("news on https://a.com")
    assert extract_urls("see https://a.com/x, and https://b.org.") == ["https://a.com/x", "https://b.org"]


class FakeSearch(BraveSearch):
    def __init__(self, results):
        super().__init__("k")
        self.results = results
        self.queries = []

    async def search(self, query, *, count=6, news=False):
        self.queries.append(query)
        return self.results


async def test_pipeline_reads_pages_and_falls_back_to_snippets():
    from dhanz_knowledge import SearchResult

    results = [
        SearchResult("Chips", "https://example.com/chips", "snippet 1"),
        SearchResult("Blocked", "https://blocked.com/x", "Blocked page snippet about 2nm chips"),
    ]
    routes = {
        "https://example.com/robots.txt": httpx.Response(404),
        "https://example.com/chips": html(ARTICLE),
        "https://blocked.com/robots.txt": httpx.Response(200, text="User-agent: *\nDisallow: /"),
    }
    pipeline = ResearchPipeline(FakeSearch(results), make_fetcher(routes))
    events = [e async for e in pipeline.run("latest 2nm semiconductor process", use_search=True)]
    stages = [e.stage for e in events[:-1]]
    assert stages == ["searching", "reading", "done"]
    outcome = events[-1]
    assert isinstance(outcome, ResearchOutcome)
    assert {p.url for p in outcome.passages} == {"https://example.com/chips", "https://blocked.com/x"}
    assert outcome.failures[0]["url"] == "https://blocked.com/x"

    context, citations = build_context(outcome.passages)
    assert [c.n for c in citations] == [1, 2]
    assert context.startswith("[1] Chip news - Example (Example Tech; published 2026-10-20")
    assert "URL: https://example.com/chips" in context


async def test_pipeline_reads_linked_url_without_search():
    routes = {"https://example.com/robots.txt": httpx.Response(404), "https://example.com/chips": html(ARTICLE)}
    pipeline = ResearchPipeline(None, make_fetcher(routes))
    events = [e async for e in pipeline.run("Summarize https://example.com/chips", use_search=True)]
    outcome = events[-1]
    assert outcome.query is None and len(outcome.pages) == 1
    assert isinstance(outcome.pages[0], Page)
