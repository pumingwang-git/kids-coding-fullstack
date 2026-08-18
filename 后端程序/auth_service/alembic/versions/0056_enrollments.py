"""add individual course enrollments

Revision ID: 0056_enrollments
Revises: 0055_class_groups
Create Date: 2026-08-18

The time window is the access authority. Status is retained for administrative
disablement and later reporting; it must not replace real-time expiry checks.
"""
import sqlalchemy as sa

from alembic import op

revision = "0056_enrollments"
down_revision = "0055_class_groups"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "enrollments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "student_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "course_id",
            sa.Integer(),
            sa.ForeignKey("courses.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        # E3a only writes admin. Do not constrain source here: E3b adds
        # class_batch and redeem/order/self remain post-E7 product decisions.
        sa.Column("source", sa.String(length=32), nullable=False, server_default="admin"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "status IN ('active', 'disabled', 'expired')", name="ck_enrollments_status"
        ),
        sa.CheckConstraint(
            "expires_at IS NULL OR expires_at >= opened_at",
            name="ck_enrollments_time_range",
        ),
        sa.UniqueConstraint(
            "student_id", "course_id", "source", name="uq_enrollments_student_course_source"
        ),
    )
    op.create_index("ix_enrollments_student_id", "enrollments", ["student_id"])
    op.create_index("ix_enrollments_course_id", "enrollments", ["course_id"])
    op.create_index("ix_enrollments_source", "enrollments", ["source"])
    op.create_index("ix_enrollments_status", "enrollments", ["status"])
    op.create_index(
        "ix_enrollments_access_window",
        "enrollments",
        ["student_id", "course_id", "status", "opened_at", "expires_at"],
    )


def downgrade() -> None:
    conn = op.get_bind()
    count = conn.execute(sa.text("SELECT COUNT(*) FROM enrollments")).scalar()
    if count:
        raise RuntimeError(
            f"enrollments 已有 {count} 行业务数据，拒绝回滚。"
            "请改用向前修复（新增一个迁移），不要 downgrade。"
        )
    op.drop_table("enrollments")
