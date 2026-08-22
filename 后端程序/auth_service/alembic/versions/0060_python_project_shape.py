"""add programming problem shape + project-only columns

Revision ID: 0060_python_project_shape
Revises: 0059_exam_assignments

操作题分出第二个维度「形态」：algorithm（标准输入输出的算法题，即存量全部）
与 project（作品题，画线/画气球那类，没有 stdin/stdout）。作品题的判分依据是
starter_code + allowed_modules + rules_json + rubric_json，与测试点链路互斥。

五列都带 server_default 且 NOT NULL：存量行必须在同一条 ALTER 里拿到取值，
否则回显路径读到 NULL 就得在每个出口写一遍 `or "algorithm"` 的兜底。
默认值随列一起留在库上（不 drop），新插入的行由 ORM 的 default 决定，
两边取值一致，不会出现"迁移后建的题没有形态"。

**这几列没有外键**，SQLite 上 `op.add_column` 可以直接跑（CLAUDE.md 记的
0008_admin_auth 那个坑是 add_column 带外键，与本条无关）。
"""

import sqlalchemy as sa

from alembic import op


revision = "0060_python_project_shape"
down_revision = "0059_exam_assignments"
branch_labels = None
depends_on = None


COLUMNS = (
    ("shape", sa.String(length=16), "algorithm"),
    ("starter_code", sa.Text(), ""),
    ("allowed_modules", sa.Text(), "[]"),
    ("rules_json", sa.Text(), "[]"),
    ("rubric_json", sa.Text(), "{}"),
)


def upgrade() -> None:
    for name, type_, default in COLUMNS:
        op.add_column(
            "programming_details",
            sa.Column(name, type_, nullable=False, server_default=default),
        )


def downgrade() -> None:
    for name, _type, _default in reversed(COLUMNS):
        op.drop_column("programming_details", name)
