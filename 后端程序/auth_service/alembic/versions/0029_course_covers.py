"""add course_covers for course package cover images

Revision ID: 0029_course_covers
Revises: 0028_video_lesson_binding
Create Date: 2026-08-09

课包封面从「外链 URL 输入」改成「应用内上传」（用户要求：存储位置新开一个区域，
不与题干配图共用 data/media）。这张表登记封面图的存在，结构与 media_assets 一致，
但磁盘根目录和 URL 前缀是独立的一套（/course-covers/），两边清理互不干扰。

纯新增表，downgrade 直接 drop；磁盘上的文件由 cleanup_media.py 负责，不在迁移里动。
"""
from alembic import op
import sqlalchemy as sa

revision = "0029_course_covers"
down_revision = "0028_video_lesson_binding"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "course_covers",
        sa.Column("sha256", sa.String(length=64), primary_key=True),
        sa.Column("ext", sa.String(length=8), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("uploaded_by", sa.Integer(), sa.ForeignKey("admin_users.id"), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_course_covers_last_seen_at", "course_covers", ["last_seen_at"])


def downgrade() -> None:
    op.drop_index("ix_course_covers_last_seen_at", table_name="course_covers")
    op.drop_table("course_covers")
