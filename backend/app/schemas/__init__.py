"""Request/response schemas (the public API contract)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

RoutingPolicyName = Literal["balanced", "cheapest", "best", "local_first"]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- auth -----------------------------------------------------------------


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)
    display_name: str = Field(min_length=1, max_length=100)

    @field_validator("display_name")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("display_name must not be blank")
        return v

    @field_validator("password")
    @classmethod
    def _strength(cls, v: str) -> str:
        if v.isdigit() or v.isalpha() or len(set(v)) < 5:
            raise ValueError("password must mix letters with digits or symbols")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=20, max_length=200)


class UserOut(ORM):
    id: uuid.UUID
    email: str
    display_name: str
    role: str
    preferred_model: str | None
    routing_policy: str
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"  # noqa: S105
    expires_in: int
    user: UserOut


class UserUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=100)
    preferred_model: str | None = Field(default=None, max_length=200, description="'provider:model' or '' to clear")
    routing_policy: RoutingPolicyName | None = None


class DeleteAccountRequest(BaseModel):
    password: str = Field(min_length=1, max_length=128)


# --- models ---------------------------------------------------------------


class ModelOut(BaseModel):
    key: str
    provider: str
    model: str
    display_name: str
    capabilities: list[str]
    cost_tier: int
    context_window: int


class ModelsResponse(BaseModel):
    models: list[ModelOut]
    default_policy: str
    greeting: str


# --- conversations --------------------------------------------------------


class MessageOut(ORM):
    id: uuid.UUID
    role: str
    content: str
    status: str
    provider: str | None
    model: str | None
    input_tokens: int | None
    output_tokens: int | None
    error: str | None
    created_at: datetime


class ConversationCreate(BaseModel):
    title: str | None = Field(default=None, max_length=200)


class ConversationUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    pinned: bool | None = None


class ConversationOut(ORM):
    id: uuid.UUID
    title: str
    pinned: bool
    created_at: datetime
    updated_at: datetime


class ConversationDetail(ConversationOut):
    messages: list[MessageOut]


class ConversationList(BaseModel):
    items: list[ConversationOut]
    total: int


class SendMessageRequest(BaseModel):
    content: str = Field(min_length=1)
    provider: str | None = Field(default=None, max_length=50)
    model: str | None = Field(default=None, max_length=200)
    edit_message_id: uuid.UUID | None = Field(
        default=None, description="Replace this user message (and drop everything after it) before sending"
    )

    @field_validator("content")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("content must not be blank")
        return v


class RegenerateRequest(BaseModel):
    provider: str | None = Field(default=None, max_length=50)
    model: str | None = Field(default=None, max_length=200)
