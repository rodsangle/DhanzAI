from __future__ import annotations

import asyncio
import contextlib
import hmac
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST

from app.api.routes import (
    admin,
    auth,
    conversations,
    devices,
    files,
    memories,
    meta,
    projects,
    realtime,
    updates,
    users,
    voice,
)
from app.api.routes import knowledge as knowledge_routes
from app.core import rate_limit
from app.core.config import Settings, get_settings
from app.core.observability import (
    BodySizeLimitMiddleware,
    RequestContextMiddleware,
    configure_logging,
    render_metrics,
)
from app.db.session import make_engine, make_sessionmaker
from app.services.files_service import build_files_runtime
from app.services.knowledge_service import KnowledgeRuntime, build_knowledge_runtime, wait_for_background_indexing
from app.services.mailer import Mailer, build_mailer
from app.services.maintenance import maintenance_loop
from app.services.push import Notification, PushService, build_push
from app.services.stt import SpeechToText, build_stt
from app.services.turns import TurnHandle, TurnManager
from dhanz_ai import AnthropicProvider, GeminiProvider, OllamaProvider, OpenAIProvider, Orchestrator


def build_orchestrator(settings: Settings) -> Orchestrator:
    return Orchestrator(
        [
            OpenAIProvider(settings.openai_api_key, settings.openai_model_list, base_url=settings.openai_base_url),
            AnthropicProvider(settings.anthropic_api_key, settings.anthropic_model_list),
            GeminiProvider(settings.gemini_api_key, settings.gemini_model_list),
            OllamaProvider(settings.ollama_base_url, settings.ollama_model_list),
        ]
    )


def _notify_finished(app: FastAPI):
    async def notify(handle: TurnHandle) -> None:
        """Nobody was watching when the reply finished (app closed/backgrounded): send a push."""
        final = handle.final_event or {}
        if final.get("type") != "done" or not app.state.push.enabled:
            return
        # Deliberately generic text: notifications can show on a locked screen.
        await app.state.push.notify_user(
            app.state.sessionmaker,
            handle.user_id,
            Notification(
                title="Dhanz finished your answer",
                body="Tap to read it.",
                data={"conversation_id": str(handle.conversation_id), "message_id": str(handle.message_id)},
            ),
        )

    return notify


def create_app(
    settings: Settings | None = None,
    orchestrator: Orchestrator | None = None,
    knowledge: KnowledgeRuntime | None = None,
    stt: SpeechToText | None = None,
    push: PushService | None = None,
    mailer: Mailer | None = None,
    redis=None,
) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level, settings.log_format)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        engine = make_engine(
            settings.database_url, pool_size=settings.db_pool_size, max_overflow=settings.db_max_overflow
        )
        app.state.engine = engine
        app.state.sessionmaker = make_sessionmaker(engine)
        app.state.orchestrator = orchestrator or build_orchestrator(settings)
        app.state.knowledge = knowledge or build_knowledge_runtime(settings)
        app.state.files = build_files_runtime(settings)
        app.state.stt = stt if stt is not None else build_stt(settings)
        app.state.push = push if push is not None else build_push(settings)
        app.state.turns = TurnManager(on_unattended_finish=_notify_finished(app))
        app.state.mailer = mailer if mailer is not None else build_mailer(settings)
        redis_client = redis
        if redis_client is None and settings.redis_url:
            from redis.asyncio import Redis

            redis_client = Redis.from_url(settings.redis_url, socket_timeout=2, socket_connect_timeout=2)
        rate_limit.limiter.use_redis(redis_client)
        maintenance = (
            asyncio.create_task(maintenance_loop(app.state.sessionmaker, settings))
            if settings.maintenance_interval_minutes
            else None
        )
        yield
        if maintenance is not None:
            maintenance.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await maintenance
        rate_limit.limiter.use_redis(None)
        if redis_client is not None and redis is None:
            await redis_client.aclose()
        await app.state.turns.shutdown()
        await wait_for_background_indexing()
        for provider in app.state.orchestrator.providers.values():
            await provider.aclose()
        await app.state.knowledge.aclose()
        if app.state.stt is not None:
            await app.state.stt.aclose()
        await app.state.push.aclose()
        await engine.dispose()

    app = FastAPI(
        title="DHANZ AI API",
        version="0.5.0",
        description="Backend for the DHANZ AI assistant. Your World. Your Knowledge. Your AI.",
        lifespan=lifespan,
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None,
        openapi_url=None if settings.is_production else "/openapi.json",
    )
    app.state.settings = settings

    # Added innermost first: RequestContext (request IDs, metrics, access log) wraps everything.
    app.add_middleware(
        BodySizeLimitMiddleware,
        default_limit=settings.max_request_kb * 1024,
        limits={
            "/files": (settings.max_upload_mb + 1) * 1024 * 1024,
            "/voice/transcribe": (settings.max_audio_mb + 1) * 1024 * 1024,
        },
    )
    # Compresses JSON/text responses; Server-Sent Events are excluded so streaming stays live.
    app.add_middleware(GZipMiddleware, minimum_size=1024)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=False,  # bearer tokens, no cookies
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
        if settings.is_production:
            response.headers.setdefault("Strict-Transport-Security", "max-age=63072000; includeSubDomains")
            # The API serves JSON and downloads only, never pages (the docs UI is off in production).
            response.headers.setdefault("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")
        return response

    app.add_middleware(RequestContextMiddleware)

    @app.get("/metrics", include_in_schema=False)
    async def metrics(request: Request) -> Response:
        """Prometheus metrics; only served when METRICS_TOKEN is set, and only with that token."""
        token = settings.metrics_token
        given = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
        if not token or not hmac.compare_digest(given.encode(), token.encode()):
            return Response(status_code=404)
        return Response(render_metrics(), media_type=CONTENT_TYPE_LATEST)

    for router in (
        meta.router,
        auth.router,
        users.router,
        conversations.router,
        knowledge_routes.router,
        files.router,
        projects.router,
        memories.router,
        voice.router,
        devices.router,
        updates.router,
        realtime.router,
        admin.router,
    ):
        app.include_router(router, prefix=settings.api_prefix)
    return app


app = create_app()
