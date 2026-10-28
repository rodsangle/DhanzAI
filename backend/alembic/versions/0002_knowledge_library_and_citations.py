"""Knowledge library (documents + chunks with embeddings), message citations, auto-index preference.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-28 21:43:22.459658
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _embedding_type():
    # pgvector on PostgreSQL (unconstrained dimensions: rows record their embedding model), JSON elsewhere.
    if op.get_bind().dialect.name == "postgresql":
        from pgvector.sqlalchemy import Vector

        return Vector()
    return sa.JSON()


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "knowledge_documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("url", sa.String(length=2048), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("site_name", sa.String(length=200), nullable=True),
        sa.Column("author", sa.String(length=200), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("added_via", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_knowledge_documents_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_knowledge_documents")),
        sa.UniqueConstraint("user_id", "url", name="uq_knowledge_documents_user_url"),
    )
    with op.batch_alter_table("knowledge_documents", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_knowledge_documents_user_id"), ["user_id"], unique=False)

    op.create_table(
        "knowledge_chunks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("embedding", _embedding_type(), nullable=True),
        sa.Column("embedding_model", sa.String(length=200), nullable=True),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["knowledge_documents.id"],
            name=op.f("fk_knowledge_chunks_document_id_knowledge_documents"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_knowledge_chunks_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_knowledge_chunks")),
    )
    with op.batch_alter_table("knowledge_chunks", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_knowledge_chunks_document_id"), ["document_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_knowledge_chunks_user_id"), ["user_id"], unique=False)

    with op.batch_alter_table("messages", schema=None) as batch_op:
        batch_op.add_column(sa.Column("citations", sa.JSON(), nullable=True))

    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(sa.Column("auto_index_web", sa.Boolean(), server_default=sa.true(), nullable=False))


def downgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_column("auto_index_web")

    with op.batch_alter_table("messages", schema=None) as batch_op:
        batch_op.drop_column("citations")

    with op.batch_alter_table("knowledge_chunks", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_knowledge_chunks_user_id"))
        batch_op.drop_index(batch_op.f("ix_knowledge_chunks_document_id"))

    op.drop_table("knowledge_chunks")
    with op.batch_alter_table("knowledge_documents", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_knowledge_documents_user_id"))

    op.drop_table("knowledge_documents")
