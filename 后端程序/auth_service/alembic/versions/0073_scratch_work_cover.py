"""add cover_key to scratch_works

封面由工作台在保存时截舞台画面上传，服务端重编码后内容寻址落盘（见《63》）。
可空：老作品、分享来的快照、以及截图失败的那次保存都会留空，下发时回落到生成
占位图。**只加这一列**——下发地址上的缓存版本号直接取 key 里的内容哈希，
不需要另存一个"封面更新时间"。

add_column 不带外键——`0008_admin_auth` 那条用 op.add_column 加外键，
SQLite 不支持 ALTER 约束，整条迁移链在 SQLite 上就是从那里断的。这里不重蹈。
"""

import sqlalchemy as sa

from alembic import op

revision = "0073_scratch_work_cover"
down_revision = "0072_dynamic_admin_rbac"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("scratch_works", sa.Column("cover_key", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("scratch_works", "cover_key")
