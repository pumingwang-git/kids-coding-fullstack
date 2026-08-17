"""add lesson content blocks (积木化编排)

Revision ID: 0030_lesson_content_blocks
Revises: 0029_course_covers
Create Date: 2026-08-09

课包内容积木化编排的数据层（交接文档 §5）：把 `course_lessons` 上固定的
「单份 content_md / 单平台视频 / 单外链」升级为「0..N 有序内容块 + 类型明细」。

- 主表 course_lesson_blocks：块级公共字段（block_type / title / sort_order / required）；
- 三张明细表：lesson_markdown_blocks、lesson_video_blocks、lesson_paper_blocks，各与主表 1:1。

回填规则（§5.3，顺序固定为 图文 → 平台视频 → 外链视频，避免迁移结果不确定）：
1. content_md 非空 → markdown 块；
2. video_id 非空 → platform video 块；
3. video_url 非空 → external video 块。

**downgrade 无损**：旧列 content_md / video_id / video_url 本迁移**不删除**，
回填数据都来自它们；降级只需 drop 新表，旧数据仍完整留在 course_lessons 上。
旧列删除放到新链路稳定后的独立迁移（§5.3 第 8 条）。
"""
from alembic import op
import sqlalchemy as sa

revision = "0030_lesson_content_blocks"
down_revision = "0029_course_covers"
branch_labels = None
depends_on = None


def _create_tables() -> None:
    op.create_table(
        "course_lesson_blocks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("lesson_id", sa.Integer(), sa.ForeignKey("course_lessons.id", ondelete="CASCADE"), nullable=False),
        sa.Column("block_type", sa.String(length=16), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("required", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("lesson_id", "sort_order", name="uq_lesson_blocks_order"),
    )
    op.create_index("ix_course_lesson_blocks_lesson_id", "course_lesson_blocks", ["lesson_id"])
    op.create_index("ix_course_lesson_blocks_block_type", "course_lesson_blocks", ["block_type"])

    op.create_table(
        "lesson_markdown_blocks",
        sa.Column("block_id", sa.Integer(), sa.ForeignKey("course_lesson_blocks.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("content_md", sa.Text(), nullable=False, server_default=""),
    )

    op.create_table(
        "lesson_video_blocks",
        sa.Column("block_id", sa.Integer(), sa.ForeignKey("course_lesson_blocks.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("source_type", sa.String(length=16), nullable=False, server_default="platform"),
        sa.Column("video_id", sa.Integer(), sa.ForeignKey("videos.id"), nullable=True),
        sa.Column("video_url", sa.String(length=512), nullable=True),
        sa.Column("completion_percent", sa.Integer(), nullable=False, server_default="100"),
    )

    op.create_table(
        "lesson_paper_blocks",
        sa.Column("block_id", sa.Integer(), sa.ForeignKey("course_lesson_blocks.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("paper_id", sa.Integer(), sa.ForeignKey("papers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("mode", sa.String(length=16), nullable=False, server_default="practice"),
        sa.Column("attempt_limit", sa.Integer(), nullable=True),
        sa.Column("shuffle_questions", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("shuffle_options", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("show_score", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("show_analysis", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_lesson_paper_blocks_paper_id", "lesson_paper_blocks", ["paper_id"])


def _backfill_legacy_lessons() -> None:
    """把旧课时行上的单份内容回填成块（§5.3 第 1～4 条）。

    用原生 SQL 而不是 ORM：迁移运行在没有任何业务代码依赖的裸环境下，
    ORM 模型的字段变更可能比迁移文件先被加载，导致回填读到错误的列集合。
    """
    conn = op.get_bind()
    rows = conn.execute(
        sa.text(
            "SELECT l.id AS lesson_id, l.title AS lesson_title, "
            "l.content_md, l.video_id, l.video_url, v.title AS video_title "
            "FROM course_lessons l LEFT JOIN videos v ON v.id = l.video_id "
            "ORDER BY l.id"
        )
    ).mappings().all()
    insert_block = sa.text(
        "INSERT INTO course_lesson_blocks "
        "(lesson_id, block_type, title, sort_order, required) "
        "VALUES (:lesson_id, :block_type, :title, :sort_order, TRUE) "
        "RETURNING id"
    )
    for lesson in rows:
        order = 0
        if lesson["content_md"]:
            block_id = conn.execute(
                insert_block,
                {
                    "lesson_id": lesson["lesson_id"],
                    "block_type": "markdown",
                    "title": lesson["lesson_title"],
                    "sort_order": order,
                },
            ).scalar_one()
            conn.execute(
                sa.text("INSERT INTO lesson_markdown_blocks (block_id, content_md) VALUES (:block_id, :content_md)"),
                {"block_id": block_id, "content_md": lesson["content_md"]},
            )
            order += 1
        if lesson["video_id"] is not None:
            block_id = conn.execute(
                insert_block,
                {
                    "lesson_id": lesson["lesson_id"],
                    "block_type": "video",
                    "title": lesson["video_title"] or lesson["lesson_title"],
                    "sort_order": order,
                },
            ).scalar_one()
            conn.execute(
                sa.text(
                    "INSERT INTO lesson_video_blocks (block_id, source_type, video_id, video_url, completion_percent) "
                    "VALUES (:block_id, 'platform', :video_id, NULL, 100)"
                ),
                {"block_id": block_id, "video_id": lesson["video_id"]},
            )
            order += 1
        if lesson["video_url"]:
            block_id = conn.execute(
                insert_block,
                {
                    "lesson_id": lesson["lesson_id"],
                    "block_type": "video",
                    "title": lesson["lesson_title"],
                    "sort_order": order,
                },
            ).scalar_one()
            conn.execute(
                sa.text(
                    "INSERT INTO lesson_video_blocks (block_id, source_type, video_id, video_url, completion_percent) "
                    "VALUES (:block_id, 'external', NULL, :video_url, 100)"
                ),
                {"block_id": block_id, "video_url": lesson["video_url"]},
            )
            order += 1


def upgrade() -> None:
    _create_tables()
    _backfill_legacy_lessons()


def downgrade() -> None:
    # 无损降级：旧列仍在 course_lessons 上，回填数据可完全还原，只 drop 新表。
    op.drop_index("ix_lesson_paper_blocks_paper_id", table_name="lesson_paper_blocks")
    op.drop_table("lesson_paper_blocks")
    op.drop_table("lesson_video_blocks")
    op.drop_table("lesson_markdown_blocks")
    op.drop_index("ix_course_lesson_blocks_block_type", table_name="course_lesson_blocks")
    op.drop_index("ix_course_lesson_blocks_lesson_id", table_name="course_lesson_blocks")
    op.drop_table("course_lesson_blocks")
