"""preserve every individual enrollment grant as history

Revision ID: 0057_enrollment_history
Revises: 0056_enrollments
"""
import sqlalchemy as sa

from alembic import op

revision = "0057_enrollment_history"
down_revision = "0056_enrollments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("enrollments") as batch:
        batch.drop_constraint("uq_enrollments_student_course_source", type_="unique")
    op.create_index(
        "ix_enrollments_student_course_source_opened",
        "enrollments",
        ["student_id", "course_id", "source", "opened_at"],
    )


def downgrade() -> None:
    conn = op.get_bind()
    count = conn.execute(sa.text("SELECT COUNT(*) FROM enrollments")).scalar()
    if count:
        raise RuntimeError(
            f"enrollments 已有 {count} 行业务数据，拒绝回滚历史结构。"
            "请改用向前修复，不要 downgrade。"
        )
    op.drop_index("ix_enrollments_student_course_source_opened", table_name="enrollments")
    with op.batch_alter_table("enrollments") as batch:
        batch.create_unique_constraint(
            "uq_enrollments_student_course_source", ["student_id", "course_id", "source"]
        )
