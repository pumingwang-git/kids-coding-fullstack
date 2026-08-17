"""add scratch works (自由作品与作品广场)

Revision ID: 0046_scratch_works
Revises: 0045_scratch_rubric_and_return
Create Date: 2026-08-14
"""
from alembic import op
import sqlalchemy as sa


revision = "0046_scratch_works"
down_revision = "0045_scratch_rubric_and_return"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 自由作品：一人多份、可命名、可公开，公开作品进广场展出。
    # 内容只存当前版本（无版本链）；source 区分 free / challenge（闯关作品分享快照）。
    op.create_table(
        "scratch_works",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("student_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("sb3_key", sa.String(255), nullable=True),
        sa.Column("sha256", sa.String(64), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sprite_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("extensions_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("source", sa.String(16), nullable=False, server_default="free"),
        sa.Column("source_project_id", sa.Integer(), sa.ForeignKey("scratch_projects.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("source_challenge_id", sa.Integer(), sa.ForeignKey("scratch_challenges.id", ondelete="SET NULL"), nullable=True),
        # PG 布尔列默认值不能用 1（DatatypeMismatch），SQLite 也认 true 字面量。
        sa.Column("is_public", sa.Boolean(), nullable=False, server_default=sa.text("true"), index=True),
        sa.Column("views", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("scratch_works")
