"""add lesson open policy (课时学习开放策略)

Revision ID: 0032_lesson_open_policy
Revises: 0031_material_module
Create Date: 2026-08-10

课时级「学习开放策略」替代单一 is_trial 布尔（2026-08-10 设计定稿）：
- open_policy: closed(不开放) / whole(整节试看) / first_n(试看前 N 块) / video_minutes(视频试听 N 分钟)
- trial_block_count / trial_minutes 分别是 first_n / video_minutes 的参数

回填：is_trial=true → whole；其余 → closed。
同时把视频块 source_type 的旧值 external 平滑迁移为 embed（外链播放器地址走 iframe，
与现网行为一致；直链 MP4/HLS 由管理员在编辑内容块时改为 direct）。

is_trial 列保留不删：旧代码（目录 chip、旧前端）仍读它，接口层随 open_policy=whole
同步维护，待新链路稳定后的独立迁移再移除。
"""
from alembic import op
import sqlalchemy as sa

revision = "0032_lesson_open_policy"
down_revision = "0031_material_module"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "course_lessons",
        sa.Column("open_policy", sa.String(length=16), nullable=False, server_default="closed"),
    )
    op.add_column(
        "course_lessons",
        sa.Column("trial_block_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "course_lessons",
        sa.Column("trial_minutes", sa.Integer(), nullable=False, server_default="0"),
    )
    op.execute("UPDATE course_lessons SET open_policy = 'whole' WHERE is_trial = TRUE")
    # source_type: external → embed（语义即「外链播放器 iframe 地址」，见 0030 回填 §3）
    op.execute("UPDATE lesson_video_blocks SET source_type = 'embed' WHERE source_type = 'external'")


def downgrade() -> None:
    op.drop_column("course_lessons", "trial_minutes")
    op.drop_column("course_lessons", "trial_block_count")
    op.drop_column("course_lessons", "open_policy")
    # external 已退役，不反向恢复（降级也不应产生已被废弃的取值）
