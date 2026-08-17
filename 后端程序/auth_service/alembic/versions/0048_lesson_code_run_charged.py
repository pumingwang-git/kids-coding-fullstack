"""lesson_code_runs.charged（计分提交的次数凭据，用于判题失败退次）

Revision ID: 0048_lesson_code_run_charged
Revises: 0047_scratch_challenge_edit_seq
Create Date: 2026-08-15

编程题计分提交在**入队前**就 `tries += 1`，这一条不动——判完再扣会被连点绕过。
但入队后到判出结果之间有六条失败路径（队列满、沙箱不可用、测试数据缺失、题目已变更、
无测试点、判题线程崩溃），它们全是系统侧故障，学生的代码触发不了，却照样吃掉一次次数。
attempt_limit 配 1~3 时，两次运维抖动就能让学生失去正常完成这道题的机会。

`charged` 是「**这条 run 正拿着一次已扣的次数**」的凭据：
- 计分提交（scope=all）建 run 时置 true，与 `tries += 1` 同一个事务提交——
  两者要么都生效要么都不生效，不会出现扣了次数却没有凭据可退的中间态；
- 任何一条 JUDGE_FAILED 路径退次时 `tries -= 1` 并把它翻回 false。
  翻回 false 同时就是幂等闸：同一条 run 重复走到失败收尾也只退一次。

存量数据一律 false（server_default "0"）：历史上那些失败的提交是在旧口径下扣的次数，
追溯退还既没有凭据能判断该退给谁，也会让已经结课的成绩单对不上账。
"""
import sqlalchemy as sa

from alembic import op

revision = "0048_lesson_code_run_charged"
down_revision = "0047_scratch_challenge_edit_seq"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 走 batch：给**已有表**加 NOT NULL 列时，SQLite 不支持 ALTER 加约束
    # （Boolean 会带 CHECK），直接 op.add_column 在 SQLite 上会炸。
    # 项目里同类改动一律用 batch（0018_exam_links 的写法），这里照办。
    with op.batch_alter_table("lesson_code_runs") as batch:
        batch.add_column(
            sa.Column("charged", sa.Boolean(), nullable=False, server_default=sa.false())
        )


def downgrade() -> None:
    with op.batch_alter_table("lesson_code_runs") as batch:
        batch.drop_column("charged")
