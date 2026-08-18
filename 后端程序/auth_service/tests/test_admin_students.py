from pathlib import Path

from test_admin_classes import login_as_role, seed_course, seed_student
from test_exam import admin_login, build_app

from app.models import ClassMember, ClassTeacher


def test_students_list_uses_new_pagination_sorting_and_search_contract(tmp_path: Path):
    app = build_app(tmp_path)
    client, headers = admin_login(app)
    for student_id in range(1, 6):
        seed_student(app, student_id)

    response = client.get(
        "/api/admin/students",
        headers=headers,
        params={"page": 2, "page_size": 2, "sort": "-id"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert [row["id"] for row in body["items"]] == [3, 2]
    assert body["total"] == 5
    assert body["page"] == 2
    assert body["page_size"] == 2
    assert body["items"][0]["status_label"] == "待验证"
    searched = client.get("/api/admin/students", headers=headers, params={"keyword": "student-4"})
    assert [row["id"] for row in searched.json()["items"]] == [4]
    assert client.get("/api/admin/students", headers=headers, params={"sort": "password"}).status_code == 422


def test_students_list_and_detail_are_limited_to_active_class_members(tmp_path: Path, caplog):
    app = build_app(tmp_path)
    super_client, super_headers = admin_login(app)
    seed_student(app, 1)
    seed_student(app, 2)
    course_id = seed_course(app)
    own_class_id = super_client.post(
        "/api/admin/classes", headers=super_headers, json={"name": "本班", "course_id": course_id}
    ).json()["id"]
    other_class_id = super_client.post(
        "/api/admin/classes", headers=super_headers, json={"name": "其他班", "course_id": course_id}
    ).json()["id"]
    teacher, teacher_headers = login_as_role(app, "teacher", admin_id=2)

    db = app.state.session_factory()
    try:
        db.add(ClassTeacher(class_id=own_class_id, admin_user_id=2, role_in_class="teacher"))
        db.add(ClassMember(class_id=own_class_id, student_id=1))
        db.add(ClassMember(class_id=other_class_id, student_id=2))
        db.commit()
    finally:
        db.close()

    listed = teacher.get("/api/admin/students", headers=teacher_headers)
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert [row["id"] for row in listed.json()["items"]] == [1]
    assert teacher.get("/api/admin/students/1", headers=teacher_headers).status_code == 200

    with caplog.at_level("WARNING", logger="app.permissions"):
        foreign = teacher.get("/api/admin/students/2", headers=teacher_headers)
    missing = teacher.get("/api/admin/students/99999", headers=teacher_headers)
    assert foreign.status_code == missing.status_code == 404
    assert foreign.json() == missing.json()
    assert any(
        record.getMessage().startswith(
            "scope_denied role=teacher admin_user_id=2 resource=student:2"
        )
        for record in caplog.records
    )


def test_roles_without_student_read_capability_are_forbidden(tmp_path: Path, caplog):
    app = build_app(tmp_path)
    seed_student(app)
    editor, headers = login_as_role(app, "editor", admin_id=2)

    with caplog.at_level("WARNING", logger="app.permissions"):
        listed = editor.get("/api/admin/students", headers=headers)
        detail = editor.get("/api/admin/students/1", headers=headers)
    assert listed.status_code == detail.status_code == 403
    assert not caplog.records
