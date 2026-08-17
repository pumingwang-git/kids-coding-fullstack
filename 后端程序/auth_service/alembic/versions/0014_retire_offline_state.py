"""retire the offline state and flatten revision lineage to one level

Revision ID: 0014_retire_offline_state
Revises: 0013_question_governance

题库工作流简化（2026-08-05 决策）：
- 取消 `offline` 状态。已下线题目退回 `draft`，内容保留在负责人手里，
  由他们决定重新提交审核还是删除——直接丢弃会让历史录入白做。
- 修订链压平成一层：副本的 root_problem_id 指向"当前已发布行"，
  副本通过审核时继承其 problem_id_no 并顶替它，因此不再有多版本共存。
"""

from alembic import op
import sqlalchemy as sa


revision = "0014_retire_offline_state"
down_revision = "0013_question_governance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    # 已下线题目占用的对外编号必须释放：编号从此只属于当前生效的那一版。
    connection.execute(
        sa.text("UPDATE problems SET status = 'draft', problem_id_no = NULL WHERE status = 'offline'")
    )
    # 历史遗留的多版本链：只有已发布行保留自指的 root，其余草稿/待审自成一链，
    # 避免旧数据里出现"副本指向一个已下线行"这种删不掉也审不了的死结。
    connection.execute(
        sa.text(
            "UPDATE problems SET root_problem_id = id "
            "WHERE root_problem_id IS NULL "
            "   OR root_problem_id NOT IN (SELECT id FROM problems WHERE status = 'approved')"
        )
    )


def downgrade() -> None:
    # offline 语义已被删除取代，退回时无法还原哪些草稿曾经是下线态，只放开状态取值。
    pass
