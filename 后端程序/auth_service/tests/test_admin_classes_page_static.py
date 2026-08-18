"""班级管理页的状态与班内角色文案必须由后端下发。"""
from pathlib import Path

from app.routers.admin_classes import CLASS_ROLE_LABELS, CLASS_STATUS_LABELS

ADMIN_DIR = Path(__file__).resolve().parents[3] / "前端程序" / "study-blog-vue" / "public" / "admin"


def test_classes_page_does_not_hardcode_backend_status_or_class_role_labels():
    source = "\n".join(
        (ADMIN_DIR / name).read_text(encoding="utf-8")
        for name in ("classes.js", "classes.html")
    )
    for label in (*CLASS_STATUS_LABELS.values(), *CLASS_ROLE_LABELS.values()):
        assert label not in source, f"班级文案 {label} 被硬编码进前端"


def test_classes_page_renders_status_label_from_the_api():
    classes_js = (ADMIN_DIR / "classes.js").read_text(encoding="utf-8")
    assert classes_js.count("status_label") >= 2
    assert "escapeHtml(row.status)" not in classes_js
