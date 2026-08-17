"""add math game sessions

Revision ID: 0054_math_games
Revises: 0053_student_profiles
Create Date: 2026-08-16
"""
import sqlalchemy as sa

from alembic import op

revision = "0054_math_games"
down_revision = "0053_student_profiles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "math_game_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("student_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("client_uuid", sa.String(length=36), nullable=False),
        sa.Column("game_key", sa.String(length=32), nullable=False),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("difficulty", sa.String(length=16), nullable=False),
        sa.Column("duration_sec", sa.Integer(), server_default="0", nullable=False),
        sa.Column("score", sa.Integer(), server_default="0", nullable=False),
        sa.Column("count_correct", sa.Integer(), server_default="0", nullable=False),
        sa.Column("count_wrong", sa.Integer(), server_default="0", nullable=False),
        sa.Column("max_combo", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_math_game_sessions_student_id", "math_game_sessions", ["student_id"])
    op.create_index("ix_math_game_sessions_client_uuid", "math_game_sessions", ["client_uuid"], unique=True)
    op.create_index("ix_math_game_sessions_game_key", "math_game_sessions", ["game_key"])
    op.create_index("ix_math_game_sessions_mode", "math_game_sessions", ["mode"])
    op.create_index("ix_math_game_sessions_difficulty", "math_game_sessions", ["difficulty"])


def downgrade() -> None:
    op.drop_table("math_game_sessions")
