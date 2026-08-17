"""add class groups, members, and teachers

Revision ID: 0055_class_groups
Revises: 0054_math_games
Create Date: 2026-08-18

Class relationships retain their history.  The downgrade is deliberately
fail-closed once any business data has been written; use a forward migration
to repair a populated database.
"""
import sqlalchemy as sa

from alembic import op

revision = "0055_class_groups"
down_revision = "0054_math_games"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "class_groups",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column(
            "course_id",
            sa.Integer(),
            sa.ForeignKey("courses.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="draft"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "status IN ('draft', 'active', 'archived')", name="ck_class_groups_status"
        ),
        sa.CheckConstraint(
            "end_at IS NULL OR start_at IS NULL OR end_at >= start_at",
            name="ck_class_groups_time_range",
        ),
    )
    op.create_index("ix_class_groups_course_id", "class_groups", ["course_id"])
    op.create_index("ix_class_groups_status", "class_groups", ["status"])

    op.create_table(
        "class_members",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "class_id",
            sa.Integer(),
            sa.ForeignKey("class_groups.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "student_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("left_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.CheckConstraint("status IN ('active', 'left')", name="ck_class_members_status"),
        sa.CheckConstraint(
            "left_at IS NULL OR left_at >= joined_at", name="ck_class_members_time_range"
        ),
        sa.CheckConstraint(
            "(status = 'active' AND left_at IS NULL) OR (status = 'left' AND left_at IS NOT NULL)",
            name="ck_class_members_status_matches_left_at",
        ),
    )
    op.create_index("ix_class_members_class_id", "class_members", ["class_id"])
    op.create_index("ix_class_members_student_id", "class_members", ["student_id"])
    op.create_index("ix_class_members_status", "class_members", ["status"])
    op.create_index(
        "uq_class_members_active",
        "class_members",
        ["class_id", "student_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
        sqlite_where=sa.text("status = 'active'"),
    )

    op.create_table(
        "class_teachers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "class_id",
            sa.Integer(),
            sa.ForeignKey("class_groups.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "admin_user_id",
            sa.Integer(),
            sa.ForeignKey("admin_users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("role_in_class", sa.String(length=16), nullable=False),
        sa.Column(
            "assigned_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "role_in_class IN ('teacher', 'assistant')", name="ck_class_teachers_role_in_class"
        ),
        sa.CheckConstraint(
            "ended_at IS NULL OR ended_at >= assigned_at", name="ck_class_teachers_time_range"
        ),
    )
    op.create_index("ix_class_teachers_class_id", "class_teachers", ["class_id"])
    op.create_index("ix_class_teachers_admin_user_id", "class_teachers", ["admin_user_id"])
    op.create_index("ix_class_teachers_role_in_class", "class_teachers", ["role_in_class"])
    op.create_index(
        "uq_class_teachers_active",
        "class_teachers",
        ["class_id", "admin_user_id"],
        unique=True,
        postgresql_where=sa.text("ended_at IS NULL"),
        sqlite_where=sa.text("ended_at IS NULL"),
    )


def downgrade() -> None:
    conn = op.get_bind()
    for table in ("class_teachers", "class_members", "class_groups"):
        count = conn.execute(sa.text(f"SELECT COUNT(*) FROM {table}")).scalar()
        if count:
            raise RuntimeError(
                f"{table} 已有 {count} 行业务数据，拒绝回滚。"
                "请改用向前修复（新增一个迁移），不要 downgrade。"
            )

    op.drop_index("uq_class_teachers_active", table_name="class_teachers")
    op.drop_table("class_teachers")
    op.drop_index("uq_class_members_active", table_name="class_members")
    op.drop_table("class_members")
    op.drop_table("class_groups")
