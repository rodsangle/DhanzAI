"""ORM models. Import everything here so Alembic sees the full metadata."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, ForeignKey, Index, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UTCDateTime, utcnow


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
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)

    conversations: Mapped[list[Conversation]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )


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
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    conversation: Mapped[Conversation] = relationship(back_populates="messages")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    # Kept (with user_id nulled) after account deletion so security events stay traceable.
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    action: Mapped[str] = mapped_column(String(64), index=True)
    ip_address: Mapped[str | None] = mapped_column(String(64))
    detail: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)


__all__ = ["AuditLog", "Base", "Conversation", "Message", "RefreshToken", "User"]
