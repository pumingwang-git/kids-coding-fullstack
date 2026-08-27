"""add persistent asynchronous export jobs"""
from alembic import op
import sqlalchemy as sa

revision = "0070_export_jobs"
down_revision = "0069_audit_events_created_idx"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "export_jobs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("requested_by", sa.Integer(), sa.ForeignKey("admin_users.id"), nullable=False),
        sa.Column("export_type", sa.String(length=64), nullable=False),
        sa.Column("params", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="queued"),
        sa.Column("row_count", sa.Integer(), nullable=True),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_export_jobs_requested_by", "export_jobs", ["requested_by"])
    op.create_index("ix_export_jobs_export_type", "export_jobs", ["export_type"])
    op.create_index("ix_export_jobs_status", "export_jobs", ["status"])


def downgrade():
    op.drop_index("ix_export_jobs_status", table_name="export_jobs")
    op.drop_index("ix_export_jobs_export_type", table_name="export_jobs")
    op.drop_index("ix_export_jobs_requested_by", table_name="export_jobs")
    op.drop_table("export_jobs")
