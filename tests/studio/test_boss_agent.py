import hashlib
import runpy
import sqlite3
import stat
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.assistant_studio import boss_agent as core
from app.assistant_studio import boss_tools
from app.db.base import Base
from app.models import User
from app.services import assistant_tools

NOW = datetime(2026, 11, 11, 14, tzinfo=UTC)


def key(value):
    return hashlib.sha256(str(value).encode()).hexdigest()


def perform(root, owner, op, *, token=None, **args):
    return core.execute(root, owner, {"operation": op, **args}, key(token or uuid.uuid4()), now=NOW)


def test_owner_isolation_persistence_idempotence_and_private_permissions(tmp_path):
    owner, other = uuid.uuid4(), uuid.uuid4()
    first = perform(tmp_path, owner, "task_add", title="Plan the app", token="once")
    retry = perform(tmp_path, owner, "task_add", title="Plan the app", token="once")
    assert retry["deduplicated"] and retry["task"]["id"] == first["task"]["id"]
    assert perform(tmp_path, owner, "status")["open_tasks"] == 1
    assert perform(tmp_path, other, "task_list")["items"] == []
    with pytest.raises(ValueError, match="not found"):
        perform(tmp_path, other, "task_complete", task_id=first["task"]["id"])
    with pytest.raises(ValueError, match="different instructions"):
        perform(tmp_path, owner, "task_add", title="Different task", token="once")
    folder = core.folder(tmp_path, owner)
    assert stat.S_IMODE(folder.stat().st_mode) == 0o700
    assert stat.S_IMODE((folder / "boss.sqlite3").stat().st_mode) == 0o600
    assert perform(tmp_path, owner, "task_list")["items"][0]["title"] == "Plan the app"


def test_deadlines_require_timezone_and_handle_daylight_saving_time():
    assert core.stamp("2026-11-12T09:00", "America/New_York") == "2026-11-12T14:00:00+00:00"
    assert core.stamp("2026-11-12T09:00-05:00") == "2026-11-12T14:00:00+00:00"
    with pytest.raises(ValueError, match="timezone"):
        core.stamp("2026-11-12T09:00")
    with pytest.raises(ValueError, match="occurs twice"):
        core.stamp("2026-11-01T01:30", "America/New_York")
    with pytest.raises(ValueError, match="does not exist"):
        core.stamp("2026-03-08T02:30", "America/New_York")
    with pytest.raises(ValueError):
        core.stamp("9999-12-31T23:59:59-12:00")


def test_reminders_are_queried_and_acknowledged_without_delivery(tmp_path):
    owner = uuid.uuid4()
    event = perform(
        tmp_path, owner, "event_add", title="Planning", deadline="2026-11-11T15:00Z", reminder="2026-11-11T13:00Z"
    )["event"]
    result = perform(tmp_path, owner, "event_reminders")
    assert [e["id"] for e in result["items"]] == [event["id"]]
    assert "on request" in result["capabilities_note"]
    perform(tmp_path, owner, "event_ack", event_id=event["id"])
    assert perform(tmp_path, owner, "event_reminders")["items"] == []
    with pytest.raises(ValueError, match="no later"):
        perform(
            tmp_path, owner, "event_add", title="Invalid", deadline="2026-11-11T15:00Z", reminder="2026-11-11T16:00Z"
        )
    assert perform(tmp_path, owner, "status")["events"] == 1


def test_assignment_reassignment_and_completion_stay_consistent(tmp_path):
    owner = uuid.uuid4()
    for name in ("Research", "Builder"):
        perform(tmp_path, owner, "agent_add", agent=name, role="Recorded worker")
    with pytest.raises(ValueError, match="already registered"):
        perform(tmp_path, owner, "agent_add", agent=" research ")
    task = perform(tmp_path, owner, "task_add", title="Review requirements")["task"]
    result = perform(tmp_path, owner, "delegate", task_id=task["id"], agent="Research")
    assert result["assignment_recorded"] and result["execution_started"] is False
    perform(tmp_path, owner, "delegate", task_id=task["id"], agent="Builder")
    agents = {a["name"]: a for a in perform(tmp_path, owner, "agent_list")["items"]}
    assert agents["Research"]["assigned_tasks"] == [] and agents["Research"]["status"] == "idle"
    assert agents["Builder"]["assigned_tasks"] == [task["id"]] and agents["Builder"]["status"] == "busy"
    perform(tmp_path, owner, "task_complete", task_id=task["id"])
    agents = {a["name"]: a for a in perform(tmp_path, owner, "agent_list")["items"]}
    assert agents["Builder"]["status"] == "idle" and agents["Builder"]["assigned_tasks"] == []
    with pytest.raises(ValueError, match="open task"):
        perform(tmp_path, owner, "delegate", task_id=task["id"], agent="Research")


def test_decision_rules_do_not_execute_and_failed_updates_are_rolled_back(tmp_path):
    owner = uuid.uuid4()
    perform(tmp_path, owner, "task_add", title="Future important", priority=5, deadline="2026-11-12T12:00Z")
    overdue = perform(tmp_path, owner, "task_add", title="Overdue", priority=1, deadline="2026-11-10T12:00Z")["task"]
    result = perform(tmp_path, owner, "decide_next")
    assert result["task"]["id"] == overdue["id"] and result["execution_started"] is False
    with pytest.raises(ValueError, match="Priority"):
        perform(tmp_path, owner, "task_update", task_id=overdue["id"], title="Lost title", priority=True)
    result = perform(tmp_path, owner, "decide_task", task_id=overdue["id"])
    assert result["task"]["title"] == "Overdue"
    perform(tmp_path, owner, "task_update", task_id=overdue["id"], deadline=None)
    assert perform(tmp_path, owner, "decide_task", task_id=overdue["id"])["task"]["deadline"] is None


def test_concurrent_updates_and_retries_do_not_lose_or_duplicate_tasks(tmp_path):
    owner = uuid.uuid4()
    perform(tmp_path, owner, "status")
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(
            pool.map(
                lambda n: perform(tmp_path, owner, "task_add", title=f"Task {n}", token=f"action-{n}"),
                [0, 1, 2, 3, 4, 5, 0, 1],
            )
        )
    assert len({r["task"]["id"] for r in results}) == 6
    assert perform(tmp_path, owner, "status")["open_tasks"] == 6


def test_notes_are_internal_and_storage_corruption_is_not_silently_reset(tmp_path):
    owner = uuid.uuid4()
    result = perform(tmp_path, owner, "note_add", content="Daily planning note")
    assert "Saved privately" in result["delivery"]
    assert perform(tmp_path, owner, "note_list")["items"][0]["content"] == "Daily planning note"
    database = core.folder(tmp_path, owner) / "boss.sqlite3"
    with sqlite3.connect(database) as db:
        db.execute("UPDATE records SET body='broken json'")
    with pytest.raises(ValueError):
        perform(tmp_path, owner, "note_list")
    with sqlite3.connect(database) as db:
        assert db.execute("SELECT count(*) FROM records").fetchone()[0] == 1


@pytest_asyncio.fixture
async def workspace(tmp_path, monkeypatch):
    sql = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with sql.begin() as db:
        await db.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(sql, expire_on_commit=False)
    owner, other = uuid.uuid4(), uuid.uuid4()
    async with maker() as db:
        db.add_all(
            [
                User(id=owner, email="boss-owner@example.test", display_name="Owner"),
                User(id=other, email="boss-other@example.test", display_name="Other"),
            ]
        )
        await db.commit()
    ctx = SimpleNamespace(
        settings=SimpleNamespace(storage_dir=str(tmp_path)),
        maker=maker,
        user_id=owner,
        assistant_message_id=uuid.uuid4(),
    )
    monkeypatch.setattr(assistant_tools, "TOOLS", {})
    boss_tools.install()
    yield SimpleNamespace(ctx=ctx, other=other, run=assistant_tools.TOOLS["boss_agent"].run)
    await sql.dispose()


@pytest.mark.asyncio
async def test_chat_actions_are_owned_idempotent_and_cannot_expand_permissions(workspace):
    s = workspace
    first = await s.run(s.ctx, {"operation": "task_add", "title": "Plan deployment"})
    second = await s.run(s.ctx, {"operation": "task_add", "title": "Plan deployment"})
    assert first.data["task"]["id"] == second.data["task"]["id"] and second.data["deduplicated"]
    outsider = SimpleNamespace(**{**s.ctx.__dict__, "user_id": s.other})
    with pytest.raises(assistant_tools.ToolInputError, match="not found"):
        await s.run(outsider, {"operation": "task_complete", "task_id": first.data["task"]["id"]})
    with pytest.raises(assistant_tools.ToolInputError, match="fields"):
        await s.run(s.ctx, {"operation": "task_add", "title": "Bad", "command": "anything"})
    async with s.ctx.maker() as db:
        user = await db.get(User, s.ctx.user_id)
        user.is_active = False
        await db.commit()
    with pytest.raises(assistant_tools.ToolInputError, match="active account"):
        await s.run(s.ctx, {"operation": "status"})


def test_installer_preserves_hooks_freezes_sources_and_requires_persistent_storage():
    root = Path(__file__).resolve().parents[2]
    updater = runpy.run_path(str(root / "deploy/updaters/install_boss_agent.py"))
    source = (
        "def install(app):\n    app.include_router(router, prefix=app.state.settings.api_prefix)\n    old_features()\n"
    )
    patched = updater["patch_bootstrap"](source)
    assert "old_features()" in patched and updater["patch_bootstrap"](patched) == patched
    for key_name, file in (("module", "boss_tools.py"), ("engine", "boss_agent.py")):
        assert updater["payload"]()[key_name] == (root / "server_extensions/assistant_studio" / file).read_text()
    updater["validate_storage"]([{"Type": "volume", "RW": True, "Destination": "/data"}], "/data/private")
    for mount, path in (
        ({"Type": "tmpfs", "RW": True, "Destination": "/data"}, "/data"),
        ({"Type": "volume", "RW": False, "Destination": "/data"}, "/data"),
        ({"Type": "volume", "RW": True, "Destination": "/data"}, "/data-other"),
    ):
        with pytest.raises(ValueError, match="persistent"):
            updater["validate_storage"]([mount], path)


def test_startup_registers_boss_without_creating_user_work(tmp_path, monkeypatch):
    from fastapi import APIRouter, FastAPI

    monkeypatch.setattr(assistant_tools, 'TOOLS', {})
    root = Path(__file__).resolve().parents[2]
    updater = runpy.run_path(str(root / 'deploy/updaters/install_boss_agent.py'))
    source = updater['patch_bootstrap'](
        'def install(app):\n    app.include_router(router, prefix=app.state.settings.api_prefix)\n')
    namespace = {'__name__': 'app.assistant_studio._boss_startup_test',
                 '__package__': 'app.assistant_studio', 'router': APIRouter()}
    exec(compile(source, 'bootstrap.py', 'exec'), namespace)  # noqa: S102 - reviewed installer source
    application = FastAPI()
    application.state.settings = SimpleNamespace(api_prefix='/api/v1', storage_dir=str(tmp_path))
    namespace['install'](application)
    assert 'boss_agent' in assistant_tools.TOOLS
    assert not (tmp_path / 'boss-agent').exists()
