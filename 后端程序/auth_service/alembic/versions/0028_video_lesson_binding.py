"""统一课时→视频绑定：回填 course_lessons.video_id 后删除 videos.lesson_id

Revision ID: 0028_video_lesson_binding
Revises: 0027_course_module
Create Date: 2026-08-09

背景：0026 建 videos 时课程表还不存在，于是在 videos 上留了一个逻辑列 lesson_id
（不建外键）。0027 落地课程模块后，课时→视频的绑定写在 course_lessons.video_id 上，
而播放端仍在读 videos.lesson_id——写入方和读取方各用一套，后台挂好的视频学生端播不出来。

本迁移把权威收敛到 course_lessons.video_id：先回填，再删列。删列之后，
「哪个课时用哪个视频」在整个系统里只有一个答案。

回填只在 course_lessons.video_id 为空时写入，绝不覆盖后台已经手动挂好的绑定。
"""
from alembic import op
import sqlalchemy as sa

revision = "0028_video_lesson_binding"
down_revision = "0027_course_module"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    before = conn.execute(sa.text("SELECT COUNT(*) FROM videos")).scalar_one()

    conn.execute(sa.text("""
        UPDATE course_lessons SET video_id = (
            SELECT v.id FROM videos v WHERE v.lesson_id = course_lessons.id
        )
        WHERE video_id IS NULL
          AND EXISTS (SELECT 1 FROM videos v WHERE v.lesson_id = course_lessons.id)
    """))

    # SQLite 不支持 DROP COLUMN，batch_alter_table 会整表重建；videos 承载真实上传记录，
    # 重建后必须断言行数不变（纪律同《7、…-补丁说明》1.5 对 paper_attempts 的要求）。
    with op.batch_alter_table("videos") as batch:
        batch.drop_index("ix_videos_lesson_id")
        batch.drop_column("lesson_id")

    after = conn.execute(sa.text("SELECT COUNT(*) FROM videos")).scalar_one()
    if before != after:
        raise RuntimeError(f"videos 表重建后行数不一致：迁移前 {before}，迁移后 {after}")


def downgrade() -> None:
    with op.batch_alter_table("videos") as batch:
        batch.add_column(sa.Column("lesson_id", sa.Integer(), nullable=True))
    op.create_index("ix_videos_lesson_id", "videos", ["lesson_id"])
    # 反向回填尽力而为：一个视频只能写回一个课时，多课时共用同一视频时取 id 最小的那个。
    op.get_bind().execute(sa.text("""
        UPDATE videos SET lesson_id = (
            SELECT MIN(l.id) FROM course_lessons l WHERE l.video_id = videos.id
        )
    """))
