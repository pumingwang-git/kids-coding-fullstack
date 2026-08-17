"""内容块解锁体系：块级 unlock_rule + 学习完成记录表

Revision ID: 0034_lesson_block_unlock
Revises: 0033_lesson_problem_blocks
Create Date: 2026-08-10

《14、单课时学习界面-开发交接》第六节 P1。本次落地的是 **Gate B（路径闸）**——
「按教学顺序，现在轮到你学了吗」，与既有的 Gate A（权限闸，open_policy）正交：

- `course_lesson_blocks.unlock_rule`：free（任意顺序学，默认）/ sequential（前面所有
  「必修且有权限」的块完成后才开放）。存在**块**上而不是课时上，因为「前面随便看、
  最后的编程练习必须按顺序」是最常见的诉求；课时级「整节闯关」由管理端一键批量设置。
- `lesson_block_completions`：学习完成记录。此表之前**完全不存在**，导致
  `course_lesson_blocks.required`（models.py:789）与
  `lesson_video_blocks.completion_percent`（models.py:823，注释写着「第一版只存不用」）
  两个字段一直是摆设——本次一并激活。

**升级即生效、零行为变化**：`server_default='free'` 让所有存量块落到「自由学习」。
闯关是老师主动去开的开关，不是升级后突然全站生效的默认行为。因此本迁移
**不需要备份表**（对比 0033：那次改写了存量数据，必须可无损回滚；本次只加列加表，
downgrade 直接 drop 即可，不存在「误伤迁移后新建数据」的问题）。

SQLite 加列走 batch_alter_table（整表重建），PostgreSQL 走原生 ALTER——两条路径
都由 batch_alter_table 统一处理，与 0028 同范式。
"""
from alembic import op
import sqlalchemy as sa

revision = "0034_lesson_block_unlock"
down_revision = "0033_lesson_problem_blocks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. 块主表加解锁规则列。server_default 必须给，否则存量行 NOT NULL 会失败。
    with op.batch_alter_table("course_lesson_blocks") as batch:
        batch.add_column(
            sa.Column("unlock_rule", sa.String(length=16), nullable=False, server_default="free")
        )

    # 2. 学习完成记录表
    op.create_table(
        "lesson_block_completions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id", sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "block_id", sa.Integer(),
            sa.ForeignKey("course_lesson_blocks.id", ondelete="CASCADE"), nullable=False,
        ),
        # lesson_id 是**有意的冗余列**：课时详情接口要一次性拿「本课时我完成了哪些块」，
        # 有它就是 WHERE user_id=? AND lesson_id=? 一次索引扫描；没有它每次详情都得
        # join 回 course_lesson_blocks 才能按课时过滤。块删除时 CASCADE 一并清理，
        # 课时删除时也 CASCADE——两条外键都在，冗余不会漂移。
        sa.Column(
            "lesson_id", sa.Integer(),
            sa.ForeignKey("course_lessons.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("source", sa.String(length=16), nullable=False, server_default="manual"),
        sa.Column(
            "completed_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        # 幂等的依据：重复上报撞唯一约束 → 接口层吞掉返回 200（交接文档 §5.3）
        sa.UniqueConstraint("user_id", "block_id", name="uq_block_completion"),
    )
    op.create_index(
        "ix_block_completion_user_lesson", "lesson_block_completions", ["user_id", "lesson_id"]
    )
    op.create_index("ix_block_completion_block", "lesson_block_completions", ["block_id"])

    conn = op.get_bind()
    blocks = conn.execute(sa.text("SELECT COUNT(*) FROM course_lesson_blocks")).scalar_one()
    print(
        f"[0034] 已加列 course_lesson_blocks.unlock_rule（{blocks} 个存量块全部落到 'free'，"
        f"行为零变化）并新建 lesson_block_completions。"
    )


def downgrade() -> None:
    op.drop_index("ix_block_completion_block", table_name="lesson_block_completions")
    op.drop_index("ix_block_completion_user_lesson", table_name="lesson_block_completions")
    op.drop_table("lesson_block_completions")
    with op.batch_alter_table("course_lesson_blocks") as batch:
        batch.drop_column("unlock_rule")
    print("[0034] downgrade：已删除 lesson_block_completions 与 unlock_rule 列。")
