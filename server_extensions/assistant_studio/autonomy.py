"""Account-scoped routine decision preferences; never grants external permissions."""

import functools
import sys
from types import SimpleNamespace

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from app.api.deps import CurrentUser, DbDep
from app.models import AssistantSkill

NAME = "dhanz-autonomy"
POLICY = (
    "Use discretion for routine decisions within the task I requested. Proceed with reasonable defaults "
    "instead of asking permission to plan, draft, inspect, format, generate code or make reversible project edits. "
    "Reuse details already supplied, choose a focused first milestone and explain important assumptions briefly. "
    "Respect explicit task instructions over these defaults. Ask only when a missing target, credential, "
    "material ambiguity or consequential choice blocks safe progress. Read only relevant skills, then act; "
    "do not spend the whole reply reading every workflow stage. Queue long app/coding work using available "
    "background tools and report actual job status instead of repeatedly polling or promising a later message. "
    "Do not start new builds for acknowledgements, status requests or purely informational questions. "
    "Preserve original files and unrelated features. Use existing connected GitHub/server tools within their "
    "actual account scope and standing grants. This preference is not a new permission, credential, merge, "
    "deployment, purchase or destructive-action grant. If required authorization is absent, prepare the work "
    "and request the specific missing decision. Honor existing explicit authorization without asking again. "
    "Do not invent access, completed actions, tests, downloads or deployment results. Use bounded steps and "
    "at most the existing one automatic coding repair; do not retry authentication, quota or access failures "
    "automatically. Stop and report a concrete blocker when further progress requires user input."
)
router = APIRouter(prefix="/assistant-studio", tags=["assistant-studio"])


async def enabled(db, user_id):
    skill = await db.scalar(
        select(AssistantSkill).where(AssistantSkill.user_id == user_id, AssistantSkill.name == NAME)
    )
    return bool(skill and skill.enabled)


class Preference(BaseModel):
    enabled: bool


@router.get("/autonomy")
async def get_preference(user: CurrentUser, db: DbDep):
    return {"enabled": await enabled(db, user.id)}


@router.put("/autonomy")
async def set_preference(body: Preference, user: CurrentUser, db: DbDep):
    from app.services.skills_service import SkillSpec, save_skill

    try:
        await save_skill(
            db,
            user.id,
            SkillSpec(
                name=NAME,
                description="Use discretion for routine chat and coding decisions within existing permissions.",
                instructions=POLICY,
                enabled=body.enabled,
            ),
        )
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None
    return {"enabled": body.enabled}


async def job_enabled(settings, job):
    if not getattr(job, "user_id", None):
        return False
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    try:
        async with async_sessionmaker(engine)() as db:
            return await enabled(db, job.user_id)
    finally:
        await engine.dispose()


def install(app):
    from . import builder

    app.include_router(router, prefix=app.state.settings.api_prefix)
    from app.services import skills_service

    old_catalog = skills_service.catalog
    if not getattr(old_catalog, "_dhanz_autonomy", False):

        @functools.wraps(old_catalog)
        async def catalog(*args, **kwargs):
            return [s for s in await old_catalog(*args, **kwargs) if s["name"] != NAME]

        catalog._dhanz_autonomy = True
        skills_service.catalog = catalog
    chat = sys.modules.get("app.services.chat_service")
    original = getattr(chat, "_turn_context", None)
    if original and not getattr(original, "_dhanz_autonomy", False):

        @functools.wraps(original)
        async def context(db, user, conv):
            result = await original(db, user, conv)
            if await enabled(db, user.id):
                result["project_instructions"] = (
                    (result.get("project_instructions") or "") + "\n\nAccount decision preference:\n" + POLICY
                )
            return result

        context._dhanz_autonomy = True
        chat._turn_context = context
    previous = builder.generate
    if not getattr(previous, "_dhanz_autonomy", False):

        @functools.wraps(previous)
        async def generate(settings, job, **kwargs):
            if getattr(job, "_dhanz_autonomy_prepared", False):
                return await previous(settings, job, **kwargs)
            if await job_enabled(settings, job):

                class JobView(SimpleNamespace):
                    def __getattr__(self, name):
                        return getattr(job, name)

                view = JobView(
                    prompt=job.prompt + "\n\nAccount decision preference:\n" + POLICY, _dhanz_autonomy_prepared=True
                )
                return await previous(settings, view, **kwargs)
            return await previous(settings, job, **kwargs)

        generate._dhanz_autonomy = True
        builder.generate = generate
