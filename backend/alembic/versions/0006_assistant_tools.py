"""Assistant tools: reminders and the tool activity of each reply.

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-29 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "reminders",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("text", sa.String(length=500), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=True),
        sa.Column("location", sa.String(length=200), nullable=True),
        sa.Column("conversation_id", sa.Uuid(), nullable=True),
        sa.Column("notified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("done_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            name=op.f("fk_reminders_conversation_id_conversations"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_reminders_user_id_users"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_reminders")),
    )
    with op.batch_alter_table("reminders", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_reminders_due_at"), ["due_at"], unique=False)
        batch_op.create_index(batch_op.f("ix_reminders_user_id"), ["user_id"], unique=False)
    with op.batch_alter_table("messages", schema=None) as batch_op:
        batch_op.add_column(sa.Column("tool_activity", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("messages", schema=None) as batch_op:
        batch_op.drop_column("tool_activity")
    with op.batch_alter_table("reminders", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_reminders_user_id"))
        batch_op.drop_index(batch_op.f("ix_reminders_due_at"))
    op.drop_table("reminders")
