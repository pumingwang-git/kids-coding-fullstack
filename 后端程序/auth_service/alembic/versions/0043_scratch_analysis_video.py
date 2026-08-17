"""add optional Scratch analysis video

Revision ID: 0043_scratch_analysis_video
Revises: 0042_scratch_module
Create Date: 2026-08-14
"""

from alembic import op
import sqlalchemy as sa


revision = "0043_scratch_analysis_video"
down_revision = "0042_scratch_module"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("scratch_challenges") as batch:
        batch.add_column(sa.Column("analysis_video_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_scratch_challenges_analysis_video_id_videos",
            "videos",
            ["analysis_video_id"],
            ["id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("scratch_challenges") as batch:
        batch.drop_constraint("fk_scratch_challenges_analysis_video_id_videos", type_="foreignkey")
        batch.drop_column("analysis_video_id")
