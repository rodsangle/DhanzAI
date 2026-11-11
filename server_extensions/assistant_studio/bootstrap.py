import asyncio
import contextlib
from contextlib import asynccontextmanager

from . import builder
from .routes import router


def install(app):
    app.include_router(router, prefix=app.state.settings.api_prefix)
    from .csv_totals_tools import install as _install_csv_totals_tools
    _install_csv_totals_tools(app)
    from .app_building_models import install as _install_app_building_models
    _install_app_building_models(app)
    # Keep the existing capability report, adding only the implemented workspace.
    from app.services import capabilities_service

    old_report = capabilities_service.report
    if not getattr(old_report, "_studio_wrapped", False):

        async def report(db, user, settings, *args, **kwargs):
            result = await old_report(db, user, settings, *args, **kwargs)
            configured = bool(
                settings.openai_api_key
                and settings.openai_base_url.rstrip("/") == "https://api.openai.com/v1"
                and user.routing_policy != "local_only"
            )
            for item in result.get("capabilities", []):
                if item.get("name") == "Coding workspace and OpenAI Codex integration":
                    item.update(
                        status="available" if configured else "requires_connection",
                        details="App/agent project files, private builds and sandboxed static previews. Uses configured OpenAI API models; "
                        "Codex is offered only when its API models are listed. No terminal execution or automatic deployment.",
                    )
            # A listed API model is not proof that a paid generation succeeded.
            from sqlalchemy import select

            from .models import BuilderProject

            verified = await db.scalar(
                select(BuilderProject.id)
                .where(
                    BuilderProject.user_id == user.id,
                    BuilderProject.status == "complete",
                    BuilderProject.model.contains("codex"),
                )
                .limit(1)
            )
            result["codex_connected"] = bool(configured and verified)
            return result

        report._studio_wrapped = True
        capabilities_service.report = report
    original = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(application):
        async with original(application):
            task = asyncio.create_task(builder.worker(application.state.sessionmaker, application.state.settings))
            try:
                yield
            finally:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task

    app.router.lifespan_context = lifespan

_DHANZ_APP_MODELS_VERSION = 1

_DHANZ_CSV_TOTALS_VERSION = 1
