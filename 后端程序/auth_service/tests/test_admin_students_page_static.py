"""学员页只消费后端下发的状态文案。"""
from pathlib import Path

from app.routers.admin_enrollments import ENROLLMENT_STATUS_LABELS
from app.routers.admin_students import STUDENT_STATUS_LABELS

ADMIN_DIR = Path(__file__).resolve().parents[3] / "前端程序" / "study-blog-vue" / "public" / "admin"


def test_students_page_does_not_hardcode_backend_status_labels():
    source = "\n".join(
        (ADMIN_DIR / name).read_text(encoding="utf-8")
        for name in ("students.js", "students.html", "student-picker.js")
    )
    for label in (*STUDENT_STATUS_LABELS.values(), *ENROLLMENT_STATUS_LABELS.values()):
        assert label not in source, f"学员状态文案 {label} 被硬编码进前端"


def test_students_page_renders_status_label_from_the_api():
    students_js = (ADMIN_DIR / "students.js").read_text(encoding="utf-8")
    assert "student.status_label" in students_js
    assert "student.status)" not in students_js


def test_students_page_renders_enrollment_status_from_the_api():
    students_js = (ADMIN_DIR / "students.js").read_text(encoding="utf-8")
    assert "row.status_label" in students_js
    assert "row.allowed_actions" in students_js
    assert "row.status ===" not in students_js
    assert "/enrollments" in students_js
    assert "data-enrollment-status" in students_js
