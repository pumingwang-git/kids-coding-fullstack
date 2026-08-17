"""add rejection audit fields for problems

Revision ID: 0012_problem_rejection_audit
Revises: 0011_problem_owner_workflow
"""

from alembic import op
import sqlalchemy as sa


revision = "0012_problem_rejection_audit"
down_revision = "0011_problem_owner_workflow"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("problems") as batch:
        batch.add_column(sa.Column("rejected_by", sa.Integer(), sa.ForeignKey("admin_users.id"), nullable=True))
        batch.add_column(sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("rejection_reason", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("problems") as batch:
        batch.drop_column("rejection_reason")
        batch.drop_column("rejected_at")
        batch.drop_column("rejected_by")
