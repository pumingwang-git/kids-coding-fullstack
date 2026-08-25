"""审计摘要的唯一构造入口。"""

from __future__ import annotations

import json
import logging
from datetime import UTC, date, datetime
from typing import Any, Sequence

_SENSITIVE = ("password", "token", "secret", "ip", "email")
_MAX_BYTES = 4 * 1024
logger = logging.getLogger(__name__)

# 保留期的唯一口径。键是 audit_events.event_type 的最终数据库值。
CATEGORY_AUTHZ = "authz"
CATEGORY_GRADE = "grade"
CATEGORY_SESSION = "session"
CATEGORY_CONTENT = "content"
CATEGORY_COLLAB = "collab"
AUDIT_OUTCOMES = ("success", "failure")
AUDIT_OUTCOME_LABELS = {"success": "成功", "failure": "失败"}


def _admin_events(*events: str) -> set[str]:
    return {f"admin_{event}" for event in events}


EVENT_CATEGORY: dict[str, str] = {
    **{event: CATEGORY_CONTENT for event in _admin_events(
        "course_block_create", "course_block_delete",
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
        "material_upload_init", "paper_preview_answers", "problem_dry_run",
        "problem_approve", "problem_media_upload", "problem_reject", "problem_submit",
        "problem_tag_create", "scratch_challenge_approve",
        "scratch_challenge_create", "scratch_challenge_delete", "scratch_challenge_duplicate",
        "scratch_challenge_demo", "scratch_challenge_starter",
        "scratch_challenge_publish", "scratch_challenge_reject", "scratch_challenge_submit",
        "scratch_challenge_unpublish", "scratch_challenge_update", "video_delete",
        "video_upload_abort", "video_upload_complete", "video_upload_create",
    )},
    **{event: CATEGORY_AUTHZ for event in _admin_events(
        "enrollment_grant", "enrollment_status_change", "exam_assign", "exam_unassign",
        "audit_events_read", "role_change", "account_status_change", "class_teacher_assign",
        "class_teacher_unassign", "class_member_enroll", "class_member_withdraw",
        "class_member_transfer", "export_download",
    )},
    **{event: CATEGORY_GRADE for event in _admin_events(
        "course_homework_deadline_extend", "scratch_submission_review", "scratch_submission_return",
    )},
    # 学生端事件按实际库值登记（无 admin_ 前缀）。
    "profile_update": CATEGORY_AUTHZ,   # 改名/换头像属身份类变更，5 年
    "work_share": CATEGORY_COLLAB,      # 作品公开发布，传播范围类，2 年
    **{event: CATEGORY_COLLAB for event in _admin_events(
        "class_announcement_create", "notification_revoke", "help_request_create",
        "help_request_reply", "help_request_close", "help_request_reassign",
    )},
    **{event: CATEGORY_SESSION for event in _admin_events("login", "logout", "refresh")},
    **{event: CATEGORY_SESSION for event in (
        "email_resend", "email_verify", "login", "logout", "password_change",
        "password_change_request", "password_reset_confirm", "password_reset_request", "refresh", "register",
    )},
}

# 历史事件与包装器事件：这些值仍可能存在于库中，即使当前 router 没有裸
# `audit()` 字面量调用，仍必须可被后续保留期清理识别。
EVENT_CATEGORY.update({
    **{f"admin_{event}": CATEGORY_CONTENT for event in (
        "paper_archive", "paper_create", "paper_delete", "paper_link_create",
        "paper_link_delete", "paper_link_disable", "paper_link_enable", "paper_link_reset_token",
        "paper_link_update", "paper_link_reveal_url", "paper_publish", "paper_update", "paper_transfer_owner",
        # 历史事件，代码已移除：保留供清理任务识别。
        "problem_clone",
        "problem_create", "problem_delete",
        # 历史事件，代码已移除：保留供清理任务识别。
        "problem_offline",
        "problem_revise", "problem_testcase_meta", "problem_testdata_download", "problem_testdata_upload",
        "problem_unify_limits", "problem_update", "problem_transfer_owner",
    )},
    "exam_auto_seal": CATEGORY_GRADE, "exam_judge_failed": CATEGORY_GRADE,
    "exam_start": CATEGORY_GRADE, "exam_submit": CATEGORY_GRADE, "exam_entry_denied": CATEGORY_GRADE,
    # 由保留期清理 cron 写入的运行审计，按授权类长期保留。
    "audit_retention_purge": CATEGORY_AUTHZ,
})


def event_type_options() -> list[dict[str, str]]:
    """Return the event dictionary for management UIs from the canonical map."""
    options = []
    for machine_name in sorted(EVENT_CATEGORY):
        display_name = machine_name.removeprefix("admin_").replace("_", " ")
        options.append({
            "machine_name": machine_name,
            "display_name": display_name,
        })
    return options

RETENTION_DAYS = {
    CATEGORY_AUTHZ: 5 * 365,
    CATEGORY_GRADE: 5 * 365,
    CATEGORY_SESSION: 180,
    CATEGORY_CONTENT: 2 * 365,
    CATEGORY_COLLAB: 2 * 365,
}



def ensure_known_event_type(event_type: str, environment: str) -> None:
    """Reject unmapped events before they reach development/test databases.

    Production keeps the business action and audit write available while making
    the classification omission visible to operations.
    """
    if event_type in EVENT_CATEGORY:
        return
    message = f"未归类的审计 event_type：{event_type}"
    if environment == "production":
        logger.warning(message)
        return
    raise AssertionError(message)


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
