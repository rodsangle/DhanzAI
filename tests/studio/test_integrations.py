import asyncio
import base64
import hashlib
import json
import uuid
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI, HTTPException, Request, Response

from app.api import deps
from app.assistant_studio import integrations as api
from app.assistant_studio.integration_service import AUTH, SCOPES, TOKEN, Service
from app.assistant_studio.integration_store import IntegrationError, Store
from app.models import User


@pytest.fixture
def setup(tmp_path):
    store = Store(tmp_path / "integrations")
    for name in AUTH:
        store.configure(name, "application-" + name, "private-client-secret-" + name, "https://dhanzai.com")
    uid, other = uuid.uuid4(), uuid.uuid4()
    return SimpleNamespace(
        store=store,
        uid=uid,
        other=other,
        settings=SimpleNamespace(storage_dir=str(tmp_path), api_prefix="/api/v1", max_upload_mb=25),
    )


def connected(s, name="google", services=("files", "mail"), expires=None):
    value = {
        "access_token": "private-access-token",
        "refresh_token": "private-refresh-token",
        "expires": expires or s.store.clock() + 3600,
        "services": list(services),
        "account": "owner@example.test",
        "subject": "external-owner",
        "revision": s.store.revision(s.store.config(name)),
    }
    s.store.save(s.uid, name, value)


def token_reply(name):
    return {
        "access_token": "new-private-access",
        "refresh_token": "new-private-refresh",
        "expires_in": 3600,
        "scope": " ".join(SCOPES[name]["base"] + SCOPES[name]["files"] + SCOPES[name]["mail"]),
    }


def test_credentials_encrypted_private_and_owned(setup):
    s = setup
    connected(s)
    raw = (s.store.root / "connections.sqlite3").read_bytes()
    for secret in (b"private-client-secret", b"private-access-token", b"private-refresh-token"):
        assert secret not in raw
    assert (s.store.root / "oauth.key").stat().st_mode & 0o777 == 0o600
    assert s.store.root.stat().st_mode & 0o777 == 0o700
    assert s.store.connection(s.other, "google") is None
    s.store.disconnect(s.other, "google")
    assert s.store.connection(s.uid, "google") is not None
    s.store.disconnect(s.uid, "google")
    assert s.store.connection(s.uid, "google") is None


def test_oauth_pkce_cookie_binding_single_use_and_expiry(setup):
    s = setup
    value = Service(s.store).begin(s.uid, "google", ["files"])
    query = parse_qs(urlsplit(value["authorization_url"]).query)
    assert query["access_type"] == ["offline"] and query["prompt"] == ["consent"]
    with pytest.raises(IntegrationError):
        s.store.consume(value["state"], "google", "wrong-browser")
    with pytest.raises(IntegrationError):
        s.store.consume(value["state"], "microsoft", value["cookie"])
    uid, pending = s.store.consume(value["state"], "google", value["cookie"])
    assert uid == str(s.uid)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(pending["verifier"].encode()).digest()).decode().rstrip("=")
    assert query["code_challenge"] == [challenge]
    assert "gmail" not in query["scope"][0]
    with pytest.raises(IntegrationError):
        s.store.consume(value["state"], "google", value["cookie"])
    value = Service(s.store).begin(s.uid, "google", ["files"])
    s.store.clock = lambda: 99999999999
    with pytest.raises(IntegrationError):
        s.store.consume(value["state"], "google", value["cookie"])


def test_uncertain_write_never_replays_and_completed_write_is_idempotent(setup):
    s = setup
    key = "request_" + uuid.uuid4().hex
    assert s.store.intent(s.uid, key, {"body": "draft"}) is None
    with pytest.raises(IntegrationError, match="uncertain"):
        s.store.intent(s.uid, key, {"body": "draft"})
    s.store.finish(s.uid, key, {"draft_id": "one", "sent": False})
    assert s.store.intent(s.uid, key, {"body": "draft"}) == {"draft_id": "one", "sent": False}
    with pytest.raises(IntegrationError):
        s.store.intent(s.uid, key, {"body": "changed"})
    assert s.store.intent(s.other, key, {"body": "draft"}) is None


@pytest.mark.asyncio
async def test_refresh_serialized_and_invalid_grant_requires_reconnect(setup):
    s = setup
    connected(s, expires=1)
    requests = []

    async def handler(request):
        requests.append(request)
        await asyncio.sleep(0.01)
        return httpx.Response(200, json=token_reply("google"))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        async with Service(s.store, client) as service:
            values = await asyncio.gather(*[service.access(s.uid, "google", "files") for _ in range(4)])
    assert len(requests) == 1 and all(v["Authorization"] == "Bearer new-private-access" for v in values)
    connected(s, expires=1)
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(400, json={"error": "invalid_grant"}))
    ) as client:
        async with Service(s.store, client) as service:
            with pytest.raises(IntegrationError, match="sign-in again"):
                await service.access(s.uid, "google", "files")
            assert not service.status(s.uid)[1]["connected"]


@pytest.mark.asyncio
async def test_disconnect_wins_over_inflight_refresh_and_oauth_completion(setup):
    s = setup
    connected(s, expires=1)

    def refresh(request):
        s.store.disconnect(s.uid, "google")
        return httpx.Response(200, json=token_reply("google"))

    async with httpx.AsyncClient(transport=httpx.MockTransport(refresh)) as client:
        async with Service(s.store, client) as service:
            with pytest.raises(IntegrationError, match="disconnected"):
                await service.access(s.uid, "google", "files")
    assert s.store.connection(s.uid, "google") is None
    begin = Service(s.store).begin(s.uid, "google", ["files"])
    uid, pending = s.store.consume(begin["state"], "google", begin["cookie"])

    def complete(request):
        if request.url.path.endswith("/token"):
            return httpx.Response(200, json=token_reply("google"))
        s.store.disconnect(s.uid, "google")
        return httpx.Response(200, json={"sub": "external-owner", "email": "owner@example.test"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(complete)) as client:
        async with Service(s.store, client) as service:
            with pytest.raises(IntegrationError, match="disconnected"):
                await service.complete(uid, "google", "code", pending)
    assert s.store.connection(s.uid, "google") is None


@pytest.mark.asyncio
async def test_microsoft_download_redirect_does_not_forward_access_token(setup):
    s = setup
    connected(s, "microsoft")
    requests = []

    def handler(request):
        requests.append(request)
        if request.url.host == "files.1drv.com":
            assert "authorization" not in request.headers
            return httpx.Response(200, content=b"workbook-bytes")
        assert request.headers["authorization"] == "Bearer private-access-token"
        if request.url.path.endswith("/content"):
            return httpx.Response(302, headers={"location": "https://files.1drv.com/download?signature=test"})
        return httpx.Response(200, json={"name": "Schedule.xlsx", "size": 14})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        async with Service(s.store, client) as service:
            title, data = await service.download(s.uid, "microsoft", "item!1", 1024)
    assert title == "Schedule.xlsx" and data == b"workbook-bytes" and len(requests) == 3

    def evil(request):
        assert request.url.host == "graph.microsoft.com"
        return (
            httpx.Response(302, headers={"location": "https://evil.example/file"})
            if request.url.path.endswith("/content")
            else httpx.Response(200, json={"name": "Schedule.xlsx"})
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(evil)) as client:
        async with Service(s.store, client) as service:
            with pytest.raises(IntegrationError, match="unsupported download"):
                await service.download(s.uid, "microsoft", "item1", 1024)


@pytest.mark.asyncio
async def test_google_sheet_import_export_and_draft_use_documented_endpoints(setup):
    s = setup
    connected(s)
    requests = []

    def handler(request):
        requests.append(request)
        if request.url.path.endswith("/export"):
            assert "spreadsheetml.sheet" in request.url.params["mimeType"]
            return httpx.Response(200, content=b"xlsx-content")
        if "/upload/" in request.url.path:
            assert b"application/vnd.google-apps.spreadsheet" in request.content
            return httpx.Response(200, json={"id": "new-sheet", "name": "Edited workbook"})
        if request.url.path.endswith("/drafts"):
            encoded = json.loads(request.content)["message"]["raw"]
            message = base64.urlsafe_b64decode(encoded)
            assert b"To: recipient@example.test" in message
            return httpx.Response(200, json={"id": "draft-1"})
        return httpx.Response(200, json={"name": "Schedule", "mimeType": "application/vnd.google-apps.spreadsheet"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        async with Service(s.store, client) as service:
            title, data = await service.download(s.uid, "google", "file1", 1024)
            assert title == "Schedule.xlsx" and data == b"xlsx-content"
            assert (await service.upload(s.uid, "google", "Edited.xlsx", b"xlsx", "application/octet-stream", True))[
                "created"
            ]
            draft = await service.draft(s.uid, "google", "recipient@example.test", "Subject", "Review this draft.")
            assert draft["draft_created"] and draft["sent"] is False
    assert not any("/send" in r.url.path for r in requests)


@pytest_asyncio.fixture
async def web(setup, monkeypatch):
    s = setup
    requests = []

    def handler(request):
        requests.append(request)
        if str(request.url) in TOKEN.values():
            name = "microsoft" if "microsoftonline" in request.url.host else "google"
            return httpx.Response(200, json=token_reply(name))
        if request.url.path == "/oauth2/v3/userinfo":
            return httpx.Response(200, json={"sub": "external-owner", "email": "owner@example.test"})
        if request.url.path.endswith("/drafts"):
            return httpx.Response(200, json={"id": "draft-one"})
        return httpx.Response(200, json={"id": "external-owner", "mail": "owner@example.test"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(api, "Service", lambda store: Service(store, client))
    app = FastAPI()
    app.state.settings = s.settings
    app.include_router(api.router, prefix="/api/v1")
    users = {s.uid: SimpleNamespace(id=s.uid, is_active=True), s.other: SimpleNamespace(id=s.other, is_active=True)}
    docs = {}

    async def auth(request: Request):
        try:
            return users[uuid.UUID(request.headers["x-owner"])]
        except (KeyError, ValueError):
            raise HTTPException(401) from None

    async def db():
        async def get(model, identifier):
            return users.get(identifier) if model is User else docs.get(identifier)

        return SimpleNamespace(get=get)

    async def settings():
        return s.settings

    app.dependency_overrides.update({deps.get_current_user: auth, deps.get_db: db, deps.get_settings: settings})
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://dhanzai.com") as browser:
        yield SimpleNamespace(s=s, browser=browser, app=app, requests=requests, users=users, docs=docs)
    await client.aclose()


@pytest.mark.asyncio
async def test_oauth_http_requires_same_browser_and_does_not_expose_tokens(web):
    w = web
    response = await w.browser.post(
        "/api/v1/integrations/google/connect", json={"services": ["files", "mail"]}, headers={"x-owner": str(w.s.uid)}
    )
    assert response.status_code == 200
    assert "HttpOnly" in response.headers["set-cookie"] and "Secure" in response.headers["set-cookie"]
    query = parse_qs(urlsplit(response.json()["authorization_url"]).query)
    path = "/api/v1/integrations/callback/google?state=" + query["state"][0] + "&code=single-use-code"
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=w.app), base_url="https://dhanzai.com") as stranger:
        assert (await stranger.get(path)).status_code == 400
    assert not w.requests
    assert (await w.browser.get(path)).status_code == 200
    assert (await w.browser.get(path)).status_code == 400
    for uid, connected_value in ((w.s.uid, True), (w.s.other, False)):
        response = await w.browser.get("/api/v1/integrations", headers={"x-owner": str(uid)})
        google = response.json()["connections"][1]
        assert google["connected"] is connected_value
        assert "private-access" not in response.text and "refresh_token" not in response.text


@pytest.mark.asyncio
async def test_http_draft_is_idempotent_upload_ownership_and_send_operation_rejected(web):
    w = web
    connected(w.s)
    body = {
        "operation": "save_draft",
        "to": "recipient@example.test",
        "subject": "Subject",
        "body": "Draft body",
        "request_key": "draft_" + uuid.uuid4().hex,
    }
    headers = {"x-owner": str(w.s.uid)}
    path = "/api/v1/integrations/google/operations"
    for _ in range(2):
        response = await w.browser.post(path, headers=headers, json=body)
        assert response.status_code == 200 and response.json()["sent"] is False
    assert len(w.requests) == 1 and w.requests[0].url.path.endswith("/drafts")
    assert (await w.browser.post(path, headers=headers, json={"operation": "send_mail"})).status_code == 422
    assert (await w.browser.post(path, headers={"x-owner": str(w.s.other)}, json=body)).status_code == 409
    foreign = uuid.uuid4()
    w.docs[foreign] = SimpleNamespace(user_id=w.s.other, storage_key="private-file")
    response = await w.browser.post(
        path,
        headers=headers,
        json={"operation": "upload_copy", "document_id": str(foreign), "request_key": "upload_" + uuid.uuid4().hex},
    )
    assert response.status_code == 409 and len(w.requests) == 1
    assert (await w.browser.delete("/api/v1/integrations/google", headers=headers)).status_code == 200
    assert w.s.store.connection(w.s.uid, "google") is None


@pytest.mark.asyncio
async def test_inactive_dhanz_account_cannot_finish_oauth(web):
    w = web
    response = await w.browser.post(
        "/api/v1/integrations/google/connect", json={"services": ["files"]}, headers={"x-owner": str(w.s.uid)}
    )
    state = parse_qs(urlsplit(response.json()["authorization_url"]).query)["state"][0]
    w.users[w.s.uid].is_active = False
    response = await w.browser.get("/api/v1/integrations/callback/google", params={"state": state, "code": "code"})
    assert response.status_code == 400 and not w.requests


@pytest.mark.asyncio
async def test_account_deletion_removes_only_own_integration_credentials(web):
    w = web
    connected(w.s)
    other = w.s.store.connection(w.s.uid, "google").copy()
    w.s.store.save(w.s.other, "google", other)
    api.install_account_cleanup(w.app)

    @w.app.delete("/api/v1/users/me")
    async def delete(request: Request):
        request.state.user_id = w.s.uid
        return Response(status_code=204)

    assert (await w.browser.delete("/api/v1/users/me")).status_code == 204
    assert w.s.store.connection(w.s.uid, "google") is None
    assert w.s.store.connection(w.s.other, "google") is not None


def test_frozen_integrations_updaters_stage_only_reviewed_modules():
    import runpy

    root = Path(__file__).resolve().parents[2]
    installer = runpy.run_path(str(root / "deploy/updaters/install_integrations_backend.py"))
    value = installer["payload"]()
    for name, source in value["modules"].items():
        assert source == (root / "server_extensions/assistant_studio" / name).read_text()
    assert value["wizard"] == (root / "apps/server_companion/configure_integrations.py").read_text()
    current = "def install(app):\n    _install_chat_files(app)\n    _install_rog_worker(app)\n"
    updated = installer["patch_bootstrap"](current)
    assert installer["patch_bootstrap"](updated) == updated
    assert "_install_rog_worker(app)" in updated
    wrapper = runpy.run_path(str(root / "deploy/updaters/install_integrations.py"))
    import base64
    import gzip

    contents = json.loads(gzip.decompress(base64.b64decode(wrapper["PAYLOAD"])))
    assert (
        contents["install_integrations_backend.py"]
        == (root / "deploy/updaters/install_integrations_backend.py").read_text()
    )


def test_unsafe_identifiers_and_redirect_origins_rejected():
    from app.assistant_studio.integration_service import identifier
    from app.assistant_studio.integration_store import origin

    assert identifier("AAMk_message=") == "AAMk_message%3D"
    for value in ("../secret", "https://evil.example/file", "file?token=secret"):
        with pytest.raises(IntegrationError):
            identifier(value)
    for value in ("http://dhanzai.com", "https://user:secret@dhanzai.com", "https://dhanzai.com/path"):
        with pytest.raises(IntegrationError):
            origin(value)
