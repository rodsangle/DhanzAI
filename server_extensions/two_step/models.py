"""Two-step verification tables. New tables only: the existing `users` table is not changed."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UTCDateTime, utcnow


class TwoStepSetting(Base):
    """One row per account that started or finished turning two-step verification on."""

    __tablename__ = "two_step_settings"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    # "totp" (authenticator app). Room for "email" once the server can send email.
    method: Mapped[str] = mapped_column(String(10), default="totp")
    # The TOTP secret, AES-256-GCM encrypted ("v1:..."); set while scanning the QR code.
    secret: Mapped[str | None] = mapped_column(String(255))
    # NULL until the first code from the app is confirmed: two-step verification is off.
    enabled_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    # Last accepted 30-second step: a code cannot be used twice.
    last_step: Mapped[int | None] = mapped_column(BigInteger)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


class TwoStepRecoveryCode(Base):
    """Single-use backup code (Argon2id hash only)."""

    __tablename__ = "two_step_recovery_codes"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    code_hash: Mapped[str] = mapped_column(String(255))
    used_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class TwoStepDevice(Base):
    """A device where the user chose "remember this device" (SHA-256 of its token only).

    `password_fingerprint` ties it to the password at that moment: changing or resetting the
    password makes every remembered device ask for the second step again.
    """

    __tablename__ = "two_step_devices"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    password_fingerprint: Mapped[str] = mapped_column(String(64))
    label: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    last_used_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)


TABLES = (TwoStepSetting.__table__, TwoStepRecoveryCode.__table__, TwoStepDevice.__table__)
