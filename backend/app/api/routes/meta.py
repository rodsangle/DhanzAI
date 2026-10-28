from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.deps import CurrentUser, OrchestratorDep, SettingsDep
from app.schemas import ModelOut, ModelsResponse
from dhanz_ai import GREETING

router = APIRouter(tags=["meta"])


@router.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@router.get("/health/ready")
async def ready(request: Request, orchestrator: OrchestratorDep) -> JSONResponse:
    db_ok = True
    try:
        async with request.app.state.sessionmaker() as db:
            await db.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001 - readiness must report, not raise
        db_ok = False
    providers = sorted(name for name, p in orchestrator.providers.items() if p.is_configured())
    ok = db_ok and bool(providers)
    return JSONResponse(
        {"status": "ok" if ok else "degraded", "database": db_ok, "providers": providers},
        status_code=200 if ok else 503,
    )


@router.get("/models", response_model=ModelsResponse)
async def list_models(_: CurrentUser, orchestrator: OrchestratorDep, settings: SettingsDep) -> ModelsResponse:
    return ModelsResponse(
        models=[
            ModelOut(
                key=m.key,
                provider=m.provider,
                model=m.model,
                display_name=m.display_name,
                capabilities=sorted(c.value for c in m.capabilities),
                cost_tier=int(m.cost_tier),
                context_window=m.context_window,
            )
            for m in orchestrator.available_models()
        ],
        default_policy=settings.default_routing_policy,
        greeting=GREETING,
    )
