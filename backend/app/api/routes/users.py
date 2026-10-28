from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentUser, DbDep, OrchestratorDep
from app.core import rate_limit
from app.core.security import verify_password
from app.db.base import utcnow
from app.models import Conversation, User
from app.schemas import ConversationDetail, DeleteAccountRequest, UserOut, UserUpdate
from app.services import audit

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
    user.updated_at = utcnow()
    await db.commit()
    return user


@router.get("/me/export")
async def export_my_data(user: CurrentUser, db: DbDep) -> dict:
    """Machine-readable copy of everything stored about the user (data portability)."""
    convs = await db.scalars(
        select(Conversation).where(Conversation.user_id == user.id).options(selectinload(Conversation.messages))
    )
    return {
        "exported_at": utcnow().isoformat(),
        "user": UserOut.model_validate(user).model_dump(mode="json"),
        "conversations": [ConversationDetail.model_validate(c).model_dump(mode="json") for c in convs],
    }


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
async def delete_me(body: DeleteAccountRequest, request: Request, user: CurrentUser, db: DbDep) -> Response:
    """Permanently delete the account and all conversations (cascades in the database)."""
    if not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Password is incorrect")
    audit.record(db, "user.deleted", user_id=None, ip=rate_limit.client_ip(request), detail={"user_id": str(user.id)})
    await db.delete(user)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
