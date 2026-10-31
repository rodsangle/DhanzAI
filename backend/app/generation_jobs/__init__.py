"""Durable database-backed generation queue, leases, terminal transitions and credit settlement."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import secrets
from datetime import timedelta

from sqlalchemy import and_, or_, select, update

from app.content_moderation import ModerationRejected, build_moderator
from app.credit_billing import lock_account, settle
from app.db.base import utcnow
from app.image_generation import ImageProvider
from app.media_storage import build_storage, validate_image
from app.models import GenerationJob, MediaDeletion, User
from app.video_generation import VideoProvider

log = logging.getLogger(__name__)
ACTIVE = ("queued", "processing")


class CreativeRuntime:
    def __init__(self, settings):
        self.settings = settings
        self.storage = build_storage(settings)
        self.image = None
        self.video = None
        self.moderator = None
        if settings.creative_enabled:
            self.moderator = build_moderator(settings)
            if self.moderator is None:
                log.warning(
                    "Creative Studio is enabled but content moderation is not configured; generation stays unavailable"
                )
            else:
                image_key = settings.creative_image_api_key or settings.openai_api_key
                if image_key:
                    self.image = ImageProvider(
                        image_key,
                        settings.creative_image_base_url,
                        settings.creative_image_model,
                        edits=settings.creative_image_edits,
                        transparency=settings.creative_image_transparency,
                    )
                if settings.runway_api_key:
                    self.video = VideoProvider(settings.runway_api_key)

    def capabilities(self):
        return [provider.capabilities() for provider in (self.image, self.video) if provider is not None]

    async def aclose(self):
        for provider in (self.image, self.video, self.moderator):
            if provider is not None:
                await provider.aclose()


async def finish(maker, runtime, job_id, status, *, media_key=None, mime=None, error=None, token=None):
    """Account lock + conditional terminal transition ensures exactly-once internal settlement."""
    accepted = False
    async with maker() as db:
        job = await db.get(GenerationJob, job_id)
        if job is not None:
            account, _ = await lock_account(db, job.user_id, runtime.settings)
            await db.refresh(job)
            if job.status in ACTIVE and (token is None or job.lease_token == token):
                job.status, job.error, job.updated_at = status, error, utcnow()
                job.progress = 100 if status == "completed" else job.progress
                job.media_key, job.mime_type = media_key, mime
                job.lease_token, job.lease_until = None, None
                if status == "completed":
                    job.provenance = {
                        "ai_generated": True,
                        "provider": job.provider,
                        "model": job.model,
                        "generated_at": utcnow().isoformat(),
                        "disclosure": "AI-generated content; verify accuracy and usage rights.",
                    }
                settle(db, account, job, status == "completed")
                await db.commit()
                accepted = True
    if media_key and not accepted:
        await runtime.storage.delete(media_key)
    return accepted


async def claim(maker):
    now = utcnow()
    async with maker() as db:
        candidates = list(
            await db.scalars(
                select(GenerationJob.id)
                .where(
                    GenerationJob.status.in_(ACTIVE),
                    GenerationJob.next_poll_at <= now,
                    or_(GenerationJob.lease_until.is_(None), GenerationJob.lease_until < now),
                )
                .order_by(GenerationJob.created_at)
                .limit(10)
            )
        )
        for job_id in candidates:
            token = secrets.token_hex(24)
            changed = await db.execute(
                update(GenerationJob)
                .where(
                    GenerationJob.id == job_id,
                    GenerationJob.status.in_(ACTIVE),
                    GenerationJob.next_poll_at <= now,
                    or_(GenerationJob.lease_until.is_(None), GenerationJob.lease_until < now),
                )
                .values(status="processing", lease_token=token, lease_until=now + timedelta(minutes=10), updated_at=now)
            )
            if changed.rowcount:
                await db.commit()
                return job_id, token
        await db.rollback()
    return None


async def save_provider_id(maker, job_id, token, provider_id):
    # Save even if canceled during submission, so the worker can cancel the remote task later.
    async with maker() as db:
        changed = await db.execute(
            update(GenerationJob)
            .where(
                GenerationJob.id == job_id,
                or_(GenerationJob.lease_token == token, GenerationJob.status == "canceled"),
            )
            .values(provider_job_id=provider_id)
        )
        await db.commit()
        return bool(changed.rowcount)


async def process_one(maker, runtime):
    leased = await claim(maker)
    if leased is None:
        return False
    job_id, token = leased
    media_key = None
    try:
        async with maker() as db:
            job = await db.get(GenerationJob, job_id)
            active_user = await db.get(User, job.user_id)
            if not active_user or not active_user.is_active:
                raise ValueError("Account is unavailable")
        if job.expires_at <= utcnow() or job.created_at < utcnow() - timedelta(hours=2):
            raise ValueError("Generation expired before completion")
        provider = runtime.image if job.kind == "image" else runtime.video
        if provider is None or runtime.moderator is None:
            raise ValueError("Generation provider or moderation is unavailable")
        if not job.submitted:
            reference = await runtime.storage.get(job.reference_key) if job.reference_key else None
            await runtime.moderator.check(job.prompt, reference, job.reference_mime)
            # Commit submission intent before the external call. Crash recovery must never
            # blindly repeat an image request or a video submission of uncertain outcome.
            async with maker() as db:
                changed = await db.execute(
                    update(GenerationJob)
                    .where(
                        GenerationJob.id == job_id,
                        GenerationJob.lease_token == token,
                        GenerationJob.status == "processing",
                    )
                    .values(submitted=True, progress=10)
                )
                await db.commit()
            if not changed.rowcount:
                return True
            if job.kind == "image":
                data = await provider.generate(job, reference)
                mime = await asyncio.to_thread(validate_image, data)
                if mime != f"image/{job.options['format']}":
                    raise ValueError("Image provider returned a different file format than requested")
                await runtime.moderator.check("Screen generated image for safety", data, mime)
                media_key = await runtime.storage.put(data)
                await finish(maker, runtime, job_id, "completed", media_key=media_key, mime=mime, token=token)
                media_key = None
                return True
            provider_id = await provider.submit(job, reference)
            saved = await save_provider_id(maker, job_id, token, provider_id)
            async with maker() as db:
                current = await db.get(GenerationJob, job_id)
                still_active = current is not None and current.status in ACTIVE
            if not saved or not still_active:
                await provider.cancel(provider_id)
                return True
            job.provider_job_id = provider_id
        elif not job.provider_job_id:
            raise ValueError(
                "Provider submission outcome is uncertain; credits released. Start a new request to retry."
            )
        result = await provider.poll(job.provider_job_id)
        state = result.get("status")
        if state == "SUCCEEDED":
            data = await provider.download(result["output"][0], runtime.settings.creative_max_media_mb * 1024 * 1024)
            media_key = await runtime.storage.put(data)
            await finish(maker, runtime, job_id, "completed", media_key=media_key, mime="video/mp4", token=token)
            media_key = None
        elif state in ("FAILED", "CANCELLED", "CANCELED"):
            await finish(
                maker,
                runtime,
                job_id,
                "failed",
                error="Video generation failed or was blocked by the provider",
                token=token,
            )
        elif state in ("PENDING", "THROTTLED", "RUNNING"):
            async with maker() as db:
                await db.execute(
                    update(GenerationJob)
                    .where(
                        GenerationJob.id == job_id,
                        GenerationJob.lease_token == token,
                        GenerationJob.status == "processing",
                    )
                    .values(
                        lease_until=None,
                        lease_token=None,
                        progress=50 if state == "RUNNING" else 15,
                        next_poll_at=utcnow() + timedelta(seconds=10),
                    )
                )
                await db.commit()
        else:
            raise ValueError("Provider returned an unrecognized video status")
    except Exception as exc:  # noqa: BLE001 - durable failures must release reserved credits
        log.warning("Creative generation %s failed (%s)", job_id, type(exc).__name__)
        safe_error = (
            str(exc)
            if isinstance(exc, ModerationRejected | ValueError)
            else ("Generation service failed. Credits were released; please try again later.")
        )
        await finish(maker, runtime, job_id, "failed", error=safe_error[:500], token=token)
    finally:
        if media_key:
            await runtime.storage.delete(media_key)
    return True


async def cleanup(maker, runtime):
    """Delete expired bytes and release canceled/failed references. Retry failed deletions next round."""
    async with maker() as db:
        removals = list(await db.scalars(select(MediaDeletion).limit(200)))
    for removal in removals:
        try:
            if removal.kind == "object":
                await runtime.storage.delete(removal.key)
            elif removal.kind == "runway_task" and runtime.video:
                await runtime.video.cancel(removal.key)
            else:
                continue
            async with maker() as db:
                row = await db.get(MediaDeletion, (removal.key, removal.kind))
                if row:
                    await db.delete(row)
                    await db.commit()
        except Exception:  # noqa: BLE001 - retain deletion outbox item for retry
            log.warning("Creative deletion will be retried")
    async with maker() as db:
        jobs = list(
            await db.scalars(
                select(GenerationJob)
                .where(
                    or_(
                        and_(
                            GenerationJob.status.in_(("failed", "canceled", "completed")),
                            GenerationJob.reference_key.is_not(None),
                        ),
                        and_(
                            GenerationJob.status.in_(("canceled", "failed")), GenerationJob.provider_job_id.is_not(None)
                        ),
                        and_(
                            GenerationJob.expires_at < utcnow(),
                            or_(GenerationJob.media_key.is_not(None), GenerationJob.status.in_(ACTIVE)),
                        ),
                    ),
                )
                .limit(200)
            )
        )
    for job in jobs:
        if job.status in ACTIVE:
            await finish(maker, runtime, job.id, "failed", error="Generation expired")
            continue
        canceled_remote = False
        if job.status in ("canceled", "failed") and job.provider_job_id and runtime.video:
            with contextlib.suppress(Exception):
                await runtime.video.cancel(job.provider_job_id)
                canceled_remote = True
        async with maker() as db:
            current = await db.get(GenerationJob, job.id)
            if current is None:
                continue
            if canceled_remote:
                current.provider_job_id = None
            if current.reference_key:
                await runtime.storage.delete(current.reference_key)
                current.reference_key = None
            if current.expires_at < utcnow() and current.media_key:
                await runtime.storage.delete(current.media_key)
                current.media_key = None
            await db.commit()


async def worker_loop(maker, runtime):
    while True:
        try:
            await process_one(maker, runtime)
            await cleanup(maker, runtime)
        except Exception:  # noqa: BLE001 - retry database/storage outages next round
            log.exception("Creative worker iteration failed")
        await asyncio.sleep(2)


async def standalone():
    from app.core.config import get_settings
    from app.db.session import make_engine, make_sessionmaker

    settings = get_settings()
    engine = make_engine(settings.database_url)
    runtime = CreativeRuntime(settings)
    try:
        await worker_loop(make_sessionmaker(engine), runtime)
    finally:
        await runtime.aclose()
        await engine.dispose()
