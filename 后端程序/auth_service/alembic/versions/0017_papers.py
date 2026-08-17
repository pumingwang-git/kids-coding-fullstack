"""add papers: papers, paper_questions (组卷模块 M5)

Revision ID: 0017_papers
Revises: 0016_tag_description
Create Date: 2026-08-05

paper_attempts（作答记录表）留到学员端那期再建，结构已在设计文档定死。
paper_questions.problem_id_no 是逻辑引用，故意不建外键：题库 approve 顶替旧行时
编号短暂无主，外键会炸；删除保护由应用层 _reference_blockers() 前置检查负责。
"""
from alembic import op
import sqlalchemy as sa

revision = "0017_papers"
down_revision = "0016_tag_description"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "papers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("paper_id_no", sa.String(length=64), nullable=True, unique=True),
        sa.Column("access_token", sa.String(length=32), nullable=True, unique=True),
        sa.Column("title", sa.Text(), nullable=False, server_default=""),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("paper_type", sa.String(length=32), nullable=False, server_default="练习卷"),
        sa.Column("subject", sa.String(length=16), nullable=False, server_default="cpp"),
        sa.Column("ruleset", sa.String(length=16), nullable=False, server_default="IOI"),
        sa.Column("score_mode", sa.String(length=16), nullable=False, server_default="testcase"),
        sa.Column("score_policy", sa.String(length=16), nullable=False, server_default="best"),
        sa.Column("attempt_limit", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("feedback_mode", sa.String(length=16), nullable=False, server_default="realtime"),
        sa.Column("penalty_minutes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("partial_credit_multi", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("shuffle_questions", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("shuffle_options", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("show_analysis", sa.String(length=16), nullable=False, server_default="after_submit"),
        sa.Column("show_score", sa.String(length=16), nullable=False, server_default="immediate"),
        sa.Column("open_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("close_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_minutes", sa.Integer(), nullable=True),
        sa.Column("late_start_policy", sa.String(length=16), nullable=False, server_default="truncate"),
        sa.Column("total_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("pass_score", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="draft"),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("admin_users.id"), nullable=True),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("admin_users.id"), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_papers_paper_type", "papers", ["paper_type"])
    op.create_index("ix_papers_subject", "papers", ["subject"])
    op.create_index("ix_papers_status", "papers", ["status"])
    op.create_index("ix_papers_owner_id", "papers", ["owner_id"])

    op.create_table(
        "paper_questions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("paper_id", sa.Integer(), sa.ForeignKey("papers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("problem_id_no", sa.String(length=64), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("score", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("paper_id", "problem_id_no", name="uq_paper_questions"),
    )
    op.create_index("ix_paper_questions_paper_id", "paper_questions", ["paper_id"])
    op.create_index("ix_paper_questions_problem_id_no", "paper_questions", ["problem_id_no"])


def downgrade() -> None:
    op.drop_table("paper_questions")
    op.drop_table("papers")
