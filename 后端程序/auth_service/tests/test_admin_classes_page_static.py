"""班级管理页的状态与班内角色文案必须由后端下发。"""
from pathlib import Path

from app.routers.admin_classes import (
    CLASS_ROLE_LABELS,
    CLASS_STATUS_LABELS,
    MEMBER_STATUS_LABELS,
)
from app.routers.admin_enrollments import ENROLLMENT_STATUS_LABELS

ADMIN_DIR = Path(__file__).resolve().parents[3] / "前端程序" / "study-blog-vue" / "public" / "admin"


def test_classes_page_does_not_hardcode_backend_status_or_class_role_labels():
    source = "\n".join(
        (ADMIN_DIR / name).read_text(encoding="utf-8")
        for name in ("classes.js", "classes.html")
    )
    for label in (
        *CLASS_STATUS_LABELS.values(),
        *CLASS_ROLE_LABELS.values(),
        *MEMBER_STATUS_LABELS.values(),
        *ENROLLMENT_STATUS_LABELS.values(),
    ):
        assert label not in source, f"班级文案 {label} 被硬编码进前端"


def test_classes_page_renders_status_label_from_the_api():
    classes_js = (ADMIN_DIR / "classes.js").read_text(encoding="utf-8")
    assert classes_js.count("status_label") >= 2
    assert "escapeHtml(row.status)" not in classes_js


def test_classes_page_uses_global_role_options_and_select_transfer_picker():
    classes_js = (ADMIN_DIR / "classes.js").read_text(encoding="utf-8")
    admin_ui = (ADMIN_DIR / "admin-ui.js").read_text(encoding="utf-8")
    assert "roleOptions = Array.isArray(payload.role_options)" in classes_js
    assert "teacherPayload?.role_options" not in classes_js
    assert "selectOptions: options.map" in classes_js
    assert "teachers.forEach" not in classes_js
    assert "Array.isArray(selectOptions)" in admin_ui


def test_classes_page_wires_master_data_actions_and_capability_gate():
    classes_js = (ADMIN_DIR / "classes.js").read_text(encoding="utf-8")
    classes_html = (ADMIN_DIR / "classes.html").read_text(encoding="utf-8")
    assert 'adminRequest("/me")' in classes_js
    assert "can_manage_classes" in classes_js
    assert 'method: editingClassId ? "PUT" : "POST"' in classes_js
    assert 'adminRequest(`/classes/${row.id}/publish`' in classes_js
    assert 'adminRequest(`/classes/${row.id}/archive`' in classes_js
    assert 'adminRequest(`/classes/${row.id}`, { method: "DELETE" })' in classes_js
    for element_id in (
        "createClassBtn",
        "editClassBtn",
        "publishClassBtn",
        "archiveClassBtn",
        "deleteClassBtn",
        "classFormMask",
    ):
        assert f'id="{element_id}"' in classes_html


def test_classes_page_clears_relationship_state_after_load_failure_and_css_is_balanced():
    classes_js = (ADMIN_DIR / "classes.js").read_text(encoding="utf-8")
    css = (ADMIN_DIR / "admin.css").read_text(encoding="utf-8")
    failure_reset = "members = [];\n    teachers = [];"
    assert failure_reset in classes_js
    assert "memberHistoryVisible = false;\n    teacherHistoryVisible = false;" in classes_js
    assert "renderMembers();\n    renderTeachers();" in classes_js
    assert '$("classMemberEmpty").hidden = true;' in classes_js
    assert '$("classTeacherEmpty").hidden = true;' in classes_js
    assert css.count("{") == css.count("}")
