"""Two-step verification by email code, and remembered (trusted) devices.

Adds users.mfa_method ("totp" or "email"); accounts that already have two-step verification on
used an authenticator app, so they are set to "totp". Creates trusted_devices.

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-16 09:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(sa.Column("mfa_method", sa.String(length=10), nullable=True))
    op.execute("UPDATE users SET mfa_method = 'totp' WHERE mfa_enabled_at IS NOT NULL")
    op.create_table(
        "trusted_devices",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("label", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_trusted_devices_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_trusted_devices")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_trusted_devices_token_hash")),
    )
    with op.batch_alter_table("trusted_devices", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_trusted_devices_user_id"), ["user_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("trusted_devices", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_trusted_devices_user_id"))
    op.drop_table("trusted_devices")
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_column("mfa_method")
