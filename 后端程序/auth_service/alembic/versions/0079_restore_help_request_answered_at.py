"""restore the help request answer timestamp missing from some upgraded databases"""

import sqlalchemy as sa
from alembic import op


revision = "0079_restore_help_answered_at"
down_revision = "0078_help_attachments_and_reads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("help_requests")}
    if "answered_at" not in columns:
        op.add_column(
            "help_requests",
            sa.Column("answered_at", sa.DateTime(timezone=True), nullable=True),
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("help_requests")}
    if "answered_at" in columns:
        op.drop_column("help_requests", "answered_at")
