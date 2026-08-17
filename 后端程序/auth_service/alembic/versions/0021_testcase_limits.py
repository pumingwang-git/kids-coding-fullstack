"""add per-test-case time/memory limits

Revision ID: 0021_testcase_limits
Revises: 0020_exam_attempts
Create Date: 2026-08-07

让编程题的每个测试点都能单独设时间/内存限制（测试点独立时空限制特性）。
null = 继承题目级（ProgrammingDetail 的同名字段），所以存量数据天然语义正确，
不需要回填。见《测试点独立时空限制-交接》§2。
"""
from alembic import op
import sqlalchemy as sa

revision = "0021_testcase_limits"
down_revision = "0020_exam_attempts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("test_cases", sa.Column("time_limit_ms", sa.Integer(), nullable=True))
    op.add_column("test_cases", sa.Column("memory_limit_mb", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("test_cases", "memory_limit_mb")
    op.drop_column("test_cases", "time_limit_ms")
