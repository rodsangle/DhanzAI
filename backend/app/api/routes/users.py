from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import delete, func, select
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentUser, DbDep, OrchestratorDep, SettingsDep, current_session, parse_uuid
from app.core import mfa, rate_limit
from app.core.security import hash_password_async, verify_password_async
from app.db.base import utcnow
from app.models import (
    Conversation,
    KnowledgeDocument,
    Memory,
    MfaRecoveryCode,
    OAuthIdentity,
    Project,
    RefreshToken,
    User,
)
from app.schemas import (
    ChangePasswordRequest,
    ConversationDetail,
    DeleteAccountRequest,
    DocumentOut,
    EmailCodeConfirm,
    IdentityOut,
    MemoryOut,
    MfaCodeRequest,
    MfaSetupOut,
    MfaSetupRequest,
    ProjectOut,
    RecoveryCodesOut,
    SessionOut,
    UserOut,
    UserUpdate,
)
from app.services import accounts, audit, files_service
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
    return {
        "exported_at": utcnow().isoformat(),
        "user": UserOut.model_validate(user).model_dump(mode="json"),
        "conversations": [ConversationDetail.model_validate(c).model_dump(mode="json") for c in convs],
        "knowledge_documents": [DocumentOut.model_validate(d).model_dump(mode="json") for d in docs],
        "projects": [ProjectOut.model_validate(p).model_dump(mode="json") for p in projects],
        "memories": [MemoryOut.model_validate(m).model_dump(mode="json") for m in memories],
        "note": "Uploaded files can be downloaded individually from the knowledge library.",
    }


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
async def delete_me(
    body: DeleteAccountRequest, request: Request, user: CurrentUser, db: DbDep, settings: SettingsDep
) -> Response:
    """Permanently delete the account and all conversations (cascades in the database).

    Confirm with the password, or for Google/Apple-only accounts by retyping the email; accounts with
    two-factor authentication also need a current code.
    """
    await rate_limit.enforce(f"delete-account:{user.id}", 5)
    if user.has_password:
        if not body.password or not await verify_password_async(body.password, user.password_hash):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Password is incorrect")
    elif (body.confirm_email or "").strip().lower() != user.email:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Type your email address to confirm")
    if user.mfa_enabled and not (
        body.mfa_code and await accounts.guarded_second_factor(db, settings, user, body.mfa_code)
    ):
        await db.commit()  # keep the consumed/failed-attempt state
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Enter a current code from your authenticator app")
    audit.record(db, "user.deleted", user_id=None, ip=rate_limit.client_ip(request), detail={"user_id": str(user.id)})
    uploads = list(
        await db.scalars(
            select(KnowledgeDocument).where(
                KnowledgeDocument.user_id == user.id, KnowledgeDocument.storage_key.is_not(None)
            )
        )
    )
    await db.delete(user)
    await db.commit()
    # Stored file bytes live outside the database: remove them too.
    await files_service.delete_document_files(request.app.state.files, uploads)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- email verification ----------------------------------------------------------------------------


@router.post("/me/email-verification", status_code=status.HTTP_202_ACCEPTED)
async def send_email_code(request: Request, user: CurrentUser, db: DbDep, settings: SettingsDep) -> dict:
    """Email a new 6-digit code that confirms the account's address."""
    mailer = request.app.state.mailer
    if mailer is None:
        raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "Email is not configured on this server")
    if user.email_verified:
        return {"detail": "Your email address is already confirmed."}
    await rate_limit.enforce(f"verify-mail:{user.id}", 3, 3600)
    await accounts.issue_email_code(db, settings, mailer, user)
    await db.commit()
    return {"detail": f"We sent a code to {user.email}."}


@router.post("/me/email-verification/confirm", response_model=UserOut)
async def confirm_email(body: EmailCodeConfirm, request: Request, user: CurrentUser, db: DbDep) -> User:
    await rate_limit.enforce(f"verify-confirm:{user.id}", 10)
    if not user.email_verified:
        if not await accounts.confirm_email_code(db, user, body.code):
            await db.commit()
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "The code is invalid or has expired. Request a new one.")
        audit.record(db, "user.email_verified", user_id=user.id, ip=rate_limit.client_ip(request))
        await db.commit()
    return user


# --- two-factor authentication ---------------------------------------------------------------------


@router.post("/me/mfa/setup", response_model=MfaSetupOut)
async def mfa_setup(body: MfaSetupRequest, user: CurrentUser, db: DbDep, settings: SettingsDep) -> MfaSetupOut:
    """Start turning on two-factor authentication: a new secret to add to an authenticator app.

    Nothing changes for sign-in until `/me/mfa/enable` receives a code from the app.
    """
    await rate_limit.enforce(f"mfa-setup:{user.id}", 5)
    if user.mfa_enabled:
        raise HTTPException(status.HTTP_409_CONFLICT, "Two-factor authentication is already on")
    if user.has_password and not (body.password and await verify_password_async(body.password, user.password_hash)):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Password is incorrect")
    secret = mfa.new_secret()
    user.mfa_secret = mfa.encrypt_secret(settings, secret)
    user.mfa_last_step = None
    await db.commit()
    return MfaSetupOut(secret=secret, otpauth_uri=mfa.provisioning_uri(secret, user.email))


@router.post("/me/mfa/enable", response_model=RecoveryCodesOut)
async def mfa_enable(
    body: MfaCodeRequest, request: Request, user: CurrentUser, db: DbDep, settings: SettingsDep
) -> RecoveryCodesOut:
    """Confirm the authenticator app works; returns ten single-use recovery codes (shown only now)."""
    await rate_limit.enforce(f"mfa-enable:{user.id}", 10)
    if user.mfa_enabled:
        raise HTTPException(status.HTTP_409_CONFLICT, "Two-factor authentication is already on")
    if user.mfa_secret is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Start the setup first")
    step = mfa.match_step(mfa.decrypt_secret(settings, user.mfa_secret), body.code)
    if step is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "That code is not correct. Check the time on your phone.")
    user.mfa_last_step = step
    user.mfa_enabled_at = utcnow()
    codes = await accounts.new_recovery_codes(db, user)
    # Sessions on other devices were opened with one factor only.
    ended = await revoke_user_sessions(db, user.id, keep=current_session(request))
    audit.record(
        db, "user.mfa_enabled", user_id=user.id, ip=rate_limit.client_ip(request), detail={"sessions_ended": ended}
    )
    await db.commit()
    return RecoveryCodesOut(recovery_codes=codes)


@router.post("/me/mfa/disable", response_model=UserOut)
async def mfa_disable(
    body: MfaCodeRequest, request: Request, user: CurrentUser, db: DbDep, settings: SettingsDep
) -> User:
    if not user.mfa_enabled:
        return user
    if await accounts.guarded_second_factor(db, settings, user, body.code) is None:
        await db.commit()
        raise HTTPException(status.HTTP_403_FORBIDDEN, "That code is not correct")
    user.mfa_secret = None
    user.mfa_enabled_at = None
    user.mfa_last_step = None
    await db.execute(delete(MfaRecoveryCode).where(MfaRecoveryCode.user_id == user.id))
    audit.record(db, "user.mfa_disabled", user_id=user.id, ip=rate_limit.client_ip(request))
    await db.commit()
    return user


@router.post("/me/mfa/recovery-codes", response_model=RecoveryCodesOut)
async def mfa_new_recovery_codes(
    body: MfaCodeRequest, request: Request, user: CurrentUser, db: DbDep, settings: SettingsDep
) -> RecoveryCodesOut:
    """Replace all recovery codes (the old ones stop working)."""
    if not user.mfa_enabled:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Two-factor authentication is off")
    if await accounts.guarded_second_factor(db, settings, user, body.code) is None:
        await db.commit()
        raise HTTPException(status.HTTP_403_FORBIDDEN, "That code is not correct")
    codes = await accounts.new_recovery_codes(db, user)
    audit.record(db, "user.mfa_recovery_codes_replaced", user_id=user.id, ip=rate_limit.client_ip(request))
    await db.commit()
    return RecoveryCodesOut(recovery_codes=codes)


@router.get("/me/mfa/recovery-codes/remaining")
async def mfa_recovery_codes_left(user: CurrentUser, db: DbDep) -> dict:
    left = await db.scalar(
        select(func.count(MfaRecoveryCode.id)).where(
            MfaRecoveryCode.user_id == user.id, MfaRecoveryCode.used_at.is_(None)
        )
    )
    return {"remaining": left or 0}


# --- Google / Apple sign-in ------------------------------------------------------------------------


@router.get("/me/identities", response_model=list[IdentityOut])
async def list_identities(user: CurrentUser, db: DbDep) -> list[OAuthIdentity]:
    return list(
        await db.scalars(
            select(OAuthIdentity).where(OAuthIdentity.user_id == user.id).order_by(OAuthIdentity.created_at)
        )
    )


@router.delete("/me/identities/{provider}", status_code=status.HTTP_204_NO_CONTENT)
async def unlink_identity(provider: str, request: Request, user: CurrentUser, db: DbDep) -> Response:
    links = list(await db.scalars(select(OAuthIdentity).where(OAuthIdentity.user_id == user.id)))
    target = [link for link in links if link.provider == provider]
    if not target:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not linked")
    if not user.has_password and len(links) == len(target):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "This is your only way to sign in. Set a password first (Forgot password on the sign-in screen).",
        )
    for link in target:
        await db.delete(link)
    audit.record(
        db, "user.identity_unlinked", user_id=user.id, ip=rate_limit.client_ip(request), detail={"provider": provider}
    )
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
