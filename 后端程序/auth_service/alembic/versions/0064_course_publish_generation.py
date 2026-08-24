"""add publish generations for E6 notification idempotency

Revision ID: 0064_course_publish_generation
Revises: 0063_help_requests
"""

import sqlalchemy as sa

from alembic import op

revision = "0064_course_publish_generation"
down_revision = "0063_help_requests"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("courses", sa.Column("publish_generation", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("courses", sa.Column("last_publish_idempotency_key_hash", sa.String(length=128), nullable=True))
    op.add_column("courses", sa.Column("last_publish_request_hash", sa.String(length=128), nullable=True))


def downgrade() -> None:
    op.drop_column("courses", "last_publish_request_hash")
    op.drop_column("courses", "last_publish_idempotency_key_hash")
    op.drop_column("courses", "publish_generation")
