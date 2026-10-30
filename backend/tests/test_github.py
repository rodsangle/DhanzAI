import base64
import json
import uuid

import httpx
import pytest
from cryptography.fernet import Fernet

from app.db.session import make_engine, make_sessionmaker
from app.models import GitHubConnection
from app.services import github_service as github
from app.services.assistant_tools import ToolBox, ToolContext
from dhanz_ai import ToolCall
from tests.test_tools import ToolCallingProvider, make_client, signup

TOKEN = "github_pat_" + "test" * 12
REPO = {"id": 7, "full_name": "ada/project", "default_branch": "main", "private": True}
ROOT = "/api/v1/github"


@pytest.fixture(autouse=True)
def remote(settings, monkeypatch):
    settings.github_token_encryption_key = Fernet.generate_key().decode()
    state = {"requests": [], "status": 200, "repo": dict(REPO), "text": "print('hello')\n" * 230}

    def respond(request):
        state["requests"].append(request)
        assert request.method == "GET"
        assert request.url.host == "api.github.com"
        assert request.headers["authorization"] == "Bearer " + TOKEN
        if state["status"] != 200:
            return httpx.Response(state["status"], text=TOKEN, headers={"location": "https://evil.example/secret"})
        path = request.url.path
        if path == "/user":
            return httpx.Response(200, json={"login": "ada"})
        if path == "/repos/ada/project":
            return httpx.Response(200, json=state["repo"])
        if path == "/repos/ada/project/contents/":
            return httpx.Response(
                200, json=[{"name": "main.py", "path": "main.py", "type": "file", "size": 15, "sha": "abc"}]
            )
        if path.startswith("/repos/ada/project/contents/"):
            if "file_response" in state:
                return httpx.Response(200, json=state["file_response"])
            raw = state["text"].encode()
            return httpx.Response(
                200,
                json={
                    "type": "file",
                    "size": len(raw),
                    "encoding": "base64",
                    "content": base64.b64encode(raw).decode(),
                    "sha": "abc",
                },
            )
        if path == "/repos/ada/project/pulls/2":
            return httpx.Response(
                200, json={"title": "Fix", "body": "Review me", "head": {"sha": "head"}, "base": {"sha": "base"}}
            )
        if path.endswith("/files"):
            return httpx.Response(200, json=[{"filename": "main.py", "status": "modified", "patch": "x" * 3000}])
        if path.endswith("/issues") or path.endswith("/pulls"):
            return httpx.Response(
                200, json=[{"number": i, "title": "Issue", "body": "Body", "state": "open"} for i in range(20)]
            )
        return httpx.Response(404)

    monkeypatch.setattr(github, "http_client", lambda: httpx.AsyncClient(transport=httpx.MockTransport(respond)))
    return state


def connect(client, auth):
    response = client.put(
        ROOT + "/connection", headers=auth["headers"], json={"token": TOKEN, "repositories": ["ada/project"]}
    )
    assert response.status_code == 200, response.text
    assert TOKEN not in response.text
    return response.json()


def read(client, auth, operation="file", **query):
    return client.get(
        ROOT + "/read", headers=auth["headers"], params={"operation": operation, "repository": "ada/project", **query}
    )


def test_connection_auth_status_disconnect(client, auth):
    assert client.get(ROOT + "/connection").status_code == 401
    assert not client.get(ROOT + "/connection", headers=auth["headers"]).json()["connected"]
    assert connect(client, auth)["repositories"] == [REPO]
    assert read(client, auth, "repositories").json()["repositories"] == [REPO]
    assert client.delete(ROOT + "/connection", headers=auth["headers"]).status_code == 204
    assert read(client, auth).status_code == 409


async def test_token_encrypted_and_bound_to_account(client, auth, settings):
    connect(client, auth)
    engine = make_engine(settings.database_url)
    async with make_sessionmaker(engine)() as db:
        record = await db.get(GitHubConnection, uuid.UUID(auth["user"]["id"]))
        assert TOKEN not in record.encrypted_token
        decrypted = json.loads(github.cipher(settings).decrypt(record.encrypted_token.encode()))
        assert decrypted == {"user_id": auth["user"]["id"], "token": TOKEN}
        record.encrypted_token = (
            github.cipher(settings).encrypt(json.dumps({"user_id": "other", "token": TOKEN}).encode()).decode()
        )
        await db.commit()
    assert read(client, auth).status_code == 409
    await engine.dispose()


def test_isolation_and_selected_repository_only(client, auth, remote):
    connect(client, auth)
    other = client.post(
        "/api/v1/auth/register",
        json={"email": "other@example.com", "password": "correct-horse-9", "display_name": "Other"},
    ).json()
    headers = {"Authorization": "Bearer " + other["access_token"]}
    assert client.get(ROOT + "/connection", headers=headers).json()["repositories"] == []
    assert (
        client.get(
            ROOT + "/read", headers=headers, params={"operation": "file", "repository": "ada/project"}
        ).status_code
        == 409
    )
    count = len(remote["requests"])
    assert read(client, auth, repository="other/private").status_code == 403
    assert len(remote["requests"]) == count


def test_directory_file_pagination_and_safe_refs(client, auth, remote):
    connect(client, auth)
    assert read(client, auth, "directory").json()["entries"][0]["path"] == "main.py"
    first = read(client, auth, path="main.py", ref="feature/test?secret=1").json()
    assert first["next_line"] == 201 and first["end_line"] == 200
    assert remote["requests"][-1].url.params["ref"] == "feature/test?secret=1"
    assert first["sha"] == "abc"
    second = read(client, auth, path="main.py", start_line=201).json()
    assert second["next_line"] is None and second["end_line"] == 230
    assert read(client, auth, path="main.py", start_line=9999).status_code == 400


@pytest.mark.parametrize("path", ["../secret", "/etc/passwd", "a/../../secret", "a\\b", "a//b", "a/./b"])
def test_path_traversal_rejected(client, auth, path):
    connect(client, auth)
    assert read(client, auth, path=path).status_code == 400


@pytest.mark.parametrize("text", ["\0binary", "x" * 128001, "x" * 25000])
def test_binary_oversize_and_long_lines(client, auth, remote, text):
    connect(client, auth)
    remote["text"] = text
    assert read(client, auth, path="file").status_code in {400, 413}


@pytest.mark.parametrize("status", [301, 302, 401, 403, 404, 429, 500])
def test_upstream_errors_redacted_and_redirects_not_followed(client, auth, remote, status):
    connect(client, auth)
    remote["status"] = status
    before = len(remote["requests"])
    response = read(client, auth)
    assert response.status_code == 502
    assert TOKEN not in response.text
    assert len(remote["requests"]) == before + 1


def test_no_writes_and_changed_repo_identity(client, auth, remote):
    connect(client, auth)
    assert read(client, auth, "create_branch").status_code == 422
    remote["repo"]["id"] = 123
    assert read(client, auth).status_code == 409


def test_pr_patch_truncation_and_list_pagination(client, auth):
    connect(client, auth)
    assert read(client, auth, "issues").json()["next_page"] == 2
    assert read(client, auth, "pulls").json()["items"][0]["is_pull_request"]
    result = read(client, auth, "pull", number=2).json()
    assert result["head_sha"] == "head"
    assert result["files"][0]["patch_incomplete"]
    assert len(result["files"][0]["patch"]) == 2000


def test_missing_key_invalid_token_and_rotation(client, auth, settings):
    settings.github_token_encryption_key = None
    assert not client.get(ROOT + "/connection", headers=auth["headers"]).json()["configured"]
    assert (
        client.put(
            ROOT + "/connection", headers=auth["headers"], json={"token": TOKEN, "repositories": ["ada/project"]}
        ).status_code
        == 503
    )
    settings.github_token_encryption_key = Fernet.generate_key().decode()
    assert (
        client.put(
            ROOT + "/connection", headers=auth["headers"], json={"token": "bad", "repositories": ["ada/project"]}
        ).status_code
        == 400
    )
    connect(client, auth)
    settings.github_token_encryption_key = Fernet.generate_key().decode()
    assert read(client, auth).status_code == 409


async def test_tool_uses_users_connection_and_handles_invalid_arguments(client, auth, settings):
    connect(client, auth)
    engine = make_engine(settings.database_url)
    box = ToolBox(ToolContext(make_sessionmaker(engine), uuid.UUID(auth["user"]["id"]), None, settings=settings))
    assert "github_read" in [s.name for s in box.specs]
    result = await box.run(
        ToolCall("call", "github_read", {"operation": "file", "repository": "ada/project", "path": "main.py"})
    )
    assert not result.is_error
    assert TOKEN not in str(result) and TOKEN not in str(box.activity)
    result = await box.run(ToolCall("bad", "github_read", {"operation": "file", "url": "https://evil.example"}))
    assert result.is_error
    await engine.dispose()


async def test_account_deletion_cascades_credentials(client, auth, settings):
    connect(client, auth)
    response = client.request(
        "DELETE", "/api/v1/users/me", headers=auth["headers"], json={"password": "correct-horse-9"}
    )
    assert response.status_code == 204
    engine = make_engine(settings.database_url)
    async with make_sessionmaker(engine)() as db:
        assert await db.get(GitHubConnection, uuid.UUID(auth["user"]["id"])) is None
    await engine.dispose()


def test_account_export_excludes_credentials(client, auth):
    connect(client, auth)
    response = client.get("/api/v1/users/me/export", headers=auth["headers"])
    assert response.status_code == 200
    assert response.json()["github_connection"] == {"login": "ada", "repositories": [REPO]}
    assert TOKEN not in response.text and "encrypted_token" not in response.text


def test_chat_reads_repository_through_authenticated_tool(settings, knowledge):
    provider = ToolCallingProvider(
        [
            ToolCall(
                "gh1",
                "github_read",
                {
                    "operation": "file",
                    "repository": "ada/project",
                    "path": "main.py",
                },
            )
        ]
    )
    with make_client(settings, knowledge, provider=provider) as client:
        headers, _ = signup(client)
        connect(client, {"headers": headers})
        cid = client.post("/api/v1/conversations", json={}, headers=headers).json()["id"]
        response = client.post(
            f"/api/v1/conversations/{cid}/messages",
            headers=headers,
            json={"content": "Read main.py in ada/project and explain it."},
        )
        assert "Reading GitHub" in response.text
        assert "print('hello')" in response.text
        assert TOKEN not in response.text
        assert TOKEN not in str(provider.requests)


async def test_http_response_bound_and_timeout_redaction(monkeypatch):
    monkeypatch.setattr(
        github,
        "http_client",
        lambda: httpx.AsyncClient(
            transport=httpx.MockTransport(lambda r: httpx.Response(200, content=b"x" * (github.MAX_RESPONSE + 1)))
        ),
    )
    with pytest.raises(github.GitHubError, match="too large"):
        await github.GitHubReader(TOKEN).get("/user")

    def fail(request):
        raise httpx.ReadTimeout(TOKEN)

    monkeypatch.setattr(github, "http_client", lambda: httpx.AsyncClient(transport=httpx.MockTransport(fail)))
    with pytest.raises(github.GitHubError) as error:
        await github.GitHubReader(TOKEN).get("/user")
    assert TOKEN not in str(error.value)


def test_read_rate_limit(client, auth):
    connect(client, auth)
    for _ in range(60):
        assert read(client, auth, "repositories").status_code == 200
    assert read(client, auth, "repositories").status_code == 429
