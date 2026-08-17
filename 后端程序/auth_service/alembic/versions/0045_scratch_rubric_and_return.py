"""add Scratch rubric and return

Revision ID: 0045_scratch_rubric_and_return
Revises: 0044_problem_analysis_video
Create Date: 2026-08-14
"""
from alembic import op
import sqlalchemy as sa


revision = "0045_scratch_rubric_and_return"
down_revision = "0044_problem_analysis_video"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 量规：挑战上的一个 JSON 列，{} = 不用量规。与 rules_json / hints_json 同构。
    with op.batch_alter_table("scratch_challenges") as batch:
        batch.add_column(sa.Column("rubric_json", sa.Text(), nullable=False, server_default="{}"))
    # 提交行：量规冻结面 + 服务端汇总分。全部有默认值或可空，不回填、不改写已有行。
    with op.batch_alter_table("scratch_submissions") as batch:
        batch.add_column(sa.Column("rubric_snapshot", sa.Text(), nullable=False, server_default="{}"))
        batch.add_column(sa.Column("rubric_scores_json", sa.Text(), nullable=False, server_default="{}"))
        batch.add_column(sa.Column("manual_score", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("manual_score_max", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("scratch_submissions") as batch:
        batch.drop_column("manual_score_max")
        batch.drop_column("manual_score")
        batch.drop_column("rubric_scores_json")
        batch.drop_column("rubric_snapshot")
    with op.batch_alter_table("scratch_challenges") as batch:
        batch.drop_column("rubric_json")
