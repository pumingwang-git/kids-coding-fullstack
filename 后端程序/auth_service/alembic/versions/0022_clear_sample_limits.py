"""clear per-case limits on sample test cases

Revision ID: 0022_clear_sample_limits
Revises: 0021_testcase_limits
Create Date: 2026-08-07

样例改为恒继承题目级限制（录入界面已撤掉样例那两个输入框），存量里若有样例带着
逐点值，它仍会在自测时生效，而界面上再也改不到——是个看不见也修不掉的状态。
这里把它清干净。列本身保留，隐藏测试点仍然用得上。
"""
from alembic import op
import sqlalchemy as sa

revision = "0022_clear_sample_limits"
down_revision = "0021_testcase_limits"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 写成裸的 WHERE is_sample 而不是 = true：PostgreSQL 与 SQLite 都吃这一种写法
    op.execute(sa.text(
        "UPDATE test_cases SET time_limit_ms = NULL, memory_limit_mb = NULL WHERE is_sample"
    ))


def downgrade() -> None:
    """数据清理无法回退：被清掉的值没有留档，也不该留档（新口径下它本就不该存在）。"""
