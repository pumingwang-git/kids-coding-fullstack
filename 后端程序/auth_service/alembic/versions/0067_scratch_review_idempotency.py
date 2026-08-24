"""add Scratch review idempotency hashes

Revision ID: 0067_scratch_review_idempotency
Revises: 0066_help_request_hashes
"""

import sqlalchemy as sa

from alembic import op

revision = "0067_scratch_review_idempotency"
down_revision = "0066_help_request_hashes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "scratch_submissions",
        sa.Column("last_review_idempotency_key_hash", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "scratch_submissions",
        sa.Column("last_review_request_hash", sa.String(length=128), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("scratch_submissions", "last_review_request_hash")
    op.drop_column("scratch_submissions", "last_review_idempotency_key_hash")
