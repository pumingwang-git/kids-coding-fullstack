"""split exam scheduling out of papers into exam_links (试卷/链接两层模型)

Revision ID: 0018_exam_links
Revises: 0017_papers
Create Date: 2026-08-05

原设计把考试时间与访问 token 直接挂在 papers 上，一张卷只能有一条链接、一个
时间窗口。改为两层：papers 只管内容与判分口径，exam_links 是一次考试安排。

数据迁移：已发布（有 access_token）的试卷，其现有 token 与时间/呈现配置整体
搬成一条名为「默认链接」的记录，线上已发出去的链接不会失效。
"""
from alembic import op
import sqlalchemy as sa

revision = "0018_exam_links"
down_revision = "0017_papers"
branch_labels = None
depends_on = None

# 从 papers 迁往 exam_links 的列。顺序与 INSERT ... SELECT 一一对应。
MOVED = [
    "access_token", "open_at", "close_at", "duration_minutes", "late_start_policy",
    "attempt_limit", "score_policy", "penalty_minutes", "feedback_mode",
    "show_analysis", "show_score", "shuffle_questions", "shuffle_options",
]


def upgrade() -> None:
    op.create_table(
        "exam_links",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("paper_id", sa.Integer(), sa.ForeignKey("papers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("access_token", sa.String(length=32), nullable=False, unique=True),
        sa.Column("open_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("close_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_minutes", sa.Integer(), nullable=True),
        sa.Column("late_start_policy", sa.String(length=16), nullable=False, server_default="truncate"),
        sa.Column("attempt_limit", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("score_policy", sa.String(length=16), nullable=False, server_default="best"),
        sa.Column("penalty_minutes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("feedback_mode", sa.String(length=16), nullable=False, server_default="realtime"),
        sa.Column("show_analysis", sa.String(length=16), nullable=False, server_default="after_submit"),
        sa.Column("show_score", sa.String(length=16), nullable=False, server_default="immediate"),
        sa.Column("shuffle_questions", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("shuffle_options", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("admin_users.id"), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("paper_id", "name", name="uq_exam_links_name"),
    )
    op.create_index("ix_exam_links_paper_id", "exam_links", ["paper_id"])
    op.create_index("ix_exam_links_status", "exam_links", ["status"])

    # 已发布卷的现有链接配置整体搬过来，线上已流传的 URL 保持有效。
    # 归档卷的链接建成 disabled——归档即锁定的语义要贯穿两层。
    cols = ", ".join(MOVED)
    op.execute(sa.text(f"""
        INSERT INTO exam_links (paper_id, name, {cols}, status, created_by)
        SELECT id, '默认链接', {cols},
               CASE WHEN status = 'archived' THEN 'disabled' ELSE 'active' END,
               created_by
        FROM papers
        WHERE access_token IS NOT NULL
    """))

    with op.batch_alter_table("papers") as batch:
        for column in MOVED:
            batch.drop_column(column)


def downgrade() -> None:
    with op.batch_alter_table("papers") as batch:
        batch.add_column(sa.Column("access_token", sa.String(length=32), nullable=True))
        batch.add_column(sa.Column("open_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("close_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("duration_minutes", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("late_start_policy", sa.String(length=16), nullable=False, server_default="truncate"))
        batch.add_column(sa.Column("attempt_limit", sa.Integer(), nullable=False, server_default="1"))
        batch.add_column(sa.Column("score_policy", sa.String(length=16), nullable=False, server_default="best"))
        batch.add_column(sa.Column("penalty_minutes", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("feedback_mode", sa.String(length=16), nullable=False, server_default="realtime"))
        batch.add_column(sa.Column("show_analysis", sa.String(length=16), nullable=False, server_default="after_submit"))
        batch.add_column(sa.Column("show_score", sa.String(length=16), nullable=False, server_default="immediate"))
        batch.add_column(sa.Column("shuffle_questions", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.add_column(sa.Column("shuffle_options", sa.Boolean(), nullable=False, server_default=sa.false()))

    # 一卷多链接无法逆向表达，只能取最早的一条回填；其余链接的配置会丢失。
    for column in MOVED:
        op.execute(sa.text(f"""
            UPDATE papers SET {column} = (
                SELECT e.{column} FROM exam_links e
                WHERE e.paper_id = papers.id
                ORDER BY e.id LIMIT 1
            )
            WHERE EXISTS (SELECT 1 FROM exam_links e WHERE e.paper_id = papers.id)
        """))

    op.drop_table("exam_links")
