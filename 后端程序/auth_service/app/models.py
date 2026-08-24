from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(512))
    status: Mapped[str] = mapped_column(String(32), default="pending_verification", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    failed_login_count: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )


class EmailVerification(Base):
    __tablename__ = "email_verifications"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    code_hmac: Mapped[str] = mapped_column(String(128))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    last_sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    family_id: Mapped[str] = mapped_column(String(36), index=True)
    refresh_token_hmac: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    absolute_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revocation_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EmailOutbox(Base):
    __tablename__ = "email_outbox"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    verification_id: Mapped[int | None] = mapped_column(
        ForeignKey("email_verifications.id", ondelete="CASCADE"), nullable=True
    )
    encrypted_code: Mapped[str] = mapped_column(Text)
    event_type: Mapped[str] = mapped_column(String(32), default="verification")
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(String(120), nullable=True)
    locked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    lock_token: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PasswordReset(Base):
    __tablename__ = "password_resets"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    code_hmac: Mapped[str] = mapped_column(String(128))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PasswordChangeVerification(Base):
    """One-time email verification for an authenticated password change."""

    __tablename__ = "password_change_verifications"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    code_hmac: Mapped[str] = mapped_column(String(128))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PasswordHistory(Base):
    """Argon2id hashes of passwords that a user has replaced.

    The newest `password_history_count` rows per user are kept; a new password
    may not match the current hash or any of these archived hashes.
    """

    __tablename__ = "password_history"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    password_hash: Mapped[str] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AdminUser(Base):
    """B 端管理员，独立于学生账号。"""
    __tablename__ = "admin_users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(512))
    display_name: Mapped[str] = mapped_column(String(100))
    role: Mapped[str] = mapped_column(String(32), default="editor")
    status: Mapped[str] = mapped_column(String(16), default="active", index=True)
    failed_login_count: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Notification(Base):
    """A single rendered in-app notification, shared by its receipts."""

    __tablename__ = "notifications"
    __table_args__ = (
        Index("ix_notifications_created_at_id", "created_at", "id"),
        CheckConstraint(
            "(source_type IS NULL AND source_id IS NULL) OR "
            "(source_type IS NOT NULL AND source_id IS NOT NULL)",
            name="ck_notifications_source_pair",
        ),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    target_type: Mapped[str] = mapped_column(String(64))
    target_id: Mapped[int] = mapped_column(Integer)
    source_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    link_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    request_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("admin_users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    revoked_by: Mapped[int | None] = mapped_column(
        ForeignKey("admin_users.id", ondelete="SET NULL"), nullable=True, index=True
    )


class NotificationReceipt(Base):
    """Per-recipient state for a notification; exactly one account type owns it."""

    __tablename__ = "notification_receipts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    notification_id: Mapped[int] = mapped_column(
        ForeignKey("notifications.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    admin_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("admin_users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    read_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    dismissed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (
        CheckConstraint(
            "(user_id IS NOT NULL AND admin_user_id IS NULL) OR "
            "(user_id IS NULL AND admin_user_id IS NOT NULL)",
            name="ck_notification_receipts_one_recipient",
        ),
        Index(
            "uq_notification_receipts_notification_user", "notification_id", "user_id", unique=True,
            sqlite_where=sa.text("user_id IS NOT NULL"),
            postgresql_where=sa.text("user_id IS NOT NULL"),
        ),
        Index(
            "uq_notification_receipts_notification_admin", "notification_id", "admin_user_id", unique=True,
            sqlite_where=sa.text("admin_user_id IS NOT NULL"),
            postgresql_where=sa.text("admin_user_id IS NOT NULL"),
        ),
        Index(
            "ix_notification_receipts_user_unread", "user_id", "read_at", "notification_id",
            sqlite_where=sa.text("user_id IS NOT NULL"),
            postgresql_where=sa.text("user_id IS NOT NULL"),
        ),
        Index(
            "ix_notification_receipts_admin_unread", "admin_user_id", "read_at", "notification_id",
            sqlite_where=sa.text("admin_user_id IS NOT NULL"),
            postgresql_where=sa.text("admin_user_id IS NOT NULL"),
        ),
    )


class HelpRequest(Base):
    """Asynchronous student-to-teacher teaching support ticket."""

    __tablename__ = "help_requests"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    class_id: Mapped[int] = mapped_column(
        ForeignKey("class_groups.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    student_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    assigned_admin_user_id: Mapped[int] = mapped_column(
        ForeignKey("admin_users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    context_type: Mapped[str] = mapped_column(String(64), nullable=False)
    context_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    request_key_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="open", index=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

    __table_args__ = (
        CheckConstraint("status IN ('open', 'closed')", name="ck_help_requests_status"),
        CheckConstraint(
            "(status = 'open' AND closed_at IS NULL) OR (status = 'closed' AND closed_at IS NOT NULL)",
            name="ck_help_requests_status_matches_closed_at",
        ),
        UniqueConstraint("student_id", "request_key_hash", name="uq_help_requests_student_key"),
    )


class HelpMessage(Base):
    __tablename__ = "help_messages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    help_request_id: Mapped[int] = mapped_column(
        ForeignKey("help_requests.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sender_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    sender_admin_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("admin_users.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    request_key_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    request_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

    __table_args__ = (
        CheckConstraint(
            "(sender_user_id IS NOT NULL AND sender_admin_user_id IS NULL) OR "
            "(sender_user_id IS NULL AND sender_admin_user_id IS NOT NULL)",
            name="ck_help_messages_one_sender",
        ),
        UniqueConstraint("help_request_id", "sender_admin_user_id", "request_key_hash", name="uq_help_messages_admin_key"),
    )


class AdminSession(Base):
    """管理员会话：短 access + 轮换 refresh，与学生会话同模式。"""
    __tablename__ = "admin_sessions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    admin_user_id: Mapped[int] = mapped_column(ForeignKey("admin_users.id", ondelete="CASCADE"), index=True)
    family_id: Mapped[str] = mapped_column(String(36), index=True)
    refresh_token_hmac: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    absolute_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revocation_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SliderCaptchaChallenge(Base):
    """滑块验证码挑战：水平偏移 x 为唯一秘密，Fernet 加密存储。"""
    __tablename__ = "slider_captcha_challenges"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    answer_x_encrypted: Mapped[str] = mapped_column(String(512))
    answer_y: Mapped[int] = mapped_column(Integer)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MfaTotp(Base):
    __tablename__ = "mfa_totp"
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    encrypted_secret: Mapped[str] = mapped_column(Text)
    enabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CaptchaChallenge(Base):
    __tablename__ = "captcha_challenges"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    answer_hmac: Mapped[str] = mapped_column(String(128))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    outcome: Mapped[str] = mapped_column(String(16))
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    admin_user_id: Mapped[int | None] = mapped_column(ForeignKey("admin_users.id"), nullable=True, index=True)
    resource_type: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    resource_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    summary_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip_hmac: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LoginHistory(Base):
    """An append-only, privacy-preserving successful-login audit trail."""

    __tablename__ = "login_history"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    ip_hmac: Mapped[str] = mapped_column(String(128), index=True)
    country: Mapped[str | None] = mapped_column(String(80), nullable=True)
    province: Mapped[str | None] = mapped_column(String(120), nullable=True)
    city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    location_key: Mapped[str | None] = mapped_column(String(384), nullable=True, index=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    device_hmac: Mapped[str | None] = mapped_column(String(128), nullable=True)
    anomaly: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    login_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

class Problem(Base):
    """题目主表：题型由 type 区分，sub_type 仅操作题（cpp/python）使用，单表枚举不拆表。"""
    __tablename__ = "problems"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    type: Mapped[str] = mapped_column(String(24), index=True)  # choice/multi_choice/judge/fill/programming
    sub_type: Mapped[str | None] = mapped_column(String(16), nullable=True)  # 仅 programming：cpp/python
    title: Mapped[str] = mapped_column(Text, default="")  # 纯文本；非操作题由 stem 派生
    # 题干与解析存 Markdown 源码（不是渲染后的 HTML）：入库不净化，渲染出口负责 XSS，
    # 否则 `#include <iostream>`、`vector<int>` 这类题面内容会被按标签剥掉。
    stem: Mapped[str] = mapped_column(Text, default="")
    analysis: Mapped[str] = mapped_column(Text, default="")
    # 所有题型共用的讲解视频；学生端只能从其所属练习/试卷结果上下文签发播放地址。
    analysis_video_id: Mapped[int | None] = mapped_column(ForeignKey("videos.id"), nullable=True)
    difficulty: Mapped[str] = mapped_column(String(32), default="入门", index=True)
    source: Mapped[str] = mapped_column(String(64), default="第三方")
    structure: Mapped[str] = mapped_column(String(32), default="单项知识点")
    status: Mapped[str] = mapped_column(String(16), default="draft", index=True)  # draft/pending/approved
    # 对外唯一编号，审核通过后分配。修订版通过时继承上一版的编号并顶替它，
    # 因此这个值始终指向"当前生效的那一版"——组卷引用它才不会随题目改版失效。
    problem_id_no: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    # 修订关系只有一层：已发布行自指，草稿副本指向它所修订的已发布行。
    root_problem_id: Mapped[int | None] = mapped_column(ForeignKey("problems.id"), nullable=True, index=True)
    version_no: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    # 所有写操作的乐观锁版本；客户端通过 If-Match 提交。
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("admin_users.id"), nullable=True)
    # 当前维护责任人：新题由当前登录管理员自动写入；与创建人、审核人分别记录。
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("admin_users.id"), nullable=True, index=True)
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("admin_users.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejected_by: Mapped[int | None] = mapped_column(ForeignKey("admin_users.id"), nullable=True)
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Tag(Base):
    """标签表：分类(category) + 层级(parent_id)，is_system 区分系统预设与运营自定义。"""
    __tablename__ = "tags"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64))
    category: Mapped[str] = mapped_column(String(32), index=True)  # knowledge/stage/business/difficulty/source...
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("tags.id", ondelete="CASCADE"), nullable=True)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)  # 悬浮提示/说明（如去括号后的原文）
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (UniqueConstraint("name", "category", name="uq_tags_name_category"),)


class ProblemTag(Base):
    """题目-标签多对多关联（标签可以是叶子或任意层级节点）。"""
    __tablename__ = "problem_tags"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    problem_id: Mapped[int] = mapped_column(ForeignKey("problems.id", ondelete="CASCADE"), index=True)
    tag_id: Mapped[int] = mapped_column(ForeignKey("tags.id", ondelete="CASCADE"), index=True)
    __table_args__ = (UniqueConstraint("problem_id", "tag_id", name="uq_problem_tags"),)


class ChoiceOption(Base):
    """选择/多选/判断题选项（判断题固定 对/错 两条）。"""
    __tablename__ = "choice_options"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    problem_id: Mapped[int] = mapped_column(ForeignKey("problems.id", ondelete="CASCADE"), index=True)
    option_label: Mapped[str] = mapped_column(String(8), default="")
    content: Mapped[str] = mapped_column(Text, default="")  # Markdown 源码，同 Problem.stem
    is_correct: Mapped[bool] = mapped_column(Boolean, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class FillAnswer(Base):
    """填空答案子表：blank_key 对应题干的 MathLive placeholder 标识。"""
    __tablename__ = "fill_answers"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    problem_id: Mapped[int] = mapped_column(ForeignKey("problems.id", ondelete="CASCADE"), index=True)
    blank_index: Mapped[int] = mapped_column(Integer, default=0)
    blank_key: Mapped[str] = mapped_column(String(64), default="")
    # 标准答案。判分接受它和 alternatives_json 里的任意一条，但**展示的永远是它**：
    # 学员看到的「正确答案」得是一个确定的写法，不能是一串或关系。
    answer: Mapped[str] = mapped_column(Text, default="")
    # 其它可接受写法的 JSON 数组，null / [] = 只认标准答案。
    # 为什么不是多开几行 FillAnswer：本表有 UNIQUE(problem_id, blank_key)，
    # 一个空一行是这张表的身份；多答案是同一个空的属性，不是另一个空。
    alternatives_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    __table_args__ = (UniqueConstraint("problem_id", "blank_key", name="uq_fill_answers_problem_blank_key"),)


class ProgrammingDetail(Base):
    """编程题详情：与测试数据/参考代码物理分离。

    `shape` 是操作题的**形态**，第二个枚举维度，与 `Problem.sub_type`（语言）正交：

      algorithm  标准输入输出的算法题。判分靠 `test_cases` 逐点比对，
                 `input_format` / `output_format` / 样例 / 隐藏测试点都为它服务。
      project    作品题——画线、画气球那一类。**没有 stdin/stdout**，
                 判分靠 `rules_json`（AST 静态规则）+ `rubric_json`（教师量规）。

    **为什么形态在这张表而不在 `problems`**：它只在操作题下有意义，`problems` 已经
    为操作题背了一个 `sub_type` 稀疏列，再加一个就是把主表当操作题的私有表用。
    这张 1:1 明细表本来就是放操作题差异的地方。代价是按形态筛题目列表要 join——
    真需要时再加冗余快照列（`lesson_problem_blocks.problem_type` 已有先例），
    不要为了一个还没人提的筛选先污染主表。

    **两种形态的字段互斥，由 `schemas.ProgrammingPayload` 在写入前闸住**：算法题不许带
    starter_code / rules / rubric，作品题不许带 input_format / output_format / 样例 /
    隐藏测试点。不互斥的话，一道题从算法改成作品之后，库里会同时留着两套判分依据，
    而"到底按哪套判"这个问题没有任何一处代码能回答。

    `allowed_modules` / `rules_json` / `rubric_json` 都是 JSON 文本：SQLite 与
    PostgreSQL 都要支持，且只整存整取、不做 SQL 内查询，用 JSON 列换不来检索能力
    （与 `ScratchChallenge` 同款取舍）。
    """
    __tablename__ = "programming_details"
    problem_id: Mapped[int] = mapped_column(ForeignKey("problems.id", ondelete="CASCADE"), primary_key=True)
    shape: Mapped[str] = mapped_column(String(16), default="algorithm", server_default="algorithm")
    input_format: Mapped[str] = mapped_column(Text, default="")
    output_format: Mapped[str] = mapped_column(Text, default="")
    hints: Mapped[str] = mapped_column(Text, default="无")
    pass_condition: Mapped[str] = mapped_column(String(32), default="编译通过")
    time_limit_ms: Mapped[int] = mapped_column(Integer, default=1000)
    memory_limit_mb: Mapped[int] = mapped_column(Integer, default=256)
    # ---- 以下四列仅 shape="project" 使用 ----
    # 学生打开编辑器时预置的代码骨架。作品题没有"输入格式"可写，起手式全靠它
    # （Runestone ActiveCode 的 starter code、nbgrader 的 answer cell 同一角色）。
    starter_code: Mapped[str] = mapped_column(Text, default="", server_default="")
    # 允许 import 的模块白名单，JSON 数组。空数组 = 不限制。
    # 与 `ScratchChallenge.allowed_extensions` 同一角色：作品题要能说清"这节课只准用 turtle"。
    allowed_modules: Mapped[str] = mapped_column(Text, default="[]", server_default="[]")
    # 声明式 AST 判定规则，JSON 数组。类型表与写入校验在 `app/python_rules.py`。
    rules_json: Mapped[str] = mapped_column(Text, default="[]", server_default="[]")
    # 教师量规：准则 × 档位 × 分值。`{}` = 不用量规，批改只给通过/不通过。
    # 结构与校验在 `app/rubric.py`，与 Scratch 共用同一份，不另立一套。
    rubric_json: Mapped[str] = mapped_column(Text, default="{}", server_default="{}")


class ReferenceSolution(Base):
    """编程题参考代码：纯文本 + language。"""
    __tablename__ = "reference_solutions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    problem_id: Mapped[int] = mapped_column(ForeignKey("problems.id", ondelete="CASCADE"), index=True)
    language: Mapped[str] = mapped_column(String(16), index=True)  # cpp/python
    code: Mapped[str] = mapped_column(Text, default="")
    __table_args__ = (UniqueConstraint("problem_id", "language", name="uq_ref_solution_lang"),)


class TestCase(Base):
    """编程题测试点：is_sample 区分展示用样例与隐藏测试点。"""
    __tablename__ = "test_cases"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    problem_id: Mapped[int] = mapped_column(ForeignKey("problems.id", ondelete="CASCADE"), index=True)
    input: Mapped[str] = mapped_column(Text, default="")
    output: Mapped[str] = mapped_column(Text, default="")
    is_sample: Mapped[bool] = mapped_column(Boolean, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    case_no: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    input_file: Mapped[str | None] = mapped_column(String(512), nullable=True)
    output_file: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # 逐点限制：null = 继承题目级（ProgrammingDetail 同名字段），不是"无限制"。
    # 别用 0/-1 当哨兵：null 天然就是"没设"，整个特性的语义基石。
    time_limit_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    memory_limit_mb: Mapped[int | None] = mapped_column(Integer, nullable=True)


class Paper(Base):
    """试卷主表：只管内容与判分口径。考试安排（时间/次数/呈现）在 ExamLink。

    两层模型：试卷是内容，链接是场次。一张卷可挂多条链接，共用同一份题目与
    分值——同一张卷发给两个班、考试时间不同，不需要复制两份卷。
    paper_type 与 ruleset 只记录预设来源，后端判分/校验永远只读展开后的具体列。
    """
    __tablename__ = "papers"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # 对外唯一编号，发布时分配（P{id:06d}）。人读的、课程节点绑定引用的。
    # 学员端链接不用它（顺序可枚举会泄题），走 ExamLink.access_token。
    paper_id_no: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    title: Mapped[str] = mapped_column(Text, default="")
    description: Mapped[str] = mapped_column(Text, default="")
    paper_type: Mapped[str] = mapped_column(String(32), default="练习卷", index=True)  # 练习卷/测试卷/模拟卷/竞赛卷/作业卷
    subject: Mapped[str] = mapped_column(String(16), default="cpp", index=True)  # cpp/python/scratch/general，软标签
    ruleset: Mapped[str] = mapped_column(String(16), default="IOI")  # IOI/ACM/OI/custom —— 仅记录预设来源
    score_mode: Mapped[str] = mapped_column(String(16), default="testcase")  # testcase/all_or_nothing
    partial_credit_multi: Mapped[bool] = mapped_column(Boolean, default=False)  # 多选少选是否给半分
    total_score: Mapped[int] = mapped_column(Integer, default=0)  # 服务端汇总，不接受前端传值
    pass_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="draft", index=True)  # draft/published/archived
    created_by: Mapped[int | None] = mapped_column(ForeignKey("admin_users.id"), nullable=True)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("admin_users.id"), nullable=True, index=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # 所有写操作的乐观锁版本；客户端通过 If-Match 提交。
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ExamLink(Base):
    """考试链接 = 一次考试安排（场次）。一张卷可有多条，各自独立配置与作废。

    拆这一层解决三件事：同一张卷不同班次考试时间不同不必复制卷；某条链接泄露
    只停这一条而不是全部失效；ACM 罚时/排行榜所需的"统一起跑线"就是这张表。
    """
    __tablename__ = "exam_links"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    paper_id: Mapped[int] = mapped_column(ForeignKey("papers.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(100))  # 如「三班期中考」，同一张卷内不重名
    access_token: Mapped[str] = mapped_column(String(32), unique=True)  # 学员端链接标识，可单独重置
    # ---- 时间：三个钟见组卷文档第四节 ----
    open_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)  # null = 立即开放
    close_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)  # null = 长期有效
    duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)  # null = 不限时
    late_start_policy: Mapped[str] = mapped_column(String(16), default="truncate")  # truncate/block/overrun
    # ---- 作答 ----
    attempt_limit: Mapped[int] = mapped_column(Integer, default=1)  # 按链接计数，0 = 不限
    score_policy: Mapped[str] = mapped_column(String(16), default="best")  # best/last/first
    penalty_minutes: Mapped[int] = mapped_column(Integer, default=0)  # ACM 罚时，本期只存不用
    # ---- 呈现：同一张卷当考试用不给解析、当自测用给，所以挂链接不挂卷 ----
    feedback_mode: Mapped[str] = mapped_column(String(16), default="realtime")  # realtime/compile_only/after_close
    show_analysis: Mapped[str] = mapped_column(String(16), default="after_submit")  # never/after_submit/after_close
    show_score: Mapped[str] = mapped_column(String(16), default="immediate")  # immediate/after_close/never
    shuffle_questions: Mapped[bool] = mapped_column(Boolean, default=False)
    shuffle_options: Mapped[bool] = mapped_column(Boolean, default=False)  # 仅作用于选择/多选题
    # ---- 考前提醒与规则：本期只在后台配置与存储，学员端（M9）消费 ----
    notice: Mapped[str] = mapped_column(Text, default="")                       # 考试须知 Markdown
    notice_ack_required: Mapped[bool] = mapped_column(Boolean, default=False)
    entry_open_minutes: Mapped[int] = mapped_column(Integer, default=0)         # 开考前 N 分钟可进候考页
    remind_minutes: Mapped[str] = mapped_column(String(64), default="")         # 剩余 N 分钟提醒，逗号分隔降序
    warn_unanswered: Mapped[bool] = mapped_column(Boolean, default=True)
    # ---- 治理 ----
    status: Mapped[str] = mapped_column(String(16), default="active", index=True)  # active/disabled
    created_by: Mapped[int | None] = mapped_column(ForeignKey("admin_users.id"), nullable=True)
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    __table_args__ = (UniqueConstraint("paper_id", "name", name="uq_exam_links_name"),)


class ExamAssignment(Base):
    """考试名单：一条考试链接投给一个班或一个学生，只管可见性，不管准入。"""

    __tablename__ = "exam_assignments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    exam_link_id: Mapped[int] = mapped_column(
        ForeignKey("exam_links.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # 多态目标键必须整体非空；target_id 不建 FK，解析时按 target_type 过滤。
    target_type: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    target_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="active", server_default="active", index=True
    )
    assigned_by: Mapped[int | None] = mapped_column(
        ForeignKey("admin_users.id"), nullable=True
    )
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "(status = 'active' AND ended_at IS NULL) OR "
            "(status = 'ended' AND ended_at IS NOT NULL)",
            name="ck_exam_assignments_status_matches_ended_at",
        ),
        Index(
            "uq_exam_assignments_active",
            "exam_link_id",
            "target_type",
            "target_id",
            unique=True,
            postgresql_where=sa.text("status = 'active'"),
            sqlite_where=sa.text("status = 'active'"),
        ),
    )


class PaperQuestion(Base):
    """卷题关联：用 problem_id_no 逻辑引用题目，故意不建外键（见组卷文档 5.1）。"""
    __tablename__ = "paper_questions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    paper_id: Mapped[int] = mapped_column(ForeignKey("papers.id", ondelete="CASCADE"), index=True)
    problem_id_no: Mapped[str] = mapped_column(String(64), index=True)  # 逻辑引用，不建 FK
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    score: Mapped[int] = mapped_column(Integer, default=0)  # 该题在本卷的分值
    __table_args__ = (UniqueConstraint("paper_id", "problem_id_no", name="uq_paper_questions"),)


class PaperAttempt(Base):
    """一次整卷作答。挂**来源**而非挂卷——次数按场次计，见组卷文档 7.1。

    deadline_at 在开考时算死并落库，之后永不重算：断线重连倒计时接着走、
    换设备作答时间不重置、管理员事后改 duration 不影响已开考的学员。

    **作答来源（0037 起，见《16、paper_attempts 作答来源改造设计》）**：
    权威身份是 `(source_type, source_id)`，能力由 `app/attempt_source.AttemptSource`
    提供。`exam_link_id` 退化为「考试来源的冗余外键」并改为可空——审计与既有报表
    还按它查，删列的收益远小于改动面。

    唯一约束用 `(source_type, source_id, user_id, attempt_no)` 而**不是**部分唯一索引：
    键里没有可空列，NULL 在唯一索引中互不相等这个坑根本不存在（计划评测报告 P0 风险 1
    担心的正是这个）。加新来源时无需再补索引。
    """
    __tablename__ = "paper_attempts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_type: Mapped[str] = mapped_column(String(16), default="exam_link", index=True)
    source_id: Mapped[int] = mapped_column(Integer, default=0)
    exam_link_id: Mapped[int | None] = mapped_column(
        ForeignKey("exam_links.id", ondelete="CASCADE"), nullable=True, index=True
    )
    paper_id: Mapped[int] = mapped_column(ForeignKey("papers.id", ondelete="CASCADE"), index=True)  # 冗余，便于按卷统计
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    attempt_no: Mapped[int] = mapped_column(Integer, default=1)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)  # null = 不限时
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    submit_kind: Mapped[str | None] = mapped_column(String(16), nullable=True)  # manual/auto_timeout/auto_close
    shuffle_seed: Mapped[int] = mapped_column(Integer, default=0)  # 确定性洗牌，仅后端使用
    total_score: Mapped[int] = mapped_column(Integer, default=0)  # 交卷时固化
    penalty_minutes: Mapped[int] = mapped_column(Integer, default=0)  # 只存不用，见组卷文档 3.3
    status: Mapped[str] = mapped_column(String(16), default="ongoing", index=True)  # ongoing/submitted/expired
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 实际用时，防作弊留痕
    ip_hmac: Mapped[str | None] = mapped_column(String(128), nullable=True)  # 开考 IP，不存明文
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    __table_args__ = (
        UniqueConstraint("source_type", "source_id", "user_id", "attempt_no",
                         name="uq_attempt_source"),
    )


class AttemptAnswer(Base):
    """一次作答里某一题的当前作答与得分。

    按题一行而不是整卷一个 JSON：自动保存要按题覆盖（互不踩踏）、判分要按题固化、
    统计要按题聚合——整卷一个 JSON 三件事都做不了。
    """
    __tablename__ = "attempt_answers"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    attempt_id: Mapped[int] = mapped_column(ForeignKey("paper_attempts.id", ondelete="CASCADE"), index=True)
    problem_id_no: Mapped[str] = mapped_column(String(64), index=True)  # 逻辑引用，与 paper_questions 同口径
    answer_json: Mapped[str] = mapped_column(Text, default="")  # 结构见学员端文档 3.4
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)  # null = 尚未判分
    is_correct: Mapped[bool | None] = mapped_column(Boolean, nullable=True)  # 统计用；编程题拿部分分时为 False
    judge_status: Mapped[str] = mapped_column(String(16), default="pending")  # pending/judged/failed
    judged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    detail_json: Mapped[str | None] = mapped_column(Text, nullable=True)  # 判分明细：逐空对错 / 逐测试点
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    __table_args__ = (UniqueConstraint("attempt_id", "problem_id_no", name="uq_attempt_answers"),)


class StudentMistake(Base):
    """学生对一道原题的当前错题档案。题干与答案仍以 problems 为权威来源。"""
    __tablename__ = "student_mistakes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    problem_id: Mapped[int] = mapped_column(ForeignKey("problems.id", ondelete="CASCADE"), index=True)
    first_wrong_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_wrong_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    wrong_count: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    review_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    review_correct_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    consecutive_correct_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    mastery_level: Mapped[str] = mapped_column(String(24), default="unmastered", server_default="unmastered")
    status: Mapped[str] = mapped_column(String(24), default="pending_review", server_default="pending_review", index=True)
    next_review_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    first_source_type: Mapped[str] = mapped_column(String(32), default="")
    first_source_id: Mapped[str] = mapped_column(String(64), default="")
    latest_source_type: Mapped[str] = mapped_column(String(32), default="")
    latest_source_id: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    __table_args__ = (UniqueConstraint("student_id", "problem_id", name="uq_student_mistake_problem"),)


class StudentMistakeReview(Base):
    """错题本内一次重做的不可变记录。"""
    __tablename__ = "student_mistake_reviews"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_mistake_id: Mapped[int] = mapped_column(
        ForeignKey("student_mistakes.id", ondelete="CASCADE"), index=True
    )
    answer_json: Mapped[str] = mapped_column(Text, default="")
    is_correct: Mapped[bool] = mapped_column(Boolean, default=False)
    source: Mapped[str] = mapped_column(String(24), default="single")
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class StudentProfile(Base):
    """学生个人资料（文档 28 P2）。独立于 users 表：资料字段会持续增多，
    且 users 是认证核心表、被各路由广泛读取，动它的列只为了承载展示性资料不值得。

    avatar_url 存的是 `/avatars/...` 内容寻址相对路径（student_profile 路由里拼 URL），
    原文件在 data/avatars，由 StaticFiles 直发；learning_signature 为学生自定义学习签名。
    """
    __tablename__ = "student_profiles"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    avatar_url: Mapped[str] = mapped_column(String(255), default="", server_default="")
    learning_signature: Mapped[str] = mapped_column(String(255), default="", server_default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CodeSubmission(Base):
    """编程题的一次代码提交。与 attempt 是两层，见组卷文档 3.4：

    单题代码重测不受 attempt_limit 约束——不允许调试就没法做题。全部提交留档，
    但只有最后一次 kind="submit" 的成绩写进 attempt_answers。
    """
    __tablename__ = "code_submissions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    attempt_id: Mapped[int] = mapped_column(ForeignKey("paper_attempts.id", ondelete="CASCADE"), index=True)
    problem_id_no: Mapped[str] = mapped_column(String(64), index=True)
    language: Mapped[str] = mapped_column(String(16))  # cpp/python
    code: Mapped[str] = mapped_column(Text, default="")
    kind: Mapped[str] = mapped_column(String(8), index=True)  # trial（只跑样例，不计分）/ submit（跑全部，计分）
    # queued/compiling/judging 为异步化预留；本期同步判题只会落终态。
    status: Mapped[str] = mapped_column(String(24), default="queued")
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 仅 kind="submit"
    detail_json: Mapped[str | None] = mapped_column(Text, nullable=True)  # 逐测试点结果
    time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 最大值
    memory_kb: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 最大值
    compile_message: Mapped[str] = mapped_column(Text, default="")  # 唯一允许回显给学员的编译器输出
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TestDataPackage(Base):
    """操作题 ZIP 测试数据的导入清单；原始 in/out 文件保存在受控目录。"""

    __tablename__ = "test_data_packages"
    problem_id: Mapped[int] = mapped_column(
        ForeignKey("problems.id", ondelete="CASCADE"), primary_key=True
    )
    archive_name: Mapped[str] = mapped_column(String(255))
    storage_dir: Mapped[str] = mapped_column(String(512))
    config_yaml: Mapped[str | None] = mapped_column(Text, nullable=True)
    manifest_json: Mapped[str] = mapped_column(Text, default="[]")
    checker: Mapped[str] = mapped_column(String(128), default="default")
    uploaded_by: Mapped[int | None] = mapped_column(ForeignKey("admin_users.id"), nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ProblemDryRun(Base):
    """一次参考代码试跑：用题目自己的参考代码跑一遍自己的测试数据。

    与 CodeSubmission 平行但不相干——那是学员的成绩载体，这是录题人的验证工具。
    不复用它是因为它的 attempt_id 是 NOT NULL 外键；为试跑造一条假 attempt，
    就是把一张业务表当通用容器用，之后所有"按 attempt 统计"的查询都要记得排除假行。

    **不存 code**：参考代码在 reference_solutions 里，试跑永远读那一份。存副本就会
    出现"试跑时的代码"和"库里的代码"不一致，而这个功能的全部意义就是验证库里那一份。
    """

    __tablename__ = "problem_dry_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    problem_id: Mapped[int] = mapped_column(ForeignKey("problems.id", ondelete="CASCADE"), index=True)
    # 试跑时题目的乐观锁版本。提交审核的前置校验靠它判断"这次试跑是不是对着当前这一版跑的"，
    # 用时间戳只能证明"跑在保存之后"，证明不了跑的是哪一版。
    problem_revision: Mapped[int] = mapped_column(Integer)
    admin_user_id: Mapped[int | None] = mapped_column(ForeignKey("admin_users.id"), nullable=True)
    language: Mapped[str] = mapped_column(String(16))       # cpp/python
    scope: Mapped[str] = mapped_column(String(8), index=True)  # samples/all/custom
    status: Mapped[str] = mapped_column(String(24), default="queued")  # 与 CodeSubmission 同一套终态
    detail_json: Mapped[str | None] = mapped_column(Text, nullable=True)  # 逐点结果，含隐藏点内容
    compile_message: Mapped[str] = mapped_column(Text, default="")
    time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    memory_kb: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MediaAsset(Base):
    """题干/解析/选项里的配图。内容寻址：同一张图无论被多少道题引用都只有一行、一个文件。

    **故意没有 problem_id 外键。** 引用关系存在 Markdown 正文的 URL 里，而不是这张表里——
    录题人复制题干到另一道题是常态，一张图天然可能被多处引用。加了外键就会出现
    "删 A 题把 B 题的图删了"。生命周期靠 cleanup_media.py 离线扫描，见该脚本。

    主键就是 sha256，不另发自增 id：URL 里出现的是哈希，多一个 id 只会制造
    "按 id 查还是按 hash 查"的选择题。
    """

    __tablename__ = "media_assets"
    sha256: Mapped[str] = mapped_column(String(64), primary_key=True)
    ext: Mapped[str] = mapped_column(String(8))          # 规范化后的扩展名，不是上传时的
    byte_size: Mapped[int] = mapped_column(Integer)      # 重编码之后的大小
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    uploaded_by: Mapped[int | None] = mapped_column(ForeignKey("admin_users.id"), nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # 最后一次被引用扫描确认还在用的时间。清理脚本只删这个时间足够旧的行。
    last_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    # 原始文件名不存：对系统没用途，却是一条会跟着图一路走到学员端的个人信息
    # （"张三的作业截图.png"）。


class CourseCover(Base):
    """课包封面图。与 MediaAsset（题干配图）结构相同、**存储区域不同**：

    - 磁盘根目录与 URL 前缀都是独立的一套（course_cover_upload_root / /course-covers/），
      不跟题目配图混在一个目录——两边的清理脚本各扫各的引用列，互不干扰。
    - 内容寻址 + 无鉴权 URL 的取舍与 MediaAsset 一致：封面不是判分资产，sha256 不可枚举
      已经足够；引用关系存在 courses.cover_url 里，生命周期由 cleanup_media.py 离线扫描。
    - 主键就是 sha256，理由同 MediaAsset：URL 里出现的是哈希，多一个 id 只会制造
      "按 id 查还是按 hash 查"的选择题。
    """

    __tablename__ = "course_covers"
    sha256: Mapped[str] = mapped_column(String(64), primary_key=True)
    ext: Mapped[str] = mapped_column(String(8))          # 规范化后的扩展名，不是上传时的
    byte_size: Mapped[int] = mapped_column(Integer)      # 重编码之后的大小
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    uploaded_by: Mapped[int | None] = mapped_column(ForeignKey("admin_users.id"), nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )


class VideoVariant(Base):
    """转码产物：一个清晰度档位 = 一个 HLS 目录（master.m3u8 或子列表 + 切片）。

    object_key 存的是 **master.m3u8 的 key**，其所在目录里才是子列表与切片——
    播放代理按「整条 HLS 路径前缀」授权，靠的就是这个目录。源文件档位的
    resolution 记为 ``source``，status 永远 ready，不进转码队列。
    """

    __tablename__ = "video_variants"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    video_id: Mapped[int] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"), index=True)
    bucket: Mapped[str] = mapped_column(String(64))  # 播放桶，通常 videos-play
    # master.m3u8 的完整 key。其目录（key 去掉文件名）下才是子列表与 .ts 切片，
    # 播放代理校验「目录前缀」即可覆盖整条 HLS 路径。
    object_key: Mapped[str] = mapped_column(String(512))
    resolution: Mapped[str] = mapped_column(String(16), default="source")  # source/1080p/720p/480p
    bitrate_kbps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)  # pending/ready/failed
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Video(Base):
    """课时视频的逻辑记录。

    源文件在 MinIO 源桶（videos-source），转码产物（HLS）在播放桶（videos-play）。

    **视频不知道自己属于哪个课时**：绑定的唯一权威是 `course_lessons.video_id`
    （0028 迁移删掉了本表原有的 lesson_id 逻辑列）。方向定死为「课时指向视频」，
    因为一节课时最多一个视频、而一个视频理论上可以被换绑到别的课时。

    primary_variant_id 指向该视频用于播放的主档（如 1080p）；转码完成前为 NULL，
    前端据此判断「可播 / 转码中」。刻意不建回向外键，避免 Video↔VideoVariant 双向依赖。
    """

    __tablename__ = "videos"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("admin_users.id"), nullable=True, index=True)
    status: Mapped[str] = mapped_column(
        String(16), default="draft", index=True
    )  # draft/uploaded/transcoding/ready/failed
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    primary_variant_id: Mapped[int | None] = mapped_column(
        ForeignKey("video_variants.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class VideoUpload(Base):
    """一次源文件上传会话：对应 MinIO 的一次 multipart upload。

    浏览器拿到 upload_id 后，逐 part 向 MinIO 直传（服务端只签发每片的预签名 URL，
    不碰文件字节）。complete 时**不信任前端**自报成功——由服务端用 upload_id 向
    MinIO 列 parts 核对 ETag，再 complete_multipart_upload，最后把状态回写 Video。
    """

    __tablename__ = "video_uploads"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    video_id: Mapped[int] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"), index=True)
    uploader_id: Mapped[int | None] = mapped_column(ForeignKey("admin_users.id"), nullable=True)
    bucket: Mapped[str] = mapped_column(String(64))  # 源桶，通常 videos-source
    object_key: Mapped[str] = mapped_column(String(512))  # 源文件在源桶的完整 key
    upload_id: Mapped[str] = mapped_column(String(256))  # MinIO 返回的 multipart upload id
    content_type: Mapped[str] = mapped_column(String(128), default="video/mp4")
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    part_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), default="initiated", index=True
    )  # initiated/completed/aborted
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    __table_args__ = (UniqueConstraint("upload_id", name="uq_video_uploads_upload_id"),)


class CourseCategory(Base):
    """专区内的通用分类树；学生端首版将前两层显示为方向与主题。"""

    __tablename__ = "course_categories"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    area_key: Mapped[str] = mapped_column(
        ForeignKey("learning_areas.key", ondelete="RESTRICT"), default="kids", index=True
    )
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("course_categories.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    key: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(50))
    description: Mapped[str | None] = mapped_column(String(300), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (
        UniqueConstraint("area_key", "parent_id", "key", name="uq_course_category_tree_key"),
    )


class LearningArea(Base):
    """可由后台维护的学习专区；key 是路由与课程归属的稳定标识。"""

    __tablename__ = "learning_areas"
    key: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(50))
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    audience: Mapped[str | None] = mapped_column(String(200), nullable=True)
    theme_key: Mapped[str] = mapped_column(String(32), default="default")
    status: Mapped[str] = mapped_column(String(16), default="planning", index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LearningAreaModule(Base):
    """专区工作台导航；module_key 只能引用前端已经注册的通用能力。"""

    __tablename__ = "learning_area_modules"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    area_key: Mapped[str] = mapped_column(
        ForeignKey("learning_areas.key", ondelete="CASCADE"), index=True
    )
    module_key: Mapped[str] = mapped_column(String(32))
    label: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(16), default="planning")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    __table_args__ = (
        UniqueConstraint("area_key", "module_key", name="uq_learning_area_module"),
    )


class CourseType(Base):
    """可维护的横向课程类型，例如系统课、专题课与训练营。"""

    __tablename__ = "course_types"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    area_key: Mapped[str] = mapped_column(
        ForeignKey("learning_areas.key", ondelete="CASCADE"), index=True
    )
    key: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(50))
    description: Mapped[str | None] = mapped_column(String(200), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    __table_args__ = (UniqueConstraint("area_key", "key", name="uq_course_type_area_key"),)


class CourseTag(Base):
    """专区内检索标签，不参与课程主归属和进度统计。"""

    __tablename__ = "course_tags"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    area_key: Mapped[str] = mapped_column(
        ForeignKey("learning_areas.key", ondelete="CASCADE"), index=True
    )
    key: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(50))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    __table_args__ = (UniqueConstraint("area_key", "key", name="uq_course_tag_area_key"),)


class CourseTagLink(Base):
    __tablename__ = "course_tag_links"
    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), primary_key=True
    )
    tag_id: Mapped[int] = mapped_column(
        ForeignKey("course_tags.id", ondelete="RESTRICT"), primary_key=True
    )


class Course(Base):
    """课包：课程组织的最小发布单位，拥有章节课时目录。

    status 状态机：draft → published → off_shelf（可回 draft 继续编辑后重新发布）。
    发布前由接口层做完整性校验（基本信息、至少一个章节、至少一个可学课时、课时内容已配置）。
    封面本期存外链 URL；素材中心落地后再接 MediaAsset 内容寻址。
    """

    __tablename__ = "courses"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    subtitle: Mapped[str | None] = mapped_column(String(300), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)  # Markdown 简介
    cover_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("course_categories.id", ondelete="SET NULL"), nullable=True, index=True
    )
    area_key: Mapped[str] = mapped_column(
        ForeignKey("learning_areas.key", ondelete="RESTRICT"), default="kids", index=True
    )
    course_kind: Mapped[str] = mapped_column(String(32), default="systematic", index=True)
    difficulty: Mapped[str] = mapped_column(
        String(16), default="beginner"
    )  # beginner / intermediate / advanced
    price_cents: Mapped[int] = mapped_column(Integer, default=0)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default="draft", index=True)
    publish_generation: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    last_publish_idempotency_key_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    last_publish_request_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("admin_users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Enrollment(Base):
    """学员的课程开通记录。

    ``opened_at`` / ``expires_at`` 是访问资格的权威时间窗；``status`` 只表示
    管理端是否停用这条记录。实际访问判断必须集中在 ``course_access._enrolled``。
    ``source`` 在 E3a 只由后台写入 ``admin``，E3b 再增加班级来源。
    """

    __tablename__ = "enrollments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="RESTRICT"), index=True
    )
    class_id: Mapped[int | None] = mapped_column(
        ForeignKey("class_groups.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    source: Mapped[str] = mapped_column(String(32), default="admin", index=True)
    status: Mapped[str] = mapped_column(String(16), default="active", index=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    __table_args__ = (
        Index(
            "ix_enrollments_student_course_source_opened",
            "student_id",
            "course_id",
            "source",
            "opened_at",
        ),
    )


class CourseSection(Base):
    """章节：课包下的第一层目录，拥有课时列表。

    sort_order 为章节内排序；删除章节级联删除其课时（video_id 置空由 ORM 层处理——
    级联删课时会带走 course_lessons 行，课时表上的 video_id 外键随之消失，视频本身
    不受影响，仍留在 videos 表供重新绑定）。
    """

    __tablename__ = "course_sections"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(200))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CourseLesson(Base):
    """课时：章节下的学习单元。

    内容三选一或组合：content_md（图文）、video_id（绑定已转码视频）、video_url（外链）。
    发布校验要求至少一种内容存在。

    video_id 外键指向 videos.id，是课时↔视频绑定的**唯一权威**（0028 起）。
    不加唯一约束：换绑时会短暂出现两节课时指向同一视频，DB 层拦下来只会让后台报错，
    改由 nodes.html 在选择器上提示「已被《XX》使用」。
    """

    __tablename__ = "course_lessons"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), index=True
    )  # 冗余列，跨章节统计与发布校验用，避免每次 join sections
    section_id: Mapped[int] = mapped_column(
        ForeignKey("course_sections.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(200))
    summary: Mapped[str | None] = mapped_column(String(500), nullable=True)
    content_md: Mapped[str | None] = mapped_column(Text, nullable=True)
    video_id: Mapped[int | None] = mapped_column(ForeignKey("videos.id"), nullable=True)
    video_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    duration_minutes: Mapped[int] = mapped_column(Integer, default=0)
    is_trial: Mapped[bool] = mapped_column(Boolean, default=False)  # 试看课时（由 open_policy=whole 同步维护，兼容旧口径）
    # 学习开放策略（2026-08-10 定稿替代 is_trial 复选框）：
    #   closed=不开放 / whole=整节试看 / first_n=试看前 N 块 / video_minutes=视频试听 N 分钟（二期）
    open_policy: Mapped[str] = mapped_column(String(16), default="closed")
    trial_block_count: Mapped[int] = mapped_column(Integer, default=0)  # first_n 参数：前 N 块可学
    trial_minutes: Mapped[int] = mapped_column(Integer, default=0)  # video_minutes 参数：视频试听 N 分钟
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CourseLessonBlock(Base):
    """课时内容块：一节课时下有序的内容单元（积木化编排）。

    为什么拆「主表 + 类型明细表」而不是在 course_lessons 上堆列：内容可以
    0..N 混排（两个视频中间夹图文、多个练习多个作业），堆列撑不起可变数量，
    也会让前端继续被固定表单绑死。主表只放块级公共字段，各类型差异进明细表，
    每块最多一张与 block_type 匹配的明细行。

    block_type 只允许 markdown / video / practice / homework / materials
    （枚举以 admin_course_content.BLOCK_TYPES 为准）。
    sort_order 在同一课时内必须压实为连续的 0..n-1（排序接口在事务内重写）。
    required=True 表示学生完成课时时需要看完/完成该块（默认口径，规则见交接文档 §14）。

    unlock_rule 是 **Gate B（路径闸）** 的配置，与 open_policy（Gate A 权限闸）正交：
      free       任意顺序学，不受前置块影响（默认，存量块全部是它）
      sequential 前面所有「必修（required）且有权限（can_access）」的块完成后才开放
    判定唯一入口是 `course_access.block_unlocked` / `block_lock_reason`，
    不要在路由体里复刻——与 lesson_block_open 同一条红线。
    """

    __tablename__ = "course_lesson_blocks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lesson_id: Mapped[int] = mapped_column(
        ForeignKey("course_lessons.id", ondelete="CASCADE"), index=True
    )
    block_type: Mapped[str] = mapped_column(String(16), index=True)  # markdown/video/practice/homework
    title: Mapped[str] = mapped_column(String(200), default="")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    required: Mapped[bool] = mapped_column(Boolean, default=True)
    unlock_rule: Mapped[str] = mapped_column(String(16), default="free")  # free / sequential
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    __table_args__ = (UniqueConstraint("lesson_id", "sort_order", name="uq_lesson_blocks_order"),)


class LessonMarkdownBlock(Base):
    """图文块明细：标题在块主表，正文在这里。与块主表 1:1。"""

    __tablename__ = "lesson_markdown_blocks"
    block_id: Mapped[int] = mapped_column(
        ForeignKey("course_lesson_blocks.id", ondelete="CASCADE"), primary_key=True
    )
    content_md: Mapped[str] = mapped_column(Text, default="")


class LessonVideoBlock(Base):
    """视频块明细：平台视频 / 外链视频二选一，用 source_type 区分。

    约束：platform 必须有 video_id 且 video_url 为空；external 反之。
    video_id 指向 videos.id（素材本体，删除块只解除引用，不删视频）。
    completion_percent 是「看多少算完成」的阈值（0～100），第一版只存不用，
    学生端完成判定仍按「全部 required 块完成」的默认口径。
    """

    __tablename__ = "lesson_video_blocks"
    block_id: Mapped[int] = mapped_column(
        ForeignKey("course_lesson_blocks.id", ondelete="CASCADE"), primary_key=True
    )
    source_type: Mapped[str] = mapped_column(String(16), default="platform")  # platform/external
    video_id: Mapped[int | None] = mapped_column(ForeignKey("videos.id"), nullable=True)
    video_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    completion_percent: Mapped[int] = mapped_column(Integer, default=100)


class LessonPaperBlock(Base):
    """练习 / 作业块明细：绑定一张试卷 + 投放规则。

    mode 只允许 practice / homework，并与块主表 block_type 一致。
    乱序配置属于**投放设置**，不回写全局试卷默认值（见交接文档 §7.3）。
    attempt_limit：NULL = 不限次数；接口层统一处理「0 → NULL」的转换。
    due_at 仅作业块有意义；练习块必须为空。
    """

    __tablename__ = "lesson_paper_blocks"
    block_id: Mapped[int] = mapped_column(
        ForeignKey("course_lesson_blocks.id", ondelete="CASCADE"), primary_key=True
    )
    paper_id: Mapped[int] = mapped_column(ForeignKey("papers.id", ondelete="CASCADE"), index=True)
    mode: Mapped[str] = mapped_column(String(16), default="practice")  # practice/homework
    attempt_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)  # NULL = 不限次数
    shuffle_questions: Mapped[bool] = mapped_column(Boolean, default=True)
    shuffle_options: Mapped[bool] = mapped_column(Boolean, default=True)
    show_score: Mapped[bool] = mapped_column(Boolean, default=True)
    show_analysis: Mapped[bool] = mapped_column(Boolean, default=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class LessonProblemBlock(Base):
    """课中练习单题块明细：绑定题库单题 + 投放规则，与块主表 1:1（v2 单题化）。

    `problem_id_no` 逻辑引用题库题号，沿用 `paper_questions` 范式（models.py:420 注释
    「故意不建外键」）——题库题可被多个卷/单题块引用，删题只影响引用方可见性，
    由发布检查（problem_missing）兜底、删除保护（_reference_blockers）事前阻止。

    `problem_type` 是冗余快照，**只用于管理端列表展示与筛选**；作答与判分一律以
    `problems.type` 实际值为准（修订版继承顶替会让快照失真，发布检查对快照过期
    输出不拦截的 `problem_type_stale` 提示，见实现计划 v2 §3.1 说明 4）。

    `display_no` 为「题号」：可编辑字符串，NULL = 回退该课时内 practice 块之间序号
    （图文/视频/资料不占位，不是 `sort_order + 1`，见实现计划 v2 §4.4）。

    `attempt_limit`：NULL = 不限次数；接口层统一处理「0 → NULL」转换（与
    LessonPaperBlock 同口径，models.py:841）。
    """

    __tablename__ = "lesson_problem_blocks"
    block_id: Mapped[int] = mapped_column(
        ForeignKey("course_lesson_blocks.id", ondelete="CASCADE"), primary_key=True
    )
    problem_id_no: Mapped[str] = mapped_column(String(64), index=True)  # 逻辑引用，不建 FK
    problem_type: Mapped[str] = mapped_column(String(24), index=True)  # 冗余快照（仅列表展示/筛选）
    display_no: Mapped[str | None] = mapped_column(String(32), nullable=True)
    score: Mapped[int] = mapped_column(Integer, default=0)
    attempt_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)  # NULL = 不限次数
    shuffle_options: Mapped[bool] = mapped_column(Boolean, default=True)
    show_analysis: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    # 单向关系即可满足「由明细找块」；不建反向 back_populates，避免扰动既有无关系的主表。
    block: Mapped["CourseLessonBlock"] = relationship()


class LessonBlockCompletion(Base):
    """学生完成内容块的记录（Gate B 路径闸的事实来源，交接文档 14 §5）。

    **只增不减**：没有「取消完成」接口。学生重看一遍视频不该把进度打回去，
    也避免闯关状态来回抖动；老师改块内容同样不重置学生进度（本期口径）。
    重复上报撞 uq_block_completion，接口层吞掉并返回 200（幂等，§5.3）。

    lesson_id 是有意的冗余列：详情接口要按课时一次性取完成集合，避免 join 块主表。
    两条外键（block_id / lesson_id）都在，块或课时被删时一并 CASCADE，冗余不会漂移。

    source 记录完成来自哪条路径，供将来学情分析区分「自己点的」与「系统判定的」：
      manual    学生点「完成，继续」（图文 / 资料）
      video     播放进度达到 lesson_video_blocks.completion_percent
      practice  课中练习提交作答（不论对错）
      homework  课后练习提交 / 编程题全部 AC
    """

    __tablename__ = "lesson_block_completions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    block_id: Mapped[int] = mapped_column(ForeignKey("course_lesson_blocks.id", ondelete="CASCADE"))
    lesson_id: Mapped[int] = mapped_column(ForeignKey("course_lessons.id", ondelete="CASCADE"))
    source: Mapped[str] = mapped_column(String(16), default="manual")
    completed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    __table_args__ = (UniqueConstraint("user_id", "block_id", name="uq_block_completion"),)


class LessonVideoWatch(Base):
    """视频块观看时长账本（一人一块一行）。见《20、视频观看时长服务端记账-设计》。

    存在的理由：`lesson_video_blocks.completion_percent` 此前完全由客户端断言——
    一个 `progress_percent: 100` 的请求就能把任何视频标成看完，依赖它的 sequential
    闯关闸随之作废。本表是服务端手里唯一能反驳客户端的事实。

    **它不防挂机**，只把作弊成本从「一个请求」抬到「一段真实墙钟时间」，
    口径与边界见设计文档 §1.1，实现前务必读完。

    ## 两条建表决策，改结构前先读

    **1. 为什么不并进 `lesson_block_completions`**
    那张表是「完成事实」：只增不减、一块一行、是 Gate B 判定的必经查询
    （`course_access.completed_block_ids`）。这张是「过程账」：每 15 秒 UPDATE 一次。
    混在一起会把顺序锁的热路径打成写热点。

    **2. 为什么按 (user, block) 唯一，而不是按「一次播放会话」分行**
    墙钟下界必须夹在**账本**上。按会话分行的话，每个标签页各拿一份完整的墙钟预算，
    开 N 个标签页就能把观看时长刷成 N 倍——直接打穿本方案的核心保证（设计文档 §4.5）。
    想统计「播了几次」用 beat_count，不要为此拆行。

    ## 字段

    watched_seconds        累计**已认可**的观看秒数，只由 video_watch.credit() 推进
    max_position_seconds   到达过的最远位置。防「循环看片头」（§4.4），兼作续播断点
    last_position_seconds  上次心跳的位置，用来算 position_delta
    last_beat_at           上次心跳的**服务端**时刻。客户端时间一律不信
    video_id               冗余：换绑视频后旧账作废靠它识别（§9.6）
    beat_count             纯审计。心跳数异常少而时长异常多的记录值得人工看一眼
    """

    __tablename__ = "lesson_video_watch"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    block_id: Mapped[int] = mapped_column(ForeignKey("course_lesson_blocks.id", ondelete="CASCADE"))
    lesson_id: Mapped[int] = mapped_column(ForeignKey("course_lessons.id", ondelete="CASCADE"))
    video_id: Mapped[int | None] = mapped_column(ForeignKey("videos.id"), nullable=True)
    watched_seconds: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    max_position_seconds: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    last_position_seconds: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    last_beat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    beat_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    __table_args__ = (UniqueConstraint("user_id", "block_id", name="uq_lesson_video_watch"),)


class LessonProblemAttempt(Base):
    """课中练习单题的作答状态（交接文档 15 §3）。与块主表按 (user, block) 唯一。

    **为什么不是 paper_attempts**：沿用 ProblemDryRun（models.py:513）立下的先例——
    需要一次"没有 attempt 的作答"时另建平行窄表，而不是伪造 attempt。课中练习是
    随堂快测：没有会话、没有倒计时、没有交卷。塞进 paper_attempts 会让此后每一条
    "按 attempt 统计成绩"的查询都要先 WHERE 掉它。

    **本表不进成绩统计**（PRD v2 Q3 的退化口径「即时反馈、不记成绩」）。X2 落地后
    由它迁移进统一 attempt 模型。

    tries 是累加计数（不是每答一次一行）：`attempt_limit` 的裁决要在服务端做，
    只靠前端计数刷新一次就绕过去了。answer_json 存最后一次作答，纯为"刷新不丢"。

    **reset_count / last_reset_at 只是审计**（0038）。学生自助「重做本题」清的是作答态
    （answer_json / last_* / detail_json），**不动 tries、更不动 LessonBlockCompletion**：
    完成度是学习履历，只增不减；顺序锁一旦因为复习而回退，学生复习一道题就被踢回
    闯关起点。两者一混就没法解释「我明明学完了，怎么后面又锁上了」。
    """

    __tablename__ = "lesson_problem_attempts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    block_id: Mapped[int] = mapped_column(ForeignKey("course_lesson_blocks.id", ondelete="CASCADE"))
    lesson_id: Mapped[int] = mapped_column(ForeignKey("course_lessons.id", ondelete="CASCADE"))
    tries: Mapped[int] = mapped_column(Integer, default=0)
    answer_json: Mapped[str] = mapped_column(Text, default="")
    last_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_correct: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    detail_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    reset_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    last_reset_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    __table_args__ = (
        UniqueConstraint("user_id", "block_id", name="uq_lesson_problem_attempt"),
    )


class LessonCodeRun(Base):
    """课时内编程题的一次试跑（交接文档 15 §8.1 S4）。**只跑样例，不进成绩。**

    与 ProblemDryRun 同类（一次不带 attempt 的运行），区别只在使用者：
    那张是录题人跑参考代码，这张是学生跑自己的代码。
    不复用 CodeSubmission 的理由与 ProblemDryRun 一字不差——它的 attempt_id 是
    NOT NULL 外键，为试跑造假 attempt 会污染此后所有「按 attempt 统计」的查询。

    **存 code**（与 ProblemDryRun 相反）：参考代码在 reference_solutions 里有权威副本，
    学生的代码没有别处可存，不存就没法异步判完再回填结果。

    scope：samples = 跑题目样例；custom = 跑学生自填的输入（没有期望输出，只看跑出什么）。
    隐藏测试点在任何配置下都不进入本链路——那是判分资产。
    """

    __tablename__ = "lesson_code_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    block_id: Mapped[int] = mapped_column(ForeignKey("course_lesson_blocks.id", ondelete="CASCADE"))
    lesson_id: Mapped[int] = mapped_column(ForeignKey("course_lessons.id", ondelete="CASCADE"))
    language: Mapped[str] = mapped_column(String(16))
    scope: Mapped[str] = mapped_column(String(8), default="samples")
    code: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(24), default="queued")
    compile_message: Mapped[str] = mapped_column(Text, default="")
    detail_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    memory_kb: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # 「这条 run 正拿着一次已扣的次数」（0048）。计分提交（scope=all）在入队前扣次数，
    # 与建这行 run 同一个事务落库；判题失败退次时 tries-1 并把它翻回 false——
    # 翻回 false 同时就是幂等闸，同一条 run 重复走到失败收尾也只退一次。
    # 试跑（samples/custom）不计分，永远是 false。
    charged: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MaterialFolder(Base):
    """资料文件夹：组织视图，不是唯一检索维度（跨文件夹仍可按名称/类型/标签搜索）。

    **防止目录循环靠应用层**（PATCH 移动时校验新父不能是自身或自身后代），
    DB 不建循环约束——PostgreSQL 自引用循环检测需要递归 CTE 触发器，成本高于收益。
    路径不做冗余存储（path_cache 标注为可选项，读优化用，本期不建）：
    树按 parent_id 懒加载，深层目录用祖先链接口拼面包屑，不依赖整条路径字符串。
    同级重名（含根目录）由应用层检查；目录删除为非空即拒（见 §4.1 局部刷新约定）。
    """

    __tablename__ = "material_folders"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("material_folders.id", ondelete="SET NULL"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("admin_users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    # 同级重名唯一约束（PG 对 NULL 不生效，根目录重名仍靠应用层检查）
    __table_args__ = (
        UniqueConstraint("parent_id", "name", name="uq_material_folders_parent_name"),
    )


class MaterialAsset(Base):
    """资料文件：display_name 与 object_key 分离（重命名目录/文件不搬对象）。

    - sha256 由**服务端**下载对象计算（前端自报值不做唯一可信依据，见交接文档 §5）；
    - status: uploading（对象已创建未校验）/ ready / failed / quarantined；
    - asset_type 由服务端按 MIME/扩展名推断（document/image/video/audio/archive/other），
      支撑 DEMO 的类型筛选——交接文档 §6 未列该列，属合理补充；
    - 去重：同 sha256 的 ready 行共享同一 object_key（复用对象不重复存储），
      删除资产时若 object_key 仍有其他 ready 行引用则只删行、不删对象。
    """

    __tablename__ = "material_assets"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    folder_id: Mapped[int | None] = mapped_column(
        ForeignKey("material_folders.id", ondelete="SET NULL"), nullable=True, index=True
    )
    display_name: Mapped[str] = mapped_column(String(255))
    object_key: Mapped[str] = mapped_column(String(512))
    mime_type: Mapped[str] = mapped_column(String(128), default="application/octet-stream")
    asset_type: Mapped[str] = mapped_column(String(16), default="other", index=True)
    size_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(16), default="uploading", index=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("admin_users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class MaterialTag(Base):
    """资料标签：跨目录分类的额外检索维度，不是文件夹的替代品。"""

    __tablename__ = "material_tags"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("admin_users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MaterialAssetTag(Base):
    """资料-标签多对多关联。"""

    __tablename__ = "material_asset_tags"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    asset_id: Mapped[int] = mapped_column(
        ForeignKey("material_assets.id", ondelete="CASCADE"), index=True
    )
    tag_id: Mapped[int] = mapped_column(
        ForeignKey("material_tags.id", ondelete="CASCADE"), index=True
    )
    __table_args__ = (UniqueConstraint("asset_id", "tag_id", name="uq_material_asset_tags"),)


class LessonBlockMaterial(Base):
    """阅读资料块与资料库的关联：删除块只删关联，源文件留在资料库（交接文档 §4.3）。"""

    __tablename__ = "lesson_block_materials"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    block_id: Mapped[int] = mapped_column(
        ForeignKey("course_lesson_blocks.id", ondelete="CASCADE"), index=True
    )
    material_id: Mapped[int] = mapped_column(
        ForeignKey("material_assets.id", ondelete="CASCADE"), index=True
    )
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (
        UniqueConstraint("block_id", "material_id", name="uq_lesson_block_materials"),
    )


class MaterialUpload(Base):
    """一次普通资料上传会话（非迁移）：对应 MinIO 的一次 multipart 或 presigned PUT。

    upload_mode 区分两种上传路径（S3 协议限制单 part ≥ 5MB，小文件无法走 multipart）：
    - presigned_put：整文件一次 PUT，head_object 核对大小；
    - multipart：逐 part 预签名直传，complete 时列 parts 核对 ETag（不信任前端自报）。
    上传完成前不能把资产标为 ready——sha256 校验在后台任务完成后才置 ready/failed。
    """

    __tablename__ = "material_uploads"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    asset_id: Mapped[int] = mapped_column(
        ForeignKey("material_assets.id", ondelete="CASCADE"), index=True
    )
    uploader_id: Mapped[int | None] = mapped_column(ForeignKey("admin_users.id"), nullable=True)
    bucket: Mapped[str] = mapped_column(String(64))
    object_key: Mapped[str] = mapped_column(String(512))
    upload_mode: Mapped[str] = mapped_column(String(16), default="multipart")  # presigned_put/multipart
    upload_id: Mapped[str | None] = mapped_column(String(256), nullable=True, unique=True)
    content_type: Mapped[str] = mapped_column(String(128), default="application/octet-stream")
    file_size: Mapped[int] = mapped_column(BigInteger, default=0)
    part_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), default="initiated", index=True
    )  # initiated/completed/aborted
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class MaterialImportSession(Base):
    """Windows 文件夹迁移会话：记录操作人、来源根目录名、目标目录、冲突策略与结果摘要。

    status: collecting（清单分批提交中）→ uploading（客户端逐文件上传）→
            finalizing（服务端校验建档中）→ completed / failed / cancelled。
    结果摘要 summary_json 在 finalize 结束时写成功/跳过/冲突/失败统计（交接文档 §5 第 9 步）。
    """

    __tablename__ = "material_import_sessions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_root_name: Mapped[str] = mapped_column(String(255))
    target_folder_id: Mapped[int | None] = mapped_column(
        ForeignKey("material_folders.id", ondelete="SET NULL"), nullable=True, index=True
    )
    preserve_structure: Mapped[bool] = mapped_column(Boolean, default=True)  # 保留相对目录结构
    conflict_policy: Mapped[str] = mapped_column(String(16), default="skip")  # skip/rename/version
    status: Mapped[str] = mapped_column(String(16), default="collecting", index=True)
    total_items: Mapped[int] = mapped_column(Integer, default=0)
    total_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    summary_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("admin_users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class MaterialImportItem(Base):
    """迁移清单中的一个文件条目。

    - client_id 是前端分配的稳定 ID（幂等 upsert 与断点续传的锚点，见交接文档 §5）；
    - upload 完成后 status=uploaded，finalize 阶段下载算 sha256、按冲突策略建档；
    - target_folder_id / asset_id 是 finalize 回填的实际落库位置，供审计对账。
    """

    __tablename__ = "material_import_items"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("material_import_sessions.id", ondelete="CASCADE"), index=True
    )
    client_id: Mapped[str] = mapped_column(String(64))
    relative_path: Mapped[str] = mapped_column(String(1024))
    file_name: Mapped[str] = mapped_column(String(255))
    size_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    mime_type: Mapped[str] = mapped_column(String(128), default="application/octet-stream")
    status: Mapped[str] = mapped_column(
        String(16), default="pending", index=True
    )  # pending/uploading/uploaded/imported/failed/skipped/conflicted
    error: Mapped[str | None] = mapped_column(String(255), nullable=True)
    bucket: Mapped[str | None] = mapped_column(String(64), nullable=True)
    object_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    upload_mode: Mapped[str | None] = mapped_column(String(16), nullable=True)
    upload_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    part_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    target_folder_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    asset_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    __table_args__ = (
        UniqueConstraint("session_id", "client_id", name="uq_import_items_client_id"),
    )


# ---------------------------------------------------------------------------
# Scratch 图形化编程（《21、Scratch 图形化编程模块-开发计划》P1 / 任务书 21b）
#
# 四张表的分工，改结构前先读：
#   ScratchChallenge        教研侧的题面：说明、初始项目、允许扩展、声明式规则、发布状态
#   ScratchProject          学生的工作副本（一人一挑战一份），只记"当前进度指针"
#   ScratchProjectRevision  每次保存冻结一份**不可变**版本；提交只能指向它
#   ScratchSubmission       一次提交 + 服务端判定结论 + 教师点评
#
# 为什么提交不直接挂在 ScratchProject 上：项目会被学生一直改下去。提交若指向
# "当前项目"，学生交完再改两下，老师回看到的就不是判定时的那份作品，判定证据
# 与作品对不上——这跟考试系统里 PaperAttempt 冻结答案是同一条纪律。
#
# 为什么不复用 PaperAttempt：那套身份是 (source_type, source_id) + answers JSON，
# 服务的是"题目/试卷作答"。`.sb3` 是二进制作品文件，塞进 answers 既撑爆字段，
# 也会让成绩汇总把它当一份答卷统计。见任务书 21b「强制架构约束」第 4 条。
# ---------------------------------------------------------------------------


class ScratchChallenge(Base):
    """Scratch 挑战：可发布、可版本化的课程关卡。内容块只绑它的 id。

    **两个序号，各管一件事**：
    - `version` = 第几次发布。首次发布为 1，撤回再发 +1（见 admin_scratch 的
      publish/unpublish）。提交时把 `version` 与 `rules_json` 一起快照进
      `ScratchSubmission`，此后老师再改题面/规则都不会追溯改写历史判定结论——
      否则同一条提交记录今天"通过"、明天变"未通过"，学生的课时进度也会跟着抖。
    - `edit_seq` = 草稿编辑序号。每次保存草稿 +1，只给管理端乐观锁
      （`base_version`）用。两者曾经共用一个计数器，后果是"编辑三次再首发，
      学生提交冻结的 challenge_version 是 4"——发布版次被编辑次数污染，审计口径
      对不上，所以拆开。

    `starter_sb3_key` 是内容寻址的相对路径（`ab/<sha256>.sb3`，与题干配图同构），
    **不是权限凭证**：学生取初始项目一律走 `/api/scratch/lesson-blocks/{id}/starter.sb3`
    并重跑课时门控，绝不把 key 或存储路径当作可访问的证明。

    `allowed_extensions` / `rules_json` / `hints_json` 都是 JSON 文本：SQLite 与
    PostgreSQL 都要支持，且这几个字段只整存整取、不做 SQL 内查询，用 JSON 列
    换不来任何检索能力，反而多一套方言差异。
    """

    __tablename__ = "scratch_challenges"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    instructions_md: Mapped[str] = mapped_column(Text, default="")
    starter_sb3_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    starter_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    starter_size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    demo_sb3_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # 解析视频是教师讲解，不是初始项目或标准答案的替代物。只在学生提交后由
    # Scratch 专属播放端点按课时门控签发，不能把 video_id 直接下发给浏览器。
    analysis_video_id: Mapped[int | None] = mapped_column(ForeignKey("videos.id"), nullable=True)
    allowed_extensions: Mapped[str] = mapped_column(Text, default="[]")  # JSON 数组
    rules_json: Mapped[str] = mapped_column(Text, default="[]")  # JSON 数组，声明式规则
    hints_json: Mapped[str] = mapped_column(Text, default="[]")  # JSON 数组，学生可见提示
    # 量规（rubric）：准则 × 档位 × 分值。整存整取、不做 SQL 内查询，与 rules_json /
    # hints_json 同构。`{}` 或缺 criteria = 这条挑战不用量规，批改只给通过/不通过。
    rubric_json: Mapped[str] = mapped_column(Text, default="{}")  # JSON 对象
    status: Mapped[str] = mapped_column(String(16), default="draft", index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)  # 第几次发布（撤回再发 +1）
    edit_seq: Mapped[int] = mapped_column(Integer, default=1)  # 草稿编辑序号（乐观锁用）
    # 审核人记录与打回原因（2026-08-15 补齐，对齐 problems 表同名字段）：
    # 审核结果可追溯，打回原因列表可见——录入员不用打开详情才知道为什么被退。
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("admin_users.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejected_by: Mapped[int | None] = mapped_column(ForeignKey("admin_users.id"), nullable=True)
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("admin_users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class LessonScratchBlock(Base):
    """Scratch 内容块明细：块 ↔ 挑战的绑定关系。与块主表 1:1。

    只有 `challenge_id` 一列业务字段——这是有意的。挑战的说明、规则、初始项目全部
    住在 `scratch_challenges`，块只做引用。把大段挑战配置 JSON 塞进内容块，
    换一节课复用同一关卡就得复制一份，改题面要改 N 处（任务书 21b 强制约束第 1 条）。
    """

    __tablename__ = "lesson_scratch_blocks"
    block_id: Mapped[int] = mapped_column(
        ForeignKey("course_lesson_blocks.id", ondelete="CASCADE"), primary_key=True
    )
    challenge_id: Mapped[int] = mapped_column(
        ForeignKey("scratch_challenges.id", ondelete="RESTRICT"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ScratchProject(Base):
    """学生的工作副本：一个学生 × 一个挑战唯一一份（计划文档 §5.1）。

    本行**不存作品内容**，只存"当前进度指针"（`current_revision_no`）。内容全部在
    `scratch_project_revisions` 里按版本堆叠，谁也覆盖不掉谁。

    `lesson_block_id` 记建档来源块：保存接口 `PUT /api/scratch/projects/{id}` 的 URL 上
    没有课时，若不记来源块，保存这条路径就没法重跑课时门控——等于给未解锁的块开了
    一扇只要知道 project_id 就能写的后门。同一挑战被两节课复用时，工作副本共享，
    门控以建档那一块为准（交接记录里已写明这条取舍）。

    `current_revision_no` 用序号而不是 `current_revision_id` 外键：projects 与
    revisions 互指会造成循环外键，SQLite 建表顺序处理不了，还要 use_alter 特判。
    (project_id, revision_no) 本来就有唯一约束，按序号定位一样精确。0 = 还没保存过。
    """

    __tablename__ = "scratch_projects"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    challenge_id: Mapped[int] = mapped_column(
        ForeignKey("scratch_challenges.id", ondelete="CASCADE"), index=True
    )
    lesson_block_id: Mapped[int | None] = mapped_column(
        ForeignKey("course_lesson_blocks.id", ondelete="SET NULL"), nullable=True, index=True
    )
    current_revision_no: Mapped[int] = mapped_column(Integer, default=0)
    revision_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    __table_args__ = (
        UniqueConstraint("student_id", "challenge_id", name="uq_scratch_project_student_challenge"),
    )


class ScratchProjectRevision(Base):
    """项目版本：一次保存冻结一份 `.sb3`。**只增不改**。

    `sb3_key` 内容寻址（`ab/<sha256>.sb3`）：学生连点五次保存、内容没变，磁盘上只有
    一份文件，五行版本记录各自指向它。删除某个版本行不能顺手删文件——别的版本
    （甚至别的学生的同名项目）可能还指着同一个 key。

    `sprite_count` / `extensions_json` 是保存时解析 `project.json` 得到的**结构摘要**，
    存下来是为了让作品列表、判定复算和排障不必每次重新解压一遍 ZIP。
    """

    __tablename__ = "scratch_project_revisions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("scratch_projects.id", ondelete="CASCADE"), index=True
    )
    revision_no: Mapped[int] = mapped_column(Integer)
    sb3_key: Mapped[str] = mapped_column(String(255))
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    sprite_count: Mapped[int] = mapped_column(Integer, default=0)
    extensions_json: Mapped[str] = mapped_column(Text, default="[]")
    source: Mapped[str] = mapped_column(String(16), default="autosave")  # autosave/manual
    saved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (
        UniqueConstraint("project_id", "revision_no", name="uq_scratch_revision_no"),
    )


class ScratchSubmission(Base):
    """一次提交 + 服务端判定结论（+ 后续人工点评）。

    **`passed` / `score` 永远由服务端写**。客户端在提交请求里传什么都不看——
    路由层的 payload 模型根本没有这两个字段，多传的键被 pydantic 丢掉。
    这是任务书 21b 强制约束第 5 条，也是整个模块唯一不能松的一条：一旦采信客户端
    的通过标记，Scratch 块的完成、进度和 sequential 闯关闸会被一个请求全部绕过。

    status 三态（第一版只做静态判定，故意留了第三态）：
      passed        全部规则通过 → 服务端**自行**调既有完成流程写 LessonBlockCompletion
      failed        有规则未通过 → 不完成、不解锁，返回逐条反馈
      needs_review  规则里含本版判不了的运行型规则 → 挂起等人工点评，**绝不自动通过**
                    （fail closed：判不了就不能算过，见 scratch_rules.UNSUPPORTED）

    教师人工批改可以把它改成任意态，另有一个**不是终态**的第四态：
      returned      教师退回重做 → 老行保持 returned 作为历史，学生改完再交产生新行
                    （attempt_no + 1）。不撤销已写下的完成记录（见 admin_scratch 的
                    review/return 注释），它不是"未通过"，是"老师要你再改一版"。

    `challenge_version` + `rules_snapshot` 是判定证据的冻结面：老师明天改了规则，
    这条记录仍然能说明"当时按哪一版规则、判成了什么"。
    """

    __tablename__ = "scratch_submissions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    lesson_block_id: Mapped[int] = mapped_column(
        ForeignKey("course_lesson_blocks.id", ondelete="CASCADE"), index=True
    )
    lesson_id: Mapped[int] = mapped_column(
        ForeignKey("course_lessons.id", ondelete="CASCADE"), index=True
    )  # 冗余列：按课时/课包查作品时不必 join 块主表（与 LessonBlockCompletion 同口径）
    project_id: Mapped[int] = mapped_column(
        ForeignKey("scratch_projects.id", ondelete="CASCADE"), index=True
    )
    project_revision_id: Mapped[int] = mapped_column(
        ForeignKey("scratch_project_revisions.id", ondelete="RESTRICT"), index=True
    )  # RESTRICT：提交引用的版本不许被清理掉，否则判定证据断链
    challenge_id: Mapped[int] = mapped_column(ForeignKey("scratch_challenges.id"), index=True)
    challenge_version: Mapped[int] = mapped_column(Integer, default=1)  # 冻结：判定时的挑战版本
    rules_snapshot: Mapped[str] = mapped_column(Text, default="[]")  # 冻结：判定时的规则原文
    attempt_no: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(16), default="failed", index=True)
    passed: Mapped[bool] = mapped_column(Boolean, default=False)
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 通过率百分比；挂起时为 NULL
    evaluation_json: Mapped[str] = mapped_column(Text, default="{}")  # 逐条规则结论与证据
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("admin_users.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    review_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 教师量规批改的冻结面与结果。`manual_score` / `manual_score_max` 永远由服务端
    # 按量规查表写出，客户端传值不看（同 `passed` / `score`）。
    rubric_snapshot: Mapped[str] = mapped_column(Text, default="{}")  # 批改时冻结的量规原文
    rubric_scores_json: Mapped[str] = mapped_column(Text, default="{}")  # 逐项打分与逐项评语
    manual_score: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 后端汇总总分
    manual_score_max: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 冻结时的满分
    review_revision: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    last_review_idempotency_key_hash: Mapped[str | None] = mapped_column(
        String(128), nullable=True
    )
    last_review_request_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    __table_args__ = (
        UniqueConstraint("user_id", "lesson_block_id", "attempt_no",
                         name="uq_scratch_submission_attempt"),
    )


class ScratchWork(Base):
    """自由作品：学生在工作台里自由创作的 Scratch 项目，可公开展出。

    与 `ScratchProject`（闯关工作副本）的分工：
    - 闯关副本：一人一挑战一份、绑定课时、服务端判定，是"做任务"的产物；
    - 自由作品：一人多份、不绑课时、可命名可公开，是"创作"本身，直接进广场展出。

    内容**只存当前版本**（无版本链）：自由作品没有提交判定、没有"交的是哪一版"
    的证据问题，保存即覆盖指针。`source="challenge"` 的作品是闯关作品分享来的
    快照——分享时刻复制当时的 `sb3_key`（内容寻址，同一份字节天然去重），此后
    两边各自演化、互不牵连；`source_project_id` / `source_challenge_id` 只作溯源。

    `is_public` 是展出开关：公开作品出现在 `/api/scratch/gallery`（首页 / 探索页），
    私密作品只有本人可见。`views` 是展示页打开计数（详情接口 +1），只供"最热"
    排序，不是权威统计。
    """

    __tablename__ = "scratch_works"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    sb3_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    sprite_count: Mapped[int] = mapped_column(Integer, default=0)
    extensions_json: Mapped[str] = mapped_column(Text, default="[]")
    source: Mapped[str] = mapped_column(String(16), default="free")  # free / challenge
    source_project_id: Mapped[int | None] = mapped_column(
        ForeignKey("scratch_projects.id", ondelete="SET NULL"), nullable=True, index=True
    )  # 分享溯源；闯关副本被删不牵连已发布的作品
    source_challenge_id: Mapped[int | None] = mapped_column(
        ForeignKey("scratch_challenges.id", ondelete="SET NULL"), nullable=True
    )
    is_public: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    views: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class FocusSession(Base):
    """一次专注段的完成记录：append-only 事件流，永不更新，只插入。

    与 `FocusSetting`（一人一行配置）的分工（设计见《开发文档/26》§7.3/7.4）：
    - 本表是**发生过的事实**，靠 `client_uuid` 幂等，多设备并集合并天然无冲突；
    - 配置表是**当前状态**，靠 `updated_at` 后写覆盖。
    两者混用一套同步策略必然出并发 bug（同 25 号文档第 4 条）。

    `outcome='catchup'` 表示这条是客户端补算出来的历史段（设备休眠/长时间
    离开后按绝对时间重放，见《开发文档/26》§6.3），不是实时完成的。统计"今日
    专注时长"时照常计入，但**不计入连续专注天数**这类需要真实在场的指标。

    `source` 预留：本期只有 'toolbox'；将来专注进课时闭环时写 'lesson' 并
    补 lesson_block_id，不需要改表。
    """

    __tablename__ = "focus_sessions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    client_uuid: Mapped[str] = mapped_column(String(36), unique=True, index=True)
    section_type: Mapped[str] = mapped_column(String(16))
    planned_ms: Mapped[int] = mapped_column(Integer)
    actual_ms: Mapped[int] = mapped_column(Integer)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ended_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    outcome: Mapped[str] = mapped_column(String(16), default="completed")
    focus_lost_count: Mapped[int] = mapped_column(Integer, default=0)
    source: Mapped[str] = mapped_column(String(16), default="toolbox")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FocusSetting(Base):
    """一人一行的专注模块配置：时长预设、ChildProfile、音效、显示样式等。

    整体存 JSON 而非拆列，因为这些字段只被子应用自己消费，服务端不做任何
    业务判定，拆列只会让每次上游设置项增减都要迁移一次库。
    """

    __tablename__ = "focus_settings"
    student_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class FocusTask(Base):
    """专注任务清单条目。跨设备同步，靠 updated_at 后写覆盖。

    与平台的课程作业**没有任何关系**——这是学生自己写的待办便签，
    不进学习闭环，不被教师批改，不产生成绩。
    """

    __tablename__ = "focus_tasks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    client_uuid: Mapped[str] = mapped_column(String(36), index=True)
    title: Mapped[str] = mapped_column(String(200))
    priority: Mapped[int] = mapped_column(Integer, default=0)
    state: Mapped[int] = mapped_column(Integer, default=0)   # 0 待办 / 1 进行中 / 2 完成
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class TypingProfile(Base):
    """打字星球·一人一行的学生档案：年龄段 + 子应用设置。

    `age_group` 只存 '3-6' / '7-12' / '13+' 三段（学前 / 小学 / 初中）：
    产品只按大段分流（字母乐园 / PEP 小学词库 / 中考编程词库），不存具体
    年龄或年级——存细了服务端也没有业务逻辑去消费，还每次都要迁移。
    `settings` 整体 JSON（默认词库、发音开关、默写开关等），字段只被子应用
    自己消费，服务端不做业务判定（同 FocusSetting 口径，见 26 号文档 §7.4）。
    """

    __tablename__ = "typing_profiles"
    student_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    age_group: Mapped[str] = mapped_column(String(8))  # '3-6' | '7-12' | '13+'
    settings: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class TypingSession(Base):
    """打字星球·章节完成记录：append-only 事件流，`client_uuid` 幂等。

    对应前端 ChapterLogUpload 数据模型（词库 / 章节 / 用时 / 输入数 / 正确数 /
    错字数 / 是否默写模式），喂养学生档案的打字能力画像（WPM 曲线 / 薄弱键位 /
    词汇掌握度）。多设备并集合并天然无冲突（同 FocusSession 口径）。
    """

    __tablename__ = "typing_sessions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    client_uuid: Mapped[str] = mapped_column(String(36), unique=True, index=True)
    dict_id: Mapped[str] = mapped_column(String(64), index=True)
    chapter: Mapped[int] = mapped_column(Integer, default=0)
    duration_sec: Mapped[int] = mapped_column(Integer, default=0)
    count_input: Mapped[int] = mapped_column(Integer, default=0)
    count_correct: Mapped[int] = mapped_column(Integer, default=0)
    count_typo: Mapped[int] = mapped_column(Integer, default=0)
    mode_dictation: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MathGameSession(Base):
    """数学星球完成记录：append-only 事件流，按 client_uuid 幂等。"""

    __tablename__ = "math_game_sessions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    client_uuid: Mapped[str] = mapped_column(String(36), unique=True, index=True)
    game_key: Mapped[str] = mapped_column(String(32), index=True)
    mode: Mapped[str] = mapped_column(String(16), index=True)
    difficulty: Mapped[str] = mapped_column(String(16), index=True)
    duration_sec: Mapped[int] = mapped_column(Integer, default=0)
    score: Mapped[int] = mapped_column(Integer, default=0)
    count_correct: Mapped[int] = mapped_column(Integer, default=0)
    count_wrong: Mapped[int] = mapped_column(Integer, default=0)
    max_combo: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ClassGroup(Base):
    """班级主表；关系历史由 ClassMember / ClassTeacher 保留。"""

    __tablename__ = "class_groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="draft", index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'active', 'archived')", name="ck_class_groups_status"
        ),
        CheckConstraint(
            "end_at IS NULL OR start_at IS NULL OR end_at >= start_at",
            name="ck_class_groups_time_range",
        ),
    )


class ClassMember(Base):
    """学生入退班关系；退班只结束当前关系，不删除历史行。"""

    __tablename__ = "class_members"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    class_id: Mapped[int] = mapped_column(
        ForeignKey("class_groups.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    student_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    left_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="active", index=True
    )

    __table_args__ = (
        CheckConstraint("status IN ('active', 'left')", name="ck_class_members_status"),
        CheckConstraint(
            "left_at IS NULL OR left_at >= joined_at", name="ck_class_members_time_range"
        ),
        CheckConstraint(
            "(status = 'active' AND left_at IS NULL) OR (status = 'left' AND left_at IS NOT NULL)",
            name="ck_class_members_status_matches_left_at",
        ),
        Index(
            "uq_class_members_active",
            "class_id",
            "student_id",
            unique=True,
            postgresql_where=sa.text("status = 'active'"),
            sqlite_where=sa.text("status = 'active'"),
        ),
    )


class ClassTeacher(Base):
    """管理员与班级的带班关系；结束关系保留历史。"""

    __tablename__ = "class_teachers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    class_id: Mapped[int] = mapped_column(
        ForeignKey("class_groups.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    admin_user_id: Mapped[int] = mapped_column(
        ForeignKey("admin_users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    role_in_class: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "role_in_class IN ('teacher', 'assistant')", name="ck_class_teachers_role_in_class"
        ),
        CheckConstraint(
            "ended_at IS NULL OR ended_at >= assigned_at", name="ck_class_teachers_time_range"
        ),
        Index(
            "uq_class_teachers_active",
            "class_id",
            "admin_user_id",
            unique=True,
            postgresql_where=sa.text("ended_at IS NULL"),
            sqlite_where=sa.text("ended_at IS NULL"),
        ),
    )
