"""课程增加专区和课程类型。

Revision ID: 0040_course_area_kind
Revises: 0039_lesson_video_watch
Create Date: 2026-08-13
"""
from alembic import op
import sqlalchemy as sa

revision = "0040_course_area_kind"
down_revision = "0039_lesson_video_watch"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "courses",
        sa.Column("area_key", sa.String(length=32), nullable=False, server_default="kids"),
    )
    op.add_column(
        "courses",
        sa.Column("course_kind", sa.String(length=16), nullable=False, server_default="systematic"),
    )
    op.create_index("ix_courses_area_key", "courses", ["area_key"])
    op.create_index("ix_courses_course_kind", "courses", ["course_kind"])


def downgrade() -> None:
    op.drop_index("ix_courses_course_kind", table_name="courses")
    op.drop_index("ix_courses_area_key", table_name="courses")
    op.drop_column("courses", "course_kind")
    op.drop_column("courses", "area_key")
