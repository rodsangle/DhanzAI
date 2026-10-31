from app.services.chat_service import attachment_context_budget, provider_failure_message
from dhanz_ai import ProviderError
from tests.conftest import parse_sse


def new_conv(client, auth, **body):
    r = client.post("/api/v1/conversations", headers=auth["headers"], json=body)
    assert r.status_code == 201
    return r.json()["id"]


def send(client, auth, conv_id, content, **extra):
    r = client.post(
        f"/api/v1/conversations/{conv_id}/messages", headers=auth["headers"], json={"content": content, **extra}
    )
    return r, (parse_sse(r.text) if r.status_code == 200 else None)


def test_models_and_greeting(client, auth):
    r = client.get("/api/v1/models", headers=auth["headers"])
    body = r.json()
    assert body["greeting"] == "Hello! I'm Dhanz, your personal AI assistant. How can I help you today?"
    assert [m["key"] for m in body["models"]] == ["echo:echo-1"]


def test_stream_persists_and_titles(client, auth, provider):
    cid = new_conv(client, auth)
    r, events = send(client, auth, cid, "What is pgvector?")
    assert r.headers["content-type"].startswith("text/event-stream")
    types = [e["type"] for e in events]
    assert types[0] == "meta" and types[1] == "model" and types[-1] == "done"
    text = "".join(e["text"] for e in events if e["type"] == "delta")
    assert text.strip() == "You said: What is pgvector?"
    done = events[-1]["message"]
    assert done["status"] == "complete" and done["model"] == "echo-1" and done["output_tokens"] == 5

    # The system prompt carries the Dhanz identity and honesty rules.
    assert provider.last_messages[0].role == "system" and "Dhanz" in provider.last_messages[0].content

    detail = client.get(f"/api/v1/conversations/{cid}", headers=auth["headers"]).json()
    assert detail["title"] == "What is pgvector?"
    assert [m["role"] for m in detail["messages"]] == ["user", "assistant"]
    assert detail["messages"][1]["content"].strip() == "You said: What is pgvector?"


def test_multi_turn_history(client, auth, provider):
    cid = new_conv(client, auth)
    send(client, auth, cid, "first")
    send(client, auth, cid, "second")
    roles = [m.role for m in provider.last_messages]
    assert roles == ["system", "user", "assistant", "user"]
    assert provider.last_messages[-1].content == "second"


def test_regenerate_replaces_last_reply(client, auth):
    cid = new_conv(client, auth)
    send(client, auth, cid, "hello")
    r = client.post(f"/api/v1/conversations/{cid}/regenerate", headers=auth["headers"], json={})
    events = parse_sse(r.text)
    assert events[0]["user_message"] is None and events[-1]["type"] == "done"
    msgs = client.get(f"/api/v1/conversations/{cid}", headers=auth["headers"]).json()["messages"]
    assert [m["role"] for m in msgs] == ["user", "assistant"]


def test_edit_and_resend_truncates(client, auth, provider):
    cid = new_conv(client, auth)
    _, ev1 = send(client, auth, cid, "one")
    send(client, auth, cid, "two")
    first_user_id = ev1[0]["user_message"]["id"]
    _, ev = send(client, auth, cid, "uno", edit_message_id=first_user_id)
    assert ev[-1]["type"] == "done"
    msgs = client.get(f"/api/v1/conversations/{cid}", headers=auth["headers"]).json()["messages"]
    assert [m["content"].strip() for m in msgs] == ["uno", "You said: uno"]
    assert [m.content for m in provider.last_messages[1:]] == ["uno"]


async def test_orchestrator_uses_context_and_read_timeout_settings():
    from app.core.config import Settings
    from app.main import build_orchestrator

    defaults = Settings(
        _env_file=None, app_env="test", ollama_base_url="http://127.0.0.1:11434", ollama_models="llama3.1"
    )
    longer = Settings(
        _env_file=None,
        app_env="test",
        provider_read_timeout_seconds=600,
        ollama_num_ctx=32_768,
        ollama_base_url="http://127.0.0.1:11434",
        ollama_models="qwen3",
    )
    first = build_orchestrator(defaults)
    second = build_orchestrator(longer)
    try:
        assert first.providers["ollama"].num_ctx == 16_384
        assert first.providers["ollama"].models()[0].context_window == 16_384
        assert first.providers["ollama"]._client.timeout.read == 300
        assert first.providers["openai"]._client.timeout.read == 120
        assert second.providers["ollama"].num_ctx == 32_768
        assert second.providers["ollama"]._client.timeout.read == 600
        assert second.providers["gemini"]._client.timeout.read == 600
    finally:
        for runtime in (first, second):
            for provider in runtime.providers.values():
                await provider.aclose()


def test_attachment_budget_follows_the_model_context_window():
    assert attachment_context_budget(16_384) == 32_768
    assert attachment_context_budget(8_192) == 16_384
    assert attachment_context_budget(128_000) == 40_000


def test_provider_errors_become_specific_user_messages():
    assert "API key" in provider_failure_message(ProviderError("xai", "nope", status_code=401))
    assert "rate limit" in provider_failure_message(ProviderError("xai", "slow", status_code=429)).lower()
    assert "timed out" in provider_failure_message(ProviderError("ollama", "Network error: ReadTimeout")).lower()
    assert "context window" in provider_failure_message(
        ProviderError("xai", "HTTP 400: context length exceeded", status_code=400)
    )
    assert "could not complete" in provider_failure_message(ProviderError("xai", "boom", status_code=500))


def test_provider_failure_is_reported_and_saved(client, auth, provider, caplog):
    provider.fail_with = ProviderError("echo", "boom", status_code=401, retryable=False)
    cid = new_conv(client, auth)
    _, events = send(client, auth, cid, "hi")
    assert events[-1]["type"] == "error"
    assert "API key" in events[-1]["detail"]
    assert "boom" not in events[-1]["detail"]  # raw provider errors are not leaked to clients
    assert "provider=echo" in caplog.text and "model=" in caplog.text
    assert events[-1]["message"]["status"] == "error"

    # A failed reply is excluded from future context.
    provider.fail_with = None
    send(client, auth, cid, "again")
    assert [m.role for m in provider.last_messages] == ["system", "user"]
    assert provider.last_messages[1].content == "hi\n\nagain"


def test_explicit_unknown_model(client, auth):
    cid = new_conv(client, auth)
    _, events = send(client, auth, cid, "hi", provider="openai", model="gpt-x")
    assert events[-1]["type"] == "error" and "not available" in events[-1]["detail"]
    r, _ = send(client, auth, cid, "hi", provider="echo")
    assert r.status_code == 422


def test_validation(client, auth, settings):
    cid = new_conv(client, auth)
    assert send(client, auth, cid, "   ")[0].status_code == 422
    assert send(client, auth, cid, "x" * (settings.max_message_chars + 1))[0].status_code == 413


def test_isolation_between_users(client, auth):
    cid = new_conv(client, auth)
    r = client.post(
        "/api/v1/auth/register", json={"email": "eve@example.com", "password": "eve-password-1", "display_name": "Eve"}
    )
    eve = {"headers": {"Authorization": f"Bearer {r.json()['access_token']}"}}
    assert client.get(f"/api/v1/conversations/{cid}", headers=eve["headers"]).status_code == 404
    assert send(client, eve, cid, "hi")[0].status_code == 404
    assert client.delete(f"/api/v1/conversations/{cid}", headers=eve["headers"]).status_code == 404
    assert client.get("/api/v1/conversations", headers=eve["headers"]).json()["total"] == 0
    assert client.get("/api/v1/conversations/not-a-uuid", headers=eve["headers"]).status_code == 404


def test_list_search_pin_rename_delete_export(client, auth):
    h = auth["headers"]
    a = new_conv(client, auth)
    b = new_conv(client, auth)
    send(client, auth, a, "Tell me about rust lifetimes")
    send(client, auth, b, "Best pasta recipe")

    assert client.get("/api/v1/conversations", headers=h, params={"q": "pasta"}).json()["total"] == 1
    assert client.get("/api/v1/conversations", headers=h, params={"q": "100%"}).json()["total"] == 0

    client.patch(f"/api/v1/conversations/{a}", headers=h, json={"pinned": True, "title": "Rust"})
    items = client.get("/api/v1/conversations", headers=h).json()["items"]
    assert items[0]["id"] == a and items[0]["pinned"] and items[0]["title"] == "Rust"

    md = client.get(f"/api/v1/conversations/{a}/export", headers=h)
    assert md.headers["content-type"].startswith("text/markdown")
    assert "# Rust" in md.text and "### Dhanz" in md.text
    txt = client.get(f"/api/v1/conversations/{a}/export", headers=h, params={"format": "txt"})
    assert "You:" in txt.text

    exported = client.get("/api/v1/users/me/export", headers=h).json()
    assert len(exported["conversations"]) == 2

    assert client.delete(f"/api/v1/conversations/{a}", headers=h).status_code == 204
    assert client.get(f"/api/v1/conversations/{a}", headers=h).status_code == 404


def test_websocket_chat(client, auth):
    cid = new_conv(client, auth)
    with client.websocket_connect("/api/v1/ws/chat") as ws:
        ws.send_json({"type": "auth", "token": auth["access_token"]})
        assert ws.receive_json()["type"] == "ready"
        ws.send_json({"type": "send", "request_id": "r1", "conversation_id": cid, "content": "via socket"})
        events = []
        while True:
            e = ws.receive_json()
            events.append(e)
            if e["type"] in ("done", "error"):
                break
        assert all(e["request_id"] == "r1" for e in events)
        assert events[-1]["type"] == "done"
        ws.send_json({"type": "send", "request_id": "r2", "conversation_id": "bogus", "content": "x"})
        assert ws.receive_json() == {"type": "error", "request_id": "r2", "detail": "Conversation not found"}


def test_websocket_rejects_bad_token(client):
    import pytest
    from starlette.websockets import WebSocketDisconnect

    with client.websocket_connect("/api/v1/ws/chat") as ws:
        ws.send_json({"type": "auth", "token": "nope"})
        with pytest.raises(WebSocketDisconnect) as info:
            ws.receive_json()
        assert info.value.code == 4401


def test_health(client):
    assert client.get("/api/v1/health").json() == {"status": "ok"}
    r = client.get("/api/v1/health/ready")
    assert r.status_code == 200 and r.json()["providers"] == ["echo"]
    assert r.headers["x-content-type-options"] == "nosniff"
