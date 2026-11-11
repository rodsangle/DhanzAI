import json
import uuid
from types import SimpleNamespace

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.assistant_studio import app_builder_tools as feature
from app.assistant_studio import builder
from app.assistant_studio.models import BuilderProject
from app.core.config import Settings
from app.db.base import Base
from app.models import User
from app.services import assistant_tools


@pytest_asyncio.fixture
async def workspace(tmp_path, monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///" + str(tmp_path / "builder.db"))
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    users = [
        User(id=uuid.uuid4(), email=f"{i}@example.test", display_name=str(i), routing_policy="balanced")
        for i in range(2)
    ]
    async with maker() as db:
        db.add_all(users)
        await db.commit()

    async def models(settings):
        return ["gpt-4.1-mini"]

    async def enforce(*args):
        pass

    from app.core import rate_limit

    monkeypatch.setattr(builder, "models", models)
    monkeypatch.setattr(rate_limit, "enforce", enforce)
    monkeypatch.setattr(assistant_tools, "TOOLS", {})
    feature.install()
    ctx = SimpleNamespace(
        maker=maker,
        settings=Settings(app_env="test", _env_file=None),
        user_id=users[0].id,
        conversation_id=uuid.uuid4(),
        assistant_message_id=uuid.uuid4(),
    )
    yield ctx, users, assistant_tools.TOOLS["build_app"].run
    await engine.dispose()


@pytest.mark.asyncio
async def test_chat_default_uses_recommended_coding_model_and_allows_explicit_override(workspace, monkeypatch):
    ctx, users, run = workspace

    async def models(settings):
        return ['gpt-5.1-codex', 'gpt-4.1-mini']

    monkeypatch.setattr(builder, 'models', models)
    first = await run(ctx, {'operation': 'start', 'runtime': 'python', 'instructions': 'Create a CSV totals agent'})
    async with ctx.maker() as db:
        row = await db.get(BuilderProject, uuid.UUID(first.data['project']['id']))
        assert row.model == 'gpt-5.1-codex' and row.kind == 'agent'
    other_turn = SimpleNamespace(**{**ctx.__dict__, 'assistant_message_id': uuid.uuid4()})
    second = await run(other_turn, {'operation': 'start', 'runtime': 'python',
        'instructions': 'Create another CSV agent', 'model': 'gpt-4.1-mini'})
    async with ctx.maker() as db:
        row = await db.get(BuilderProject, uuid.UUID(second.data['project']['id']))
        assert row.model == 'gpt-4.1-mini'


@pytest.mark.asyncio
async def test_chat_starts_one_mobile_build_and_persists_requirements(workspace):
    ctx, users, run = workspace
    args = {
        "operation": "start",
        "title": "Vehicle app",
        "runtime": "flutter",
        "instructions": "Create lock/unlock, engine start and vehicle GPS.",
    }
    first = await run(ctx, args)
    again = await run(ctx, args)
    assert first.data["project"]["id"] == again.data["project"]["id"]
    assert first.data["project"]["status"] == "queued"
    assert first.data["source_ready"] is False
    async with ctx.maker() as db:
        assert await db.scalar(select(func.count()).select_from(BuilderProject)) == 1
        row = await db.get(BuilderProject, uuid.UUID(first.data["project"]["id"]))
        assert row.prompt.startswith("[DHANZ_RUNTIME:flutter]\n")
        assert "lock/unlock" in row.prompt and "demo implementation" in row.prompt
    other = SimpleNamespace(**{**ctx.__dict__, "user_id": users[1].id})
    with pytest.raises(assistant_tools.ToolInputError, match="Project not found"):
        await run(other, {"operation": "status", "project_id": first.data["project"]["id"]})


@pytest.mark.asyncio
async def test_local_only_account_cannot_queue_external_generation(workspace):
    ctx, users, run = workspace
    async with ctx.maker() as db:
        user = await db.get(User, users[0].id)
        user.routing_policy = "local_only"
        await db.commit()
    with pytest.raises(assistant_tools.ToolInputError, match="local-only"):
        await run(ctx, {"operation": "start", "instructions": "Create an app"})


@pytest.mark.asyncio
async def test_flutter_source_requires_mobile_files_instead_of_html():
    files = [
        {"path": path, "content": content}
        for path, content in [
            ("pubspec.yaml", "name: demo\ndependencies:\n  flutter:\n    sdk: flutter\n"),
            ("lib/main.dart", "void main() {}"),
            ("simulator/index.html", "<button>Demo lock</button>"),
            ("README.md", "Run flutter create demo, then copy files."),
        ]
    ]

    def response(request):
        body = json.loads(request.content)
        assert "Flutter mobile project" in body["instructions"]
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "output": [
                    {
                        "type": "function_call",
                        "name": "publish_project",
                        "arguments": json.dumps({"summary": "Flutter source only", "files": files}),
                    }
                ],
            },
        )

    job = SimpleNamespace(
        kind="app", name="Mobile", model="gpt-4.1-mini", prompt=feature.build_instructions("Vehicle demo", "flutter")
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(response)) as client:
        result, _ = await builder.generate(SimpleNamespace(openai_api_key="fake"), job, client=client)
        assert len(result) == 4
        files.pop()
        with pytest.raises(builder.BuildError, match="Flutter project is missing"):
            await builder.generate(SimpleNamespace(openai_api_key="fake"), job, client=client)


def test_application_install_registers_chat_builder(monkeypatch):
    from fastapi import FastAPI

    from app.assistant_studio import bootstrap
    from app.services import capabilities_service

    monkeypatch.setattr(assistant_tools, "TOOLS", {})
    monkeypatch.setattr(capabilities_service, "report", capabilities_service.report)
    app = FastAPI()
    app.state.settings = Settings(app_env="test", _env_file=None)
    import runpy
    from pathlib import Path

    installer = runpy.run_path(str(Path(__file__).resolve().parents[2] / "deploy/updaters/install_app_builder_chat.py"))
    namespace = {"__name__": "app.assistant_studio._patched_bootstrap", "__package__": "app.assistant_studio"}
    source = Path(bootstrap.__file__).read_text()
    exec(compile(installer["patch_bootstrap"](source), "bootstrap.py", "exec"), namespace)  # noqa: S102 - trusted tested source
    namespace["install"](app)
    assert "build_app" in assistant_tools.TOOLS


@pytest.mark.asyncio
async def test_revision_uses_owned_source_and_preserves_original(workspace):
    from app.assistant_studio.builder_simulation import revision_context

    ctx, users, run = workspace
    first = await run(ctx, {"operation": "start", "runtime": "flutter", "instructions": "Create a vehicle demo"})
    identifier = uuid.UUID(first.data["project"]["id"])
    original_files = [{"path": "simulator/index.html", "content": "<button>Original lock</button>"}]
    async with ctx.maker() as db:
        parent = await db.get(BuilderProject, identifier)
        parent.status = "complete"
        parent.files = original_files
        await db.commit()
        database_url = str(db.bind.url)
    revised = await run(
        ctx,
        {
            "operation": "revise",
            "project_id": str(identifier),
            "instructions": "Make the lock button larger; keep GPS.",
        },
    )
    assert revised.data["project"]["id"] != str(identifier)
    assert revised.action["type"] == "app_project"
    async with ctx.maker() as db:
        parent = await db.get(BuilderProject, identifier)
        assert parent.files == original_files and parent.status == "complete"
        job = await db.get(BuilderProject, uuid.UUID(revised.data["project"]["id"]))
        source = await revision_context(SimpleNamespace(database_url=database_url), job)
        assert "Original lock" in source and "Create a vehicle demo" in source
        outsider = SimpleNamespace(prompt=job.prompt, user_id=users[1].id)
        with pytest.raises(builder.BuildError, match="unavailable to this account"):
            await revision_context(SimpleNamespace(database_url=database_url), outsider)
