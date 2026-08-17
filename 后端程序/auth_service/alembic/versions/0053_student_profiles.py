"""学生个人资料（头像、学习签名）。

Revision ID: 0053_student_profiles
Revises: 0052_student_mistakes
Create Date: 2026-08-16
"""
import sqlalchemy as sa

from alembic import op


revision = "0053_student_profiles"
down_revision = "0052_student_mistakes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "student_profiles",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("avatar_url", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("learning_signature", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("student_profiles")
