"""同屏答疑管理侧功能闸；资源范围仍由 ``permissions.py`` 收窄。"""

from __future__ import annotations

from .permissions import has_capability


def can_respond_to_help(admin, db=None) -> bool:
    return has_capability(admin, "help_respond", db)


def can_start_realtime_assist(admin, db=None) -> bool:
    return has_capability(admin, "realtime_assist", db)


def can_request_support_content(admin, db=None) -> bool:
    return has_capability(admin, "support_content_request", db)


def can_approve_support_content(admin, db=None) -> bool:
    return has_capability(admin, "support_content_approve", db)
