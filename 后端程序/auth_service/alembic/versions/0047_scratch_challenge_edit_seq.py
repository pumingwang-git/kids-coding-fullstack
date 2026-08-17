"""scratch challenge edit_seq（发布版次与编辑序号拆分）

Revision ID: 0047_scratch_challenge_edit_seq
Revises: 0046_scratch_works
Create Date: 2026-08-15

`version` 曾经身兼两职：发布版次（冻结进学生提交）+ 草稿乐观锁计数。
后果是编辑 N 次草稿再首发，冻结的 challenge_version 是 N+1，"第几版发布"
的审计口径被编辑次数污染。拆出 `edit_seq` 专管乐观锁，`version` 回归纯发布计数。

存量数据：`edit_seq` 初始值直接拷 `version`——旧值的绝对数无意义（两个口径混过），
重要的是单调递增、且不小于任何管理端手里已拿到的版本号，乐观锁不会误判"没冲突"。
`version` 存量不动：已经冻结进历史提交的数字不能追溯改写。
"""
import sqlalchemy as sa

from alembic import op

revision = "0047_scratch_challenge_edit_seq"
down_revision = "0046_scratch_works"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "scratch_challenges",
        sa.Column("edit_seq", sa.Integer(), nullable=False, server_default="1"),
    )
    op.execute("UPDATE scratch_challenges SET edit_seq = version")


def downgrade() -> None:
    op.drop_column("scratch_challenges", "edit_seq")
