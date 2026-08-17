"""add videos / video_uploads / video_variants for the HLS video module

Revision ID: 0026_video_module
Revises: 0025_problem_dry_runs
Create Date: 2026-08-08

三张表支撑「后台上传 + 转码 + 学生播放」：
- videos：课时视频逻辑记录（lesson_id 为逻辑引用，课程模块尚未后端化）。
- video_uploads：一次 MinIO multipart 上传会话。
- video_variants：一个清晰度档位 = 一个 HLS 目录（master.m3u8 所在目录）。

Video.primary_variant_id 与 VideoVariant.video_id 形成循环外键，
因此 videos 先不带该 FK 建表，video_variants 建好后再补加。
纯新增表，downgrade 直接 drop。
"""
from alembic import op
import sqlalchemy as sa

revision = "0026_video_module"
down_revision = "0025_problem_dry_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "videos",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        # 逻辑引用课程模块：本期不建 FK，待课程模块后端化再接真表。
        sa.Column("lesson_id", sa.Integer(), nullable=True),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("admin_users.id"), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        # 循环外键，先建普通列，video_variants 建好后再补 FK。
        sa.Column("primary_variant_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )
    op.create_index("ix_videos_lesson_id", "videos", ["lesson_id"])
    op.create_index("ix_videos_owner_id", "videos", ["owner_id"])
    op.create_index("ix_videos_status", "videos", ["status"])

    op.create_table(
        "video_variants",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("video_id", sa.Integer(), sa.ForeignKey("videos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("bucket", sa.String(length=64), nullable=False),
        # master.m3u8 的完整 key；其所在目录内含子列表与 .ts 切片。
        sa.Column("object_key", sa.String(length=512), nullable=False),
        sa.Column("resolution", sa.String(length=16), nullable=False),
        sa.Column("bitrate_kbps", sa.Integer(), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_video_variants_video_id", "video_variants", ["video_id"])
    op.create_index("ix_video_variants_status", "video_variants", ["status"])

    op.create_foreign_key(
        "fk_videos_primary_variant_id", "videos", "video_variants",
        ["primary_variant_id"], ["id"],
    )

    op.create_table(
        "video_uploads",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("video_id", sa.Integer(), sa.ForeignKey("videos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("uploader_id", sa.Integer(), sa.ForeignKey("admin_users.id"), nullable=True),
        sa.Column("bucket", sa.String(length=64), nullable=False),
        sa.Column("object_key", sa.String(length=512), nullable=False),
        sa.Column("upload_id", sa.String(length=256), nullable=False),
        sa.Column("content_type", sa.String(length=128), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=True),
        sa.Column("part_count", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.UniqueConstraint("upload_id", name="uq_video_uploads_upload_id"),
    )
    op.create_index("ix_video_uploads_video_id", "video_uploads", ["video_id"])
    op.create_index("ix_video_uploads_status", "video_uploads", ["status"])


def downgrade() -> None:
    op.drop_table("video_uploads")
    op.drop_constraint("fk_videos_primary_variant_id", "videos", type_="foreignkey")
    op.drop_table("video_variants")
    op.drop_table("videos")
