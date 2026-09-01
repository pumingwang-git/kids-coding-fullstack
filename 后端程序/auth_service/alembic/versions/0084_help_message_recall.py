"""add recalled timestamp to help messages"""

from alembic import op
import sqlalchemy as sa


revision = "0084_help_message_recall"
down_revision = "0083_help_student_read_receipts"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("help_messages", sa.Column("recalled_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_help_messages_recalled_at", "help_messages", ["recalled_at"])


def downgrade():
    raise RuntimeError("help message recalls retain historical facts and cannot be downgraded safely")
