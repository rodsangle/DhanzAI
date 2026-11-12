"""Account-owned server connections, revocable grants and durable action receipts."""

import uuid
from datetime import datetime

from sqlalchemy import JSON, ForeignKey, Integer, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UTCDateTime, utcnow


class OperationServer(Base):
    __tablename__ = "operation_servers"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    tasks: Mapped[list] = mapped_column(JSON, default=list)
    revoked: Mapped[bool] = mapped_column(default=False)
    last_seen: Mapped[datetime | None] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class OperationGrant(Base):
    __tablename__ = "operation_grants"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(30))
    target: Mapped[str] = mapped_column(String(200))
    scope: Mapped[dict] = mapped_column(JSON)
    remaining: Mapped[int] = mapped_column(Integer)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)
    revoked: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class OperationJob(Base):
    __tablename__ = "operation_jobs"
    __table_args__ = (UniqueConstraint("user_id", "request_key", name="uq_operation_request"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    grant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("operation_grants.id"))
    server_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("operation_servers.id"))
    request_key: Mapped[str] = mapped_column(String(100))
    task: Mapped[str] = mapped_column(String(100))
    manifest_hash: Mapped[str] = mapped_column(String(64), default="")
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    detail: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
