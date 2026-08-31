"""persist student read cursors for help chat receipts"""

import sqlalchemy as sa
from alembic import op

revision = "0083_help_student_read_receipts"
down_revision = "0082_help_status_checks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "help_chat_line_student_reads",
        sa.Column("student_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), primary_key=True),
        sa.Column("chat_line_id", sa.Integer(), sa.ForeignKey("help_chat_lines.id", ondelete="RESTRICT"), primary_key=True),
        sa.Column("last_read_message_id", sa.Integer(), sa.ForeignKey("help_messages.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("help_chat_line_student_reads")
