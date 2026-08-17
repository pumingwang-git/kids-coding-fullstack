"""课中练习：重做审计字段 + 编程题计分提交

Revision ID: 0038_practice_reset_submit
Revises: 0037_attempt_source
Create Date: 2026-08-12

《18、单课时页三处缺陷-问题分析与解决方案》A1 / B6。

两件事，一次迁移：

1. **重做（reset）**：`lesson_problem_attempts` 加 `reset_count / last_reset_at`，
   纯审计。重做只清作答态，**不动 tries、不动 lesson_block_completions**——
   完成度是学习履历（只增不减），作答态是练习工具（随时可清）。两者混在一起，
   学生复习一道题就会被顺序锁踢回闯关起点。

2. **编程题计分提交**：不加表、不加列。`lesson_code_runs.scope` 原本只有
   samples/custom 两个取值，这里扩出第三个 `all`（跑全部测试点、计分、写完成度）。
   列宽 String(8) 装得下，判定结果照旧写回 `lesson_problem_attempts`——
   编程题与客观题因此共用同一张作答表、同一套「提交即完成」口径、同一个重做端点。

   **没有为单题作答造 PaperAttempt**：那张表的 paper_id 是 NOT NULL，单题块没有卷；
   为一道题造一张假卷正是 ProblemDryRun（models.py:513）明令反对的做法。
"""
from alembic import op
import sqlalchemy as sa

revision = "0038_practice_reset_submit"
down_revision = "0037_attempt_source"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("lesson_problem_attempts") as batch:
        batch.add_column(
            sa.Column("reset_count", sa.Integer(), nullable=False, server_default="0")
        )
        batch.add_column(
            sa.Column("last_reset_at", sa.DateTime(timezone=True), nullable=True)
        )
    print("[0038] lesson_problem_attempts 已加 reset_count / last_reset_at（重做审计）。")
    print("[0038] lesson_code_runs.scope 新增取值 all（编程题计分提交），无需改表结构。")


def downgrade() -> None:
    # scope="all" 的历史记录在降级后会变成一个 lesson_practice.py 不认识的取值，
    # 但它只影响那几条记录的回看，不会让旧代码报错（_run_payload 照常返回）。
    with op.batch_alter_table("lesson_problem_attempts") as batch:
        batch.drop_column("last_reset_at")
        batch.drop_column("reset_count")
    print("[0038] downgrade：已删除 reset_count / last_reset_at。")
