"""harden question workflow, audit trail and revision lineage

Revision ID: 0013_question_governance
Revises: 0012_problem_rejection_audit
"""

from alembic import op
import sqlalchemy as sa


revision = "0013_question_governance"
down_revision = "0012_problem_rejection_audit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("problems") as batch:
        batch.add_column(sa.Column("root_problem_id", sa.Integer(), sa.ForeignKey("problems.id", name="fk_problems_root_problem_id"), nullable=True))
        batch.add_column(sa.Column("version_no", sa.Integer(), nullable=False, server_default="1"))
        batch.add_column(sa.Column("revision", sa.Integer(), nullable=False, server_default="1"))
        batch.create_index("ix_problems_root_problem_id", ["root_problem_id"])
    # 每条既有题目从自身开始一条版本链，避免猜测旧题之间的关系。
    op.execute("UPDATE problems SET root_problem_id = id WHERE root_problem_id IS NULL")
    with op.batch_alter_table("problems") as batch:
        batch.create_unique_constraint("uq_problems_root_version", ["root_problem_id", "version_no"])

    with op.batch_alter_table("audit_events") as batch:
        batch.add_column(sa.Column("resource_type", sa.String(length=32), nullable=True))
        batch.add_column(sa.Column("resource_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("summary_json", sa.Text(), nullable=True))
        batch.create_index("ix_audit_events_resource_type", ["resource_type"])
        batch.create_index("ix_audit_events_resource_id", ["resource_id"])

    # 原来的 admin 是录入员语义；超级管理员保持不变。
    op.execute("UPDATE admin_users SET role = 'editor' WHERE role = 'admin'")

    # 预置项只在缺失时创建；录题过程不再隐式制造分类。
    for category, name in [
        ("knowledge", "模拟"), ("knowledge", "贪心"), ("knowledge", "搜索"),
        ("knowledge", "图论"), ("knowledge", "动态规划"), ("knowledge", "变量与类型"),
        ("knowledge", "循环结构"), ("knowledge", "条件判断"), ("knowledge", "函数与递归"),
        ("knowledge", "数组"), ("knowledge", "栈"), ("knowledge", "队列"),
        ("knowledge", "链表"), ("knowledge", "树"), ("knowledge", "网络"),
        ("knowledge", "操作系统"), ("knowledge", "物理常识"), ("stage", "C++基础"),
        ("stage", "Python基础"), ("stage", "CSP-J"), ("stage", "CSP-S"),
        ("stage", "信奥提高"), ("business", "直播专用"), ("business", "引流题"),
        ("business", "试机题"), ("business", "内部练习"),
    ]:
        op.execute(
            sa.text(
                "INSERT INTO tags (name, category, is_system) VALUES (:name, :category, :is_system) "
                "ON CONFLICT (name, category) DO NOTHING"
            ).bindparams(name=name, category=category, is_system=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("audit_events") as batch:
        batch.drop_index("ix_audit_events_resource_id")
        batch.drop_index("ix_audit_events_resource_type")
        batch.drop_column("summary_json")
        batch.drop_column("resource_id")
        batch.drop_column("resource_type")
    with op.batch_alter_table("problems") as batch:
        batch.drop_constraint("uq_problems_root_version", type_="unique")
        batch.drop_index("ix_problems_root_problem_id")
        batch.drop_column("revision")
        batch.drop_column("version_no")
        batch.drop_column("root_problem_id")
