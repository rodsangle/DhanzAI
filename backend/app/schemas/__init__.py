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
    auto_index_web: bool
    memory_enabled: bool
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
    auto_index_web: bool | None = None
    memory_enabled: bool | None = None


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


class Features(BaseModel):
    web_search: bool
    semantic_search: bool
    speech_to_text: bool = False
    malware_scanning: bool = False
    vision: bool = False
    max_upload_mb: int = 20
    push_notifications: bool = False


class ModelsResponse(BaseModel):
    models: list[ModelOut]
    default_policy: str
    greeting: str
    features: Features


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
    citations: list[dict] | None = None
    attachments: list[dict] | None = None
    created_at: datetime


class ConversationCreate(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    project_id: uuid.UUID | None = None


class ConversationUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    pinned: bool | None = None
    project_id: uuid.UUID | None = Field(default=None, description="Move to a project; send null to remove")


class ConversationOut(ORM):
    id: uuid.UUID
    title: str
    pinned: bool
    project_id: uuid.UUID | None = None
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
    web: bool | None = Field(default=None, description="Web research: true always, false never, null automatic")
    attachment_ids: list[uuid.UUID] = Field(default_factory=list, max_length=20)

    @field_validator("content")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("content must not be blank")
        return v


class RegenerateRequest(BaseModel):
    provider: str | None = Field(default=None, max_length=50)
    model: str | None = Field(default=None, max_length=200)
    web: bool | None = None


# --- knowledge library ----------------------------------------------------


class AddDocumentRequest(BaseModel):
    url: str = Field(min_length=8, max_length=2048)
    project_id: uuid.UUID | None = None


class MoveDocumentRequest(BaseModel):
    project_id: uuid.UUID | None


class DocumentOut(ORM):
    id: uuid.UUID
    kind: str
    url: str
    title: str
    site_name: str | None
    author: str | None
    published_at: datetime | None
    retrieved_at: datetime
    added_via: str
    project_id: uuid.UUID | None = None
    file_type: str | None = None
    mime_type: str | None = None
    size_bytes: int | None = None
    scan_status: str | None = None
    notes: str | None = None
    created_at: datetime


class DocumentDetail(DocumentOut):
    content: str
    chunk_count: int


class DocumentList(BaseModel):
    items: list[DocumentOut]
    total: int


class LibraryHit(BaseModel):
    document_id: uuid.UUID
    title: str
    url: str
    site_name: str | None
    snippet: str


# --- projects -------------------------------------------------------------


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    instructions: str | None = Field(default=None, max_length=8000, description="Standing instructions for Dhanz")


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    instructions: str | None = Field(default=None, max_length=8000)


class ProjectOut(ORM):
    id: uuid.UUID
    name: str
    description: str | None
    instructions: str | None
    created_at: datetime
    updated_at: datetime


class ProjectDetail(ProjectOut):
    conversation_count: int
    document_count: int


# --- memory ---------------------------------------------------------------


class MemoryCreate(BaseModel):
    content: str = Field(min_length=1, max_length=1000)


class MemoryOut(ORM):
    id: uuid.UUID
    content: str
    source: str
    created_at: datetime
    updated_at: datetime


# --- voice ----------------------------------------------------------------


class TranscriptionOut(BaseModel):
    text: str


# --- devices & updates ----------------------------------------------------


class DeviceRegister(BaseModel):
    platform: Literal["android", "ios"]
    token: str = Field(min_length=10, max_length=512)
    app_version: str | None = Field(default=None, max_length=40)


class DeviceUnregister(BaseModel):
    token: str = Field(min_length=10, max_length=512)


class UpdateInfo(BaseModel):
    platform: str
    current_version: str
    latest_version: str | None
    update_available: bool
    mandatory: bool = False
    url: str | None = None
    sha256: str | None = None
    notes: str | None = None
