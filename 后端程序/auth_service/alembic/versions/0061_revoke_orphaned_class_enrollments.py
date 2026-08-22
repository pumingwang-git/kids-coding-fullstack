"""disable class grants with no active class access path

Revision ID: 0061_revoke_class_enrollments
Revises: 0060_python_project_shape
"""
import sqlalchemy as sa

from alembic import op

revision = "0061_revoke_class_enrollments"
down_revision = "0060_python_project_shape"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Class grants are derived access, so an archived class or a non-active
    # membership must not leave an active enrollment behind. Personal admin
    # grants are intentionally untouched.
    op.execute(sa.text("""
        UPDATE enrollments
        SET status = 'disabled'
        WHERE source = 'class_batch'
          AND status = 'active'
          AND (
              class_id IS NULL
              OR EXISTS (
                  SELECT 1 FROM class_groups cg
                  WHERE cg.id = enrollments.class_id
                    AND cg.status = 'archived'
              )
              OR NOT EXISTS (
                  SELECT 1 FROM class_members cm
                  WHERE cm.class_id = enrollments.class_id
                    AND cm.student_id = enrollments.student_id
                    AND cm.status = 'active'
              )
          )
    """))


def downgrade() -> None:
    raise RuntimeError(
        "0061 已清理历史课程开通记录，无法安全恢复 active 状态；请使用向前迁移。"
    )
