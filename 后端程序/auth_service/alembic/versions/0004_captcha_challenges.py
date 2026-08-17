"""add one-time image captcha challenges

Revision ID: 0004_captcha_challenges
Revises: 0003_auth_security_hardening
"""

import sqlalchemy as sa

from alembic import op

revision = "0004_captcha_challenges"
down_revision = "0003_auth_security_hardening"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "captcha_challenges",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("answer_hmac", sa.String(length=128), nullable=False),
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
    op.create_index("ix_captcha_challenges_expires_at", "captcha_challenges", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_captcha_challenges_expires_at", table_name="captcha_challenges")
    op.drop_table("captcha_challenges")
