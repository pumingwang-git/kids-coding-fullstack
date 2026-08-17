"""打字星球两表：typing_profiles / typing_sessions

Revision ID: 0051_typing
Revises: 0050_focus
Create Date: 2026-08-15

打字星球（qwerty-learner fork 魔改工具箱子应用）的用户数据落地（设计见工作记忆）：

- `typing_profiles`：一人一行的学生档案。`age_group` 只存 '3-6' / '7-12' / '13+'
  三段（学前 / 小学 / 初中），产品按大段分流；`settings` 整体 JSON（默认词库、
  发音、默写开关等），`updated_at` 后写覆盖（同 FocusSetting 口径）。
- `typing_sessions`：append-only 章节完成记录。`client_uuid` 幂等键，多设备
  并集合并无冲突；字段对应前端 ChapterLogUpload 模型（词库/章节/用时/输入数/
  正确数/错字数/是否默写），喂养打字能力画像。
"""
import sqlalchemy as sa

from alembic import op

revision = "0051_typing"
down_revision = "0050_focus"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "typing_profiles",
        sa.Column("student_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("age_group", sa.String(length=8), nullable=False),
        sa.Column("settings", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "typing_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("student_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("client_uuid", sa.String(length=36), nullable=False, unique=True, index=True),
        sa.Column("dict_id", sa.String(length=64), nullable=False, index=True),
        sa.Column("chapter", sa.Integer(), server_default="0", nullable=False),
        sa.Column("duration_sec", sa.Integer(), server_default="0", nullable=False),
        sa.Column("count_input", sa.Integer(), server_default="0", nullable=False),
        sa.Column("count_correct", sa.Integer(), server_default="0", nullable=False),
        sa.Column("count_typo", sa.Integer(), server_default="0", nullable=False),
        sa.Column("mode_dictation", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("typing_sessions")
    op.drop_table("typing_profiles")
