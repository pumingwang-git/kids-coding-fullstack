"""课中练习单题作答状态表

Revision ID: 0035_lesson_practice_attempts
Revises: 0034_lesson_block_unlock
Create Date: 2026-08-10

《15、课时作答与资料展示-开发交接》第三节（形态 A：块内直答）+ §8.1 S3。

**为什么另建表，而不是复用 paper_attempts**：
沿用 `ProblemDryRun` 立下的先例（models.py:513 注释）——需要一次"没有 attempt 的作答/运行"
时，本项目的既定做法是**另建一张平行的窄表**，而不是伪造一条 attempt：
「为试跑造一条假 attempt，就是把一张业务表当通用容器用，之后所有『按 attempt 统计』
的查询都要记得排除假行。」课中练习是随堂快测——没有会话、没有倒计时、没有交卷，
把它塞进 paper_attempts 会让每一条成绩统计都要先 WHERE 掉它。

**本表不进成绩统计**（PRD v2 Q3 的退化口径「即时反馈、不记成绩」）。
X2 落地后由它迁移进统一 attempt 模型，届时本表转为只读历史或直接废弃。

字段只够回答三个问题，不多存：
  还能答几次      → tries
  刷新后我答了啥   → answer_json（否则学生一刷新作答就没了，这是纯粹的体验债）
  上次判定是什么   → last_score / last_correct / detail_json
"""
from alembic import op
import sqlalchemy as sa

revision = "0035_lesson_practice_attempts"
down_revision = "0034_lesson_block_unlock"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "lesson_problem_attempts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id", sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "block_id", sa.Integer(),
            sa.ForeignKey("course_lesson_blocks.id", ondelete="CASCADE"), nullable=False,
        ),
        # 与 lesson_block_completions 同款冗余列：按课时批量取作答态，避免 join 块主表
        sa.Column(
            "lesson_id", sa.Integer(),
            sa.ForeignKey("course_lessons.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("tries", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("answer_json", sa.Text(), nullable=False, server_default=""),
        sa.Column("last_score", sa.Integer(), nullable=True),
        sa.Column("last_correct", sa.Boolean(), nullable=True),
        sa.Column("detail_json", sa.Text(), nullable=True),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        # 一个学生对一个块只有一条作答态（tries 累加，不是每次一行）
        sa.UniqueConstraint("user_id", "block_id", name="uq_lesson_problem_attempt"),
    )
    op.create_index(
        "ix_lesson_problem_attempt_user_lesson",
        "lesson_problem_attempts", ["user_id", "lesson_id"],
    )
    print("[0035] 已新建 lesson_problem_attempts（课中练习单题作答状态，不进成绩统计）。")


def downgrade() -> None:
    op.drop_index("ix_lesson_problem_attempt_user_lesson", table_name="lesson_problem_attempts")
    op.drop_table("lesson_problem_attempts")
    print("[0035] downgrade：已删除 lesson_problem_attempts。")
