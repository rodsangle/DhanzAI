"""Per-account encrypted read-only GitHub connections."""

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "github_connections",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("login", sa.String(100), nullable=False),
        sa.Column("encrypted_token", sa.Text(), nullable=False),
        sa.Column("repositories", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )


def downgrade() -> None:
    op.drop_table("github_connections")
