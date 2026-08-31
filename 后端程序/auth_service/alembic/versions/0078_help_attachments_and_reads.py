"""add help message attachments and teacher read cursors

Revision ID: 0078_help_attachments_and_reads
Revises: 0077_ai_conversations
"""

from alembic import op
import sqlalchemy as sa

revision = "0078_help_attachments_and_reads"
down_revision = "0077_ai_conversations"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "help_message_attachments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("help_message_id", sa.Integer(), sa.ForeignKey("help_messages.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("mime", sa.String(length=128), nullable=False),
        sa.Column("original_name", sa.String(length=255), nullable=False),
        sa.Column("storage_key", sa.String(length=255), nullable=False, unique=True),
        sa.Column("uploaded_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("uploaded_by_admin_user_id", sa.Integer(), sa.ForeignKey("admin_users.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("purged_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("kind IN ('image', 'text_file')", name="ck_help_attachment_kind"),
        sa.CheckConstraint("byte_size > 0", name="ck_help_attachment_byte_size"),
        sa.CheckConstraint("(uploaded_by_user_id IS NOT NULL AND uploaded_by_admin_user_id IS NULL) OR (uploaded_by_user_id IS NULL AND uploaded_by_admin_user_id IS NOT NULL)", name="ck_help_attachments_one_uploader"),
    )
    op.create_index("ix_help_message_attachments_help_message_id", "help_message_attachments", ["help_message_id"])
    op.create_index("ix_help_message_attachments_sha256", "help_message_attachments", ["sha256"])
    op.create_index("ix_help_message_attachments_purged_at", "help_message_attachments", ["purged_at"])
    op.create_table(
        "help_chat_line_reads",
        sa.Column("admin_user_id", sa.Integer(), sa.ForeignKey("admin_users.id", ondelete="RESTRICT"), primary_key=True),
        sa.Column("chat_line_id", sa.Integer(), sa.ForeignKey("help_chat_lines.id", ondelete="RESTRICT"), primary_key=True),
        sa.Column("last_read_message_id", sa.Integer(), sa.ForeignKey("help_messages.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade():
    op.drop_table("help_chat_line_reads")
    op.drop_index("ix_help_message_attachments_purged_at", table_name="help_message_attachments")
    op.drop_index("ix_help_message_attachments_sha256", table_name="help_message_attachments")
    op.drop_index("ix_help_message_attachments_help_message_id", table_name="help_message_attachments")
    op.drop_table("help_message_attachments")
