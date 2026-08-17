"""add email verification records for authenticated password changes

Revision ID: 0007_password_change_verify
Revises: 0006_password_history
"""

import sqlalchemy as sa

from alembic import op

revision = "0007_password_change_verify"
down_revision = "0006_password_history"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "password_change_verifications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("code_hmac", sa.String(length=128), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.create_index(
        "ix_password_change_verifications_user_id", "password_change_verifications", ["user_id"]
    )
    op.create_index(
        "ix_password_change_verifications_expires_at",
        "password_change_verifications",
        ["expires_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_password_change_verifications_expires_at", table_name="password_change_verifications"
    )
    op.drop_index(
        "ix_password_change_verifications_user_id", table_name="password_change_verifications"
    )
    op.drop_table("password_change_verifications")
