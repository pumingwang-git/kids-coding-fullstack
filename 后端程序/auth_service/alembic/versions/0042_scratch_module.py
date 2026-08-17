"""Scratch 挑战、学生项目版本与提交判定

Revision ID: 0042_scratch_module
Revises: 0041_learning_catalog
Create Date: 2026-08-13

《21、Scratch 图形化编程模块-开发计划》P1 + 任务书 21b。

**只加表，不改既有表**。`course_lesson_blocks.block_type` 是 String 列、没有数据库
层枚举约束，新增的 `scratch` 取值不需要迁移；类型白名单在应用层
（`admin_course_content.BLOCK_TYPES`）。因此本迁移可以独立上线：老前端看不到
scratch 块，也不会被这五张空表影响。

`lesson_block_completions.source` 同理新增 `scratch` 取值——那也是无约束的 String 列，
只由服务端写（学生端 `/complete` 上报对 scratch 块一律只读，见 courses.complete_block）。

表间关系（判定证据的完整链路，反过来读）：

    ScratchSubmission → ScratchProjectRevision（不可变版本，RESTRICT 不许被删）
                      → ScratchChallenge + challenge_version + rules_snapshot（冻结规则）
                      → CourseLessonBlock（哪一节课的哪一块）
"""
from alembic import op
import sqlalchemy as sa

revision = "0042_scratch_module"
# 排在 0041_learning_catalog 之后而不是并列挂在 0040 上：两条 down_revision 都指向
# 0040 会让 alembic 出现两个 head，`upgrade head` 直接报错。本迁移与学习目录那条
# 互不相干（只加表），谁先谁后都行，接在后面即可保持线性。
down_revision = "0041_learning_catalog"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scratch_challenges",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("instructions_md", sa.Text(), nullable=False, server_default=""),
        # 内容寻址相对路径 ab/<sha256>.sb3。**不是权限凭证**：学生取初始项目要重跑课时门控。
        sa.Column("starter_sb3_key", sa.String(length=255), nullable=True),
        sa.Column("starter_sha256", sa.String(length=64), nullable=True),
        sa.Column("starter_size_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("demo_sb3_key", sa.String(length=255), nullable=True),
        sa.Column("allowed_extensions", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("rules_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("hints_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="draft"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("admin_users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
    )
    op.create_index("ix_scratch_challenges_status", "scratch_challenges", ["status"])

    op.create_table(
        "lesson_scratch_blocks",
        sa.Column("block_id", sa.Integer(),
                  sa.ForeignKey("course_lesson_blocks.id", ondelete="CASCADE"),
                  primary_key=True),
        # RESTRICT：挑战被课时引用时不许直接删，否则学生端会拿到一个指向空气的块。
        sa.Column("challenge_id", sa.Integer(),
                  sa.ForeignKey("scratch_challenges.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
    )
    op.create_index("ix_lesson_scratch_blocks_challenge_id", "lesson_scratch_blocks",
                    ["challenge_id"])

    op.create_table(
        "scratch_projects",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("student_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("challenge_id", sa.Integer(),
                  sa.ForeignKey("scratch_challenges.id", ondelete="CASCADE"), nullable=False),
        # 建档来源块：保存接口的 URL 上没有课时，靠它重跑门控（models.ScratchProject 有详述）。
        sa.Column("lesson_block_id", sa.Integer(),
                  sa.ForeignKey("course_lesson_blocks.id", ondelete="SET NULL"), nullable=True),
        sa.Column("current_revision_no", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("revision_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        # 一个学生对一个挑战只有一份工作副本（计划文档 §5.1）。
        sa.UniqueConstraint("student_id", "challenge_id",
                            name="uq_scratch_project_student_challenge"),
    )
    op.create_index("ix_scratch_projects_student_id", "scratch_projects", ["student_id"])
    op.create_index("ix_scratch_projects_challenge_id", "scratch_projects", ["challenge_id"])
    op.create_index("ix_scratch_projects_lesson_block_id", "scratch_projects",
                    ["lesson_block_id"])

    op.create_table(
        "scratch_project_revisions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(),
                  sa.ForeignKey("scratch_projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("revision_no", sa.Integer(), nullable=False),
        sa.Column("sb3_key", sa.String(length=255), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sprite_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("extensions_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("source", sa.String(length=16), nullable=False, server_default="autosave"),
        sa.Column("saved_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        # 版本号在项目内唯一：并发保存撞这条约束，由接口层 409 让客户端重试，
        # 绝不"顺手加一号再写一次"——那会把两份不同的作品交错成一条版本链。
        sa.UniqueConstraint("project_id", "revision_no", name="uq_scratch_revision_no"),
    )
    op.create_index("ix_scratch_project_revisions_project_id", "scratch_project_revisions",
                    ["project_id"])
    op.create_index("ix_scratch_project_revisions_sha256", "scratch_project_revisions",
                    ["sha256"])

    op.create_table(
        "scratch_submissions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("lesson_block_id", sa.Integer(),
                  sa.ForeignKey("course_lesson_blocks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("lesson_id", sa.Integer(),
                  sa.ForeignKey("course_lessons.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", sa.Integer(),
                  sa.ForeignKey("scratch_projects.id", ondelete="CASCADE"), nullable=False),
        # RESTRICT：提交引用的版本不许被清理掉，否则判定证据断链、老师回看不到当时的作品。
        sa.Column("project_revision_id", sa.Integer(),
                  sa.ForeignKey("scratch_project_revisions.id", ondelete="RESTRICT"),
                  nullable=False),
        sa.Column("challenge_id", sa.Integer(), sa.ForeignKey("scratch_challenges.id"),
                  nullable=False),
        # 冻结面：挑战版本 + 规则原文。老师之后改规则不会追溯改写这条判定结论。
        sa.Column("challenge_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("rules_snapshot", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("attempt_no", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="failed"),
        sa.Column("passed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("score", sa.Integer(), nullable=True),
        sa.Column("evaluation_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("reviewed_by", sa.Integer(), sa.ForeignKey("admin_users.id"), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_comment", sa.Text(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        sa.UniqueConstraint("user_id", "lesson_block_id", "attempt_no",
                            name="uq_scratch_submission_attempt"),
    )
    op.create_index("ix_scratch_submissions_user_id", "scratch_submissions", ["user_id"])
    op.create_index("ix_scratch_submissions_lesson_block_id", "scratch_submissions",
                    ["lesson_block_id"])
    op.create_index("ix_scratch_submissions_lesson_id", "scratch_submissions", ["lesson_id"])
    op.create_index("ix_scratch_submissions_project_id", "scratch_submissions", ["project_id"])
    op.create_index("ix_scratch_submissions_project_revision_id", "scratch_submissions",
                    ["project_revision_id"])
    op.create_index("ix_scratch_submissions_challenge_id", "scratch_submissions",
                    ["challenge_id"])
    op.create_index("ix_scratch_submissions_status", "scratch_submissions", ["status"])
    op.create_index("ix_scratch_submissions_submitted_at", "scratch_submissions",
                    ["submitted_at"])

    print("[0042] Scratch 五张表已建：挑战 / 块绑定 / 学生项目 / 项目版本 / 提交。")
    print("[0042] 未改动任何既有表；block_type='scratch' 与 completion source='scratch' "
          "都是无约束 String 列的新取值。")


def downgrade() -> None:
    op.drop_table("scratch_submissions")
    op.drop_table("scratch_project_revisions")
    op.drop_table("scratch_projects")
    op.drop_table("lesson_scratch_blocks")
    op.drop_table("scratch_challenges")
    print("[0042] downgrade：Scratch 五张表已删除。")
    print("[0042] 注意：磁盘上的 .sb3（SCRATCH_UPLOAD_ROOT）不会被删除，"
          "降级后成为无人引用的孤儿文件，需要人工确认后清理。")
