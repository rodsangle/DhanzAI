import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.api.deps import get_current_user
from app.core.config import Settings
from app.db.base import Base
from app.models import User, Conversation, Message
from app.assistant_studio.models import ResponseFeedback, BuilderProject, BuilderLease
from app.assistant_studio.routes import router
from app.assistant_studio import builder


@pytest_asyncio.fixture
async def service(tmp_path, monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///" + str(tmp_path / "test.db"))
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    one = User(id=uuid.uuid4(), email="one@example.test", display_name="One", routing_policy="balanced")
    two = User(id=uuid.uuid4(), email="two@example.test", display_name="Two", routing_policy="balanced")
    conv = Conversation(id=uuid.uuid4(), user_id=one.id, title="Private chat")
    msg = Message(
        id=uuid.uuid4(), conversation_id=conv.id, position=0, role="assistant", status="complete", content="A reply"
    )
    async with maker() as db:
        db.add_all([one, two])
        await db.flush()
        db.add(conv)
        await db.flush()
        db.add(msg)
        db.add(BuilderLease(id=1))
        await db.commit()
    app = FastAPI()
    app.state.sessionmaker = maker
    app.state.settings = Settings(app_env="test", _env_file=None)

    async def current(request: Request):
        identifier = request.headers.get("x-test-user")
        if not identifier:
            raise HTTPException(401, "Not authenticated")
        return one if identifier == "one" else two

    app.dependency_overrides[get_current_user] = current
    app.include_router(router, prefix="/api/v1")

    async def models(settings):
        return ["test-codex"]

    monkeypatch.setattr(builder, "models", models)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        yield client, maker, one, two, msg
    await engine.dispose()


@pytest.mark.asyncio
async def test_feedback_is_persisted_clearable_and_owner_scoped(service):
    client, maker, one, two, msg = service
    url = "/api/v1/assistant-studio/feedback/" + str(msg.id)
    assert (await client.get(url)).status_code == 401
    assert (await client.put(url, headers={"x-test-user": "two"}, json={"rating": "up"})).status_code == 404
    assert (await client.put(url, headers={"x-test-user": "one"}, json={"rating": "up"})).status_code == 200
    async with maker() as db:
        assert (await db.get(ResponseFeedback, (msg.id, one.id))).rating == "up"
    assert (await client.get(url, headers={"x-test-user": "one"})).json()["rating"] == "up"
    await client.put(url, headers={"x-test-user": "one"}, json={"rating": None})
    async with maker() as db:
        assert await db.get(ResponseFeedback, (msg.id, one.id)) is None


@pytest.mark.asyncio
async def test_project_request_is_idempotent_and_other_users_cannot_read_or_download(service):
    client, maker, one, two, msg = service
    body = {
        "name": "Example",
        "kind": "agent",
        "prompt": "Make an agent",
        "model": "test-codex",
        "request_key": "test_request_123456",
    }
    url = "/api/v1/assistant-studio/projects"
    first = await client.post(url, headers={"x-test-user": "one"}, json=body)
    assert first.status_code == 201
    second = await client.post(url, headers={"x-test-user": "one"}, json=body)
    assert first.json()["id"] == second.json()["id"]
    identifier = first.json()["id"]
    assert (await client.get(url + "/" + identifier, headers={"x-test-user": "two"})).status_code == 404
    assert (await client.get(url + "/" + identifier + "/download", headers={"x-test-user": "one"})).status_code == 409
    async with maker() as db:
        project = await db.get(BuilderProject, uuid.UUID(identifier))
        project.status = "complete"
        project.files = [{"path": "agent.py", "content": "print(1)"}]
        await db.commit()
    response = await client.get(url + "/" + identifier + "/download", headers={"x-test-user": "one"})
    assert response.status_code == 200 and response.content.startswith(b"PK")
    assert (await client.get(url + "/" + identifier + "/download", headers={"x-test-user": "two"})).status_code == 404


@pytest.mark.asyncio
async def test_only_one_worker_claims_a_job(service):
    _, maker, one, _, _ = service
    async with maker() as db:
        db.add_all(
            [
                BuilderProject(
                    user_id=one.id,
                    request_key=str(uuid.uuid4()),
                    name="Job",
                    kind="agent",
                    prompt="Make an agent",
                    model="test-codex",
                )
                for _ in range(2)
            ]
        )
        await db.commit()
    first = await builder.claim(maker)
    second = await builder.claim(maker)
    assert first is not None and second is None
