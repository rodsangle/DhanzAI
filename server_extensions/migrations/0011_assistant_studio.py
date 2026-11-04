"""Account-owned response feedback and durable app/agent project builds."""

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "response_feedback",
        sa.Column("message_id", sa.Uuid(), sa.ForeignKey("messages.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("rating", sa.String(4), nullable=False),
        sa.Column("note", sa.String(1000), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("rating IN ('up','down')", name=op.f("ck_response_feedback_rating_value")),
    )
    op.create_table(
        "builder_projects",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("request_key", sa.String(80), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("kind", sa.String(10), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("model", sa.String(200), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("files", sa.JSON()),
        sa.Column("summary", sa.Text()),
        sa.Column("error", sa.String(500)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "request_key", name="uq_builder_request"),
    )
    op.create_index("ix_builder_projects_user_id", "builder_projects", ["user_id"])
    op.create_index("ix_builder_projects_status", "builder_projects", ["status"])
    table = op.create_table(
        "builder_leases",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("job_id", sa.Uuid()),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
    )
    op.bulk_insert(table, [{"id": 1, "job_id": None, "expires_at": None}])


def downgrade():
    op.drop_table("builder_leases")
    op.drop_table("builder_projects")
    op.drop_table("response_feedback")
