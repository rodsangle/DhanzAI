"""Creative Studio API. Media and generation jobs are private by default."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import time
import uuid
from datetime import timedelta
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select

from app.api.deps import AdminUser, CurrentUser, DbDep, SettingsDep, parse_uuid
from app.core import rate_limit
from app.credit_billing import grant, lock_account, policy, reserve
from app.db.base import utcnow
from app.generation_jobs import ACTIVE, finish
from app.media_storage import validate_image
from app.models import CreditEntry, GenerationJob, MediaReport, User
from app.services import audit

router = APIRouter(prefix="/creative", tags=["creative"])
# Signed media URLs authenticate with an HMAC, not a bearer token, so they stay off the
# email-verification gate applied to `router` (see app.main).
public_router = APIRouter(prefix="/creative", tags=["creative"])


class GenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_key: str = Field(min_length=8, max_length=80, pattern=r"^[a-zA-Z0-9_-]+$")
    kind: Literal["image", "video"]
    model: str = Field(max_length=100)
    prompt: str = Field(min_length=3, max_length=4000)
    ratio: str = "1:1"
    quality: str = "medium"
    format: Literal["png", "jpeg", "webp", "mp4"] = "png"
    operation: str = "generate"
    duration: int = Field(default=5, ge=2, le=10)
    resolution: str = "720p"
    reference_id: uuid.UUID | None = None
    rights_confirmed: bool = False


def output(job):
    return {
        "id": str(job.id),
        "kind": job.kind,
        "provider": job.provider,
        "model": job.model,
        "prompt": job.prompt,
        "options": job.options,
        "status": job.status,
        "progress": job.progress,
        "cost": job.cost,
        "error": job.error,
        "created_at": job.created_at.isoformat(),
        "expires_at": job.expires_at.isoformat(),
        "has_media": bool(job.media_key) and job.expires_at > utcnow(),
        "provenance": job.provenance,
    }


async def owned(db, job_id, user_id):
    job = await db.get(GenerationJob, parse_uuid(job_id))
    if job is None or job.user_id != user_id or job.deleted:
        raise HTTPException(404, "Creation not found")
    return job


@router.get("/capabilities")
async def capabilities(request: Request, user: CurrentUser):
    return {
        "models": request.app.state.creative.capabilities(),
        "notice": "Creations are private. Only upload images you have rights and consent to use.",
    }


@router.get("/credits")
async def credits(user: CurrentUser, db: DbDep, settings: SettingsDep):
    account, rules = await lock_account(db, user.id, settings)
    await db.commit()
    return {
        "balance": account.balance,
        "reserved": account.reserved,
        "consumed": account.consumed,
        "allowance_month": account.allowance_month,
        "monthly_allowance": account.monthly_allowance
        if account.monthly_allowance is not None
        else rules.monthly_allowance,
        "image_cost": rules.image_cost,
        "video_cost_per_second": rules.video_cost_per_second,
    }


@router.get("/credits/history")
async def credit_history(user: CurrentUser, db: DbDep):
    rows = await db.scalars(
        select(CreditEntry).where(CreditEntry.user_id == user.id).order_by(CreditEntry.created_at.desc()).limit(100)
    )
    return [{"kind": row.kind, "amount": row.amount, "created_at": row.created_at.isoformat()} for row in rows]


@router.post("/jobs", status_code=201)
async def generate(body: GenerateRequest, request: Request, user: CurrentUser, db: DbDep, settings: SettingsDep):
    runtime = request.app.state.creative
    await rate_limit.enforce(f"creative:{user.id}", 10)
    if not body.rights_confirmed:
        raise HTTPException(422, "Confirm that you have rights and consent for the requested content")
    fingerprint = hashlib.sha256(
        json.dumps(body.model_dump(mode="json", exclude={"request_key"}), sort_keys=True).encode()
    ).hexdigest()
    account, rules = await lock_account(db, user.id, settings)
    existing = await db.scalar(
        select(GenerationJob).where(GenerationJob.user_id == user.id, GenerationJob.request_key == body.request_key)
    )
    if existing:
        if existing.request_hash != fingerprint:
            raise HTTPException(409, "Request key already used with different generation settings")
        await db.commit()
        return output(existing)
    caps = next(
        (cap for cap in runtime.capabilities() if cap["kind"] == body.kind and cap["model"] == body.model), None
    )
    if caps is None:
        raise HTTPException(503, "This generation model is not configured")
    if (
        body.ratio not in caps["ratios"]
        or body.format not in caps["formats"]
        or body.operation not in caps["operations"]
    ):
        raise HTTPException(422, "Unsupported aspect ratio, format or operation")
    if body.kind == "image" and body.quality not in caps["qualities"]:
        raise HTTPException(422, "Unsupported image quality")
    if body.kind == "video" and (body.duration not in caps["durations"] or body.resolution not in caps["resolutions"]):
        raise HTTPException(422, "Unsupported video duration or resolution")
    if body.operation == "remove_background" and body.format == "jpeg":
        raise HTTPException(422, "Transparent backgrounds require PNG or WebP")
    if body.operation != "generate" and body.reference_id is None:
        raise HTTPException(422, "This editing operation requires a reference image")
    active = await db.scalar(
        select(func.count())
        .select_from(GenerationJob)
        .where(GenerationJob.user_id == user.id, GenerationJob.status.in_(ACTIVE))
    )
    if active >= settings.creative_max_active_jobs:
        raise HTTPException(429, "Wait for an active generation to finish or cancel it")
    reference, reference_mime = None, None
    if body.reference_id:
        if not caps["reference"]:
            raise HTTPException(422, "This model does not support reference images")
        from app.models import KnowledgeDocument

        doc = await db.get(KnowledgeDocument, body.reference_id)
        if doc is None or doc.user_id != user.id or doc.file_type != "image" or not doc.storage_key:
            raise HTTPException(404, "Reference image not found")
        reference = await request.app.state.files.storage.get(doc.storage_key)
        try:
            reference_mime = await asyncio.to_thread(validate_image, reference)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None
    cost = rules.image_cost if body.kind == "image" else rules.video_cost_per_second * body.duration
    job = GenerationJob(
        id=uuid.uuid4(),
        user_id=user.id,
        request_key=body.request_key,
        request_hash=fingerprint,
        kind=body.kind,
        provider=caps["provider"],
        model=body.model,
        prompt=body.prompt.strip(),
        options=body.model_dump(exclude={"prompt", "request_key", "reference_id", "rights_confirmed", "kind", "model"}),
        cost=cost,
        status="queued",
        progress=0,
        reference_mime=reference_mime,
        expires_at=utcnow() + timedelta(days=settings.creative_media_days),
    )
    reserve(db, account, job)
    key = None
    try:
        if reference:
            key = await runtime.storage.put(reference)
            job.reference_key = key
        db.add(job)
        audit.record(db, "creative.queued", user_id=user.id, detail={"job_id": str(job.id), "kind": job.kind})
        await db.commit()
    except Exception:
        await db.rollback()
        if key:
            await runtime.storage.delete(key)
        raise
    return output(job)


@router.get("/jobs")
async def gallery(
    user: CurrentUser, db: DbDep, offset: int = Query(default=0, ge=0), limit: int = Query(default=30, ge=1, le=100)
):
    rows = await db.scalars(
        select(GenerationJob)
        .where(GenerationJob.user_id == user.id, GenerationJob.deleted.is_(False))
        .order_by(GenerationJob.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    return [output(row) for row in rows]


@router.get("/jobs/{job_id}")
async def detail(job_id: str, user: CurrentUser, db: DbDep):
    return output(await owned(db, job_id, user.id))


@router.post("/jobs/{job_id}/cancel")
async def cancel(job_id: str, request: Request, user: CurrentUser, db: DbDep):
    user_id = user.id
    await owned(db, job_id, user_id)
    # Release the request's read transaction before opening the settlement transaction.
    await db.rollback()
    await finish(request.app.state.sessionmaker, request.app.state.creative, parse_uuid(job_id), "canceled")
    return output(await owned(db, job_id, user_id))


@router.delete("/jobs/{job_id}", status_code=204)
async def delete_creation(job_id: str, user: CurrentUser, db: DbDep, settings: SettingsDep):
    await lock_account(db, user.id, settings)
    job = await owned(db, job_id, user.id)
    if job.status in ACTIVE:
        raise HTTPException(409, "Cancel the generation before deleting it")
    # Durable tombstone: cleanup retries storage errors; idempotency and accounting remain intact.
    job.deleted, job.expires_at, job.prompt, job.options = True, utcnow(), "", {}
    await db.commit()
    return Response(status_code=204)


class ReportRequest(BaseModel):
    reason: str = Field(min_length=5, max_length=1000)


@router.post("/jobs/{job_id}/report", status_code=201)
async def report(job_id: str, body: ReportRequest, user: CurrentUser, db: DbDep):
    job = await owned(db, job_id, user.id)
    await rate_limit.enforce(f"creative-report:{user.id}", 5)
    db.add(MediaReport(job_id=job.id, user_id=user.id, reason=body.reason))
    await db.commit()
    return {"reported": True}


def media_signature(settings, job_id, expires):
    return hmac.new(settings.jwt_secret.encode(), f"creative:{job_id}:{expires}".encode(), hashlib.sha256).hexdigest()


@router.post("/jobs/{job_id}/media-link")
async def media_link(job_id: str, user: CurrentUser, db: DbDep, settings: SettingsDep):
    job = await owned(db, job_id, user.id)
    if not job.media_key or job.expires_at <= utcnow():
        raise HTTPException(404, "Media is unavailable or expired")
    expires = int(time.time()) + 300
    return {
        "path": f"/creative/media/{job.id}?expires={expires}&signature={media_signature(settings, job.id, expires)}",
        "expires_in": 300,
    }


async def media_response(job, request, settings):
    if job.deleted or job.status != "completed" or not job.media_key or job.expires_at <= utcnow():
        raise HTTPException(404, "Media is unavailable or expired")
    try:
        data = await request.app.state.creative.storage.get(job.media_key)
    except FileNotFoundError:
        raise HTTPException(404, "Media is unavailable") from None
    headers = {
        "Cache-Control": "private, no-store",
        "Accept-Ranges": "bytes",
        "Cross-Origin-Resource-Policy": "cross-origin",
        "Content-Disposition": f'inline; filename="dhanz-{job.id}.{job.mime_type.split("/")[-1]}"',
    }
    range_header = request.headers.get("range")
    if range_header:
        import re

        match = re.fullmatch(r"bytes=(\d*)-(\d*)", range_header)
        if not match or not any(match.groups()):
            return Response(status_code=416, headers={"Content-Range": f"bytes */{len(data)}"})
        first, last = match.groups()
        start = int(first) if first else max(0, len(data) - int(last))
        end = min(int(last), len(data) - 1) if last and first else len(data) - 1
        if start > end or start >= len(data):
            return Response(status_code=416, headers={"Content-Range": f"bytes */{len(data)}"})
        headers["Content-Range"] = f"bytes {start}-{end}/{len(data)}"
        return Response(data[start : end + 1], status_code=206, media_type=job.mime_type, headers=headers)
    return Response(data, media_type=job.mime_type, headers=headers)


@public_router.get("/media/{job_id}")
async def signed_media(job_id: str, request: Request, db: DbDep, settings: SettingsDep, expires: int, signature: str):
    job_uuid = parse_uuid(job_id)
    if (
        expires < time.time()
        or expires > time.time() + 301
        or not hmac.compare_digest(signature, media_signature(settings, job_uuid, expires))
    ):
        raise HTTPException(403, "Media link is invalid or expired")
    job = await db.get(GenerationJob, job_uuid)
    user = await db.get(User, job.user_id) if job else None
    if not user or not user.is_active:
        raise HTTPException(404, "Media not found")
    return await media_response(job, request, settings)


@router.get("/jobs/{job_id}/download")
async def download(job_id: str, request: Request, user: CurrentUser, db: DbDep, settings: SettingsDep):
    return await media_response(await owned(db, job_id, user.id), request, settings)


class PolicyRequest(BaseModel):
    image_cost: int = Field(ge=1, le=100000)
    video_cost_per_second: int = Field(ge=1, le=100000)
    monthly_allowance: int = Field(ge=0, le=1000000)


@router.get("/admin/policy")
async def get_policy(admin: AdminUser, db: DbDep, settings: SettingsDep):
    rules = await policy(db, settings)
    result = {
        "image_cost": rules.image_cost,
        "video_cost_per_second": rules.video_cost_per_second,
        "monthly_allowance": rules.monthly_allowance,
    }
    await db.commit()
    return result


@router.put("/admin/policy")
async def update_policy(body: PolicyRequest, admin: AdminUser, db: DbDep, settings: SettingsDep):
    rules = await policy(db, settings)
    for name, value in body.model_dump().items():
        setattr(rules, name, value)
    audit.record(db, "creative.policy_updated", user_id=admin.id, detail=body.model_dump())
    await db.commit()
    return body


class GrantRequest(BaseModel):
    amount: int = Field(ge=1, le=1000000)
    request_key: str = Field(min_length=8, max_length=80)


@router.post("/admin/users/{user_id}/credits")
async def grant_credits(user_id: str, body: GrantRequest, admin: AdminUser, db: DbDep, settings: SettingsDep):
    target = parse_uuid(user_id)
    if await db.get(User, target) is None:
        raise HTTPException(404, "User not found")
    account = await grant(db, target, body.amount, body.request_key, settings)
    audit.record(
        db,
        "creative.credits_granted",
        user_id=admin.id,
        detail={"user_id": user_id, "amount": body.amount, "request_key": body.request_key},
    )
    await db.commit()
    return {"balance": account.balance}


@router.get("/admin/reports")
async def reports(admin: AdminUser, db: DbDep):
    rows = await db.scalars(select(MediaReport).order_by(MediaReport.created_at.desc()).limit(100))
    return [
        {
            "id": str(row.id),
            "job_id": str(row.job_id),
            "user_id": str(row.user_id),
            "reason": row.reason,
            "created_at": row.created_at.isoformat(),
        }
        for row in rows
    ]


@router.delete("/admin/jobs/{job_id}", status_code=204)
async def remove_unsafe(job_id: str, request: Request, admin: AdminUser, db: DbDep, settings: SettingsDep):
    job_uuid = parse_uuid(job_id)
    job = await db.get(GenerationJob, job_uuid)
    if job is None:
        raise HTTPException(404, "Creation not found")
    user_id, admin_id = job.user_id, admin.id
    await db.rollback()
    await finish(request.app.state.sessionmaker, request.app.state.creative, job_uuid, "canceled")
    await lock_account(db, user_id, settings)
    job = await db.get(GenerationJob, job_uuid, populate_existing=True)
    job.deleted, job.expires_at, job.prompt, job.options = True, utcnow(), "", {}
    audit.record(db, "creative.removed", user_id=admin_id, detail={"job_id": job_id})
    await db.commit()
    return Response(status_code=204)


class AllowanceRequest(BaseModel):
    monthly_allowance: int | None = Field(default=None, ge=0, le=1000000)


@router.put("/admin/users/{user_id}/allowance")
async def set_allowance(user_id: str, body: AllowanceRequest, admin: AdminUser, db: DbDep, settings: SettingsDep):
    target = parse_uuid(user_id)
    if await db.get(User, target) is None:
        raise HTTPException(404, "User not found")
    account, _ = await lock_account(db, target, settings)
    account.monthly_allowance = body.monthly_allowance
    audit.record(
        db,
        "creative.allowance_updated",
        user_id=admin.id,
        detail={"user_id": user_id, "monthly_allowance": body.monthly_allowance},
    )
    await db.commit()
    return {"monthly_allowance": account.monthly_allowance, "effective": "next UTC calendar month"}
