"""Phase 2: web research, citations and the knowledge library."""

from alembic import command
from alembic.config import Config

from app.services.knowledge_service import wait_for_background_indexing
from tests.conftest import BACKEND_DIR, parse_sse


def chat(client, auth, content, **extra):
    cid = client.post("/api/v1/conversations", headers=auth["headers"], json={}).json()["id"]
    r = client.post(
        f"/api/v1/conversations/{cid}/messages", headers=auth["headers"], json={"content": content, **extra}
    )
    assert r.status_code == 200, r.text
    return cid, parse_sse(r.text)


def research_stages(events):
    return [e["stage"] for e in events if e["type"] == "research"]


def documents(client, auth):
    return client.get("/api/v1/knowledge/documents", headers=auth["headers"]).json()


def test_features_reported(client, auth):
    features = client.get("/api/v1/models", headers=auth["headers"]).json()["features"]
    assert features == {"web_search": True, "semantic_search": True}


def test_web_research_turn_cites_sources_and_indexes(client, auth, provider, search):
    cid, events = chat(client, auth, "Hey Dhanz, search the internet for the latest semiconductor technology")
    assert search.queries == ["the latest semiconductor technology"]
    assert research_stages(events) == ["searching", "reading", "done", "sources"]
    sources = next(e for e in events if e.get("stage") == "sources")["sources"]
    assert sources[0]["n"] == 1 and sources[0]["url"] == "https://chips.example/2nm"
    assert sources[0]["site_name"] == "Chip Times" and sources[0]["published_at"].startswith("2026-10-20")

    system = provider.last_messages[0].content
    assert "<sources>" in system and "[1] 2nm chips arrive" in system and "gate-all-around" in system
    assert "untrusted" in system

    done = events[-1]
    assert done["type"] == "done" and done["message"]["citations"][0]["url"] == "https://chips.example/2nm"
    saved = client.get(f"/api/v1/conversations/{cid}", headers=auth["headers"]).json()["messages"][-1]
    assert saved["citations"] == done["message"]["citations"]

    client.portal.call(wait_for_background_indexing)
    docs = documents(client, auth)
    assert docs["total"] == 1 and docs["items"][0]["added_via"] == "research"


def test_no_research_for_ordinary_or_disabled_messages(client, auth, provider, search):
    _, events = chat(client, auth, "Write a haiku about autumn leaves")
    assert research_stages(events) == [] and "<sources>" not in provider.last_messages[0].content
    _, events = chat(client, auth, "latest chip news", web=False)
    assert research_stages(events) == [] and search.queries == []


def test_forced_web_research(client, auth, search):
    _, events = chat(client, auth, "Tell me about chips", web=True)
    assert "searching" in research_stages(events) and search.queries == ["Tell me about chips"]


def test_pasted_link_is_read_and_summarised(client, auth, provider, search):
    _, events = chat(client, auth, "Please summarize https://garden.example/tomatoes", web=False)
    assert research_stages(events) == []  # web=False also disables reading links
    _, events = chat(client, auth, "Please summarize https://garden.example/tomatoes")
    assert search.queries == [] and "reading" in research_stages(events)
    assert "six hours of direct sunlight" in provider.last_messages[0].content


def test_unreadable_page_is_reported_to_the_model(client, auth, provider):
    chat(client, auth, "What does https://private.example/page say?")
    system = provider.last_messages[0].content
    assert "could not be read" in system and "robots.txt" in system


def test_web_search_unavailable(settings, provider, knowledge):
    from fastapi.testclient import TestClient

    from app.core.rate_limit import limiter
    from app.main import create_app
    from dhanz_ai import Orchestrator

    knowledge.search = None
    limiter.reset()
    with TestClient(create_app(settings, Orchestrator([provider]), knowledge)) as c:
        r = c.post(
            "/api/v1/auth/register",
            json={"email": "x@example.com", "password": "correct-horse-9", "display_name": "X"},
        )
        auth = {"headers": {"Authorization": f"Bearer {r.json()['access_token']}"}}
        assert c.get("/api/v1/models", headers=auth["headers"]).json()["features"]["web_search"] is False
        _, events = chat(c, auth, "latest semiconductor news")
    assert research_stages(events) == ["unavailable"]
    assert "Web search is not configured" in provider.last_messages[0].content


def test_auto_index_can_be_disabled(client, auth):
    assert (
        client.patch("/api/v1/users/me", headers=auth["headers"], json={"auto_index_web": False}).json()[
            "auto_index_web"
        ]
        is False
    )
    chat(client, auth, "latest semiconductor news")
    client.portal.call(wait_for_background_indexing)
    assert documents(client, auth)["total"] == 0


def test_library_add_list_search_delete_and_use_in_chat(client, auth, provider):
    h = auth["headers"]
    r = client.post("/api/v1/knowledge/documents", headers=h, json={"url": "https://garden.example/tomatoes"})
    assert r.status_code == 201, r.text
    doc = r.json()
    assert doc["title"] == "Growing tomatoes" and doc["added_via"] == "manual"

    detail = client.get(f"/api/v1/knowledge/documents/{doc['id']}", headers=h).json()
    assert detail["chunk_count"] >= 1 and "suckers" in detail["content"]
    assert documents(client, auth)["total"] == 1
    assert client.get("/api/v1/knowledge/documents", headers=h, params={"q": "tomato"}).json()["total"] == 1

    hits = client.get("/api/v1/knowledge/search", headers=h, params={"q": "how much sunlight do tomato plants need"})
    assert hits.json()[0]["url"] == "https://garden.example/tomatoes"

    # A non-web question still draws on the user's own library.
    _, events = chat(client, auth, "How should I prune tomato plants?")
    sources = next(e for e in events if e.get("stage") == "sources")["sources"]
    assert sources[0]["origin"] == "library"
    assert "your library" in provider.last_messages[0].content

    assert client.delete(f"/api/v1/knowledge/documents/{doc['id']}", headers=h).status_code == 204
    assert documents(client, auth)["total"] == 0

    exported = client.get("/api/v1/users/me/export", headers=h).json()
    assert exported["knowledge_documents"] == []


def test_keyword_library_search_without_embeddings(client, auth, knowledge, provider):
    knowledge.embedder = None  # e.g. EMBEDDING_PROVIDER=none
    h = auth["headers"]
    client.post("/api/v1/knowledge/documents", headers=h, json={"url": "https://garden.example/tomatoes"})
    hits = client.get("/api/v1/knowledge/search", headers=h, params={"q": "How much sun do tomato plants need?"}).json()
    assert hits and hits[0]["url"] == "https://garden.example/tomatoes"
    assert client.get("/api/v1/knowledge/search", headers=h, params={"q": "stock market crash"}).json() == []
    _, events = chat(client, auth, "How much sun do tomato plants need?", web=None)
    assert any(e.get("stage") == "sources" for e in events)
    assert "six hours of direct sunlight" in provider.last_messages[0].content


def test_library_is_private(client, auth):
    h = auth["headers"]
    doc = client.post("/api/v1/knowledge/documents", headers=h, json={"url": "https://garden.example/tomatoes"}).json()
    r = client.post(
        "/api/v1/auth/register", json={"email": "eve@example.com", "password": "eve-password-1", "display_name": "E"}
    )
    eve = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert client.get(f"/api/v1/knowledge/documents/{doc['id']}", headers=eve).status_code == 404
    assert client.delete(f"/api/v1/knowledge/documents/{doc['id']}", headers=eve).status_code == 404
    assert client.get("/api/v1/knowledge/documents", headers=eve).json()["total"] == 0
    assert client.get("/api/v1/knowledge/search", headers=eve, params={"q": "tomato sunlight"}).json() == []


def test_library_refuses_blocked_and_internal_pages(client, auth):
    h = auth["headers"]
    r = client.post("/api/v1/knowledge/documents", headers=h, json={"url": "https://private.example/page"})
    assert r.status_code == 422 and "robots.txt" in r.json()["detail"]
    r = client.post("/api/v1/knowledge/documents", headers=h, json={"url": "http://intranet.example/admin"})
    assert r.status_code == 422 and "private or internal" in r.json()["detail"]
    r = client.post("/api/v1/knowledge/documents", headers=h, json={"url": "file:///etc/passwd"})
    assert r.status_code == 422


def test_migrations_match_models(tmp_path):
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.attributes["database_url"] = f"sqlite+aiosqlite:///{tmp_path / 'check.db'}"
    cfg.attributes["configure_logger"] = False
    command.upgrade(cfg, "head")
    command.check(cfg)  # raises if models and migrations differ
