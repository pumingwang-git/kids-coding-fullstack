"""专注星球三表：focus_sessions / focus_settings / focus_tasks

Revision ID: 0050_focus
Revises: 0049_scratch_review_fields
Create Date: 2026-08-15

专注星球（FocusTide fork 工具箱子应用）的用户数据落地（设计见《开发文档/26》§7.5）：

- `focus_sessions`：append-only 专注段完成记录。`client_uuid` 幂等键，
  多设备并集合并天然无冲突；`outcome` 区分 completed / aborted / catchup
  （catchup = 客户端按绝对时间补算出的历史段，不算连续专注天数）；
  `source` 预留 'toolbox' / 'lesson'（本期只有前者）。
- `focus_settings`：一人一行 JSON 配置，`updated_at` 后写覆盖。
- `focus_tasks`：学生自写待办便签（与课程作业无关），客户端 UUID + 软删，
  `updated_at` 后写覆盖。

统计（今日/连续天数）不建表，按 focus_sessions 实时聚合；(student_id,
started_at) 复合索引已覆盖。
"""
import sqlalchemy as sa

from alembic import op

revision = "0050_focus"
down_revision = "0049_scratch_review_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "focus_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("student_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("client_uuid", sa.String(36), nullable=False, unique=True, index=True),
        sa.Column("section_type", sa.String(16), nullable=False),
        sa.Column("planned_ms", sa.Integer(), nullable=False),
        sa.Column("actual_ms", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("outcome", sa.String(16), nullable=False, server_default="completed"),
        sa.Column("focus_lost_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source", sa.String(16), nullable=False, server_default="toolbox"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "focus_settings",
        sa.Column("student_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("payload", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "focus_tasks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("student_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("client_uuid", sa.String(36), nullable=False, index=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("state", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    # 今日/区间统计的常用查询形态：(student_id, started_at) 已由两个独立索引覆盖，
    # 双列复合索引对量级（一人一天几十条）收益有限，暂不建，见文档 §7.5。


def downgrade() -> None:
    op.drop_table("focus_tasks")
    op.drop_table("focus_settings")
    op.drop_table("focus_sessions")
