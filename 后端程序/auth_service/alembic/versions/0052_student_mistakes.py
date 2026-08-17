"""学生错题档案与重做记录。

Revision ID: 0052_student_mistakes
Revises: 0051_typing
Create Date: 2026-08-16
"""
import sqlalchemy as sa

from alembic import op


revision = "0052_student_mistakes"
down_revision = "0051_typing"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "student_mistakes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("student_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("problem_id", sa.Integer(), sa.ForeignKey("problems.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("first_wrong_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("last_wrong_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("wrong_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("review_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("review_correct_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("consecutive_correct_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("mastery_level", sa.String(length=24), nullable=False, server_default="unmastered"),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="pending_review"),
        sa.Column("next_review_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("first_source_type", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("first_source_id", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("latest_source_type", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("latest_source_id", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("student_id", "problem_id", name="uq_student_mistake_problem"),
    )
    op.create_index("ix_student_mistakes_student_status", "student_mistakes", ["student_id", "status"])
    op.create_table(
        "student_mistake_reviews",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("student_mistake_id", sa.Integer(), sa.ForeignKey("student_mistakes.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("answer_json", sa.Text(), nullable=False, server_default=""),
        sa.Column("is_correct", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("source", sa.String(length=24), nullable=False, server_default="single"),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("student_mistake_reviews")
    op.drop_index("ix_student_mistakes_student_status", table_name="student_mistakes")
    op.drop_table("student_mistakes")
