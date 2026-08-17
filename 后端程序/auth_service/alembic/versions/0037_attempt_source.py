"""paper_attempts 作答来源改造（X1）

Revision ID: 0037_attempt_source
Revises: 0036_lesson_code_runs
Create Date: 2026-08-10

《16、paper_attempts 作答来源改造设计（X1）》第五节。

把「一次作答」从考试链接上解绑：加 (source_type, source_id) 作为权威身份，
`exam_link_id` 改可空退化为考试来源的冗余外键。

**唯一约束换成不含可空列的复合键**（设计文档第二节）：
    旧：UNIQUE(exam_link_id, user_id, attempt_no)
    新：UNIQUE(source_type, source_id, user_id, attempt_no)
计划评测报告 P0 风险 1 担心的是「exam_link_id 改可空后 NULL 在唯一索引里互不相等，
非考试来源的作答完全失去唯一性保护」，并建议用部分唯一索引绕开。本迁移改为把可空列
**从键里彻底拿掉**——比绕开更干净，两库行为一致，加新来源时也不用再补索引。

**paper_attempts 承载真实成绩，改动窗口只有一次**（评测报告第三条纪律）。
因此四条数据保全断言写进迁移体内，失败即整个事务回滚，不依赖人工核对。

双库：Alembic 的 batch_alter_table 在 SQLite 上整表重建、在 PostgreSQL 上退化为
原生 ALTER，两库共用同一套代码。**回填必须在放开 NOT NULL 之前**：先回填、再放开，
中间任何一步失败都不会留下 source_id=0 的孤儿行。
"""
from alembic import op
import sqlalchemy as sa

revision = "0037_attempt_source"
down_revision = "0036_lesson_code_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    before = conn.execute(sa.text("SELECT COUNT(*) FROM paper_attempts")).scalar_one()
    score_before = conn.execute(
        sa.text("SELECT COALESCE(SUM(total_score), 0) FROM paper_attempts")
    ).scalar_one()

    # 1. 加两列（带 server_default，存量行才填得上）
    with op.batch_alter_table("paper_attempts") as batch:
        batch.add_column(sa.Column("source_type", sa.String(16), nullable=False,
                                   server_default="exam_link"))
        batch.add_column(sa.Column("source_id", sa.Integer(), nullable=False,
                                   server_default="0"))

    # 2. 回填 —— 必须在放开 exam_link_id 的 NOT NULL 之前
    op.execute("UPDATE paper_attempts SET source_id = exam_link_id")

    # 3. 数据保全断言（回填后、结构再动之前）
    orphan = conn.execute(
        sa.text("SELECT COUNT(*) FROM paper_attempts WHERE source_id = 0")
    ).scalar_one()
    matched = conn.execute(
        sa.text("SELECT COUNT(*) FROM paper_attempts WHERE source_id = exam_link_id")
    ).scalar_one()
    typed = conn.execute(
        sa.text("SELECT COUNT(*) FROM paper_attempts WHERE source_type = 'exam_link'")
    ).scalar_one()
    if orphan != 0:
        raise RuntimeError(f"[0037] 回填后仍有 {orphan} 行 source_id=0，迁移中止")
    if matched != before:
        raise RuntimeError(f"[0037] source_id 与 exam_link_id 不一致：{matched}/{before}")
    if typed != before:
        raise RuntimeError(f"[0037] source_type 未全部落到 exam_link：{typed}/{before}")

    # 4. exam_link_id 改可空 + 换唯一约束（SQLite 在这里整表重建）
    with op.batch_alter_table("paper_attempts") as batch:
        batch.alter_column("exam_link_id", existing_type=sa.Integer(), nullable=True)
        batch.drop_constraint("uq_paper_attempts", type_="unique")
        batch.create_unique_constraint(
            "uq_attempt_source", ["source_type", "source_id", "user_id", "attempt_no"]
        )

    op.create_index("ix_attempt_source", "paper_attempts", ["source_type", "source_id"])

    # 5. 重建后再核一次行数与总分：SQLite 整表重建是真的在搬数据
    after = conn.execute(sa.text("SELECT COUNT(*) FROM paper_attempts")).scalar_one()
    score_after = conn.execute(
        sa.text("SELECT COALESCE(SUM(total_score), 0) FROM paper_attempts")
    ).scalar_one()
    if after != before:
        raise RuntimeError(f"[0037] 重建前后行数不一致：{before} → {after}")
    if score_after != score_before:
        raise RuntimeError(f"[0037] 重建前后总分不一致：{score_before} → {score_after}")
    print(f"[0037] 作答来源改造完成：{after} 条作答全部落到 source_type='exam_link'，"
          f"总分校验通过（{score_after}）。")


def downgrade() -> None:
    conn = op.get_bind()
    # 已经有非考试来源的作答时不可降级：exam_link_id 改回 NOT NULL 会直接违约，
    # 而那些作答本身没有对应的 exam_link 可填。宁可拒绝，也不静默丢数据。
    foreign = conn.execute(
        sa.text("SELECT COUNT(*) FROM paper_attempts WHERE source_type <> 'exam_link'")
    ).scalar_one()
    if foreign:
        raise RuntimeError(
            f"[0037] 存在 {foreign} 条非考试来源的作答，无法降级"
            f"（exam_link_id 改回 NOT NULL 会丢掉它们的来源）。请先清理后再降级。"
        )

    op.drop_index("ix_attempt_source", table_name="paper_attempts")
    with op.batch_alter_table("paper_attempts") as batch:
        batch.drop_constraint("uq_attempt_source", type_="unique")
        batch.create_unique_constraint(
            "uq_paper_attempts", ["exam_link_id", "user_id", "attempt_no"]
        )
        batch.alter_column("exam_link_id", existing_type=sa.Integer(), nullable=False)
        batch.drop_column("source_id")
        batch.drop_column("source_type")
    print("[0037] downgrade：已恢复 exam_link_id NOT NULL 与旧唯一约束。")
