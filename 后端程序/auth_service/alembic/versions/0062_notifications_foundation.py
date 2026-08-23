"""add the E6 in-app notification foundation

Revision ID: 0062_notifications_foundation
Revises: 0061_revoke_class_enrollments
"""

import sqlalchemy as sa

from alembic import op

revision = "0062_notifications_foundation"
down_revision = "0061_revoke_class_enrollments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("target_type", sa.String(length=64), nullable=False),
        sa.Column("target_id", sa.Integer(), nullable=False),
        sa.Column("source_type", sa.String(length=64), nullable=True),
        sa.Column("source_id", sa.Integer(), nullable=True),
        sa.Column("link_url", sa.String(length=500), nullable=True),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("request_hash", sa.String(length=128), nullable=True),
        sa.Column(
            "created_by",
            sa.Integer(),
            sa.ForeignKey("admin_users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "revoked_by",
            sa.Integer(),
            sa.ForeignKey("admin_users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.CheckConstraint(
            "(source_type IS NULL AND source_id IS NULL) OR "
            "(source_type IS NOT NULL AND source_id IS NOT NULL)",
            name="ck_notifications_source_pair",
        ),
    )
    op.create_index("ix_notifications_kind", "notifications", ["kind"])
    op.create_index(
        "ix_notifications_idempotency_key", "notifications", ["idempotency_key"], unique=True
    )
    op.create_index("ix_notifications_created_at_id", "notifications", ["created_at", "id"])
    op.create_index("ix_notifications_created_by", "notifications", ["created_by"])
    op.create_index("ix_notifications_revoked_at", "notifications", ["revoked_at"])
    op.create_index("ix_notifications_revoked_by", "notifications", ["revoked_by"])

    op.create_table(
        "notification_receipts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "notification_id",
            sa.Integer(),
            sa.ForeignKey("notifications.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True
        ),
        sa.Column(
            "admin_user_id",
            sa.Integer(),
            sa.ForeignKey("admin_users.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dismissed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "(user_id IS NOT NULL AND admin_user_id IS NULL) OR "
            "(user_id IS NULL AND admin_user_id IS NOT NULL)",
            name="ck_notification_receipts_one_recipient",
        ),
    )
    op.create_index(
        "ix_notification_receipts_notification_id", "notification_receipts", ["notification_id"]
    )
    op.create_index("ix_notification_receipts_user_id", "notification_receipts", ["user_id"])
    op.create_index(
        "ix_notification_receipts_admin_user_id", "notification_receipts", ["admin_user_id"]
    )
    op.create_index("ix_notification_receipts_read_at", "notification_receipts", ["read_at"])
    op.create_index(
        "uq_notification_receipts_notification_user",
        "notification_receipts",
        ["notification_id", "user_id"],
        unique=True,
        sqlite_where=sa.text("user_id IS NOT NULL"),
        postgresql_where=sa.text("user_id IS NOT NULL"),
    )
    op.create_index(
        "uq_notification_receipts_notification_admin",
        "notification_receipts",
        ["notification_id", "admin_user_id"],
        unique=True,
        sqlite_where=sa.text("admin_user_id IS NOT NULL"),
        postgresql_where=sa.text("admin_user_id IS NOT NULL"),
    )
    op.create_index(
        "ix_notification_receipts_user_unread",
        "notification_receipts",
        ["user_id", "read_at", "notification_id"],
        sqlite_where=sa.text("user_id IS NOT NULL"),
        postgresql_where=sa.text("user_id IS NOT NULL"),
    )
    op.create_index(
        "ix_notification_receipts_admin_unread",
        "notification_receipts",
        ["admin_user_id", "read_at", "notification_id"],
        sqlite_where=sa.text("admin_user_id IS NOT NULL"),
        postgresql_where=sa.text("admin_user_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_notification_receipts_admin_unread", table_name="notification_receipts")
    op.drop_index("ix_notification_receipts_user_unread", table_name="notification_receipts")
    op.drop_index("uq_notification_receipts_notification_admin", table_name="notification_receipts")
    op.drop_index("uq_notification_receipts_notification_user", table_name="notification_receipts")
    op.drop_index("ix_notification_receipts_read_at", table_name="notification_receipts")
    op.drop_index("ix_notification_receipts_admin_user_id", table_name="notification_receipts")
    op.drop_index("ix_notification_receipts_user_id", table_name="notification_receipts")
    op.drop_index("ix_notification_receipts_notification_id", table_name="notification_receipts")
    op.drop_table("notification_receipts")
    for name in (
        "ix_notifications_revoked_by",
        "ix_notifications_revoked_at",
        "ix_notifications_created_by",
        "ix_notifications_created_at_id",
        "ix_notifications_idempotency_key",
        "ix_notifications_kind",
    ):
        op.drop_index(name, table_name="notifications")
    op.drop_table("notifications")
