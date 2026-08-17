"""视频观看时长账本：完成度裁决权收归服务端

Revision ID: 0039_lesson_video_watch
Revises: 0038_practice_reset_submit
Create Date: 2026-08-13

《20、视频观看时长服务端记账-设计-2026-08-13》批次 B1。

**为什么要这张表**：`lesson_video_blocks.completion_percent` 此前完全由客户端断言，
一个 `progress_percent: 100` 的请求就能把任意视频块标成看完，依赖它的 sequential
闯关闸随之作废。这张表是服务端手里唯一能反驳客户端的事实。

**只加表、不改既有表**。因此本迁移可以独立上线：`/watch` 端点上线后老前端不受
影响（它还在打 `/complete`），裁决权的正式移交在 B3，由
`VIDEO_WATCH_AUTHORITATIVE` 开关控制。

**不回填存量数据**。已有的 lesson_block_completions（source="video"）保持有效——
不能因为上线一套新记账，就把学生已经学完的课重新锁上。这与
course_access.block_unlocked 里「已完成的块永远不再上锁」是同一条道理。
新账本只对上线后的观看生效。
"""
from alembic import op
import sqlalchemy as sa

revision = "0039_lesson_video_watch"
down_revision = "0038_practice_reset_submit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "lesson_video_watch",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("block_id", sa.Integer(),
                  sa.ForeignKey("course_lesson_blocks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("lesson_id", sa.Integer(),
                  sa.ForeignKey("course_lessons.id", ondelete="CASCADE"), nullable=False),
        # 冗余 video_id：换绑视频后旧账作废靠它识别（设计文档 §9.6）。
        # 不加 ondelete=CASCADE——视频被删时账本该留着，否则学情记录会凭空消失。
        sa.Column("video_id", sa.Integer(), sa.ForeignKey("videos.id"), nullable=True),
        sa.Column("watched_seconds", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_position_seconds", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_position_seconds", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_beat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("beat_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        # 唯一约束是本方案的**核心保证之一**，不是顺手加的：墙钟下界夹在账本上，
        # 一人一块只能有一行。按「播放会话」分行的话，每个标签页各拿一份完整墙钟预算，
        # 开 N 个标签页就能把时长刷成 N 倍（设计文档 §4.5）。
        sa.UniqueConstraint("user_id", "block_id", name="uq_lesson_video_watch"),
    )
    print("[0039] lesson_video_watch 已建表（视频观看时长账本）。")
    print("[0039] 存量 lesson_block_completions 未回填——已学完的课不会被重新锁上。")


def downgrade() -> None:
    op.drop_table("lesson_video_watch")
    print("[0039] downgrade：已删除 lesson_video_watch。")
    print("[0039] 注意：降级后视频块完成度重新回到「客户端说了算」，"
          "请同时把 VIDEO_WATCH_AUTHORITATIVE 置回 false。")
