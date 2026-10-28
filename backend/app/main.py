from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import auth, conversations, files, memories, meta, projects, realtime, users, voice
from app.api.routes import knowledge as knowledge_routes
from app.core.config import Settings, get_settings
from app.db.session import make_engine, make_sessionmaker
from app.services.files_service import build_files_runtime
from app.services.knowledge_service import KnowledgeRuntime, build_knowledge_runtime, wait_for_background_indexing
from app.services.stt import SpeechToText, build_stt
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


def create_app(
    settings: Settings | None = None,
    orchestrator: Orchestrator | None = None,
    knowledge: KnowledgeRuntime | None = None,
    stt: SpeechToText | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    logging.basicConfig(level=settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        engine = make_engine(settings.database_url)
        app.state.engine = engine
        app.state.sessionmaker = make_sessionmaker(engine)
        app.state.orchestrator = orchestrator or build_orchestrator(settings)
        app.state.knowledge = knowledge or build_knowledge_runtime(settings)
        app.state.files = build_files_runtime(settings)
        app.state.stt = stt if stt is not None else build_stt(settings)
        yield
        await wait_for_background_indexing()
        for provider in app.state.orchestrator.providers.values():
            await provider.aclose()
        await app.state.knowledge.aclose()
        if app.state.stt is not None:
            await app.state.stt.aclose()
        await engine.dispose()

    app = FastAPI(
        title="DHANZ AI API",
        version="0.3.0",
        description="Backend for the DHANZ AI assistant. Your World. Your Knowledge. Your AI.",
        lifespan=lifespan,
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None,
        openapi_url=None if settings.is_production else "/openapi.json",
    )
    app.state.settings = settings

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=False,  # bearer tokens, no cookies
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        if settings.is_production:
            response.headers.setdefault("Strict-Transport-Security", "max-age=63072000; includeSubDomains")
        return response

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
        realtime.router,
    ):
        app.include_router(router, prefix=settings.api_prefix)
    return app


app = create_app()
