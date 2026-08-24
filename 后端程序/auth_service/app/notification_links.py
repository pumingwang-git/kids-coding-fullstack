"""Canonical, client-reachable paths used by in-app notifications.

Notification links are server-owned navigation data.  Keep their construction
here so a stored link cannot become an arbitrary user-provided internal path.
"""
from __future__ import annotations

import re
from urllib.parse import quote


def _positive_id(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError("notification link id must be a positive integer")
    return value


def course_link(course_id: int) -> str:
    return f"/courses/{_positive_id(course_id)}"


def lesson_homework_link(lesson_id: int, block_id: int) -> str:
    return f"/learn/{_positive_id(lesson_id)}/homework/{_positive_id(block_id)}"


def exam_attempt_link(access_token: str) -> str:
    if not isinstance(access_token, str) or not access_token:
        raise ValueError("exam access token is required")
    return f"/exam/{quote(access_token, safe='-._~')}"


def help_request_link(request_id: int) -> str:
    """Return the existing student-visible notification page for a ticket.

    Ticket detail UI is scheduled separately; until then, linking to the
    notification inbox is reachable for both a student and an assigned admin.
    """
    _positive_id(request_id)
    return "/notifications"


_ANNOUNCEMENT_ROUTES = (
    (re.compile(r"^/courses/(\d+)$"), lambda match: course_link(int(match.group(1)))),
    (re.compile(r"^/learn/(\d+)/homework/(\d+)$"),
     lambda match: lesson_homework_link(int(match.group(1)), int(match.group(2)))),
    (re.compile(r"^/exam/([^/?#]+)$"), lambda match: exam_attempt_link(match.group(1))),
    (re.compile(r"^/notifications$"), lambda match: "/notifications"),
)


def announcement_link(value: str | None) -> str | None:
    """Accept only known student routes, then rebuild the canonical path."""
    if value is None or value == "":
        return None
    for pattern, build in _ANNOUNCEMENT_ROUTES:
        match = pattern.fullmatch(value)
        if match:
            return build(match)
    raise ValueError("通知跳转地址必须是受支持的站内页面。")
