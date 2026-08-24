"""add scratch review revision for E6 notifications

Revision ID: 0065_scratch_review_revision
Revises: 0064_course_publish_generation
"""

import sqlalchemy as sa

from alembic import op

revision = "0065_scratch_review_revision"
down_revision = "0064_course_publish_generation"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column("scratch_submissions", sa.Column("review_revision", sa.Integer(), nullable=False, server_default="0"))

def downgrade() -> None:
    op.drop_column("scratch_submissions", "review_revision")
