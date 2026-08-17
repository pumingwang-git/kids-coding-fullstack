"""add alternative accepted answers to fill blanks

Revision ID: 0023_fill_answer_alternatives
Revises: 0022_clear_sample_limits
Create Date: 2026-08-07

一个空往往有多种写法（0.5 与 1/2、列表与 list、增删改查与 CRUD），原来
UNIQUE(problem_id, blank_key) 决定了一个空只能有一个标准答案，判分只能全等比对。
这里给 fill_answers 加一列 JSON 数组存"其它可接受写法"。

null 表示只认标准答案，所以存量数据不用回填——原来的行为就是"只有一个答案"。
"""
from alembic import op
import sqlalchemy as sa

revision = "0023_fill_answer_alternatives"
down_revision = "0022_clear_sample_limits"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("fill_answers", sa.Column("alternatives_json", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("fill_answers", "alternatives_json")
