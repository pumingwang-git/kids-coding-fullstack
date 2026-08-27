"""add forced password change state for admin accounts"""

from alembic import op
import sqlalchemy as sa

revision = "0071_admin_account_lifecycle"
down_revision = "0070_export_jobs"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "admin_users",
        sa.Column("must_change_password", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade():
    op.drop_column("admin_users", "must_change_password")
