"""add problem owner and tighten question workflow

Revision ID: 0011_problem_owner_workflow
Revises: 0010_oj_testdata_packages
"""

from alembic import op
import sqlalchemy as sa


revision = "0011_problem_owner_workflow"
down_revision = "0010_oj_testdata_packages"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 历史题目优先继承创建人；没有创建人记录的遗留数据保持为空，避免猜测责任人。
    with op.batch_alter_table("problems") as batch:
        batch.add_column(sa.Column(
            "owner_id", sa.Integer(),
            sa.ForeignKey("admin_users.id", name="fk_problems_owner_id_admin_users"),
            nullable=True,
        ))
        batch.create_index("ix_problems_owner_id", ["owner_id"])
    op.execute("UPDATE problems SET owner_id = created_by WHERE owner_id IS NULL AND created_by IS NOT NULL")


def downgrade() -> None:
    with op.batch_alter_table("problems") as batch:
        batch.drop_index("ix_problems_owner_id")
        batch.drop_column("owner_id")
