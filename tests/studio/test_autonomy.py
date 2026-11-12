import sys
import uuid
from types import SimpleNamespace

import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.assistant_studio import autonomy, builder
from app.core.config import Settings
from app.db.base import Base
from app.models import User


@pytest_asyncio.fixture
async def accounts(tmp_path):
    url = "sqlite+aiosqlite:///" + str(tmp_path / "preferences.db")
    engine = create_async_engine(url)
    async with engine.begin() as c:
        await c.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    users = [User(id=uuid.uuid4(), email=f"{i}@example.test", display_name=str(i)) for i in range(2)]
    async with maker.begin() as db:
        db.add_all(users)
    yield maker, users, url
    await engine.dispose()


@pytest.mark.asyncio
async def test_account_setting_applies_and_can_be_disabled_without_new_grants(accounts):
    maker, users, _ = accounts
    async with maker() as db:
        await autonomy.set_preference(autonomy.Preference(enabled=True), users[0], db)
        assert await autonomy.enabled(db, users[0].id)
        assert not await autonomy.enabled(db, users[1].id)
        await autonomy.set_preference(autonomy.Preference(enabled=False), users[0], db)
        assert not await autonomy.enabled(db, users[0].id)
    assert "not a new permission" in autonomy.POLICY


@pytest.mark.asyncio
async def test_chat_and_coding_hooks_use_only_the_owning_account(accounts, monkeypatch):
    maker, users, url = accounts
    async with maker() as db:
        await autonomy.set_preference(autonomy.Preference(enabled=True), users[0], db)

    async def context(db, user, conv):
        return {"project_instructions": "Keep existing project instructions.", "memories": []}

    chat = SimpleNamespace(_turn_context=context)
    monkeypatch.setitem(sys.modules, "app.services.chat_service", chat)
    generated = []

    async def generate(settings, job, **kwargs):
        generated.append((job.user_id, job.prompt, job.kind))
        return [], "Source only"

    monkeypatch.setattr(builder, "generate", generate)
    app = FastAPI()
    app.state.settings = Settings(app_env="test", _env_file=None)
    from app.services import skills_service

    monkeypatch.setattr(skills_service, "catalog", skills_service.catalog)
    autonomy.install(app)
    async with maker() as db:
        first = await chat._turn_context(db, users[0], SimpleNamespace(temporary=True))
        other = await chat._turn_context(db, users[1], SimpleNamespace(temporary=False))
        assert autonomy.POLICY in first["project_instructions"] and first["memories"] == []
        assert other["project_instructions"] == "Keep existing project instructions."
    first_job = SimpleNamespace(user_id=users[0].id, prompt="[DHANZ_RUNTIME:flutter]\nBuild a demo", kind="app")
    other_job = SimpleNamespace(user_id=users[1].id, prompt="Build a demo", kind="app")
    await builder.generate(SimpleNamespace(database_url=url), first_job)
    await builder.generate(SimpleNamespace(database_url=url), other_job)
    assert generated[0][1].startswith("[DHANZ_RUNTIME:flutter]\n") and autonomy.POLICY in generated[0][1]
    assert generated[1][1] == "Build a demo"
    assert first_job.prompt == "[DHANZ_RUNTIME:flutter]\nBuild a demo"


def test_installer_startup_check_handles_fastapi_included_router_objects(monkeypatch, capsys):
    import ast
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    application = FastAPI()
    application.state.settings = Settings(app_env="test", _env_file=None)
    application.include_router(autonomy.router, prefix=application.state.settings.api_prefix)
    # New FastAPI uses _IncludedRouter entries without .path; checking OpenAPI
    # must still verify both endpoint methods rather than silently skip them.
    if any(not hasattr(route, "path") for route in application.routes):
        with pytest.raises(AttributeError):
            any(route.path.endswith("/assistant-studio/autonomy") for route in application.routes)
    monkeypatch.setitem(sys.modules, "app.main", SimpleNamespace(create_app=lambda settings: application))
    tree = ast.parse((root / "deploy/updaters/install_autonomy_backend.py").read_text())
    check = next(
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and "Autonomy startup checks passed." in node.value
    )
    exec(compile(check, "<installer-startup>", "exec"), {})  # noqa: S102 - reviewed offline startup snippet
    assert "Autonomy startup checks passed." in capsys.readouterr().out
