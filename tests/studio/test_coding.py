import base64
import uuid

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.deps import get_current_user
from app.assistant_studio import builder
from app.assistant_studio import coding_service as service
from app.assistant_studio.coding_models import CodingDraft
from app.assistant_studio.coding_routes import router
from app.assistant_studio.models import BuilderProject
from app.core.config import Settings
from app.db.base import Base
from app.models import User
from app.services import github_service as gh


class Reader:
    tip = "a" * 40
    runs = []

    async def get(self, path, params=None):
        if "/commits/" in path:
            return {"sha": self.tip, "commit": {"tree": {"sha": "b" * 40}}}
        if "/git/trees/" in path:
            return {
                "tree": [{"path": "agent.py", "type": "blob", "mode": "100755", "sha": "c" * 40}],
                "truncated": False,
            }
        if "/contents/" in path:
            return {
                "type": "file",
                "encoding": "base64",
                "content": base64.b64encode(b'print("before")\n').decode(),
                "sha": "c" * 40,
            }
        if path.endswith("/actions/runs"):
            return {"workflow_runs": self.runs}
        if path.endswith("/jobs"):
            return {
                "jobs": [
                    {
                        "name": "validate",
                        "conclusion": "failure",
                        "steps": [{"name": "Run unittest suite", "conclusion": "failure"}],
                    }
                ]
            }
        raise AssertionError(path)


@pytest_asyncio.fixture
async def coding(tmp_path, monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///" + str(tmp_path / "coding.db"))
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    users = [
        User(id=uuid.uuid4(), email=name + "@example.test", display_name=name, routing_policy="balanced")
        for name in ("one", "two")
    ]
    async with maker() as db:
        db.add_all(users)
        await db.commit()
    app = FastAPI()
    app.state.sessionmaker = maker
    app.state.settings = Settings(app_env="test", _env_file=None)

    async def user(request: Request):
        value = request.headers.get("x-test-user")
        if not value:
            raise HTTPException(401, "Unauthorized")
        return users[0] if value == "one" else users[1]

    app.dependency_overrides[get_current_user] = user
    app.include_router(router, prefix="/api/v1")
    reader = Reader()
    writes = []

    async def context(db, settings, user_id, repository):
        if repository != "owner/demo" or user_id != users[0].id:
            raise gh.GitHubError("Repository is not selected.", 403)
        return "server-only-token", {"id": 123, "default_branch": "main"}, reader

    async def models(settings):
        return ["test-codex"]

    async def write(token, path, payload):
        writes.append((path, payload))
        if path.endswith("/pulls"):
            return {"number": 17}
        return {"sha": "d" * 40}

    monkeypatch.setattr(service, "context", context)
    monkeypatch.setattr(builder, "models", models)
    monkeypatch.setattr(service, "write", write)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        yield client, maker, users, reader, writes
    await engine.dispose()


def body(**extra):
    return {
        "title": "Repair app",
        "instructions": "Update the code and add tests",
        "model": "test-codex",
        "request_key": uuid.uuid4().hex,
        "repository": "owner/demo",
        "paths": ["agent.py"],
        "runtime": "python",
        **extra,
    }


async def completed(client, maker, **extra):
    response = await client.post("/api/v1/coding/drafts", headers={"x-test-user": "one"}, json=body(**extra))
    assert response.status_code == 201, response.text
    data = response.json()
    async with maker() as db:
        project = await db.get(BuilderProject, uuid.UUID(data["project_id"]))
        assert "server-only-token" not in project.prompt
        project.status = "complete"
        project.files = [{"path": "agent.py", "content": 'print("after")\n'}]
        await db.commit()
    return data


@pytest.mark.asyncio
async def test_owned_drafts_and_idempotent_generation(coding):
    client, maker, users, reader, writes = coding
    assert (await client.get("/api/v1/coding/drafts")).status_code == 401
    request = body()
    first = await client.post("/api/v1/coding/drafts", headers={"x-test-user": "one"}, json=request)
    second = await client.post("/api/v1/coding/drafts", headers={"x-test-user": "one"}, json=request)
    assert first.status_code == 201 and first.json()["id"] == second.json()["id"]
    path = "/api/v1/coding/drafts/" + first.json()["id"]
    for suffix in ("", "/review", "/publish", "/repair", "/checks"):
        response = await (
            client.get(path, headers={"x-test-user": "two"})
            if not suffix
            else client.post(
                path + suffix,
                headers={"x-test-user": "two"},
                json={"review_hash": "0" * 64} if suffix == "/publish" else {},
            )
        )
        assert response.status_code == 404
    assert not writes


@pytest.mark.asyncio
async def test_review_shows_diff_and_publish_uses_exact_reviewed_files_once(coding):
    client, maker, users, reader, writes = coding
    data = await completed(client, maker)
    path = "/api/v1/coding/drafts/" + data["id"]
    response = await client.post(path + "/review", headers={"x-test-user": "one"}, json={})
    review = response.json()
    assert review["status"] == "review" and len(review["files"]) == 2
    assert 'print("before")' in review["diffs"][0]["diff"] and 'print("after")' in review["diffs"][0]["diff"]
    workflow = review["files"][1]
    assert workflow["path"].startswith(".github/workflows/dhanz-workspace-")
    assert "persist-credentials: false" in workflow["content"]
    assert not writes
    response = await client.post(path + "/publish", headers={"x-test-user": "one"}, json={"review_hash": "0" * 64})
    assert response.status_code == 409 and not writes
    response = await client.post(
        path + "/publish", headers={"x-test-user": "one"}, json={"review_hash": review["review_hash"]}
    )
    assert response.status_code == 200, response.text
    assert response.json()["pull_url"] == "https://github.com/owner/demo/pull/17"
    assert len(writes) == 4 and writes[2][1]["ref"].startswith("refs/heads/dhanz/")
    assert writes[3][1]["draft"] is True
    assert writes[0][1]["base_tree"] == "b" * 40
    response = await client.post(
        path + "/publish", headers={"x-test-user": "one"}, json={"review_hash": review["review_hash"]}
    )
    assert response.status_code == 409 and len(writes) == 4


@pytest.mark.asyncio
async def test_stale_repository_tip_blocks_writes_and_edits_are_in_zip_project(coding):
    client, maker, users, reader, writes = coding
    data = await completed(client, maker)
    path = "/api/v1/coding/drafts/" + data["id"]
    edited = [{"path": "agent.py", "content": 'print("manual edit")\n'}]
    review = (await client.post(path + "/review", headers={"x-test-user": "one"}, json={"files": edited})).json()
    async with maker() as db:
        assert (await db.get(BuilderProject, uuid.UUID(data["project_id"]))).files == edited
    reader.tip = "e" * 40
    response = await client.post(
        path + "/publish", headers={"x-test-user": "one"}, json={"review_hash": review["review_hash"]}
    )
    assert response.status_code == 409 and "base branch changed" in response.text.lower() and not writes


@pytest.mark.asyncio
async def test_partial_github_failure_is_uncertain_and_never_replayed(coding, monkeypatch):
    client, maker, users, reader, writes = coding
    data = await completed(client, maker)
    path = "/api/v1/coding/drafts/" + data["id"]
    review = (await client.post(path + "/review", headers={"x-test-user": "one"}, json={})).json()

    async def write(token, path, payload):
        writes.append((path, payload))
        if path.endswith("/pulls"):
            raise gh.GitHubError("Check branch; write outcome uncertain.", 502)
        return {"sha": "d" * 40}

    monkeypatch.setattr(service, "write", write)
    response = await client.post(
        path + "/publish", headers={"x-test-user": "one"}, json={"review_hash": review["review_hash"]}
    )
    assert response.status_code == 502
    state = (await client.get(path, headers={"x-test-user": "one"})).json()
    assert state["status"] == "uncertain" and state["branch"]
    response = await client.post(
        path + "/publish", headers={"x-test-user": "one"}, json={"review_hash": review["review_hash"]}
    )
    assert response.status_code == 409 and len(writes) == 4


@pytest.mark.asyncio
async def test_repair_is_bounded_and_preserves_the_failed_project(coding):
    client, maker, users, reader, writes = coding
    data = await completed(client, maker, repository="", paths=[])
    path = "/api/v1/coding/drafts/" + data["id"]
    old_id = uuid.UUID(data["project_id"])
    async with maker() as db:
        project = await db.get(BuilderProject, old_id)
        project.status = "failed"
        project.error = "Invalid project JSON"
        await db.commit()
    first = await client.post(path + "/repair", headers={"x-test-user": "one"}, json={})
    second = await client.post(path + "/repair", headers={"x-test-user": "one"}, json={})
    assert first.status_code == 200 and first.json()["project_id"] != str(old_id)
    assert second.status_code == 409
    async with maker() as db:
        assert (await db.get(BuilderProject, old_id)).status == "failed"
        assert (await db.get(CodingDraft, uuid.UUID(data["id"]))).repair_count == 1


@pytest.mark.asyncio
async def test_checks_ignore_other_commit_and_wrong_workflow(coding):
    client, maker, users, reader, writes = coding
    data = await completed(client, maker)
    path = "/api/v1/coding/drafts/" + data["id"]
    review = (await client.post(path + "/review", headers={"x-test-user": "one"}, json={})).json()
    await client.post(path + "/publish", headers={"x-test-user": "one"}, json={"review_hash": review["review_hash"]})
    reader.runs = [
        {
            "id": 1,
            "head_sha": "d" * 40,
            "path": "other.yml",
            "name": "Dhanz workspace checks",
            "status": "completed",
            "conclusion": "success",
        }
    ]
    response = await client.post(path + "/checks", headers={"x-test-user": "one"}, json={})
    assert response.json()["checks"]["status"] == "not_found"
    reader.runs = [
        {
            "id": 2,
            "head_sha": "d" * 40,
            "path": review["files"][1]["path"],
            "name": "Dhanz workspace checks",
            "status": "completed",
            "conclusion": "failure",
        }
    ]
    response = await client.post(path + "/checks", headers={"x-test-user": "one"}, json={})
    assert response.json()["checks"]["conclusion"] == "failure"
    assert "Run unittest suite" in str(response.json()["checks"]["jobs"])


def test_workflows_do_not_inject_model_commands_or_provider_keys():
    for runtime in ("python", "web"):
        text = service.workflow(runtime)
        assert "contents: read" in text and "persist-credentials: false" in text
        assert "OPENAI_API_KEY" not in text and "secrets." not in text
        assert "No unittest tests were discovered" in text or "No package.json test script" in text


@pytest.mark.asyncio
async def test_automatic_repair_requires_opt_in_and_skips_quota_failures(coding):
    client, maker, users, reader, writes = coding
    data = await completed(client, maker, repository="", paths=[], auto_repair=True)
    async with maker() as db:
        row = await db.get(CodingDraft, uuid.UUID(data["id"]))
        project = await db.get(BuilderProject, row.project_id)
        project.status = "failed"
        project.error = "OpenAI HTTP 429 (insufficient_quota)"
        await db.commit()
        assert await service.repair_once(db, users[0], row, automatic=True) is False
        assert row.repair_count == 0
        project.error = "The model returned invalid project JSON"
        await db.commit()
        assert await service.repair_once(db, users[0], row, automatic=True) is True
        assert row.repair_count == 1
        assert row.project_id != project.id


def test_coding_installer_preserves_old_bootstrap_and_embedded_files_match():
    import importlib.util
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location(
        "coding_installer", root / "deploy/updaters/install_coding_workspace.py"
    )
    installer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(installer)
    original = (root / "server_extensions/assistant_studio/bootstrap.py").read_text()
    patched = installer.patch_bootstrap(original)
    assert "_install_coding_workspace(app)" in patched
    assert "builder.worker" in patched and "old_report" in patched
    assert installer.patch_bootstrap(patched) == patched
    for path, content in installer.payload().items():
        source = (
            root
            / "server_extensions"
            / ("assistant_studio/" + Path(path).name if path.startswith("app/") else "migrations/" + Path(path).name)
        )
        assert source.read_text() == content


@pytest.mark.asyncio
async def test_unselected_existing_files_get_real_before_after_diff(coding, monkeypatch):
    client, maker, users, reader, writes = coding
    data = await completed(client, maker)
    async with maker() as db:
        project = await db.get(BuilderProject, uuid.UUID(data["project_id"]))
        project.files = [*project.files, {"path": "README.md", "content": "new readme\n"}]
        await db.commit()
    original_get = reader.get

    async def get(path, params=None):
        if "/git/trees/" in path:
            result = await original_get(path, params)
            return {
                **result,
                "tree": [*result["tree"], {"path": "README.md", "type": "blob", "mode": "100644", "sha": "e" * 40}],
            }
        if "/git/blobs/" in path:
            return {"encoding": "base64", "size": 11, "content": base64.b64encode(b"old readme\n").decode()}
        return await original_get(path, params)

    monkeypatch.setattr(reader, "get", get)
    path = "/api/v1/coding/drafts/" + data["id"]
    review = (await client.post(path + "/review", headers={"x-test-user": "one"}, json={})).json()
    diff = next(d["diff"] for d in review["diffs"] if d["path"] == "README.md")
    assert "-old readme" in diff and "+new readme" in diff
    response = await client.post(
        path + "/publish", headers={"x-test-user": "one"}, json={"review_hash": review["review_hash"]}
    )
    assert response.status_code == 200
    assert next(f["mode"] for f in writes[0][1]["tree"] if f["path"] == "agent.py") == "100755"


@pytest.mark.asyncio
async def test_obvious_credentials_are_rejected_before_model_queuing(coding):
    client, maker, users, reader, writes = coding
    response = await client.post(
        "/api/v1/coding/drafts",
        headers={"x-test-user": "one"},
        json=body(repository="", paths=[], instructions="Use ghp_" + "x" * 35 + " to connect"),
    )
    assert response.status_code == 400 and "credentials" in response.text
    assert "ghp_" not in response.text
    async with maker() as db:
        assert await db.scalar(select(BuilderProject.id)) is None


def test_flutter_profile_and_monorepo_workdir_are_fixed_and_validated():
    workflow = service.workflow("flutter", "apps/dhanz_flutter")
    assert 'working-directory: "apps/dhanz_flutter"' in workflow
    assert "flutter test" in workflow and "flutter build web --release" in workflow
    assert "3.47.8" in workflow and "persist-credentials: false" in workflow
    for directory in ("../escape", "/tmp", ".github", "app/../../escape", "app; echo bad", "${{ secrets.KEY }}"):
        with pytest.raises(gh.GitHubError):
            service.workflow("python", directory)
    assert builder.validate_files([{"path": "lib/main.dart", "content": "void main() {}"}])


@pytest.mark.asyncio
async def test_standing_publication_is_scoped_and_remote_write_is_not_replayed(coding):
    from datetime import timedelta

    from app.assistant_studio.operations_models import OperationGrant
    from app.assistant_studio.operations_service import publish_granted
    from app.db.base import utcnow

    client, maker, users, reader, writes = coding
    data = await completed(client, maker)
    async with maker() as db:
        row = await db.get(CodingDraft, uuid.UUID(data["id"]))
        grant = OperationGrant(
            user_id=users[0].id,
            kind="github_publish",
            target="owner/demo",
            scope={"branch": "main", "repository_id": 999},
            remaining=1,
            expires_at=utcnow() + timedelta(hours=1),
            revoked=False,
        )
        db.add(grant)
        await db.commit()
        await publish_granted(db, Settings(app_env="test", _env_file=None), row, grant)
        assert not writes  # same repository name with a different identity is insufficient
        grant.scope = {"branch": "main", "repository_id": 123}
        grant.revoked = True
        await db.commit()
        await publish_granted(db, Settings(app_env="test", _env_file=None), row, grant)
        assert not writes
        grant.revoked = False
        await db.commit()
        await publish_granted(db, Settings(app_env="test", _env_file=None), row, grant)
        assert len(writes) == 4 and row.status == "published" and grant.remaining == 0
        await publish_granted(db, Settings(app_env="test", _env_file=None), row, grant)
        assert len(writes) == 4
