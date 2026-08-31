"""grant the super administrator access to the help desk"""

import sqlalchemy as sa
from alembic import op


revision = "0081_grant_super_help_respond"
down_revision = "0080_restore_help_assign_rev"
branch_labels = None
depends_on = None


ROLE_GRANTS = {"super_admin": ("help_respond", "realtime_assist")}


def upgrade() -> None:
    bind = op.get_bind()
    for role_key, capabilities in ROLE_GRANTS.items():
        for capability in capabilities:
            exists = bind.scalar(
                sa.text(
                    "SELECT count(*) FROM admin_role_capabilities "
                    "WHERE role_key = :role_key AND capability_key = :capability"
                ),
                {"role_key": role_key, "capability": capability},
            )
            if not exists:
                bind.execute(
                    sa.text(
                        "INSERT INTO admin_role_capabilities (role_key, capability_key) "
                        "VALUES (:role_key, :capability)"
                    ),
                    {"role_key": role_key, "capability": capability},
                )
    bind.execute(
        sa.text("UPDATE admin_roles SET revision = revision + 1 WHERE key = 'super_admin'")
    )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "DELETE FROM admin_role_capabilities "
            "WHERE role_key = 'super_admin' AND capability_key IN ('help_respond', 'realtime_assist')"
        )
    )
    bind.execute(
        sa.text("UPDATE admin_roles SET revision = revision - 1 WHERE key = 'super_admin' AND revision > 1")
    )
