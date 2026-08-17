"""add password history for reuse prevention

Revision ID: 0006_password_history
Revises: 0005_login_history
"""

import sqlalchemy as sa

from alembic import op

revision = "0006_password_history"
down_revision = "0005_login_history"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "password_history",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("password_hash", sa.String(length=512), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.create_index("ix_password_history_user_id", "password_history", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_password_history_user_id", table_name="password_history")
    op.drop_table("password_history")
