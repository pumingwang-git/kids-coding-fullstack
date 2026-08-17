"""add tag description column (tooltip text for knowledge tree nodes)

Revision ID: 0016_tag_description
Revises: 0015_stem_markdown
Create Date: 2026-08-05
"""

from alembic import op
import sqlalchemy as sa

revision = "0016_tag_description"
down_revision = "0015_stem_markdown"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tags", sa.Column("description", sa.String(length=500), nullable=True))


def downgrade() -> None:
    op.drop_column("tags", "description")
