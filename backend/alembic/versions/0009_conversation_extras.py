"""Conversation archive and public share links.

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-13 20:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "conversation_archives",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("conversation_id", name="uq_conversation_archive"),
    )
    op.create_index("ix_conversation_archives_user_id", "conversation_archives", ["user_id"])
    op.create_table(
        "shared_conversations",
        sa.Column("token", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("messages", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("token"),
    )
    op.create_index("ix_shared_conversations_user_id", "shared_conversations", ["user_id"])
    op.create_index("ix_shared_conversations_conversation_id", "shared_conversations", ["conversation_id"])


def downgrade() -> None:
    op.drop_index("ix_shared_conversations_conversation_id", table_name="shared_conversations")
    op.drop_index("ix_shared_conversations_user_id", table_name="shared_conversations")
    op.drop_table("shared_conversations")
    op.drop_index("ix_conversation_archives_user_id", table_name="conversation_archives")
    op.drop_table("conversation_archives")
