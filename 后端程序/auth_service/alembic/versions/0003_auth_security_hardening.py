"""add concurrency, absolute-session, outbox and account-security state

Revision ID: 0003_auth_security_hardening
Revises: 0002_refresh_session_families
"""

import sqlalchemy as sa

from alembic import op

revision = "0003_auth_security_hardening"
down_revision = "0002_refresh_session_families"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users", sa.Column("failed_login_count", sa.Integer(), nullable=False, server_default="0")
    )
    op.add_column("users", sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_users_locked_until", "users", ["locked_until"])

    op.add_column(
        "auth_sessions", sa.Column("absolute_expires_at", sa.DateTime(timezone=True), nullable=True)
    )
    # Conservative for existing sessions: retain their current expiry rather
    # than accidentally extending a session during the migration.
    op.execute(
        "UPDATE auth_sessions SET absolute_expires_at = expires_at WHERE absolute_expires_at IS NULL"
    )
    with op.batch_alter_table("auth_sessions") as batch:
        batch.alter_column(
            "absolute_expires_at", existing_type=sa.DateTime(timezone=True), nullable=False
        )
    op.create_index(
        "ix_auth_sessions_absolute_expires_at", "auth_sessions", ["absolute_expires_at"]
    )

    with op.batch_alter_table("email_outbox") as batch:
        batch.alter_column("verification_id", existing_type=sa.Integer(), nullable=True)
        batch.add_column(
            sa.Column(
                "event_type", sa.String(length=32), nullable=False, server_default="verification"
            )
        )
        batch.add_column(sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("lock_token", sa.String(length=36), nullable=True))
        batch.add_column(sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE email_outbox SET next_attempt_at = created_at WHERE next_attempt_at IS NULL")
    op.execute("UPDATE email_outbox SET status = 'retry' WHERE status = 'failed'")
    with op.batch_alter_table("email_outbox") as batch:
        batch.alter_column(
            "next_attempt_at", existing_type=sa.DateTime(timezone=True), nullable=False
        )
    op.create_index("ix_email_outbox_locked_at", "email_outbox", ["locked_at"])
    op.create_index("ix_email_outbox_lock_token", "email_outbox", ["lock_token"])
    op.create_index("ix_email_outbox_next_attempt_at", "email_outbox", ["next_attempt_at"])

    op.create_table(
        "password_resets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("code_hmac", sa.String(length=128), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.create_index("ix_password_resets_user_id", "password_resets", ["user_id"])
    op.create_index("ix_password_resets_expires_at", "password_resets", ["expires_at"])
    op.create_table(
        "mfa_totp",
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column("encrypted_secret", sa.Text(), nullable=False),
        sa.Column("enabled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )


def downgrade() -> None:
    op.drop_table("mfa_totp")
    op.drop_index("ix_password_resets_expires_at", table_name="password_resets")
    op.drop_index("ix_password_resets_user_id", table_name="password_resets")
    op.drop_table("password_resets")
    op.drop_index("ix_email_outbox_next_attempt_at", table_name="email_outbox")
    op.drop_index("ix_email_outbox_lock_token", table_name="email_outbox")
    op.drop_index("ix_email_outbox_locked_at", table_name="email_outbox")
    with op.batch_alter_table("email_outbox") as batch:
        batch.drop_column("next_attempt_at")
        batch.drop_column("lock_token")
        batch.drop_column("locked_at")
        batch.drop_column("event_type")
        batch.alter_column("verification_id", existing_type=sa.Integer(), nullable=False)
    op.drop_index("ix_auth_sessions_absolute_expires_at", table_name="auth_sessions")
    op.drop_column("auth_sessions", "absolute_expires_at")
    op.drop_index("ix_users_locked_until", table_name="users")
    op.drop_column("users", "locked_until")
    op.drop_column("users", "failed_login_count")
