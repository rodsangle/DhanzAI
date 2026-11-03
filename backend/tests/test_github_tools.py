import base64
import json
import uuid

import httpx
import pytest

from app.services import github_reader as github
from app.services.assistant_tools import ToolBox, ToolContext
from dhanz_ai import ToolCall


@pytest.fixture
def github_settings(settings):
    settings.github_allowed_repositories = "rodsangle/DhanzAI"
    settings.github_token = "test-only-not-a-real-token"
    settings.github_write_enabled = True
    return settings


def mock_github(monkeypatch, handler):
    original = httpx.AsyncClient
    monkeypatch.setattr(
        github.httpx, "AsyncClient", lambda **kw: original(transport=httpx.MockTransport(handler), **kw)
    )


@pytest.mark.parametrize(
    "name", ["https://github.com/rodsangle/DhanzAI", "other/private", "rodsangle/DhanzAI/../x", "foo"]
)
async def test_deny_unlisted_repositories(github_settings, name):
    with pytest.raises(github.GitHubReadError):
        await github.read_repository(github_settings, {"repository": name})


async def test_private_file_and_ref(github_settings, monkeypatch):
    def handler(request):
        assert request.url.host == "api.github.com"
        assert request.headers["authorization"] == "Bearer test-only-not-a-real-token"
        assert request.url.params["ref"] == "feature/read"
        assert request.method == "GET"
        return httpx.Response(
            200,
            json={
                "type": "file",
                "encoding": "base64",
                "size": 5,
                "content": base64.b64encode(b"hello").decode(),
                "sha": "a" * 40,
            },
        )

    mock_github(monkeypatch, handler)
    data = await github.read_repository(
        github_settings, {"repository": "rodsangle/DhanzAI", "path": "README.md", "ref": "feature/read"}, file=True
    )
    assert data["content"] == "hello"
    assert data["blob_sha"] == "a" * 40
    assert data["untrusted_repository_content"] is True


async def test_public_read_has_no_authorization(github_settings, monkeypatch):
    github_settings.github_token = None

    def handler(request):
        assert "authorization" not in request.headers
        return httpx.Response(200, json=[{"path": "README.md", "type": "file", "size": 10}])

    mock_github(monkeypatch, handler)
    data = await github.read_repository(github_settings, {"repository": "rodsangle/DhanzAI"})
    assert data["entries"][0]["path"] == "README.md"


@pytest.mark.parametrize("status", [301, 302, 401, 403, 404, 429, 500])
async def test_http_errors_are_sanitized(github_settings, monkeypatch, status):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(status, headers={"Location": "https://evil.example/"}, text="secret-error-details")

    mock_github(monkeypatch, handler)
    with pytest.raises(github.GitHubReadError) as exc:
        await github.read_repository(github_settings, {"repository": "rodsangle/DhanzAI"})
    assert len(calls) == 1
    assert "secret-error-details" not in str(exc.value)
    assert "test-only" not in str(exc.value)


@pytest.mark.parametrize("path", ["../.env", "/etc/passwd", "a//b", "a/./b", "a\\b"])
async def test_path_rejection(github_settings, path):
    with pytest.raises(github.GitHubReadError):
        await github.read_repository(github_settings, {"repository": "rodsangle/DhanzAI", "path": path})


@pytest.mark.parametrize(
    "data",
    [
        {"type": "file", "encoding": "base64", "size": 65537},
        {"type": "symlink", "encoding": "base64", "size": 1},
        {"type": "file", "encoding": "base64", "size": 1, "content": "%%%"},
        {"type": "file", "encoding": "base64", "size": 1, "content": "AA=="},
    ],
)
async def test_reject_nontext_files(github_settings, monkeypatch, data):
    mock_github(monkeypatch, lambda r: httpx.Response(200, json=data))
    with pytest.raises(github.GitHubReadError):
        await github.read_repository(github_settings, {"repository": "rodsangle/DhanzAI", "path": "file"}, file=True)


async def test_create_branch_edit_and_draft_pr(github_settings, monkeypatch):
    seen = []

    def handler(r):
        seen.append((r.method, str(r.url), json.loads(r.content) if r.content else None))
        if r.url.path.endswith("/DhanzAI"):
            return httpx.Response(200, json={"default_branch": "main"})
        if "/git/ref/" in r.url.path:
            return httpx.Response(200, json={"object": {"sha": "b" * 40}})
        if r.method == "POST" and r.url.path.endswith("/git/refs"):
            assert json.loads(r.content)["ref"] == "refs/heads/dhanz/test"
            return httpx.Response(201, json={"object": {"sha": "b" * 40}})
        if r.method == "GET":
            return httpx.Response(200, json={"type": "file", "sha": "a" * 40})
        if r.method == "PUT":
            body = json.loads(r.content)
            assert body["branch"] == "dhanz/test" and body["sha"] == "a" * 40
            assert base64.b64decode(body["content"]) == b"updated"
            return httpx.Response(200, json={"content": {"sha": "c" * 40}, "commit": {"sha": "d" * 40}})
        body = json.loads(r.content)
        assert body["draft"] is True and body["base"] == "main"
        return httpx.Response(201, json={"number": 4, "html_url": "https://github.com/rodsangle/DhanzAI/pull/4"})

    mock_github(monkeypatch, handler)
    args = {"repository": "rodsangle/DhanzAI", "branch": "dhanz/test"}
    await github.change_repository(github_settings, args, "branch")
    await github.change_repository(
        github_settings,
        {**args, "path": "README.md", "expected_sha": "a" * 40, "content": "updated", "message": "Update docs"},
        "file",
    )
    result = await github.change_repository(
        github_settings, {**args, "title": "Update docs", "body": "Validation: reviewed"}, "pull_request"
    )
    assert result["draft"] is True and result["number"] == 4
    assert all("api.github.com/repos/rodsangle/DhanzAI" in url for _, url, _ in seen)


async def test_stale_file_cannot_be_overwritten(github_settings, monkeypatch):
    def handler(r):
        assert r.method == "GET"
        if r.url.path.endswith("/DhanzAI"):
            return httpx.Response(200, json={"default_branch": "main"})
        if "/git/ref/" in r.url.path:
            return httpx.Response(200, json={"object": {"sha": "b" * 40}})
        return httpx.Response(200, json={"type": "file", "sha": "c" * 40})

    mock_github(monkeypatch, handler)
    with pytest.raises(github.GitHubReadError, match="changed"):
        await github.change_repository(
            github_settings,
            {
                "repository": "rodsangle/DhanzAI",
                "branch": "dhanz/test",
                "path": "x",
                "content": "x",
                "message": "edit",
                "expected_sha": "a" * 40,
            },
            "file",
        )


@pytest.mark.parametrize("branch", ["main", "dhanz/../main", "refs/heads/main", "dhanz/x.lock", "dhanz//x"])
async def test_protected_branch_names(github_settings, branch):
    with pytest.raises(github.GitHubReadError):
        await github.change_repository(github_settings, {"repository": "rodsangle/DhanzAI", "branch": branch}, "branch")


async def test_write_flag_required(github_settings):
    github_settings.github_write_enabled = False
    with pytest.raises(github.GitHubReadError, match="writes require"):
        await github.change_repository(github_settings, {}, "branch")


async def test_nonadmin_cannot_use_server_token(client, auth, github_settings, monkeypatch):
    from app.models import User

    uid = uuid.UUID(auth["user"]["id"])
    maker = client.app.state.sessionmaker
    async with maker() as db:
        user = await db.get(User, uid)
        user.role = "user"
        await db.commit()

    async def forbidden(*a, **kw):
        pytest.fail("Non-admin must never reach GitHub")

    monkeypatch.setattr(github, "request_json", forbidden)
    box = ToolBox(ToolContext(maker, uid, None, settings=github_settings))
    result = await box.run(ToolCall("1", "github_read_file", {"repository": "rodsangle/DhanzAI", "path": "README.md"}))
    assert result.is_error
    assert "administrator" in result.content.lower()


def test_github_tools_hidden_until_configured():
    box = ToolBox(ToolContext(None, uuid.uuid4(), None))
    assert not any(s.name.startswith("github_") for s in box.specs)


def test_chat_can_read_repository_and_save_activity(github_settings, knowledge, monkeypatch):
    from tests.conftest import parse_sse
    from tests.test_tools import ToolCallingProvider, make_client, signup

    mock_github(
        monkeypatch,
        lambda r: httpx.Response(
            200,
            json=[
                {"path": "README.md", "type": "file", "size": 5},
            ],
        ),
    )
    provider = ToolCallingProvider(
        [
            ToolCall("github-1", "github_list_directory", {"repository": "rodsangle/DhanzAI"}),
        ]
    )
    with make_client(github_settings, knowledge, provider=provider) as client:
        headers, _ = signup(client)
        cid = client.post("/api/v1/conversations", headers=headers, json={}).json()["id"]
        response = client.post(
            f"/api/v1/conversations/{cid}/messages",
            headers=headers,
            json={"content": "List root files in rodsangle/DhanzAI", "web": False},
        )
        events = parse_sse(response.text)
        assert events[-1]["type"] == "done"
        message = events[-1]["message"]
        assert "README.md" in message["content"]
        assert message["tool_activity"][0]["tool"] == "github_list_directory"
        assert message["tool_activity"][0]["error"] is False


async def test_default_branch_protected_even_with_dhanz_prefix(github_settings, monkeypatch):
    mock_github(monkeypatch, lambda r: httpx.Response(200, json={"default_branch": "dhanz/main"}))
    with pytest.raises(github.GitHubReadError, match="default branch"):
        await github.change_repository(
            github_settings,
            {
                "repository": "rodsangle/DhanzAI",
                "branch": "dhanz/main",
            },
            "branch",
        )


async def test_create_new_file_requires_absence(github_settings, monkeypatch):
    def handler(r):
        if r.url.path.endswith("/DhanzAI"):
            return httpx.Response(200, json={"default_branch": "main"})
        if "/git/ref/" in r.url.path:
            return httpx.Response(200, json={"object": {"sha": "b" * 40}})
        if r.method == "GET":
            return httpx.Response(404)
        body = json.loads(r.content)
        assert "sha" not in body
        assert body["branch"] == "dhanz/new-file"
        return httpx.Response(201, json={"content": {"sha": "c" * 40}, "commit": {"sha": "d" * 40}})

    mock_github(monkeypatch, handler)
    result = await github.change_repository(
        github_settings,
        {
            "repository": "rodsangle/DhanzAI",
            "branch": "dhanz/new-file",
            "path": "new.txt",
            "expected_sha": "",
            "content": "hello",
            "message": "Add new file",
        },
        "file",
    )
    assert result["blob_sha"] == "c" * 40
