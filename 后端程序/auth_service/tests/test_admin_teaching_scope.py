from test_admin_results_scope import _role_login
from test_exam import build_app

import app.routers.admin_teaching as admin_teaching
from app.models import ClassGroup, Course, User


def test_teaching_routes_have_real_scope_coverage(tmp_path):
    app = build_app(tmp_path)
    db = app.state.session_factory()
    try:
        course = Course(title="范围覆盖守卫课包")
        db.add(course)
        db.flush()
        foreign_class = ClassGroup(
            name="教师范围外班级", course_id=course.id, status="active"
        )
        db.add(foreign_class)
        db.add(User(username="范围外学员", email="scope-profile@example.com", hashed_password="hash"))
        db.commit()
        foreign_class_id = foreign_class.id
    finally:
        db.close()

    editor, editor_headers = _role_login(app, "editor")
    reviewer, reviewer_headers = _role_login(app, "reviewer")
    teacher, teacher_headers = _role_login(app, "teacher")

    paths = {route.path for route in admin_teaching.router.routes}
    covered = set()

    resource_paths = {
        "/api/admin/teaching/classes/{class_id}/overview": (
            f"/api/admin/teaching/classes/{foreign_class_id}/overview",
            "/api/admin/teaching/classes/99999/overview",
        ),
        "/api/admin/teaching/classes/{class_id}/students": (
            f"/api/admin/teaching/classes/{foreign_class_id}/students",
            "/api/admin/teaching/classes/99999/students",
        ),
        "/api/admin/teaching/classes/{class_id}/homework": (
            f"/api/admin/teaching/classes/{foreign_class_id}/homework",
            "/api/admin/teaching/classes/99999/homework",
        ),
        "/api/admin/teaching/classes/{class_id}/exams": (
            f"/api/admin/teaching/classes/{foreign_class_id}/exams",
            "/api/admin/teaching/classes/99999/exams",
        ),
        "/api/admin/teaching/classes/{class_id}/weak-items": (
            f"/api/admin/teaching/classes/{foreign_class_id}/weak-items",
            "/api/admin/teaching/classes/99999/weak-items",
        ),
        "/api/admin/teaching/classes/{class_id}/export": (
            f"/api/admin/teaching/classes/{foreign_class_id}/export",
            "/api/admin/teaching/classes/99999/export",
        ),
    }
    for route_path, (foreign_path, missing_path) in resource_paths.items():
        for client, headers in ((editor, editor_headers), (reviewer, reviewer_headers)):
            denied = client.get(foreign_path, headers=headers)
            assert denied.status_code == 403, f"{route_path}: {denied.text}"

        denied = teacher.get(foreign_path, headers=teacher_headers)
        missing = teacher.get(missing_path, headers=teacher_headers)
        assert denied.status_code == missing.status_code == 404, route_path
        assert denied.json() == missing.json(), route_path
        covered.add(route_path)

    for route_path in (
        "/api/admin/teaching/classes",
        "/api/admin/teaching/review-queue",
    ):
        for client, headers in ((editor, editor_headers), (reviewer, reviewer_headers)):
            denied = client.get(route_path, headers=headers)
            assert denied.status_code == 403, f"{route_path}: {denied.text}"

        response = teacher.get(route_path, headers=teacher_headers)
        assert response.status_code == 200, f"{route_path}: {response.text}"
        assert response.json()["items"] == [], route_path
        covered.add(route_path)

    profile_path = "/api/admin/teaching/students/{student_id}/profile"
    for client, headers in ((editor, editor_headers), (reviewer, reviewer_headers)):
        denied = client.get("/api/admin/teaching/students/1/profile", headers=headers)
        assert denied.status_code == 403, f"{profile_path}: {denied.text}"
    denied = teacher.get("/api/admin/teaching/students/1/profile", headers=teacher_headers)
    missing = teacher.get("/api/admin/teaching/students/99999/profile", headers=teacher_headers)
    assert denied.status_code == missing.status_code == 404, profile_path
    assert denied.json() == missing.json(), profile_path
    covered.add(profile_path)

    assert covered
    assert paths == covered, f"新端点没有范围用例：{paths - covered}"
