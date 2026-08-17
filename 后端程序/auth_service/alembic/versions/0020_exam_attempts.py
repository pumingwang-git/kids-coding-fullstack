"""add paper_attempts / attempt_answers / code_submissions

Revision ID: 0020_exam_attempts
Revises: 0019_exam_link_reminders
Create Date: 2026-08-06

学员端作答闭环的数据层。paper_attempts 的结构在《3、后台试卷-组卷模块》第七节
就已定死，这里照落；attempt_answers 与 code_submissions 是本期新增，
分别承载「每题当前生效的作答与得分」与「编程题的提交历史」。
"""
from alembic import op
import sqlalchemy as sa

revision = "0020_exam_attempts"
down_revision = "0019_exam_link_reminders"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "paper_attempts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("exam_link_id", sa.Integer(), sa.ForeignKey("exam_links.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("paper_id", sa.Integer(), sa.ForeignKey("papers.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("attempt_no", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("submit_kind", sa.String(length=16), nullable=True),
        sa.Column("shuffle_seed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("penalty_minutes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="ongoing", index=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("ip_hmac", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("exam_link_id", "user_id", "attempt_no", name="uq_paper_attempts"),
    )
    op.create_table(
        "attempt_answers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("attempt_id", sa.Integer(), sa.ForeignKey("paper_attempts.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("problem_id_no", sa.String(length=64), nullable=False, index=True),
        sa.Column("answer_json", sa.Text(), nullable=False, server_default=""),
        sa.Column("score", sa.Integer(), nullable=True),
        sa.Column("is_correct", sa.Boolean(), nullable=True),
        sa.Column("judge_status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("judged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("detail_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("attempt_id", "problem_id_no", name="uq_attempt_answers"),
    )
    op.create_table(
        "code_submissions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("attempt_id", sa.Integer(), sa.ForeignKey("paper_attempts.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("problem_id_no", sa.String(length=64), nullable=False, index=True),
        sa.Column("language", sa.String(length=16), nullable=False),
        sa.Column("code", sa.Text(), nullable=False, server_default=""),
        sa.Column("kind", sa.String(length=8), nullable=False, index=True),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="queued"),
        sa.Column("score", sa.Integer(), nullable=True),
        sa.Column("detail_json", sa.Text(), nullable=True),
        sa.Column("time_ms", sa.Integer(), nullable=True),
        sa.Column("memory_kb", sa.Integer(), nullable=True),
        sa.Column("compile_message", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("code_submissions")
    op.drop_table("attempt_answers")
    op.drop_table("paper_attempts")
