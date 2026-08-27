"""add database-managed admin roles and capability grants"""

import sqlalchemy as sa

from alembic import op

revision = "0072_dynamic_admin_rbac"
down_revision = "0071_admin_account_lifecycle"
branch_labels = None
depends_on = None


ROLE_SEEDS = (
    ("super_admin", "超级管理员", "global", True, True, True),
    ("editor", "内容录入员", "none", True, False, True),
    ("admin", "历史内容录入员", "none", True, True, False),
    ("reviewer", "内容审核员", "none", True, False, True),
    ("teacher", "教师", "class", True, False, True),
    ("assistant", "助教", "class", True, False, True),
    ("academic_admin", "教务管理员", "global", True, False, True),
)

CAPABILITIES = (
    "content_edit",
    "content_review",
    "class_read",
    "results_read",
    "scratch_review",
    "announcements_send",
    "manage_classes",
    "manage_enrollments",
    "export_class_insight",
    "export_class_relationships",
    "manage_admin_accounts",
    "manage_admin_roles",
    "audit_events_read",
)

ROLE_GRANTS = {
    "super_admin": CAPABILITIES,
    "academic_admin": (
        "class_read", "results_read", "scratch_review", "announcements_send",
        "manage_classes", "manage_enrollments", "export_class_insight",
        "export_class_relationships",
    ),
    "teacher": (
        "class_read", "results_read", "scratch_review", "announcements_send",
        "export_class_insight", "export_class_relationships",
    ),
    "assistant": (
        "class_read", "results_read", "scratch_review", "announcements_send",
        "export_class_insight", "export_class_relationships",
    ),
    "reviewer": ("content_review",),
    "editor": ("content_edit",),
    "admin": ("content_edit",),
}

BUILTIN_ROLE_KEYS = tuple(role[0] for role in ROLE_SEEDS)


def upgrade():
    op.add_column(
        "admin_users",
        sa.Column("role_revision", sa.Integer(), nullable=False, server_default="1"),
    )
    roles = op.create_table(
        "admin_roles",
        sa.Column("key", sa.String(length=32), primary_key=True),
        sa.Column("label", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("scope", sa.String(length=16), nullable=False, server_default="none"),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_protected", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_assignable", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="1000"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("scope IN ('global', 'class', 'none')", name="ck_admin_roles_scope"),
    )
    grants = op.create_table(
        "admin_role_capabilities",
        sa.Column(
            "role_key",
            sa.String(length=32),
            sa.ForeignKey("admin_roles.key", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("capability_key", sa.String(length=64), primary_key=True),
    )

    op.bulk_insert(
        roles,
        [
            {
                "key": key,
                "label": label,
                "description": "",
                "scope": scope,
                "is_system": is_system,
                "is_protected": is_protected,
                "is_assignable": is_assignable,
                "revision": 1,
                "sort_order": index * 10,
            }
            for index, (key, label, scope, is_system, is_protected, is_assignable)
            in enumerate(ROLE_SEEDS)
        ],
    )
    op.bulk_insert(
        grants,
        [
            {"role_key": role_key, "capability_key": capability}
            for role_key, capabilities in ROLE_GRANTS.items()
            for capability in capabilities
        ],
    )


def downgrade():
    # The previous application version only knows the built-in role keys.  Dropping
    # the catalog while an account still references a custom key would strand that
    # account on an unknown role and make legacy `/me` dictionary lookups fail.
    bind = op.get_bind()
    custom_role = bind.execute(
        sa.text(
            "SELECT role FROM admin_users "
            "WHERE role NOT IN :builtin_roles ORDER BY id LIMIT 1"
        ).bindparams(sa.bindparam("builtin_roles", expanding=True)),
        {"builtin_roles": BUILTIN_ROLE_KEYS},
    ).scalar()
    if custom_role is not None:
        raise RuntimeError(
            "0072 downgrade refused: reassign every admin account using a custom role "
            "to a built-in role first."
        )
    op.drop_table("admin_role_capabilities")
    op.drop_table("admin_roles")
    op.drop_column("admin_users", "role_revision")
