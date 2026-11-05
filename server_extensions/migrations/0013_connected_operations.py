"""Revocable standing permissions, paired servers and at-most-once action receipts."""

import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "operation_servers",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("tasks", sa.JSON(), nullable=False),
        sa.Column("revoked", sa.Boolean(), nullable=False),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_operation_servers_user_id", "operation_servers", ["user_id"])
    op.create_table(
        "operation_grants",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("target", sa.String(200), nullable=False),
        sa.Column("scope", sa.JSON(), nullable=False),
        sa.Column("remaining", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_operation_grants_user_id", "operation_grants", ["user_id"])
    op.create_table(
        "operation_jobs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("grant_id", sa.Uuid(), sa.ForeignKey("operation_grants.id"), nullable=False),
        sa.Column("server_id", sa.Uuid(), sa.ForeignKey("operation_servers.id"), nullable=True),
        sa.Column("request_key", sa.String(100), nullable=False),
        sa.Column("task", sa.String(100), nullable=False),
        sa.Column("manifest_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("detail", sa.String(500), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("user_id", "request_key", name="uq_operation_request"),
    )
    op.create_index("ix_operation_jobs_user_id", "operation_jobs", ["user_id"])
    op.create_index("ix_operation_jobs_status", "operation_jobs", ["status"])


def downgrade():
    op.drop_table("operation_jobs")
    op.drop_table("operation_grants")
    op.drop_table("operation_servers")
