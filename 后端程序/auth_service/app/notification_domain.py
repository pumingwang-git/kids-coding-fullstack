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


def validate_source_pair(source_type: str | None, source_id: int | None) -> None:
    """Reject a half-populated polymorphic source identity at the domain edge."""

    if (source_type is None) != (source_id is None):
        raise ValueError("source_type and source_id must be both null or both non-null")


def validate_notification_kind(kind: str) -> None:
    if kind not in NOTIFICATION_KINDS:
        raise ValueError(f"unsupported notification kind: {kind}")


def validate_recipient(*, user_id: int | None, admin_user_id: int | None) -> None:
    """Enforce the two主体 receipt invariant before a database write."""

    if (user_id is None) == (admin_user_id is None):
        raise ValueError("exactly one of user_id or admin_user_id is required")
