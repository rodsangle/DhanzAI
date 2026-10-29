"""Production readiness: password reset codes, conversation retention, temporary chats.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-29 09:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "password_reset_tokens",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_password_reset_tokens_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_password_reset_tokens")),
    )
    with op.batch_alter_table("password_reset_tokens", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_password_reset_tokens_user_id"), ["user_id"], unique=False)
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(sa.Column("retention_days", sa.Integer(), nullable=True))
    with op.batch_alter_table("conversations", schema=None) as batch_op:
        batch_op.add_column(sa.Column("temporary", sa.Boolean(), server_default=sa.false(), nullable=False))
    with op.batch_alter_table("messages", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_messages_created_at"), ["created_at"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("messages", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_messages_created_at"))
    with op.batch_alter_table("conversations", schema=None) as batch_op:
        batch_op.drop_column("temporary")
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_column("retention_days")
    with op.batch_alter_table("password_reset_tokens", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_password_reset_tokens_user_id"))
    op.drop_table("password_reset_tokens")
