"""add lesson problem blocks (课中练习单题化)

Revision ID: 0033_lesson_problem_blocks
Revises: 0032_lesson_open_policy
Create Date: 2026-08-10

课中练习单题化（《课中练习重构-实现计划-v2-2026-08-10》§3.1 / §6.1）：
- 新建 lesson_problem_blocks：课中练习（practice）块从「绑一张卷」改为「绑题库单题」，
  与块主表 course_lesson_blocks 1:1；`problem_id_no` 沿用 paper_questions 逻辑引用范式
  （故意不建外键），`problem_type` 为冗余快照（仅管理端列表展示/筛选，判分以题库实际值为准）；
- 存量 practice 块就地改写为 homework（老板拍板 Q6：**含无 lesson_paper_blocks 明细的
  脏数据块一并改写**）：
  1. lesson_paper_blocks.mode：'practice' → 'homework'（先改明细，再改主表，保证双写一致）；
  2. course_lesson_blocks.block_type：'practice' → 'homework'（全部 practice 块，含无明细块）；
  3. due_at 保持 NULL 不限时（Q4）：本迁移**不改动任何 due_at 值**；
- 课中练习单题块无存量数据（从零开始建，不涉及单题数据迁移）。

**downgrade 无损方案（备份表）**：upgrade 先把被改写的块清单（block_id / lesson_id /
title / paper_id / mode / attempt_limit / shuffle_questions / shuffle_options /
show_score / show_analysis / due_at，主表 LEFT JOIN 明细）落进备份表
`_mig0033_rewritten_blocks`，downgrade 只还原备份清单内的 block_id——迁移前就存在的
homework 与迁移后老师新建的 homework 均不被误伤，且对账清单随备份表自带，无需迁移前
手工导出存档（实现计划 v2 §6.3 / §6.4 的回滚路径由迁移自己撑起）。
若备份表缺失（极端：被手工清理），downgrade 退化为全量逆 UPDATE 并打印告警。

沿 0030 迁移范式：原生 SQL（不用 ORM）、建表 + 数据改写同一迁移。
"""
from alembic import op
import sqlalchemy as sa

revision = "0033_lesson_problem_blocks"
down_revision = "0032_lesson_open_policy"
branch_labels = None
depends_on = None


def _create_problem_blocks_table() -> None:
    op.create_table(
        "lesson_problem_blocks",
        sa.Column(
            "block_id",
            sa.Integer(),
            sa.ForeignKey("course_lesson_blocks.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("problem_id_no", sa.String(length=64), nullable=False),
        sa.Column("problem_type", sa.String(length=24), nullable=False),
        sa.Column("display_no", sa.String(length=32), nullable=True),
        sa.Column("score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("attempt_limit", sa.Integer(), nullable=True),
        sa.Column("shuffle_options", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("show_analysis", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "ix_lesson_problem_blocks_problem_id_no", "lesson_problem_blocks", ["problem_id_no"]
    )
    op.create_index(
        "ix_lesson_problem_blocks_problem_type", "lesson_problem_blocks", ["problem_type"]
    )


def _create_backup_table() -> None:
    """备份表：记录被改写的块清单（全配置字段），支撑 downgrade 无损还原与对账存档。"""
    op.create_table(
        "_mig0033_rewritten_blocks",
        sa.Column("block_id", sa.Integer(), primary_key=True),
        sa.Column("lesson_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("paper_id", sa.Integer(), nullable=True),
        sa.Column("mode", sa.String(length=16), nullable=True),
        sa.Column("attempt_limit", sa.Integer(), nullable=True),
        sa.Column("shuffle_questions", sa.Boolean(), nullable=True),
        sa.Column("shuffle_options", sa.Boolean(), nullable=True),
        sa.Column("show_score", sa.Boolean(), nullable=True),
        sa.Column("show_analysis", sa.Boolean(), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
    )


def _reconcile(conn, stage: str, practice_main: int, practice_detail: int, affected_lesson_ids) -> None:
    """对账输出（§6.1 第 4 条）：改写前后行数、受影响课时清单，以及备份表完整清单（供存档/回滚核对）。"""
    rows = conn.execute(
        sa.text(
            "SELECT block_id, lesson_id, title, paper_id, mode, attempt_limit, "
            "shuffle_questions, shuffle_options, show_score, show_analysis, due_at "
            "FROM _mig0033_rewritten_blocks ORDER BY block_id"
        )
    ).all()
    print(
        f"[0033] {stage} 对账：practice 主表 {practice_main} 行、明细 {practice_detail} 行 → homework；"
        f"受影响课时（{len(affected_lesson_ids)} 个）：{list(affected_lesson_ids)}"
    )
    print(
        f"[0033] 改写清单已存档（备份表 _mig0033_rewritten_blocks，{len(rows)} 行，"
        f"downgrade 按此清单无损还原）："
    )
    for r in rows:
        print(
            f"[0033]   block_id={r.block_id} lesson_id={r.lesson_id} title={r.title!r} "
            f"paper_id={r.paper_id} mode={r.mode} attempt_limit={r.attempt_limit} "
            f"shuffle_questions={r.shuffle_questions} shuffle_options={r.shuffle_options} "
            f"show_score={r.show_score} show_analysis={r.show_analysis} due_at={r.due_at}"
        )


def upgrade() -> None:
    _create_problem_blocks_table()
    _create_backup_table()
    conn = op.get_bind()
    practice_main = conn.execute(
        sa.text("SELECT COUNT(*) FROM course_lesson_blocks WHERE block_type = 'practice'")
    ).scalar_one()
    practice_detail = conn.execute(
        sa.text("SELECT COUNT(*) FROM lesson_paper_blocks WHERE mode = 'practice'")
    ).scalar_one()
    affected_lesson_ids = conn.execute(
        sa.text(
            "SELECT DISTINCT lesson_id FROM course_lesson_blocks "
            "WHERE block_type = 'practice' ORDER BY lesson_id"
        )
    ).scalars().all()

    # 0. 先落盘改写清单（主表 practice 块 LEFT JOIN 明细，无明细脏数据块的 paper_* 列为 NULL）
    conn.execute(
        sa.text(
            "INSERT INTO _mig0033_rewritten_blocks "
            "(block_id, lesson_id, title, paper_id, mode, attempt_limit, "
            " shuffle_questions, shuffle_options, show_score, show_analysis, due_at) "
            "SELECT b.id, b.lesson_id, b.title, p.paper_id, p.mode, p.attempt_limit, "
            "       p.shuffle_questions, p.shuffle_options, p.show_score, p.show_analysis, p.due_at "
            "FROM course_lesson_blocks b "
            "LEFT JOIN lesson_paper_blocks p ON p.block_id = b.id "
            "WHERE b.block_type = 'practice'"
        )
    )

    # 1. 先改明细 mode：practice → homework（只对有明细的块）
    op.execute("UPDATE lesson_paper_blocks SET mode = 'homework' WHERE mode = 'practice'")
    # 2. 再改主表 block_type：practice → homework
    #    - 有明细的块：其 lesson_paper_blocks.mode 此时已是 homework，双写一致；
    #    - 无明细的 practice 脏数据块（Q6 已定）：一并改写，保持「课中练习从零建」的干净边界
    #      （此类块发布检查照旧被 paper_missing_detail 拦截，老师迁移后按需补绑定）。
    op.execute("UPDATE course_lesson_blocks SET block_type = 'homework' WHERE block_type = 'practice'")

    _reconcile(conn, "upgrade", practice_main, practice_detail, affected_lesson_ids)


def downgrade() -> None:
    conn = op.get_bind()
    from sqlalchemy import inspect

    backup_exists = inspect(conn).has_table("_mig0033_rewritten_blocks")
    if backup_exists:
        # 无损路径：只还原备份清单内的块（迁移前就存在的 homework、迁移后新建的 homework 均不动）。
        restored = conn.execute(
            sa.text(
                "SELECT block_id, lesson_id, title, paper_id, mode, due_at "
                "FROM _mig0033_rewritten_blocks ORDER BY block_id"
            )
        ).all()
        op.execute(
            "UPDATE course_lesson_blocks SET block_type = 'practice' "
            "WHERE id IN (SELECT block_id FROM _mig0033_rewritten_blocks)"
        )
        op.execute(
            "UPDATE lesson_paper_blocks SET mode = 'practice' "
            "WHERE block_id IN (SELECT block_id FROM _mig0033_rewritten_blocks) "
            "  AND mode = 'homework'"
        )
        print(
            f"[0033] downgrade 按备份表无损还原 {len(restored)} 个块"
            f"（迁移前已有 homework / 迁移后新建 homework 不受影响）："
        )
        for r in restored:
            print(
                f"[0033]   block_id={r.block_id} lesson_id={r.lesson_id} title={r.title!r} "
                f"paper_id={r.paper_id} mode={r.mode} due_at={r.due_at}"
            )
    else:
        # 退化路径（备份表缺失，极端情况）：全量逆 UPDATE 有损，打印告警要求按存档人工恢复。
        homework_main = conn.execute(
            sa.text("SELECT COUNT(*) FROM course_lesson_blocks WHERE block_type = 'homework'")
        ).scalar_one()
        homework_detail = conn.execute(
            sa.text("SELECT COUNT(*) FROM lesson_paper_blocks WHERE mode = 'homework'")
        ).scalar_one()
        op.execute("UPDATE course_lesson_blocks SET block_type = 'practice' WHERE block_type = 'homework'")
        op.execute("UPDATE lesson_paper_blocks SET mode = 'practice' WHERE mode = 'homework'")
        print(
            f"[0033] [警告] 备份表 _mig0033_rewritten_blocks 不存在，downgrade 退化为有损全量逆 UPDATE"
            f"（homework 主表 {homework_main} 行、明细 {homework_detail} 行改回 practice，"
            f"含迁移后新建的 homework——请按迁移前存档清单人工恢复）。"
        )

    # 1. drop 新表（含两个索引）
    op.drop_index("ix_lesson_problem_blocks_problem_type", table_name="lesson_problem_blocks")
    op.drop_index("ix_lesson_problem_blocks_problem_id_no", table_name="lesson_problem_blocks")
    op.drop_table("lesson_problem_blocks")
    if backup_exists:
        op.drop_table("_mig0033_rewritten_blocks")
        print("[0033] 备份表 _mig0033_rewritten_blocks 已随 downgrade 清理。")
