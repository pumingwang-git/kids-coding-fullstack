"""add analysis video to all question-bank problems

Revision ID: 0044_problem_analysis_video
Revises: 0043_scratch_analysis_video
Create Date: 2026-08-14
"""
from alembic import op
import sqlalchemy as sa

revision = "0044_problem_analysis_video"
down_revision = "0043_scratch_analysis_video"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("problems") as batch:
        batch.add_column(sa.Column("analysis_video_id", sa.Integer(), nullable=True))
        batch.create_foreign_key("fk_problems_analysis_video_id_videos", "videos", ["analysis_video_id"], ["id"])


def downgrade() -> None:
    with op.batch_alter_table("problems") as batch:
        batch.drop_constraint("fk_problems_analysis_video_id_videos", type_="foreignkey")
        batch.drop_column("analysis_video_id")
