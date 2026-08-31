"""restore the help request assignment revision missing from some databases"""

import sqlalchemy as sa
from alembic import op


revision = "0080_restore_help_assign_rev"
down_revision = "0079_restore_help_answered_at"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("help_requests")}
    if "assignment_revision" not in columns:
        op.add_column(
            "help_requests",
            sa.Column("assignment_revision", sa.Integer(), nullable=False, server_default="0"),
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("help_requests")}
    if "assignment_revision" in columns:
        op.drop_column("help_requests", "assignment_revision")
