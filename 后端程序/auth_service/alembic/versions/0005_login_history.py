"""add successful-login history for new-IP and new-location detection

Revision ID: 0005_login_history
Revises: 0004_captcha_challenges
"""

import sqlalchemy as sa

from alembic import op

revision = "0005_login_history"
down_revision = "0004_captcha_challenges"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "login_history",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("ip_hmac", sa.String(length=128), nullable=False),
        sa.Column("country", sa.String(length=80), nullable=True),
        sa.Column("province", sa.String(length=120), nullable=True),
        sa.Column("city", sa.String(length=120), nullable=True),
        sa.Column("location_key", sa.String(length=384), nullable=True),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column("device_hmac", sa.String(length=128), nullable=True),
        sa.Column("anomaly", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "login_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.create_index("ix_login_history_user_id", "login_history", ["user_id"])
    op.create_index("ix_login_history_ip_hmac", "login_history", ["ip_hmac"])
    op.create_index("ix_login_history_location_key", "login_history", ["location_key"])
    op.create_index("ix_login_history_login_at", "login_history", ["login_at"])


def downgrade() -> None:
    op.drop_index("ix_login_history_login_at", table_name="login_history")
    op.drop_index("ix_login_history_location_key", table_name="login_history")
    op.drop_index("ix_login_history_ip_hmac", table_name="login_history")
    op.drop_index("ix_login_history_user_id", table_name="login_history")
    op.drop_table("login_history")
