"""add material management module (资料管理与 Windows 文件夹迁移)

Revision ID: 0031_material_module
Revises: 0030_lesson_content_blocks
Create Date: 2026-08-09

交接文档《12、资料管理与Windows文件夹迁移》§6 数据模型 + 合理补充：

- material_folders            文件夹树（parent_id 懒加载，无 path_cache）
- material_assets             资料文件（display_name 与 object_key 分离）
- material_tags / material_asset_tags   跨目录标签
- lesson_block_materials      阅读资料块与资料库的关联（删除块只删关联）
- material_uploads            普通资料上传会话（presigned_put / multipart）
- material_import_sessions / material_import_items   Windows 文件夹迁移会话与清单

说明：
- material_assets.asset_type 为补充列（交接文档 §6 未列，DEMO 的类型筛选需要）；
- 所有外键 ondelete 语义与应用层一致：文件夹 SET NULL（应用层拒绝删除非空文件夹）、
  资产/标签/块关联 CASCADE、导入项随会话 CASCADE。
"""
import sqlalchemy as sa

from alembic import op

revision = "0031_material_module"
down_revision = "0030_lesson_content_blocks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "material_folders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "parent_id",
            sa.Integer(),
            sa.ForeignKey("material_folders.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("admin_users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        # 同级重名唯一约束：应用层预查防 UX 冲突，数据库约束兜底并发竞态。
        # PostgreSQL 的 UNIQUE 对 NULL 不生效，根目录（parent_id NULL）重名仍由
        # 应用层检查（_sibling_name_taken 对根目录同样生效）。
        sa.UniqueConstraint("parent_id", "name", name="uq_material_folders_parent_name"),
    )
    op.create_index("ix_material_folders_parent_id", "material_folders", ["parent_id"])

    op.create_table(
        "material_assets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "folder_id",
            sa.Integer(),
            sa.ForeignKey("material_folders.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("object_key", sa.String(length=512), nullable=False),
        sa.Column("mime_type", sa.String(length=128), nullable=False, server_default="application/octet-stream"),
        sa.Column("asset_type", sa.String(length=16), nullable=False, server_default="other"),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("sha256", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="uploading"),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("admin_users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_material_assets_folder_id", "material_assets", ["folder_id"])
    op.create_index("ix_material_assets_asset_type", "material_assets", ["asset_type"])
    op.create_index("ix_material_assets_sha256", "material_assets", ["sha256"])
    op.create_index("ix_material_assets_status", "material_assets", ["status"])

    op.create_table(
        "material_tags",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("admin_users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("name", name="uq_material_tags_name"),
    )
    op.create_index("ix_material_tags_name", "material_tags", ["name"])

    op.create_table(
        "material_asset_tags",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("asset_id", sa.Integer(), sa.ForeignKey("material_assets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tag_id", sa.Integer(), sa.ForeignKey("material_tags.id", ondelete="CASCADE"), nullable=False),
        sa.UniqueConstraint("asset_id", "tag_id", name="uq_material_asset_tags"),
    )
    op.create_index("ix_material_asset_tags_asset_id", "material_asset_tags", ["asset_id"])
    op.create_index("ix_material_asset_tags_tag_id", "material_asset_tags", ["tag_id"])

    op.create_table(
        "lesson_block_materials",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("block_id", sa.Integer(), sa.ForeignKey("course_lesson_blocks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("material_id", sa.Integer(), sa.ForeignKey("material_assets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("block_id", "material_id", name="uq_lesson_block_materials"),
    )
    op.create_index("ix_lesson_block_materials_block_id", "lesson_block_materials", ["block_id"])
    op.create_index("ix_lesson_block_materials_material_id", "lesson_block_materials", ["material_id"])

    op.create_table(
        "material_uploads",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("asset_id", sa.Integer(), sa.ForeignKey("material_assets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("uploader_id", sa.Integer(), sa.ForeignKey("admin_users.id"), nullable=True),
        sa.Column("bucket", sa.String(length=64), nullable=False),
        sa.Column("object_key", sa.String(length=512), nullable=False),
        sa.Column("upload_mode", sa.String(length=16), nullable=False, server_default="multipart"),
        sa.Column("upload_id", sa.String(length=256), nullable=True),
        sa.Column("content_type", sa.String(length=128), nullable=False, server_default="application/octet-stream"),
        sa.Column("file_size", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("part_count", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="initiated"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("upload_id", name="uq_material_uploads_upload_id"),
    )
    op.create_index("ix_material_uploads_asset_id", "material_uploads", ["asset_id"])
    op.create_index("ix_material_uploads_status", "material_uploads", ["status"])

    op.create_table(
        "material_import_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_root_name", sa.String(length=255), nullable=False),
        sa.Column(
            "target_folder_id",
            sa.Integer(),
            sa.ForeignKey("material_folders.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("preserve_structure", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("conflict_policy", sa.String(length=16), nullable=False, server_default="skip"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="collecting"),
        sa.Column("total_items", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("summary_json", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("admin_users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_material_import_sessions_status", "material_import_sessions", ["status"])
    op.create_index(
        "ix_material_import_sessions_target_folder_id", "material_import_sessions", ["target_folder_id"]
    )

    op.create_table(
        "material_import_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("session_id", sa.Integer(), sa.ForeignKey("material_import_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("client_id", sa.String(length=64), nullable=False),
        sa.Column("relative_path", sa.String(length=1024), nullable=False),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("mime_type", sa.String(length=128), nullable=False, server_default="application/octet-stream"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("error", sa.String(length=255), nullable=True),
        sa.Column("bucket", sa.String(length=64), nullable=True),
        sa.Column("object_key", sa.String(length=512), nullable=True),
        sa.Column("upload_mode", sa.String(length=16), nullable=True),
        sa.Column("upload_id", sa.String(length=256), nullable=True),
        sa.Column("part_count", sa.Integer(), nullable=True),
        sa.Column("sha256", sa.String(length=64), nullable=True),
        sa.Column("target_folder_id", sa.Integer(), nullable=True),
        sa.Column("asset_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("session_id", "client_id", name="uq_import_items_client_id"),
    )
    op.create_index("ix_material_import_items_session_id", "material_import_items", ["session_id"])
    op.create_index("ix_material_import_items_status", "material_import_items", ["status"])


def downgrade() -> None:
    op.drop_index("ix_material_import_items_status", table_name="material_import_items")
    op.drop_index("ix_material_import_items_session_id", table_name="material_import_items")
    op.drop_table("material_import_items")
    op.drop_index("ix_material_import_sessions_target_folder_id", table_name="material_import_sessions")
    op.drop_index("ix_material_import_sessions_status", table_name="material_import_sessions")
    op.drop_table("material_import_sessions")
    op.drop_index("ix_material_uploads_status", table_name="material_uploads")
    op.drop_index("ix_material_uploads_asset_id", table_name="material_uploads")
    op.drop_table("material_uploads")
    op.drop_index("ix_lesson_block_materials_material_id", table_name="lesson_block_materials")
    op.drop_index("ix_lesson_block_materials_block_id", table_name="lesson_block_materials")
    op.drop_table("lesson_block_materials")
    op.drop_index("ix_material_asset_tags_tag_id", table_name="material_asset_tags")
    op.drop_index("ix_material_asset_tags_asset_id", table_name="material_asset_tags")
    op.drop_table("material_asset_tags")
    op.drop_index("ix_material_tags_name", table_name="material_tags")
    op.drop_table("material_tags")
    op.drop_index("ix_material_assets_status", table_name="material_assets")
    op.drop_index("ix_material_assets_sha256", table_name="material_assets")
    op.drop_index("ix_material_assets_asset_type", table_name="material_assets")
    op.drop_index("ix_material_assets_folder_id", table_name="material_assets")
    op.drop_table("material_assets")
    op.drop_index("ix_material_folders_parent_id", table_name="material_folders")
    op.drop_table("material_folders")
