"""Private coding drafts and immutable publication snapshots."""

import uuid
from datetime import datetime

from sqlalchemy import JSON, BigInteger, Boolean, ForeignKey, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UTCDateTime, utcnow


class CodingDraft(Base):
    __tablename__ = "coding_drafts"
    __table_args__ = (UniqueConstraint("user_id", "request_key", name="uq_coding_request"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("builder_projects.id", ondelete="SET NULL"))
    source_project_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    request_key: Mapped[str] = mapped_column(String(80))
    title: Mapped[str] = mapped_column(String(100))
    repository: Mapped[str] = mapped_column(String(140), default="")
    repository_id: Mapped[int | None] = mapped_column(BigInteger)
    base_branch: Mapped[str] = mapped_column(String(200), default="")
    base_sha: Mapped[str] = mapped_column(String(64), default="")
    baseline: Mapped[list] = mapped_column(JSON, default=list)
    runtime: Mapped[str] = mapped_column(String(20), default="python")
    auto_repair: Mapped[bool] = mapped_column(Boolean, default=False)
    repair_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="generating", index=True)
    reviewed_files: Mapped[list | None] = mapped_column(JSON)
    review_hash: Mapped[str | None] = mapped_column(String(64))
    branch: Mapped[str | None] = mapped_column(String(200))
    commit_sha: Mapped[str | None] = mapped_column(String(64))
    pull_url: Mapped[str | None] = mapped_column(String(500))
    check_result: Mapped[dict | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
