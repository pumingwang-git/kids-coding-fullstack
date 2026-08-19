from pathlib import Path

from test_admin_classes import login_as_role, seed_course
from test_exam import admin_login, build_app

from app.models import ClassTeacher


def test_teaching_classes_enforces_reader_roles_and_empty_teacher_scope(tmp_path: Path):
    app = build_app(tmp_path)
    manager, manager_headers = admin_login(app)
    course_id = seed_course(app)
    class_id = manager.post(
        "/api/admin/classes", headers=manager_headers,
        json={"name": "教师工作台班", "course_id": course_id},
    ).json()["id"]

    for role in ("editor", "reviewer"):
        client, headers = login_as_role(app, role, admin_id=10 if role == "editor" else 11)
        assert client.get("/api/admin/teaching/classes", headers=headers).status_code == 403

    teacher, teacher_headers = login_as_role(app, "teacher", admin_id=12)
    assert teacher.get("/api/admin/teaching/classes", headers=teacher_headers).json() == {
        "items": []
    }

    db = app.state.session_factory()
    try:
        db.add(ClassTeacher(class_id=class_id, admin_user_id=12, role_in_class="teacher"))
        db.commit()
    finally:
        db.close()
    response = teacher.get("/api/admin/teaching/classes", headers=teacher_headers)
    assert response.status_code == 200
    assert [row["id"] for row in response.json()["items"]] == [class_id]


def test_teaching_classes_match_admin_classes_scope(tmp_path: Path):
    app = build_app(tmp_path)
    manager, manager_headers = admin_login(app)
    course_id = seed_course(app)
    class_ids = [
        manager.post(
            "/api/admin/classes", headers=manager_headers,
            json={"name": name, "course_id": course_id},
        ).json()["id"]
        for name in ("工作台一班", "工作台二班")
    ]
    teacher, teacher_headers = login_as_role(app, "teacher", admin_id=13)
    db = app.state.session_factory()
    try:
        db.add(ClassTeacher(class_id=class_ids[0], admin_user_id=13, role_in_class="teacher"))
        db.add(
            ClassTeacher(
                class_id=class_ids[1], admin_user_id=13, role_in_class="assistant",
            )
        )
        db.commit()
    finally:
        db.close()

    teaching = teacher.get("/api/admin/teaching/classes", headers=teacher_headers)
    classes = teacher.get("/api/admin/classes", headers=teacher_headers)
    assert teaching.status_code == classes.status_code == 200
    assert {row["id"] for row in teaching.json()["items"]} == {
        row["id"] for row in classes.json()["items"]
    }


def test_teaching_overview_scope_denial_matches_missing_class(tmp_path: Path):
    app = build_app(tmp_path)
    manager, manager_headers = admin_login(app)
    course_id = seed_course(app)
    foreign_class_id = manager.post(
        "/api/admin/classes", headers=manager_headers,
        json={"name": "他人班级", "course_id": course_id},
    ).json()["id"]
    teacher, teacher_headers = login_as_role(app, "teacher", admin_id=14)

    foreign = teacher.get(
        f"/api/admin/teaching/classes/{foreign_class_id}/overview",
        headers=teacher_headers,
    )
    missing = teacher.get(
        "/api/admin/teaching/classes/99999/overview", headers=teacher_headers
    )
    assert foreign.status_code == missing.status_code == 404
    assert foreign.json() == missing.json() == {"detail": "班级不存在。"}


def test_teaching_router_does_not_query_teacher_relationships_directly():
    source = Path(__file__).parents[1] / "app" / "routers" / "admin_teaching.py"
    text = source.read_text(encoding="utf-8")
    assert "ClassTeacher" not in text
    assert "class_teachers" not in text
