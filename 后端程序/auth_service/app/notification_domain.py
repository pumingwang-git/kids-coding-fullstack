"""Shared notification-domain vocabulary and boundary validation.

Persistence and transaction/idempotency orchestration live in
``notification_service`` (E6-04).  This module is intentionally dependency-light
so routers can share the same event names without maintaining local strings.
"""

from __future__ import annotations

NOTIFICATION_KINDS = frozenset(
    {
        "homework_published",
        "homework_due_soon",
        "homework_graded",
        "exam_result_published",
        "homework_returned",
        "class_announcement",
        "help_request_created",
        "help_request_assigned",
        "teacher_reply",
    }
)

NOTIFICATION_KIND_LABELS = {
    "homework_published": "作业已发布",
    "homework_due_soon": "作业即将截止",
    "homework_graded": "作业已批改",
    "exam_result_published": "考试成绩已发布",
    "homework_returned": "作业已退回",
    "class_announcement": "班级公告",
    "help_request_created": "新的学生联系",
    "help_request_assigned": "工单已分配",
    "teacher_reply": "教师已回复",
}


def validate_source_pair(source_type: str | None, source_id: int | None) -> None:
    """Reject a half-populated polymorphic source identity at the domain edge."""

    if (source_type is None) != (source_id is None):
        raise ValueError("source_type and source_id must be both null or both non-null")


def validate_notification_kind(kind: str) -> None:
    if kind not in NOTIFICATION_KINDS:
        raise ValueError(f"unsupported notification kind: {kind}")


def notification_kind_label(kind: str) -> str:
    """Return the server-owned display label for a notification kind."""

    return NOTIFICATION_KIND_LABELS.get(kind, kind)


def validate_recipient(*, user_id: int | None, admin_user_id: int | None) -> None:
    """Enforce the two主体 receipt invariant before a database write."""

    if (user_id is None) == (admin_user_id is None):
        raise ValueError("exactly one of user_id or admin_user_id is required")
