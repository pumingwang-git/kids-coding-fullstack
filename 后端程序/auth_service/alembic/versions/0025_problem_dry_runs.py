"""add problem_dry_runs for reference-solution dry runs

Revision ID: 0025_problem_dry_runs
Revises: 0024_media_assets
Create Date: 2026-08-07

在这之前，**没有任何一步会去编译参考代码**：一份粘贴时丢了半行的 C++，可以一路
通过审核、进卷、发给学员。判题沙箱早就建好了，把参考代码跑一遍自己的测试数据
是现成的能力，只差一张记录表。

不复用 code_submissions：它的 attempt_id 是 NOT NULL 外键，指向 paper_attempts。
理由见 models.ProblemDryRun 的文档字符串。
"""
from alembic import op
import sqlalchemy as sa

revision = "0025_problem_dry_runs"
down_revision = "0024_media_assets"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "problem_dry_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("problem_id", sa.Integer(),
                  sa.ForeignKey("problems.id", ondelete="CASCADE"), nullable=False),
        sa.Column("problem_revision", sa.Integer(), nullable=False),
        sa.Column("admin_user_id", sa.Integer(), sa.ForeignKey("admin_users.id"), nullable=True),
        sa.Column("language", sa.String(length=16), nullable=False),
        sa.Column("scope", sa.String(length=8), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="queued"),
        sa.Column("detail_json", sa.Text(), nullable=True),
        sa.Column("compile_message", sa.Text(), nullable=False, server_default=""),
        sa.Column("time_ms", sa.Integer(), nullable=True),
        sa.Column("memory_kb", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_problem_dry_runs_problem_id", "problem_dry_runs", ["problem_id"])
    op.create_index("ix_problem_dry_runs_scope", "problem_dry_runs", ["scope"])


def downgrade() -> None:
    op.drop_index("ix_problem_dry_runs_scope", table_name="problem_dry_runs")
    op.drop_index("ix_problem_dry_runs_problem_id", table_name="problem_dry_runs")
    op.drop_table("problem_dry_runs")
