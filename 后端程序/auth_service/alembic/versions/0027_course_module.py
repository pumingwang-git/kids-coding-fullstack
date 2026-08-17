"""add courses / course_categories / course_sections / course_lessons

Revision ID: 0027_course_module
Revises: 0026_video_module
Create Date: 2026-08-09

课包最小闭环的四张表（命名按《7、后台课包-课程管理模块》第六节，以 ERD 为准）：
- course_categories：课包分类。
- courses：课包基本信息与发布状态（draft/published/off_shelf）。
- course_sections：章节，级联删除课时。
- course_lessons：课时，video_id 外键指向 videos.id（课时绑定视频）；
  videos.lesson_id 是旧逻辑引用，不建 FK、保持不变。

纯新增表，downgrade 直接 drop（注意 FK 顺序：先 drop course_lessons，
再 course_sections / courses / course_categories）。
"""
from alembic import op
import sqlalchemy as sa

revision = "0027_course_module"
down_revision = "0026_video_module"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "course_categories",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=50), nullable=False, unique=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "courses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("subtitle", sa.String(length=300), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("cover_url", sa.String(length=512), nullable=True),
        sa.Column("category_id", sa.Integer(),
                  sa.ForeignKey("course_categories.id", ondelete="SET NULL"), nullable=True),
        sa.Column("difficulty", sa.String(length=16), nullable=False, server_default="beginner"),
        sa.Column("price_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="draft"),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("admin_users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_courses_category_id", "courses", ["category_id"])
    op.create_index("ix_courses_status", "courses", ["status"])

    op.create_table(
        "course_sections",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("course_id", sa.Integer(),
                  sa.ForeignKey("courses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_course_sections_course_id", "course_sections", ["course_id"])

    op.create_table(
        "course_lessons",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("course_id", sa.Integer(),
                  sa.ForeignKey("courses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("section_id", sa.Integer(),
                  sa.ForeignKey("course_sections.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("summary", sa.String(length=500), nullable=True),
        sa.Column("content_md", sa.Text(), nullable=True),
        sa.Column("video_id", sa.Integer(), sa.ForeignKey("videos.id"), nullable=True),
        sa.Column("video_url", sa.String(length=512), nullable=True),
        sa.Column("duration_minutes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_trial", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_course_lessons_course_id", "course_lessons", ["course_id"])
    op.create_index("ix_course_lessons_section_id", "course_lessons", ["section_id"])


def downgrade() -> None:
    op.drop_index("ix_course_lessons_section_id", table_name="course_lessons")
    op.drop_index("ix_course_lessons_course_id", table_name="course_lessons")
    op.drop_table("course_lessons")
    op.drop_index("ix_course_sections_course_id", table_name="course_sections")
    op.drop_table("course_sections")
    op.drop_index("ix_courses_status", table_name="courses")
    op.drop_index("ix_courses_category_id", table_name="courses")
    op.drop_table("courses")
    op.drop_table("course_categories")
