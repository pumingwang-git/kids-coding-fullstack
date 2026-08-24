"""审计摘要的唯一构造入口。"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from typing import Any, Sequence

_SENSITIVE = ("password", "token", "secret", "ip", "email")
_MAX_BYTES = 4 * 1024

# 保留期的唯一口径。新审计事件必须先进入此表，测试会扫描 router 中的字面量调用。
EVENT_CATEGORY = {
    **{event: "content" for event in (
        "class_announcement_create", "course_block_create", "course_block_delete",
        "course_block_reorder", "course_block_update", "course_category_create",
        "course_category_delete", "course_category_update", "course_cover_upload", "course_create",
        "course_delete", "course_lesson_create", "course_lesson_delete", "course_lesson_move",
        "course_lesson_reorder", "course_lesson_update", "course_off_shelf", "course_publish",
        "course_section_create", "course_section_delete", "course_section_reorder",
        "course_section_update", "course_update", "learning_area_create", "learning_area_delete",
        "learning_area_modules_update", "learning_area_update", "lesson_block_bind_materials",
        "lesson_block_unbind_material", "material_delete", "material_folder_create",
        "material_folder_delete", "material_folder_update", "material_import_cancel",
        "material_import_create", "material_import_finalize_start", "material_import_item_complete",
        "material_import_manifest", "material_import_upload_init", "material_set_tags",
        "material_tag_create", "material_upload_abort", "material_upload_complete",
        "material_upload_init", "notification_revoke", "paper_preview_answers", "problem_dry_run",
        "problem_media_upload", "problem_tag_create", "scratch_challenge_approve",
        "scratch_challenge_create", "scratch_challenge_delete", "scratch_challenge_duplicate",
        "scratch_challenge_publish", "scratch_challenge_reject", "scratch_challenge_submit",
        "scratch_challenge_unpublish", "scratch_challenge_update", "video_delete",
        "video_upload_abort", "video_upload_complete", "video_upload_create", "export_download",
    )},
    **{event: "authorization" for event in (
        "enrollment_grant", "enrollment_status_change", "exam_assign", "exam_unassign",
        "help_request_create", "help_request_reply", "help_request_close", "help_request_reassign",
        "audit_events_read",
    )},
    **{event: "grade_deadline" for event in (
        "course_homework_deadline_extend", "scratch_submission_review", "scratch_submission_return",
    )},
    **{event: "session" for event in (
        "email_resend", "email_verify", "login", "logout", "password_change",
        "password_change_request", "password_reset_confirm", "password_reset_request", "refresh", "register",
    )},
}

RETENTION_DAYS = {
    "authorization": 5 * 365,
    "grade_deadline": 5 * 365,
    "session": 180,
    "content": 2 * 365,
}


def _safe_name(name: str) -> bool:
    lowered = name.lower()
    return not any(part in lowered for part in _SENSITIVE)


def _json_value(value: Any) -> Any:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if isinstance(value, date):
        return value.isoformat()
    return value


def diff_summary(before: dict, after: dict, fields: Sequence[str]) -> dict:
    """Return a bounded, allow-listed old/new diff with stable schema version 1."""
    changed: dict[str, dict[str, Any]] = {}
    for field in fields:
        if not _safe_name(field):
            continue
        old = _json_value(before.get(field))
        new = _json_value(after.get(field))
        if old != new:
            changed[field] = {"old": old, "new": new}
    result: dict[str, Any] = {"schema_version": 1, "changed": changed}
    if len(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")) <= _MAX_BYTES:
        return result
    bounded: dict[str, dict[str, Any]] = {}
    for field in sorted(changed):
        candidate = {"schema_version": 1, "changed": {**bounded, field: changed[field]}, "truncated": True}
        if len(json.dumps(candidate, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")) > _MAX_BYTES:
            break
        bounded[field] = changed[field]
    return {"schema_version": 1, "changed": bounded, "truncated": True}
