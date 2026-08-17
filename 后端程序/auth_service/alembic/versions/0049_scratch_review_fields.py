"""scratch_challenges 审核人记录与打回原因（对齐 problems 表）

Revision ID: 0049_scratch_review_fields
Revises: 0048_lesson_code_run_charged
Create Date: 2026-08-15

Scratch 挑战的审核此前不落库：approve 不写审核人、reject 不收原因，列表与详情都
无法追溯"谁审的、为什么退"。这与既有题目（problems.reviewed_by / rejected_by /
rejection_reason）不一致。本迁移补齐四个字段：

- reviewed_by / reviewed_at：approve 时落审核人与时间；
- rejected_by / rejected_at / rejection_reason：reject 必填原因落库，
  列表行可显示 ⚑ 打回标志（与题库同款交互）。

存量数据全部 NULL：历史挑战没有审核记录可回填，保持空即可。
"""
import sqlalchemy as sa

from alembic import op

revision = "0049_scratch_review_fields"
down_revision = "0048_lesson_code_run_charged"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("scratch_challenges", sa.Column("reviewed_by", sa.Integer(), nullable=True))
    op.add_column("scratch_challenges", sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("scratch_challenges", sa.Column("rejected_by", sa.Integer(), nullable=True))
    op.add_column("scratch_challenges", sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("scratch_challenges", sa.Column("rejection_reason", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("scratch_challenges", "rejection_reason")
    op.drop_column("scratch_challenges", "rejected_at")
    op.drop_column("scratch_challenges", "rejected_by")
    op.drop_column("scratch_challenges", "reviewed_at")
    op.drop_column("scratch_challenges", "reviewed_by")
