"""Private coding drafts, review snapshots and build-check status."""

import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "coding_drafts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", sa.Uuid(), sa.ForeignKey("builder_projects.id", ondelete="SET NULL")),
        sa.Column("source_project_id", sa.Uuid()),
        sa.Column("request_key", sa.String(80), nullable=False),
        sa.Column("title", sa.String(100), nullable=False),
        sa.Column("repository", sa.String(140), nullable=False),
        sa.Column("repository_id", sa.BigInteger()),
        sa.Column("base_branch", sa.String(200), nullable=False),
        sa.Column("base_sha", sa.String(64), nullable=False),
        sa.Column("baseline", sa.JSON(), nullable=False),
        sa.Column("runtime", sa.String(20), nullable=False),
        sa.Column("auto_repair", sa.Boolean(), nullable=False),
        sa.Column("repair_count", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("reviewed_files", sa.JSON()),
        sa.Column("review_hash", sa.String(64)),
        sa.Column("branch", sa.String(200)),
        sa.Column("commit_sha", sa.String(64)),
        sa.Column("pull_url", sa.String(500)),
        sa.Column("check_result", sa.JSON()),
        sa.Column("error", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "request_key", name="uq_coding_request"),
    )
    op.create_index("ix_coding_drafts_user_id", "coding_drafts", ["user_id"])
    op.create_index("ix_coding_drafts_status", "coding_drafts", ["status"])


def downgrade():
    op.drop_table("coding_drafts")
