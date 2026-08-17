"""add Hydro-style OJ test-data package metadata and fill blank keys

Revision ID: 0010_oj_testdata_packages
Revises: 0009_question_bank
"""

from alembic import context, op
import sqlalchemy as sa


revision = "0010_oj_testdata_packages"
down_revision = "0009_question_bank"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("fill_answers") as batch:
        batch.add_column(sa.Column("blank_key", sa.String(length=64), nullable=True))

    # 兼容旧版 {{blank}}：在线迁移时把题干和答案行一起迁移为稳定的
    # MathLive 标识。离线模式没有结果集，仍输出结构迁移和答案键回填 SQL。
    if context.is_offline_mode():
        op.execute(
            "UPDATE fill_answers SET blank_key = 'blank_' || (blank_index + 1) "
            "WHERE blank_key IS NULL"
        )
    else:
        conn = op.get_bind()
        problems = conn.execute(
            sa.text("SELECT id, stem FROM problems WHERE type = 'fill'")
        ).mappings()
        for problem in problems:
            blanks = conn.execute(
                sa.text(
                    "SELECT id, blank_index FROM fill_answers "
                    "WHERE problem_id = :problem_id ORDER BY blank_index, id"
                ),
                {"problem_id": problem["id"]},
            ).mappings().all()
            stem = problem["stem"] or ""
            for blank in blanks:
                key = f"blank_{blank['blank_index'] + 1}"
                conn.execute(
                    sa.text("UPDATE fill_answers SET blank_key = :key WHERE id = :id"),
                    {"key": key, "id": blank["id"]},
                )
                stem = stem.replace("{{blank}}", f"\\placeholder[{key}]{{}}", 1)
            conn.execute(
                sa.text("UPDATE problems SET stem = :stem WHERE id = :id"),
                {"stem": stem, "id": problem["id"]},
            )

    with op.batch_alter_table("fill_answers") as batch:
        batch.alter_column("blank_key", existing_type=sa.String(length=64), nullable=False)
        batch.create_unique_constraint("uq_fill_answers_problem_blank_key", ["problem_id", "blank_key"])

    with op.batch_alter_table("test_cases") as batch:
        batch.add_column(sa.Column("case_no", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("score", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("input_file", sa.String(length=512), nullable=True))
        batch.add_column(sa.Column("output_file", sa.String(length=512), nullable=True))
        batch.create_index("ix_test_cases_case_no", ["case_no"])

    op.create_table(
        "test_data_packages",
        sa.Column("problem_id", sa.Integer(), sa.ForeignKey("problems.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("archive_name", sa.String(length=255), nullable=False),
        sa.Column("storage_dir", sa.String(length=512), nullable=False),
        sa.Column("config_yaml", sa.Text(), nullable=True),
        sa.Column("manifest_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("checker", sa.String(length=128), nullable=False, server_default="default"),
        sa.Column("uploaded_by", sa.Integer(), sa.ForeignKey("admin_users.id"), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )


def downgrade() -> None:
    op.drop_table("test_data_packages")
    with op.batch_alter_table("test_cases") as batch:
        batch.drop_index("ix_test_cases_case_no")
        batch.drop_column("output_file")
        batch.drop_column("input_file")
        batch.drop_column("score")
        batch.drop_column("case_no")
    with op.batch_alter_table("fill_answers") as batch:
        batch.drop_constraint("uq_fill_answers_problem_blank_key", type_="unique")
        batch.drop_column("blank_key")
