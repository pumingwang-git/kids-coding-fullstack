"""add media_assets for stem/analysis images

Revision ID: 0024_media_assets
Revises: 0023_fill_answer_alternatives
Create Date: 2026-08-07

题干里一直没法放图：`stem` 上限 50000 字符，base64 内联一张 200KB 的图就是 273KB，
一张图撑爆一道题；理科题（几何、图形推理）因此根本录不进来。

这张表只登记"图存在过"，**不登记它被谁引用**——引用关系在 Markdown 正文的 URL 里。
故意不建 problem_id 外键，理由见 models.MediaAsset 的文档字符串。

纯新增表，downgrade 直接 drop；磁盘上的文件由 cleanup_media.py 负责，不在迁移里动。
"""
from alembic import op
import sqlalchemy as sa

revision = "0024_media_assets"
down_revision = "0023_fill_answer_alternatives"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "media_assets",
        sa.Column("sha256", sa.String(length=64), primary_key=True),
        sa.Column("ext", sa.String(length=8), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("uploaded_by", sa.Integer(), sa.ForeignKey("admin_users.id"), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_media_assets_last_seen_at", "media_assets", ["last_seen_at"])


def downgrade() -> None:
    op.drop_index("ix_media_assets_last_seen_at", table_name="media_assets")
    op.drop_table("media_assets")
