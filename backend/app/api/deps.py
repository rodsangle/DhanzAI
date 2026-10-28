from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.security import InvalidTokenError, decode_access_token
from app.models import User
from app.services.knowledge_service import KnowledgeRuntime
from dhanz_ai import Orchestrator

_bearer = HTTPBearer(auto_error=False)


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_sessionmaker(request: Request) -> async_sessionmaker[AsyncSession]:
    return request.app.state.sessionmaker


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.sessionmaker() as session:
        yield session


def get_orchestrator(request: Request) -> Orchestrator:
    return request.app.state.orchestrator


def get_knowledge(request: Request) -> KnowledgeRuntime:
    return request.app.state.knowledge


SettingsDep = Annotated[Settings, Depends(get_settings)]
KnowledgeDep = Annotated[KnowledgeRuntime, Depends(get_knowledge)]
DbDep = Annotated[AsyncSession, Depends(get_db)]
OrchestratorDep = Annotated[Orchestrator, Depends(get_orchestrator)]

_UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Not authenticated",
    headers={"WWW-Authenticate": "Bearer"},
)


async def user_from_token(db: AsyncSession, settings: Settings, token: str) -> User:
    try:
        user_id = decode_access_token(settings, token)
    except InvalidTokenError:
        raise _UNAUTHORIZED from None
    user = await db.get(User, user_id)
    if user is None or not user.is_active:
        raise _UNAUTHORIZED
    return user


async def get_current_user(
    db: DbDep,
    settings: SettingsDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> User:
    if credentials is None:
        raise _UNAUTHORIZED
    return await user_from_token(db, settings, credentials.credentials)


CurrentUser = Annotated[User, Depends(get_current_user)]


def parse_uuid(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found") from None
