import importlib.util
import json
import uuid
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.models import AssistantSkill, User
from app.services.skills_service import SkillSpec

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("replica_store", ROOT / "scripts/skills/replica_store.py")
store = importlib.util.module_from_spec(spec)
spec.loader.exec_module(store)
SKILLS = json.loads((ROOT / "skills/replica-pack/skills.json").read_text())
NAMES = [s["name"] for s in SKILLS]


@pytest_asyncio.fixture
async def database(tmp_path):
    engine = create_async_engine("sqlite+aiosqlite:///" + str(tmp_path / "skills.db"))
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    users = [User(id=uuid.uuid4(), email=f"{i}@example.test", display_name=str(i)) for i in range(2)]
    async with maker.begin() as db:
        db.add_all(users)
    yield maker, users
    await engine.dispose()


def test_eleven_complete_licensed_skills_fit_dhanz_and_keep_pinned_source():
    import hashlib

    assert len(SKILLS) == len(set(NAMES)) == 11
    for data in SKILLS:
        skill = SkillSpec.model_validate(data)
        assert "MIT License" in skill.instructions
        assert "77c9436fb3d18c3d58169efb8caf4fe906b0dc51" in skill.instructions
        assert "does NOT register these scripts" in skill.instructions
    provenance = json.loads((ROOT / "skills/replica-pack/provenance.json").read_text())
    for name, digest in provenance["files"].items():
        assert hashlib.sha256((ROOT / "skills/replica-pack/upstream" / name).read_bytes()).hexdigest() == digest


@pytest.mark.asyncio
async def test_scope_idempotence_and_restore_preserve_other_account(database):
    maker, users = database
    async with maker.begin() as db:
        assert await store.select_account(db) is None
        assert (await store.select_account(db, "0@EXAMPLE.TEST")).id == users[0].id
        db.add(
            AssistantSkill(
                user_id=users[1].id, name=NAMES[0], description="Other account", instructions="Keep me.", enabled=True
            )
        )
    async with maker.begin() as db:
        assert await store.install(db, users[0].id, SKILLS, store.fingerprint([])) == 11
    async with maker.begin() as db:
        rows = await store.snapshot(db, users[0].id, NAMES)
        assert rows == SKILLS
        assert await store.install(db, users[0].id, SKILLS, store.fingerprint(rows)) == 0
    async with maker.begin() as db:
        await store.restore(db, users[0].id, NAMES, [], store.fingerprint(SKILLS))
    async with maker() as db:
        assert await store.snapshot(db, users[0].id, NAMES) == []
        other = await store.snapshot(db, users[1].id, NAMES)
        assert other[0]["description"] == "Other account"


@pytest.mark.asyncio
async def test_conflicting_existing_skill_is_not_overwritten_or_partly_installed(database):
    maker, users = database
    async with maker.begin() as db:
        row = AssistantSkill(
            user_id=users[0].id,
            name=NAMES[-1],
            description="Custom",
            instructions="Keep this custom skill.",
            enabled=False,
        )
        db.add(row)
    async with maker.begin() as db:
        before = await store.snapshot(db, users[0].id, NAMES)
        with pytest.raises(store.StoreError, match="Existing skills differ"):
            await store.install(db, users[0].id, SKILLS, store.fingerprint(before))
    async with maker.begin() as db:
        assert await store.snapshot(db, users[0].id, NAMES) == before
        await store.install(db, users[0].id, SKILLS, store.fingerprint(before), replace=True)
    async with maker.begin() as db:
        await store.restore(db, users[0].id, NAMES, before, store.fingerprint(SKILLS))
    async with maker() as db:
        assert await store.snapshot(db, users[0].id, NAMES) == before
        restored = await db.scalar(select(AssistantSkill).where(AssistantSkill.user_id == users[0].id))
        assert restored.id == row.id


@pytest.mark.asyncio
async def test_rollback_refuses_later_user_edits(database):
    maker, users = database
    async with maker.begin() as db:
        await store.install(db, users[0].id, SKILLS, store.fingerprint([]))
    async with maker.begin() as db:
        row = await db.scalar(select(AssistantSkill).where(AssistantSkill.user_id == users[0].id))
        row.description = "Later user edit"
    async with maker.begin() as db:
        with pytest.raises(store.StoreError, match="edited after installation"):
            await store.restore(db, users[0].id, NAMES, [], store.fingerprint(SKILLS))
        assert len(await store.snapshot(db, users[0].id, NAMES)) == 11


@pytest.mark.asyncio
async def test_skill_limit_and_stale_backup_stop_before_changes(database):
    maker, users = database
    async with maker.begin() as db:
        for i in range(40):
            db.add(
                AssistantSkill(
                    user_id=users[0].id,
                    name=f"existing-{i}",
                    description="Existing",
                    instructions="Preserve this existing skill.",
                    enabled=True,
                )
            )
    async with maker.begin() as db:
        with pytest.raises(store.StoreError, match="50 saved-skill limit"):
            await store.install(db, users[0].id, SKILLS, store.fingerprint([]))
        assert await store.snapshot(db, users[0].id, NAMES) == []
    async with maker.begin() as db:
        with pytest.raises(store.StoreError, match="changed after the backup"):
            await store.install(db, users[1].id, SKILLS, "stale-fingerprint")
        assert await store.snapshot(db, users[1].id, NAMES) == []


def test_standalone_installer_contains_exact_reviewed_records_and_storage_code():
    spec = importlib.util.spec_from_file_location(
        "replica_installer", ROOT / "deploy/updaters/install_replica_skills.py"
    )
    installer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(installer)
    data = installer.bundle()
    assert data["skills"] == SKILLS
    assert data["store_source"] == (ROOT / "scripts/skills/replica_store.py").read_text()
    assert installer.fingerprint(SKILLS) == store.fingerprint(SKILLS)
    compile(data["store_source"], "replica_store.py", "exec")
    assert data["files"]["upstream/LICENSE"].startswith("MIT License")
