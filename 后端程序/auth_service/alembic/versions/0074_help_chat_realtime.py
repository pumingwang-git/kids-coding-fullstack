"""reserve the help chat and realtime domain revision; seed W0 capabilities"""

import sqlalchemy as sa

from alembic import op

revision = "0074_help_chat_realtime"
down_revision = "0073_scratch_work_cover"
branch_labels = None
depends_on = None

CAPABILITIES = (
    "help_respond",
    "realtime_assist",
    "support_content_request",
    "support_content_approve",
)

ROLE_GRANTS = {
    "teacher": ("help_respond", "realtime_assist"),
    "assistant": ("help_respond", "realtime_assist"),
    "academic_admin": ("support_content_request",),
    "super_admin": ("support_content_request", "support_content_approve"),
}


def upgrade() -> None:
    op.create_table(
        "help_chat_lines",
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
        sa.Column(
            "last_message_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
    )
    for column in ("class_id", "student_id", "last_message_at", "ended_at"):
        op.create_index(f"ix_help_chat_lines_{column}", "help_chat_lines", [column])
    op.create_index(
        "uq_help_chat_lines_active",
        "help_chat_lines",
        ["class_id", "student_id"],
        unique=True,
        postgresql_where=sa.text("ended_at IS NULL"),
        sqlite_where=sa.text("ended_at IS NULL"),
    )
    grants = sa.table(
        "admin_role_capabilities",
        sa.column("role_key", sa.String(length=32)),
        sa.column("capability_key", sa.String(length=64)),
    )
    op.bulk_insert(
        grants,
        [
            {"role_key": role_key, "capability_key": capability}
            for role_key, capabilities in ROLE_GRANTS.items()
            for capability in capabilities
        ],
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.scalar(sa.text("SELECT count(*) FROM help_chat_lines")):
        raise RuntimeError("0074 downgrade refused: help chat lines are not empty")
    for role_key, capabilities in ROLE_GRANTS.items():
        bind.execute(
            sa.text(
                "DELETE FROM admin_role_capabilities "
                "WHERE role_key = :role_key AND capability_key IN :capabilities"
            ).bindparams(sa.bindparam("capabilities", expanding=True)),
            {"role_key": role_key, "capabilities": tuple(capabilities)},
        )
    op.drop_index("uq_help_chat_lines_active", table_name="help_chat_lines")
    for column in ("ended_at", "last_message_at", "student_id", "class_id"):
        op.drop_index(f"ix_help_chat_lines_{column}", table_name="help_chat_lines")
    op.drop_table("help_chat_lines")
