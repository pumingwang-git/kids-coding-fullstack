"""add question bank: problems, tags, options, blanks, programming details

Revision ID: 0009_question_bank
Revises: 0008_admin_auth
"""
from alembic import op
import sqlalchemy as sa

revision = "0009_question_bank"
down_revision = "0008_admin_auth"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "problems",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("type", sa.String(length=24), nullable=False),
        sa.Column("sub_type", sa.String(length=16), nullable=True),
        sa.Column("title", sa.Text(), nullable=False, server_default=""),
        sa.Column("stem", sa.Text(), nullable=False, server_default=""),
        sa.Column("analysis", sa.Text(), nullable=False, server_default=""),
        sa.Column("difficulty", sa.String(length=32), nullable=False, server_default="入门"),
        sa.Column("source", sa.String(length=64), nullable=False, server_default="第三方"),
        sa.Column("structure", sa.String(length=32), nullable=False, server_default="单项知识点"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="draft"),
        sa.Column("problem_id_no", sa.String(length=64), nullable=True, unique=True),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("admin_users.id"), nullable=True),
        sa.Column("reviewed_by", sa.Integer(), sa.ForeignKey("admin_users.id"), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_problems_type", "problems", ["type"])
    op.create_index("ix_problems_difficulty", "problems", ["difficulty"])
    op.create_index("ix_problems_status", "problems", ["status"])

    op.create_table(
        "tags",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("parent_id", sa.Integer(), sa.ForeignKey("tags.id", ondelete="CASCADE"), nullable=True),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("name", "category", name="uq_tags_name_category"),
    )
    op.create_index("ix_tags_category", "tags", ["category"])

    op.create_table(
        "problem_tags",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("problem_id", sa.Integer(), sa.ForeignKey("problems.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tag_id", sa.Integer(), sa.ForeignKey("tags.id", ondelete="CASCADE"), nullable=False),
        sa.UniqueConstraint("problem_id", "tag_id", name="uq_problem_tags"),
    )
    op.create_index("ix_problem_tags_problem_id", "problem_tags", ["problem_id"])
    op.create_index("ix_problem_tags_tag_id", "problem_tags", ["tag_id"])

    op.create_table(
        "choice_options",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("problem_id", sa.Integer(), sa.ForeignKey("problems.id", ondelete="CASCADE"), nullable=False),
        sa.Column("option_label", sa.String(length=8), nullable=False, server_default=""),
        sa.Column("content", sa.Text(), nullable=False, server_default=""),
        sa.Column("is_correct", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_choice_options_problem_id", "choice_options", ["problem_id"])

    op.create_table(
        "fill_answers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("problem_id", sa.Integer(), sa.ForeignKey("problems.id", ondelete="CASCADE"), nullable=False),
        sa.Column("blank_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("answer", sa.Text(), nullable=False, server_default=""),
    )
    op.create_index("ix_fill_answers_problem_id", "fill_answers", ["problem_id"])

    op.create_table(
        "programming_details",
        sa.Column("problem_id", sa.Integer(), sa.ForeignKey("problems.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("input_format", sa.Text(), nullable=False, server_default=""),
        sa.Column("output_format", sa.Text(), nullable=False, server_default=""),
        sa.Column("hints", sa.Text(), nullable=False, server_default="无"),
        sa.Column("pass_condition", sa.String(length=32), nullable=False, server_default="编译通过"),
        sa.Column("time_limit_ms", sa.Integer(), nullable=False, server_default="1000"),
        sa.Column("memory_limit_mb", sa.Integer(), nullable=False, server_default="256"),
    )

    op.create_table(
        "reference_solutions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("problem_id", sa.Integer(), sa.ForeignKey("problems.id", ondelete="CASCADE"), nullable=False),
        sa.Column("language", sa.String(length=16), nullable=False),
        sa.Column("code", sa.Text(), nullable=False, server_default=""),
        sa.UniqueConstraint("problem_id", "language", name="uq_ref_solution_lang"),
    )
    op.create_index("ix_reference_solutions_problem_id", "reference_solutions", ["problem_id"])

    op.create_table(
        "test_cases",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("problem_id", sa.Integer(), sa.ForeignKey("problems.id", ondelete="CASCADE"), nullable=False),
        sa.Column("input", sa.Text(), nullable=False, server_default=""),
        sa.Column("output", sa.Text(), nullable=False, server_default=""),
        sa.Column("is_sample", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_test_cases_problem_id", "test_cases", ["problem_id"])


def downgrade() -> None:
    op.drop_table("test_cases")
    op.drop_table("reference_solutions")
    op.drop_table("programming_details")
    op.drop_table("fill_answers")
    op.drop_table("choice_options")
    op.drop_table("problem_tags")
    op.drop_table("tags")
    op.drop_table("problems")
