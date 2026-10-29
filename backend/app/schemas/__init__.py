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


def _check_strength(v: str) -> str:
    if v.isdigit() or v.isalpha() or len(set(v)) < 5:
        raise ValueError("password must mix letters with digits or symbols")
    return v


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
        return _check_strength(v)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=10, max_length=128)

    @field_validator("new_password")
    @classmethod
    def _strength(cls, v: str) -> str:
        return _check_strength(v)


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    email: EmailStr
    code: str = Field(min_length=6, max_length=20)
    new_password: str = Field(min_length=10, max_length=128)

    @field_validator("new_password")
    @classmethod
    def _strength(cls, v: str) -> str:
        return _check_strength(v)


class AuthOptions(BaseModel):
    registration_open: bool
    password_reset: bool
    # Codes are emailed to confirm new addresses; when required, chats stay locked until confirmed.
    email_verification: bool = False
    email_verification_required: bool = False
    # The OAuth client ID apps request Google ID tokens for (Android "serverClientId"), or null.
    google_client_id: str | None = None
    apple_sign_in: bool = False


class MfaChallenge(BaseModel):
    """Returned instead of tokens when the account has two-factor authentication."""

    mfa_required: Literal[True] = True
    mfa_token: str
    expires_in: int


class MfaVerifyRequest(BaseModel):
    mfa_token: str = Field(min_length=20, max_length=2000)
    code: str = Field(min_length=6, max_length=20, description="Authenticator code or a recovery code")


class OAuthSignInRequest(BaseModel):
    id_token: str = Field(min_length=20, max_length=8192)
    nonce: str | None = Field(default=None, max_length=200)
    # Apple shares the user's name only with the app, on the very first sign-in.
    display_name: str | None = Field(default=None, max_length=100)


class EmailCodeConfirm(BaseModel):
    code: str = Field(min_length=6, max_length=12)


class MfaSetupRequest(BaseModel):
    password: str | None = Field(default=None, max_length=128, description="Required when the account has one")


class MfaSetupOut(BaseModel):
    secret: str
    otpauth_uri: str


class MfaCodeRequest(BaseModel):
    code: str = Field(min_length=6, max_length=20)


class RecoveryCodesOut(BaseModel):
    recovery_codes: list[str]


class IdentityOut(ORM):
    provider: str
    email: str | None
    created_at: datetime
    last_used_at: datetime


class SessionOut(BaseModel):
    id: uuid.UUID
    user_agent: str | None
    created_at: datetime
    last_used_at: datetime
    expires_at: datetime
    current: bool


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
    retention_days: int | None = None
    email_verified: bool = True
    mfa_enabled: bool = False
    has_password: bool = True
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
    retention_days: Literal[0, 7, 30, 90, 365] | None = Field(
        default=None, description="Auto-delete conversations idle this many days; 0 keeps them forever"
    )


class DeleteAccountRequest(BaseModel):
    # Accounts that sign in with Google/Apple only have no password: they retype their email instead.
    password: str | None = Field(default=None, min_length=1, max_length=128)
    confirm_email: str | None = Field(default=None, max_length=320)
    mfa_code: str | None = Field(default=None, max_length=20)


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
    tool_activity: list[dict] | None = None
    created_at: datetime


class ConversationCreate(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    project_id: uuid.UUID | None = None
    temporary: bool = False


class ConversationUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    pinned: bool | None = None
    project_id: uuid.UUID | None = Field(default=None, description="Move to a project; send null to remove")


class ConversationOut(ORM):
    id: uuid.UUID
    title: str
    pinned: bool
    project_id: uuid.UUID | None = None
    temporary: bool = False
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
    client_time: str | None = Field(
        default=None, max_length=40, description="Device time with UTC offset (ISO 8601), for dates and reminders"
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
    web: bool | None = None
    client_time: str | None = Field(default=None, max_length=40)


class ReminderCreate(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    due_at: datetime
    duration_minutes: int | None = Field(default=None, ge=1, le=20160)
    location: str | None = Field(default=None, max_length=200)

    @field_validator("due_at")
    @classmethod
    def _aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("due_at needs a UTC offset, e.g. 2026-11-02T09:00:00+01:00")
        return v


class ReminderUpdate(BaseModel):
    text: str | None = Field(default=None, min_length=1, max_length=500)
    due_at: datetime | None = None
    done: bool | None = None

    @field_validator("due_at")
    @classmethod
    def _aware(cls, v: datetime | None) -> datetime | None:
        if v is not None and v.tzinfo is None:
            raise ValueError("due_at needs a UTC offset")
        return v


class ReminderOut(ORM):
    id: uuid.UUID
    text: str
    due_at: datetime
    duration_minutes: int | None
    location: str | None
    conversation_id: uuid.UUID | None
    notified_at: datetime | None
    done_at: datetime | None
    created_at: datetime


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
