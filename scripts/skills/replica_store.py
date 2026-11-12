"""Atomic, account-scoped storage for a reviewed Dhanz skill pack."""

import asyncio
import hashlib
import json
import sys
import uuid


class StoreError(ValueError):
    pass


def fingerprint(rows):
    return hashlib.sha256(json.dumps(sorted(rows, key=lambda r: r["name"]), sort_keys=True).encode()).hexdigest()


async def select_account(db, email=None):
    from sqlalchemy import func, select

    from app.models import User

    query = select(User).where(User.is_active.is_(True))
    if email:
        query = query.where(func.lower(User.email) == email.strip().lower())
    users = list(await db.scalars(query.limit(2)))
    if len(users) != 1:
        if email or not users:
            raise StoreError("No unique active Dhanz account matched. Nothing changed.")
        return None
    return users[0]


async def snapshot(db, user_id, names):
    from sqlalchemy import select

    from app.models import AssistantSkill

    rows = list(
        await db.scalars(
            select(AssistantSkill)
            .where(AssistantSkill.user_id == user_id, AssistantSkill.name.in_(names))
            .with_for_update()
        )
    )
    return sorted(
        [dict(name=r.name, description=r.description, instructions=r.instructions, enabled=r.enabled) for r in rows],
        key=lambda r: r["name"],
    )


async def install(db, user_id, specs, expected, *, replace=False):
    from sqlalchemy import func, select

    from app.db.base import utcnow
    from app.models import AssistantSkill, User
    from app.services.skills_service import SkillSpec

    data = [SkillSpec.model_validate(s).model_dump() for s in specs]
    names = [s["name"] for s in data]
    if len(names) != 11 or len(set(names)) != 11 or not all(n.startswith("replica-") for n in names):
        raise StoreError("Expected eleven unique Replica skill names. Nothing changed.")
    user = await db.scalar(select(User).where(User.id == user_id, User.is_active.is_(True)).with_for_update())
    if user is None:
        raise StoreError("The selected account is unavailable. Nothing changed.")
    before = await snapshot(db, user_id, names)
    if fingerprint(before) != expected:
        raise StoreError("Skills changed after the backup. Nothing changed; run the check again.")
    previous = {r["name"]: r for r in before}
    conflicts = [s["name"] for s in data if s["name"] in previous and previous[s["name"]] != s]
    if conflicts and not replace:
        raise StoreError(
            "Existing skills differ: " + ", ".join(conflicts) + ". Nothing changed; use --replace only to update them."
        )
    count = await db.scalar(select(func.count()).select_from(AssistantSkill).where(AssistantSkill.user_id == user_id))
    if count + len(set(names) - previous.keys()) > 50:
        raise StoreError("This would exceed the 50 saved-skill limit. Remove unused skills first; nothing changed.")
    changed = 0
    for spec in data:
        if previous.get(spec["name"]) == spec:
            continue
        row = await db.scalar(
            select(AssistantSkill).where(AssistantSkill.user_id == user_id, AssistantSkill.name == spec["name"])
        )
        if row is None:
            db.add(AssistantSkill(user_id=user_id, **spec))
        else:
            for key, value in spec.items():
                setattr(row, key, value)
            row.updated_at = utcnow()
        changed += 1
    await db.flush()
    return changed


async def restore(db, user_id, names, before, after_digest):
    from sqlalchemy import delete

    from app.models import AssistantSkill
    from app.services.skills_service import SkillSpec

    if set(r["name"] for r in before) - set(names):
        raise StoreError("Backup includes unrelated skills. Nothing changed.")
    data = [SkillSpec.model_validate(row).model_dump() for row in before]
    current = await snapshot(db, user_id, names)
    if fingerprint(current) == fingerprint(data):
        return
    if fingerprint(current) != after_digest:
        raise StoreError("Replica skills were edited after installation. Rollback stopped to preserve those edits.")
    from sqlalchemy import select

    from app.db.base import utcnow

    original = {spec["name"]: spec for spec in data}
    added_names = set(names) - original.keys()
    if added_names:
        await db.execute(
            delete(AssistantSkill).where(AssistantSkill.user_id == user_id, AssistantSkill.name.in_(added_names))
        )
    for spec in data:
        row = await db.scalar(
            select(AssistantSkill).where(AssistantSkill.user_id == user_id, AssistantSkill.name == spec["name"])
        )
        if row is None:
            db.add(AssistantSkill(user_id=user_id, **spec))
        else:
            for key, value in spec.items():
                setattr(row, key, value)
            row.updated_at = utcnow()
    await db.flush()


async def command(packet):
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.core.config import get_settings

    settings = get_settings()
    if not settings.assistant_skills_enabled:
        raise StoreError("Saved skills are disabled on this server. Nothing changed.")
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    try:
        async with async_sessionmaker(engine).begin() as db:
            mode = packet["mode"]
            if mode == "inspect":
                user = await select_account(db, packet.get("email"))
                if user is None:
                    return {"needs_account": True}
                before = await snapshot(db, user.id, packet["names"])
                return {"user_id": str(user.id), "before": before, "before_digest": fingerprint(before)}
            user_id = uuid.UUID(packet["user_id"])
            if mode == "install":
                changed = await install(
                    db, user_id, packet["skills"], packet["before_digest"], replace=packet.get("replace", False)
                )
                return {"installed": 11, "changed": changed}
            if mode == "restore":
                await restore(db, user_id, packet["names"], packet["before"], packet["after_digest"])
                return {"restored": True}
            raise StoreError("Unknown skill-store operation. Nothing changed.")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    try:
        result = asyncio.run(command(json.load(sys.stdin)))
    except StoreError as exc:
        result = {"error": str(exc)}
    except Exception as exc:
        result = {
            "error": "Skill storage step failed. No partial transaction was committed.",
            "error_type": type(exc).__name__,
        }
    print(json.dumps(result))
