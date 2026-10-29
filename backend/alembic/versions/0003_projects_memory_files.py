"""Projects, opt-in memory, uploaded files and message attachments.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-28 22:41:47.092586
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "memories",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_memories_user_id_users"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_memories")),
    )
    with op.batch_alter_table("memories", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_memories_user_id"), ["user_id"], unique=False)

    op.create_table(
        "projects",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("instructions", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_projects_user_id_users"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_projects")),
    )
    with op.batch_alter_table("projects", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_projects_user_id"), ["user_id"], unique=False)

    with op.batch_alter_table("conversations", schema=None) as batch_op:
        batch_op.add_column(sa.Column("project_id", sa.Uuid(), nullable=True))
        batch_op.create_index(batch_op.f("ix_conversations_project_id"), ["project_id"], unique=False)
        batch_op.create_foreign_key(
            batch_op.f("fk_conversations_project_id_projects"), "projects", ["project_id"], ["id"], ondelete="SET NULL"
        )

    with op.batch_alter_table("knowledge_documents", schema=None) as batch_op:
        batch_op.add_column(sa.Column("project_id", sa.Uuid(), nullable=True))
        batch_op.add_column(sa.Column("file_type", sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column("mime_type", sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column("size_bytes", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("storage_key", sa.String(length=80), nullable=True))
        batch_op.add_column(sa.Column("scan_status", sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column("notes", sa.Text(), nullable=True))
        batch_op.create_index(batch_op.f("ix_knowledge_documents_project_id"), ["project_id"], unique=False)
        batch_op.create_foreign_key(
            batch_op.f("fk_knowledge_documents_project_id_projects"),
            "projects",
            ["project_id"],
            ["id"],
            ondelete="SET NULL",
        )

    with op.batch_alter_table("messages", schema=None) as batch_op:
        batch_op.add_column(sa.Column("attachments", sa.JSON(), nullable=True))

    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(sa.Column("memory_enabled", sa.Boolean(), server_default=sa.false(), nullable=False))


def downgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_column("memory_enabled")

    with op.batch_alter_table("messages", schema=None) as batch_op:
        batch_op.drop_column("attachments")

    with op.batch_alter_table("knowledge_documents", schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f("fk_knowledge_documents_project_id_projects"), type_="foreignkey")
        batch_op.drop_index(batch_op.f("ix_knowledge_documents_project_id"))
        batch_op.drop_column("notes")
        batch_op.drop_column("scan_status")
        batch_op.drop_column("storage_key")
        batch_op.drop_column("size_bytes")
        batch_op.drop_column("mime_type")
        batch_op.drop_column("file_type")
        batch_op.drop_column("project_id")

    with op.batch_alter_table("conversations", schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f("fk_conversations_project_id_projects"), type_="foreignkey")
        batch_op.drop_index(batch_op.f("ix_conversations_project_id"))
        batch_op.drop_column("project_id")

    with op.batch_alter_table("projects", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_projects_user_id"))

    op.drop_table("projects")
    with op.batch_alter_table("memories", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_memories_user_id"))

    op.drop_table("memories")
