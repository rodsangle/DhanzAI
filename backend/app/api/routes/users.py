from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentUser, DbDep, OrchestratorDep, current_session, parse_uuid
from app.core import rate_limit
from app.core.security import hash_password_async, verify_password_async
from app.db.base import utcnow
from app.models import (
    Conversation,
    CreditAccount,
    CreditEntry,
    GenerationJob,
    GitHubConnection,
    KnowledgeDocument,
    MediaDeletion,
    Memory,
    Project,
    RefreshToken,
    User,
)
from app.schemas import (
    ChangePasswordRequest,
    ConversationDetail,
    DeleteAccountRequest,
    DocumentOut,
    MemoryOut,
    ProjectOut,
    SessionOut,
    UserOut,
    UserUpdate,
)
from app.services import audit, files_service
from app.services.auth_service import revoke_family, revoke_user_sessions

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser) -> User:
    return user


@router.patch("/me", response_model=UserOut)
async def update_me(body: UserUpdate, user: CurrentUser, db: DbDep, orchestrator: OrchestratorDep) -> User:
    if body.display_name is not None:
        user.display_name = body.display_name.strip() or user.display_name
    if body.preferred_model is not None:
        if body.preferred_model == "":
            user.preferred_model = None
        else:
            provider, _, model = body.preferred_model.partition(":")
            if orchestrator.find_model(provider, model) is None:
                raise HTTPException(422, "Unknown or unavailable model")
            user.preferred_model = body.preferred_model
    if body.routing_policy is not None:
        user.routing_policy = body.routing_policy
    if body.auto_index_web is not None:
        user.auto_index_web = body.auto_index_web
    if body.memory_enabled is not None:
        user.memory_enabled = body.memory_enabled
    if body.retention_days is not None:
        user.retention_days = body.retention_days or None  # 0 = keep forever
    user.updated_at = utcnow()
    await db.commit()
    return user


@router.post("/me/password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(body: ChangePasswordRequest, request: Request, user: CurrentUser, db: DbDep) -> Response:
    """Change the password and sign out every other device."""
    await rate_limit.enforce(f"password:{user.id}", 5)
    if not await verify_password_async(body.current_password, user.password_hash):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Current password is incorrect")
    if body.new_password == body.current_password:
        raise HTTPException(422, "Choose a password different from the current one")
    user.password_hash = await hash_password_async(body.new_password)
    user.updated_at = utcnow()
    ended = await revoke_user_sessions(db, user.id, keep=current_session(request))
    audit.record(
        db, "user.password_changed", user_id=user.id, ip=rate_limit.client_ip(request), detail={"sessions_ended": ended}
    )
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me/sessions", response_model=list[SessionOut])
async def list_sessions(request: Request, user: CurrentUser, db: DbDep) -> list[SessionOut]:
    """Devices signed in to this account (one per refresh-token family)."""
    now = utcnow()
    active = list(
        await db.scalars(
            select(RefreshToken).where(
                RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None), RefreshToken.expires_at > now
            )
        )
    )
    families = [t.family_id for t in active]
    started = (
        dict(
            (
                await db.execute(
                    select(RefreshToken.family_id, func.min(RefreshToken.created_at))
                    .where(RefreshToken.family_id.in_(families))
                    .group_by(RefreshToken.family_id)
                )
            ).all()
        )
        if families
        else {}
    )
    current = current_session(request)
    sessions = [
        SessionOut(
            id=t.family_id,
            user_agent=t.user_agent,
            created_at=started.get(t.family_id, t.created_at),
            last_used_at=t.created_at,  # a new refresh token is issued every time the app refreshes
            expires_at=t.expires_at,
            current=t.family_id == current,
        )
        for t in active
    ]
    return sorted(sessions, key=lambda s: (not s.current, -s.last_used_at.timestamp()))


@router.delete("/me/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_session(session_id: str, request: Request, user: CurrentUser, db: DbDep) -> Response:
    family = parse_uuid(session_id)
    owner = await db.scalar(select(RefreshToken.user_id).where(RefreshToken.family_id == family).limit(1))
    if owner != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")
    await revoke_family(db, family)
    audit.record(db, "user.session_revoked", user_id=user.id, ip=rate_limit.client_ip(request))
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/me/sessions/revoke-others")
async def revoke_other_sessions(request: Request, user: CurrentUser, db: DbDep) -> dict:
    """Sign out everywhere except this device."""
    ended = await revoke_user_sessions(db, user.id, keep=current_session(request))
    audit.record(
        db, "user.sessions_revoked", user_id=user.id, ip=rate_limit.client_ip(request), detail={"count": ended}
    )
    await db.commit()
    return {"ended": ended}


@router.get("/me/export")
async def export_my_data(user: CurrentUser, db: DbDep) -> dict:
    """Machine-readable copy of everything stored about the user (data portability)."""
    convs = await db.scalars(
        select(Conversation).where(Conversation.user_id == user.id).options(selectinload(Conversation.messages))
    )
    docs = await db.scalars(select(KnowledgeDocument).where(KnowledgeDocument.user_id == user.id))
    projects = await db.scalars(select(Project).where(Project.user_id == user.id))
    memories = await db.scalars(select(Memory).where(Memory.user_id == user.id))
    creations = list(await db.scalars(select(GenerationJob).where(GenerationJob.user_id == user.id)))
    ledger = await db.scalars(select(CreditEntry).where(CreditEntry.user_id == user.id))
    account = await db.get(CreditAccount, user.id)
    github = await db.get(GitHubConnection, user.id)
    from app.api.routes.creative import output

    return {
        "exported_at": utcnow().isoformat(),
        "github_connection": None if github is None else {"login": github.login, "repositories": github.repositories},
        "user": UserOut.model_validate(user).model_dump(mode="json"),
        "conversations": [ConversationDetail.model_validate(c).model_dump(mode="json") for c in convs],
        "knowledge_documents": [DocumentOut.model_validate(d).model_dump(mode="json") for d in docs],
        "projects": [ProjectOut.model_validate(p).model_dump(mode="json") for p in projects],
        "memories": [MemoryOut.model_validate(m).model_dump(mode="json") for m in memories],
        "creations": [output(job) for job in creations if not job.deleted],
        "creative_credits": None
        if account is None
        else {
            "balance": account.balance,
            "reserved": account.reserved,
            "consumed": account.consumed,
            "monthly_allowance": account.monthly_allowance,
            "allowance_month": account.allowance_month,
        },
        "creative_credit_history": [
            {"kind": entry.kind, "amount": entry.amount, "created_at": entry.created_at.isoformat()} for entry in ledger
        ],
        "note": "Uploaded files can be downloaded individually from the knowledge library.",
    }


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
async def delete_me(body: DeleteAccountRequest, request: Request, user: CurrentUser, db: DbDep) -> Response:
    """Permanently delete the account and all conversations (cascades in the database)."""
    if not await verify_password_async(body.password, user.password_hash):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Password is incorrect")
    audit.record(db, "user.deleted", user_id=None, ip=rate_limit.client_ip(request), detail={"user_id": str(user.id)})
    uploads = list(
        await db.scalars(
            select(KnowledgeDocument).where(
                KnowledgeDocument.user_id == user.id, KnowledgeDocument.storage_key.is_not(None)
            )
        )
    )
    creations = await db.scalars(select(GenerationJob).where(GenerationJob.user_id == user.id))
    for creation in creations:
        for key in (creation.media_key, creation.reference_key):
            if key:
                db.add(MediaDeletion(key=key, kind="object"))
        if creation.provider_job_id and creation.kind == "video" and creation.status in ("queued", "processing"):
            db.add(MediaDeletion(key=creation.provider_job_id, kind="runway_task"))
    await db.flush()
    await db.delete(user)
    await db.commit()
    # Stored file bytes live outside the database: remove them too.
    await files_service.delete_document_files(request.app.state.files, uploads)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
