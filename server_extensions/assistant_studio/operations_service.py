"""No arbitrary shell interface: a paired host advertises exact named recipes.

Grants are established by the authenticated owner, never by model tool calls.
Remote outcomes are at-most-once: lost responses remain uncertain, not replayed.
"""

import asyncio
import contextlib
import hashlib
import uuid
from contextlib import asynccontextmanager
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.db.base import utcnow
from app.models import User
from app.services import github_service as gh

from . import coding_service as coding
from .coding_models import CodingDraft
from .models import BuilderProject
from .operations_models import OperationGrant, OperationJob, OperationServer


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def active(grant):
    return not grant.revoked and grant.remaining > 0 and grant.expires_at > utcnow()


def public(row):
    if isinstance(row, OperationServer):
        return {
            "id": str(row.id),
            "name": row.name,
            "tasks": row.tasks,
            "revoked": row.revoked,
            "last_seen": row.last_seen.isoformat() if row.last_seen else None,
        }
    if isinstance(row, OperationGrant):
        return {
            "id": str(row.id),
            "kind": row.kind,
            "target": row.target,
            "scope": row.scope,
            "remaining": row.remaining,
            "expires_at": row.expires_at.isoformat(),
            "active": active(row),
        }
    return {
        "id": str(row.id),
        "grant_id": str(row.grant_id),
        "task": row.task,
        "status": row.status,
        "detail": row.detail,
        "created_at": row.created_at.isoformat(),
    }


async def owned(db, model, user_id, identifier):
    row = await db.scalar(select(model).where(model.id == identifier, model.user_id == user_id))
    if row is None:
        raise HTTPException(404, "Not found")
    return row


async def server_auth(db, token):
    row = await db.scalar(
        select(OperationServer).where(
            OperationServer.token_hash == token_hash(token), OperationServer.revoked.is_(False)
        )
    )
    if row is None:
        raise HTTPException(401, "Server connection is invalid or revoked.")
    user = await db.get(User, row.user_id)
    if user is None or not user.is_active:
        raise HTTPException(401, "Server account is inactive.")
    return row


async def consume(db, grant):
    result = await db.execute(
        update(OperationGrant)
        .where(
            OperationGrant.id == grant.id,
            OperationGrant.revoked.is_(False),
            OperationGrant.remaining > 0,
            OperationGrant.expires_at > utcnow(),
        )
        .values(remaining=OperationGrant.remaining - 1)
    )
    if result.rowcount != 1:
        raise HTTPException(403, "Standing permission expired, was revoked or reached its limit.")


async def enqueue(db, user_id, grant_id, request_key):
    grant = await owned(db, OperationGrant, user_id, grant_id)
    existing = await db.scalar(
        select(OperationJob).where(OperationJob.user_id == user_id, OperationJob.request_key == request_key)
    )
    if existing:
        if existing.grant_id != grant.id:
            raise HTTPException(409, "Request key belongs to a different operation.")
        return existing
    if grant.kind != "server_task":
        raise HTTPException(422, "Use a server task permission.")
    server = await owned(db, OperationServer, user_id, uuid.UUID(grant.target))
    recipe = next((t for t in server.tasks if t["name"] == grant.scope["task"]), None)
    if server.revoked or not recipe or recipe["manifest_hash"] != grant.scope["manifest_hash"]:
        raise HTTPException(409, "Server recipe changed. Authorize its current version first.")
    if not server.last_seen or server.last_seen < utcnow() - timedelta(minutes=2):
        raise HTTPException(409, "Server companion is offline. No task was queued.")
    await consume(db, grant)
    job = OperationJob(
        user_id=user_id,
        grant_id=grant.id,
        server_id=server.id,
        request_key=request_key,
        task=recipe["name"],
        manifest_hash=recipe["manifest_hash"],
    )
    db.add(job)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        existing = await db.scalar(
            select(OperationJob).where(OperationJob.user_id == user_id, OperationJob.request_key == request_key)
        )
        if existing and existing.grant_id == grant_id:
            return existing
        raise HTTPException(409, "Operation changed concurrently. Refresh before retrying.") from None
    return job


async def claim(db, server):
    # A dead companion never causes an executing action to be repeated.
    now = utcnow()
    await db.execute(
        update(OperationJob)
        .where(
            OperationJob.server_id == server.id,
            OperationJob.status == "executing",
            OperationJob.started_at < now - timedelta(minutes=35),
        )
        .values(status="uncertain", detail="Companion result missing; inspect server before retrying.", finished_at=now)
    )
    # Expire queued work instead of surprising the owner after a long outage.
    await db.execute(
        update(OperationJob)
        .where(
            OperationJob.server_id == server.id,
            OperationJob.status == "queued",
            OperationJob.created_at < now - timedelta(minutes=5),
        )
        .values(status="cancelled", detail="Queued task expired.", finished_at=now)
    )
    candidates = list(
        await db.scalars(
            select(OperationJob)
            .where(OperationJob.server_id == server.id, OperationJob.status == "queued")
            .order_by(OperationJob.created_at)
            .limit(20)
        )
    )
    for job in candidates:
        grant = await db.get(OperationGrant, job.grant_id)
        recipe = next((t for t in server.tasks if t["name"] == job.task), None)
        # remaining was consumed at enqueue; do not require it again here.
        if grant.revoked or grant.expires_at <= now or not recipe or recipe["manifest_hash"] != job.manifest_hash:
            job.status = "cancelled"
            job.detail = "Permission revoked/expired or server recipe changed before execution."
            continue
        result = await db.execute(
            update(OperationJob)
            .where(
                OperationJob.id == job.id,
                OperationJob.status == "queued",
            )
            .values(status="executing", started_at=now)
        )
        if result.rowcount == 1:
            await db.commit()
            return {"id": str(job.id), "task": job.task, "manifest_hash": job.manifest_hash}
    await db.commit()
    return None


async def publish_granted(db, settings, row, grant):
    user = await db.get(User, grant.user_id)
    if user is None or not user.is_active or row.user_id != grant.user_id:
        return
    project = await db.get(BuilderProject, row.project_id)
    if not project or project.status != "complete":
        return
    if (
        row.repository != grant.target
        or row.base_branch != grant.scope["branch"]
        or row.repository_id != grant.scope.get("repository_id")
        or not active(grant)
    ):
        return
    key = "publish-" + row.id.hex + "-" + str(row.repair_count)
    if await db.scalar(
        select(OperationJob.id).where(OperationJob.user_id == row.user_id, OperationJob.request_key == key)
    ):
        return
    # Snapshot validation and stale-base checks remain enforced by coding service.
    if row.status == "generating":
        await coding.prepare_review(db, settings, row.user_id, row, None)
    await consume(db, grant)
    job = OperationJob(
        user_id=row.user_id,
        grant_id=grant.id,
        request_key=key,
        task="publish_draft_pr",
        status="executing",
        started_at=utcnow(),
    )
    db.add(job)
    try:
        await db.commit()  # durable receipt BEFORE the first remote write
    except Exception:
        await db.rollback()
        return  # another worker won; no remote request made by this worker
    try:
        await coding.publish(db, settings, row.user_id, row, row.review_hash)
        job.status = "completed"
        job.detail = "Draft pull request created under standing permission. No merge or deployment."
    except gh.GitHubError:
        job.status = "uncertain" if row.status in {"publishing", "uncertain"} else "failed"
        job.detail = "Publication stopped. Inspect the coding draft and GitHub before retrying."
    job.finished_at = utcnow()
    await db.commit()


async def monitor(maker, settings):
    while True:
        await asyncio.sleep(8)
        try:
            async with maker() as db:
                grants = list(
                    await db.scalars(
                        select(OperationGrant)
                        .where(
                            OperationGrant.kind == "github_publish",
                            OperationGrant.revoked.is_(False),
                            OperationGrant.remaining > 0,
                            OperationGrant.expires_at > utcnow(),
                        )
                        .limit(100)
                    )
                )
                for grant in grants:
                    rows = list(
                        await db.scalars(
                            select(CodingDraft)
                            .where(
                                CodingDraft.user_id == grant.user_id,
                                CodingDraft.repository == grant.target,
                                CodingDraft.base_branch == grant.scope["branch"],
                                CodingDraft.created_at >= grant.created_at,
                                CodingDraft.status.in_(["generating", "review"]),
                            )
                            .limit(10)
                        )
                    )
                    for row in rows:
                        try:
                            await publish_granted(db, settings, row, grant)
                        except Exception:
                            await db.rollback()  # never retry a remote write; its durable job remains
        except Exception:  # noqa: S112 - database polling only; remote writes have durable receipts
            continue


def install(app):
    from .folder_uploads import install as install_folders
    from .operations_routes import router
    from .operations_tools import install_tools

    app.include_router(router, prefix=app.state.settings.api_prefix)
    install_tools()
    install_folders()
    original = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(application):
        async with original(application):
            task = asyncio.create_task(monitor(application.state.sessionmaker, application.state.settings))
            try:
                yield
            finally:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task

    app.router.lifespan_context = lifespan
