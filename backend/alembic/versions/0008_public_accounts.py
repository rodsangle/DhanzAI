"""Public accounts: email verification, two-factor authentication, Google/Apple sign-in.

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-29 12:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("mfa_secret", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("mfa_enabled_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("mfa_last_step", sa.BigInteger(), nullable=True))
    # Accounts created before email verification existed are trusted as they are.
    op.execute("UPDATE users SET email_verified_at = created_at")

    op.create_table(
        "verification_codes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("purpose", sa.String(length=20), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_verification_codes_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_verification_codes")),
    )
    with op.batch_alter_table("verification_codes", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_verification_codes_user_id"), ["user_id"], unique=False)

    op.create_table(
        "mfa_recovery_codes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_mfa_recovery_codes_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_mfa_recovery_codes")),
    )
    with op.batch_alter_table("mfa_recovery_codes", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_mfa_recovery_codes_user_id"), ["user_id"], unique=False)

    op.create_table(
        "oauth_identities",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_oauth_identities_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_oauth_identities")),
        sa.UniqueConstraint("provider", "subject", name="uq_oauth_identities_provider_subject"),
    )
    with op.batch_alter_table("oauth_identities", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_oauth_identities_user_id"), ["user_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("oauth_identities", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_oauth_identities_user_id"))
    op.drop_table("oauth_identities")
    with op.batch_alter_table("mfa_recovery_codes", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_mfa_recovery_codes_user_id"))
    op.drop_table("mfa_recovery_codes")
    with op.batch_alter_table("verification_codes", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_verification_codes_user_id"))
    op.drop_table("verification_codes")
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_column("mfa_last_step")
        batch_op.drop_column("mfa_enabled_at")
        batch_op.drop_column("mfa_secret")
        batch_op.drop_column("email_verified_at")
