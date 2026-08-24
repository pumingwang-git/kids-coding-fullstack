"""add E6 help-request input hashes

Revision ID: 0066_help_request_hashes
Revises: 0065_scratch_review_revision
"""

import sqlalchemy as sa

from alembic import op

revision = "0066_help_request_hashes"
down_revision = "0065_scratch_review_revision"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column("help_requests", sa.Column("request_hash", sa.String(length=128), nullable=True))
    op.execute("UPDATE help_requests SET request_hash = request_key_hash WHERE request_hash IS NULL")
    # SQLite has no standalone ALTER COLUMN. Batch mode rebuilds this table
    # while preserving its foreign keys, checks and unique constraint.
    with op.batch_alter_table("help_requests", recreate="auto") as batch:
        batch.alter_column("request_hash", existing_type=sa.String(length=128), nullable=False)
    op.add_column("help_messages", sa.Column("request_hash", sa.String(length=128), nullable=True))

def downgrade() -> None:
    op.drop_column("help_messages", "request_hash")
    op.drop_column("help_requests", "request_hash")
