"""add exam assignment roster

Revision ID: 0059_exam_assignments
Revises: 0058_enrollment_class_source
"""

import sqlalchemy as sa

from alembic import op


revision = "0059_exam_assignments"
down_revision = "0058_enrollment_class_source"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "exam_assignments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "exam_link_id",
            sa.Integer(),
            sa.ForeignKey("exam_links.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("target_type", sa.String(length=16), nullable=False),
        sa.Column("target_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("assigned_by", sa.Integer(), sa.ForeignKey("admin_users.id"), nullable=True),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "(status = 'active' AND ended_at IS NULL) OR "
            "(status = 'ended' AND ended_at IS NOT NULL)",
            name="ck_exam_assignments_status_matches_ended_at",
        ),
    )
    op.create_index("ix_exam_assignments_exam_link_id", "exam_assignments", ["exam_link_id"])
    op.create_index("ix_exam_assignments_target_type", "exam_assignments", ["target_type"])
    op.create_index("ix_exam_assignments_target_id", "exam_assignments", ["target_id"])
    op.create_index("ix_exam_assignments_status", "exam_assignments", ["status"])
    op.create_index(
        "uq_exam_assignments_active",
        "exam_assignments",
        ["exam_link_id", "target_type", "target_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
        sqlite_where=sa.text("status = 'active'"),
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT COUNT(*) FROM exam_assignments")).scalar_one():
        raise RuntimeError("exam_assignments contains data; refusing destructive downgrade")
    op.drop_index("uq_exam_assignments_active", table_name="exam_assignments")
    op.drop_index("ix_exam_assignments_status", table_name="exam_assignments")
    op.drop_index("ix_exam_assignments_target_id", table_name="exam_assignments")
    op.drop_index("ix_exam_assignments_target_type", table_name="exam_assignments")
    op.drop_index("ix_exam_assignments_exam_link_id", table_name="exam_assignments")
    op.drop_table("exam_assignments")
