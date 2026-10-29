"""ORM models. Import everything here so Alembic sees the full metadata."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    false,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, Embedding, UTCDateTime, utcnow


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str | None] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(100))
    role: Mapped[str] = mapped_column(String(20), default="user")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    preferred_model: Mapped[str | None] = mapped_column(String(200))
    routing_policy: Mapped[str] = mapped_column(String(20), default="balanced")
    # Save pages read during web research to the user's knowledge library.
    auto_index_web: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    # Long-term memory is opt-in: nothing is remembered unless the user turns it on.
    memory_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    # Delete conversations not touched for this many days (None = keep until the user deletes them).
    retention_days: Mapped[int | None] = mapped_column(Integer)
    # Set when the user proved they own the address (emailed code, or Google/Apple said so).
    email_verified_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    # Two-factor authentication: the TOTP secret, encrypted (see app.core.crypto). Set but not
    # enabled while the user is still scanning the QR code.
    mfa_secret: Mapped[str | None] = mapped_column(String(255))
    mfa_enabled_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    # Last accepted TOTP time step: a code cannot be used twice.
    mfa_last_step: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)

    conversations: Mapped[list[Conversation]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )

    @property
    def email_verified(self) -> bool:
        return self.email_verified_at is not None

    @property
    def mfa_enabled(self) -> bool:
        return self.mfa_enabled_at is not None

    @property
    def has_password(self) -> bool:
        return self.password_hash is not None


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    # Tokens from one login share a family; reuse of a rotated token revokes the whole family.
    family_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    user_agent: Mapped[str | None] = mapped_column(String(300))


class Conversation(Base):
    __tablename__ = "conversations"
    __table_args__ = (Index("ix_conversations_user_updated", "user_id", "updated_at"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(200), default="New conversation")
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"), index=True)
    # Temporary chats: no memory, no library auto-indexing, deleted automatically after TEMPORARY_CHAT_HOURS.
    temporary: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    user: Mapped[User] = relationship(back_populates="conversations")
    messages: Mapped[list[Message]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Message.position",
    )


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (UniqueConstraint("conversation_id", "position", name="uq_messages_conversation_position"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    role: Mapped[str] = mapped_column(String(20))  # user | assistant
    content: Mapped[str] = mapped_column(Text, default="")
    # streaming | complete | error | stopped
    status: Mapped[str] = mapped_column(String(20), default="complete")
    provider: Mapped[str | None] = mapped_column(String(50))
    model: Mapped[str | None] = mapped_column(String(200))
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(Text)
    # Numbered sources the reply was grounded on: [{n, title, url, site_name, published_at, retrieved_at, origin}]
    citations: Mapped[list | None] = mapped_column(JSON)
    # Files attached to a user message: [{id, filename, kind, mime_type}]
    attachments: Mapped[list | None] = mapped_column(JSON)
    # Tools used for an assistant reply: [{tool, summary, error, action}]
    tool_activity: Mapped[list | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)

    conversation: Mapped[Conversation] = relationship(back_populates="messages")


class Project(Base):
    """A workspace grouping conversations and documents, with optional standing instructions."""

    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text)
    instructions: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Memory(Base):
    """Something the user approved Dhanz to remember across conversations."""

    __tablename__ = "memories"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    content: Mapped[str] = mapped_column(Text)
    # manual (typed in Settings) | chat ("remember that …" in a conversation)
    source: Mapped[str] = mapped_column(String(20), default="manual")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class KnowledgeDocument(Base):
    """A source in a user's private knowledge library: a web page (kind "web") or an uploaded file ("file")."""

    __tablename__ = "knowledge_documents"
    __table_args__ = (UniqueConstraint("user_id", "url", name="uq_knowledge_documents_user_url"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(20), default="web")
    url: Mapped[str] = mapped_column(String(2048))
    title: Mapped[str] = mapped_column(String(300))
    site_name: Mapped[str | None] = mapped_column(String(200))
    author: Mapped[str | None] = mapped_column(String(200))
    published_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    retrieved_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    content: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64))
    # manual (user added a URL) | research (saved while answering) | upload (user uploaded a file)
    added_via: Mapped[str] = mapped_column(String(20), default="manual")
    project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"), index=True)
    # Uploaded files only:
    file_type: Mapped[str | None] = mapped_column(String(20))  # pdf | docx | xlsx | pptx | csv | text | code | image
    mime_type: Mapped[str | None] = mapped_column(String(120))
    size_bytes: Mapped[int | None] = mapped_column(Integer)
    storage_key: Mapped[str | None] = mapped_column(String(80))
    scan_status: Mapped[str | None] = mapped_column(String(20))  # clean | not_scanned
    notes: Mapped[str | None] = mapped_column(Text)  # extraction notes, e.g. scanned PDF without text
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    chunks: Mapped[list[KnowledgeChunk]] = relationship(
        back_populates="document", cascade="all, delete-orphan", passive_deletes=True, order_by="KnowledgeChunk.ordinal"
    )


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("knowledge_documents.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    ordinal: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float] | None] = mapped_column(Embedding)
    embedding_model: Mapped[str | None] = mapped_column(String(200))

    document: Mapped[KnowledgeDocument] = relationship(back_populates="chunks")


class Device(Base):
    """A phone/tablet that receives push notifications for a user."""

    __tablename__ = "devices"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    platform: Mapped[str] = mapped_column(String(20))  # android | ios
    token: Mapped[str] = mapped_column(String(512), unique=True)
    app_version: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Reminder(Base):
    """Set by the user or by Dhanz's create_reminder tool; announced by push notification when due."""

    __tablename__ = "reminders"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    text: Mapped[str] = mapped_column(String(500))
    due_at: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    # Events: how long it lasts and where (used for the calendar export).
    duration_minutes: Mapped[int | None] = mapped_column(Integer)
    location: Mapped[str | None] = mapped_column(String(200))
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("conversations.id", ondelete="SET NULL"))
    notified_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    done_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class PasswordResetToken(Base):
    """One-time code emailed for a password reset; only its SHA-256 is stored."""

    __tablename__ = "password_reset_tokens"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    code_hash: Mapped[str] = mapped_column(String(64))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)
    used_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class VerificationCode(Base):
    """One-time code emailed to the user (purpose "email": confirm the address). Only its SHA-256 is stored."""

    __tablename__ = "verification_codes"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    purpose: Mapped[str] = mapped_column(String(20))
    code_hash: Mapped[str] = mapped_column(String(64))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)
    used_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class MfaRecoveryCode(Base):
    """Single-use backup code for signing in without the authenticator app (SHA-256 only)."""

    __tablename__ = "mfa_recovery_codes"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    code_hash: Mapped[str] = mapped_column(String(64))
    used_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class OAuthIdentity(Base):
    """A Google or Apple account linked to a DHANZ AI account (the provider's stable subject id)."""

    __tablename__ = "oauth_identities"
    __table_args__ = (UniqueConstraint("provider", "subject", name="uq_oauth_identities_provider_subject"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(20))
    subject: Mapped[str] = mapped_column(String(255))
    email: Mapped[str | None] = mapped_column(String(320))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    last_used_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    # Kept (with user_id nulled) after account deletion so security events stay traceable.
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    action: Mapped[str] = mapped_column(String(64), index=True)
    ip_address: Mapped[str | None] = mapped_column(String(64))
    detail: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)


__all__ = [
    "AuditLog",
    "Base",
    "Conversation",
    "Device",
    "KnowledgeChunk",
    "KnowledgeDocument",
    "PasswordResetToken",
    "Reminder",
    "Memory",
    "Message",
    "MfaRecoveryCode",
    "OAuthIdentity",
    "Project",
    "RefreshToken",
    "User",
    "VerificationCode",
]
