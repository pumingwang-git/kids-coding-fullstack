"""add pre-exam notice & reminder rules to exam_links

Revision ID: 0019_exam_link_reminders
Revises: 0018_exam_links
Create Date: 2026-08-06

本期只落字段与后台配置界面；学员端（候考页 / 须知页 / 考中提示）随 M9 落地。
"""
from alembic import op
import sqlalchemy as sa

revision = "0019_exam_link_reminders"
down_revision = "0018_exam_links"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("exam_links") as batch:
        batch.add_column(sa.Column("notice", sa.Text(), nullable=False, server_default=""))
        batch.add_column(sa.Column("notice_ack_required", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.add_column(sa.Column("entry_open_minutes", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("remind_minutes", sa.String(length=64), nullable=False, server_default=""))
        batch.add_column(sa.Column("warn_unanswered", sa.Boolean(), nullable=False, server_default=sa.true()))


def downgrade() -> None:
    with op.batch_alter_table("exam_links") as batch:
        for column in ("warn_unanswered", "remind_minutes", "entry_open_minutes",
                       "notice_ack_required", "notice"):
            batch.drop_column(column)
