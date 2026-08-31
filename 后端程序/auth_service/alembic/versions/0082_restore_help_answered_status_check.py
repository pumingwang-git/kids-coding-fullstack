"""restore the answered state checks for help requests"""

import sqlalchemy as sa
from alembic import op


revision = "0082_help_status_checks"
down_revision = "0081_grant_super_help_respond"
branch_labels = None
depends_on = None


STATUS_CHECK = "status IN ('open', 'answered', 'closed')"
CLOSED_AT_CHECK = (
    "(status IN ('open', 'answered') AND closed_at IS NULL) "
    "OR (status = 'closed' AND closed_at IS NOT NULL)"
)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    names = {
        item["name"]
        for item in inspector.get_check_constraints("help_requests")
        if item.get("name")
    }
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("help_requests", recreate="always") as batch:
            for name in (
                "ck_help_requests_status",
                "ck_help_requests_status_matches_closed_at",
            ):
                if name in names:
                    batch.drop_constraint(name, type_="check")
            batch.create_check_constraint("ck_help_requests_status", STATUS_CHECK)
            batch.create_check_constraint(
                "ck_help_requests_status_matches_closed_at", CLOSED_AT_CHECK
            )
        return

    for name in (
        "ck_help_requests_status",
        "ck_help_requests_status_matches_closed_at",
    ):
        if name in names:
            op.drop_constraint(name, "help_requests", type_="check")
    op.create_check_constraint("ck_help_requests_status", "help_requests", STATUS_CHECK)
    op.create_check_constraint(
        "ck_help_requests_status_matches_closed_at",
        "help_requests",
        CLOSED_AT_CHECK,
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("help_requests", recreate="always") as batch:
            batch.drop_constraint("ck_help_requests_status_matches_closed_at", type_="check")
            batch.drop_constraint("ck_help_requests_status", type_="check")
            batch.create_check_constraint(
                "ck_help_requests_status", "status IN ('open', 'closed')"
            )
            batch.create_check_constraint(
                "ck_help_requests_status_matches_closed_at",
                "(status = 'open' AND closed_at IS NULL) OR "
                "(status = 'closed' AND closed_at IS NOT NULL)",
            )
        return

    op.drop_constraint("ck_help_requests_status_matches_closed_at", "help_requests", type_="check")
    op.drop_constraint("ck_help_requests_status", "help_requests", type_="check")
    op.create_check_constraint(
        "ck_help_requests_status", "help_requests", "status IN ('open', 'closed')"
    )
    op.create_check_constraint(
        "ck_help_requests_status_matches_closed_at",
        "help_requests",
        "(status = 'open' AND closed_at IS NULL) OR "
        "(status = 'closed' AND closed_at IS NOT NULL)",
    )
