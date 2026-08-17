"""课时内编程题试跑记录

Revision ID: 0036_lesson_code_runs
Revises: 0035_lesson_practice_attempts
Create Date: 2026-08-10

《15、课时作答与资料展示-开发交接》§8.1 S4（形态 B：块内工作区 · 只运行不计分）。

**为什么不复用 code_submissions**：它的 `attempt_id` 是 NOT NULL 外键，课时里没有
attempt。为一次试跑造条假 attempt，正是 ProblemDryRun 注释（models.py:513）明令
反对的做法——「把一张业务表当通用容器用，之后所有『按 attempt 统计』的查询都要
记得排除假行」。本表与 problem_dry_runs 是同一类东西（一次不进成绩的运行），
区别只在使用者：那张是录题人跑参考代码，这张是学生跑自己的代码。

**只跑样例**（scope=samples）或学生自填输入（scope=custom）。隐藏测试点在任何配置下
都不进入本链路——那是判分资产，而本表是"不计分"的运行。

**存 code**（与 ProblemDryRun 相反）：那张不存是因为参考代码在 reference_solutions 里
有权威副本；学生的代码没有别处可存，不存就没法异步判完再回填结果。
"""
from alembic import op
import sqlalchemy as sa

revision = "0036_lesson_code_runs"
down_revision = "0035_lesson_practice_attempts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "lesson_code_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id", sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "block_id", sa.Integer(),
            sa.ForeignKey("course_lesson_blocks.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "lesson_id", sa.Integer(),
            sa.ForeignKey("course_lessons.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("language", sa.String(length=16), nullable=False),
        sa.Column("scope", sa.String(length=8), nullable=False, server_default="samples"),
        sa.Column("code", sa.Text(), nullable=False, server_default=""),
        # 状态枚举与 CodeSubmission / ProblemDryRun 同一套（queued/judging/accepted/...）
        sa.Column("status", sa.String(length=24), nullable=False, server_default="queued"),
        sa.Column("compile_message", sa.Text(), nullable=False, server_default=""),
        sa.Column("detail_json", sa.Text(), nullable=True),
        sa.Column("time_ms", sa.Integer(), nullable=True),
        sa.Column("memory_kb", sa.Integer(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
    )
    op.create_index("ix_lesson_code_run_user_block", "lesson_code_runs", ["user_id", "block_id"])
    print("[0036] 已新建 lesson_code_runs（课时内编程题试跑，只跑样例，不进成绩）。")


def downgrade() -> None:
    op.drop_index("ix_lesson_code_run_user_block", table_name="lesson_code_runs")
    op.drop_table("lesson_code_runs")
    print("[0036] downgrade：已删除 lesson_code_runs。")
