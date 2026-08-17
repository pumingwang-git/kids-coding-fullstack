"""add refresh-token session families

Revision ID: 0002_refresh_session_families
Revises: 0001_auth_schema
"""

import sqlalchemy as sa

from alembic import op

revision = "0002_refresh_session_families"
down_revision = "0001_auth_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("auth_sessions", sa.Column("family_id", sa.String(length=36), nullable=True))
    op.execute("UPDATE auth_sessions SET family_id = id WHERE family_id IS NULL")
    op.alter_column("auth_sessions", "family_id", nullable=False)
    op.add_column(
        "auth_sessions", sa.Column("revocation_reason", sa.String(length=32), nullable=True)
    )
    op.create_index("ix_auth_sessions_family_id", "auth_sessions", ["family_id"])


def downgrade() -> None:
    op.drop_index("ix_auth_sessions_family_id", table_name="auth_sessions")
    op.drop_column("auth_sessions", "revocation_reason")
    op.drop_column("auth_sessions", "family_id")
