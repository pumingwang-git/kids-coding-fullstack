"""add E6 asynchronous help requests

Revision ID: 0063_help_requests
Revises: 0062_notifications_foundation
"""

import sqlalchemy as sa

from alembic import op

revision = "0063_help_requests"
down_revision = "0062_notifications_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "help_requests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("class_id", sa.Integer(), sa.ForeignKey("class_groups.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("student_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("assigned_admin_user_id", sa.Integer(), sa.ForeignKey("admin_users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("context_type", sa.String(length=64), nullable=False),
        sa.Column("context_id", sa.Integer(), nullable=True),
        sa.Column("request_key_hash", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="open"),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('open', 'closed')", name="ck_help_requests_status"),
        sa.CheckConstraint("(status = 'open' AND closed_at IS NULL) OR (status = 'closed' AND closed_at IS NOT NULL)", name="ck_help_requests_status_matches_closed_at"),
        sa.UniqueConstraint("student_id", "request_key_hash", name="uq_help_requests_student_key"),
    )
    for column in ("class_id", "student_id", "assigned_admin_user_id", "status", "created_at"):
        op.create_index(f"ix_help_requests_{column}", "help_requests", [column])
    op.create_table(
        "help_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("help_request_id", sa.Integer(), sa.ForeignKey("help_requests.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sender_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("sender_admin_user_id", sa.Integer(), sa.ForeignKey("admin_users.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("request_key_hash", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("(sender_user_id IS NOT NULL AND sender_admin_user_id IS NULL) OR (sender_user_id IS NULL AND sender_admin_user_id IS NOT NULL)", name="ck_help_messages_one_sender"),
        sa.UniqueConstraint("help_request_id", "sender_admin_user_id", "request_key_hash", name="uq_help_messages_admin_key"),
    )
    for column in ("help_request_id", "sender_user_id", "sender_admin_user_id", "created_at"):
        op.create_index(f"ix_help_messages_{column}", "help_messages", [column])


def downgrade() -> None:
    for column in ("created_at", "sender_admin_user_id", "sender_user_id", "help_request_id"):
        op.drop_index(f"ix_help_messages_{column}", table_name="help_messages")
    op.drop_table("help_messages")
    for column in ("created_at", "status", "assigned_admin_user_id", "student_id", "class_id"):
        op.drop_index(f"ix_help_requests_{column}", table_name="help_requests")
    op.drop_table("help_requests")
