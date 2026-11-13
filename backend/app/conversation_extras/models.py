from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UTCDateTime, utcnow


class ConversationArchive(Base):
    """A conversation the user archived: hidden from the history list, kept intact."""

    __tablename__ = "conversation_archives"
    __table_args__ = (UniqueConstraint("conversation_id", name="uq_conversation_archive"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"))
    archived_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class SharedConversation(Base):
    """A read-only snapshot of a conversation behind an unguessable link.

    Deleting the conversation or the account deletes the share (foreign-key cascade).
    """

    __tablename__ = "shared_conversations"

    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    messages: Mapped[list] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
