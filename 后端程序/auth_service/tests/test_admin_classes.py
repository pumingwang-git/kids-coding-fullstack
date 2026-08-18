import json
from pathlib import Path

import pytest
from sqlalchemy import select
from test_exam import ADMIN_PASSWORD, admin_login, build_app

from app.models import AdminUser, AuditEvent, ClassMember, ClassTeacher, Course, User
from app.security import password_hash


def seed_course(app) -> int:
    db = app.state.session_factory()
    try:
        course = Course(title="班级测试课包")
        db.add(course)
        db.commit()
        return course.id
    finally:
        db.close()


def seed_student(app, student_id: int = 1) -> int:
    db = app.state.session_factory()
    try:
        db.add(
            User(
                id=student_id,
                username=f"student-{student_id}",
                email=f"student-{student_id}@example.com",
                hashed_password="hash",
            )
        )
        db.commit()
        return student_id
    finally:
        db.close()


def seed_teacher(app, admin_id: int = 4) -> int:
    db = app.state.session_factory()
    try:
        db.add(
            AdminUser(
                id=admin_id,
                username=f"teacher-{admin_id}",
                password_hash=password_hash.hash(ADMIN_PASSWORD),
                display_name="班级教师",
                role="teacher",
            )
        )
        db.commit()
        return admin_id
    finally:
        db.close()


def login_as_role(app, role: str, admin_id: int = 2):
    db = app.state.session_factory()
    try:
        db.add(
            AdminUser(
                id=admin_id,
                username=f"admin-{role}",
                password_hash=password_hash.hash(ADMIN_PASSWORD),
                display_name=role,
                role=role,
            )
        )
        db.commit()
    finally:
        db.close()

    from fastapi.testclient import TestClient

    client = TestClient(app)
    client.get("/api/admin/csrf")
    headers = {"X-CSRF-Token": client.cookies.get("admin_csrf_token")}
    response = client.post(
        "/api/admin/login",
        headers=headers,
        json={"username": f"admin-{role}", "password": ADMIN_PASSWORD},
    )
    assert response.status_code == 200, response.text
    return client, {"X-CSRF-Token": client.cookies.get("admin_csrf_token")}


def test_class_crud_archive_and_delete_guard(tmp_path: Path):
    app = build_app(tmp_path)
    client, headers = admin_login(app)
    course_id = seed_course(app)
    payload = {"name": "E2 A 班", "course_id": course_id}

    created = client.post("/api/admin/classes", headers=headers, json=payload)
    assert created.status_code == 201, created.text
    class_id = created.json()["id"]
    assert created.json()["status"] == "draft"
    assert created.json()["status_label"] == "草稿"

    updated = client.put(
        f"/api/admin/classes/{class_id}",
        headers=headers,
        json={**payload, "name": "E2 A 班（更新）"},
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "E2 A 班（更新）"

    archived = client.post(f"/api/admin/classes/{class_id}/archive", headers=headers)
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"
    assert client.get(f"/api/admin/classes/{class_id}", headers=headers).status_code == 200
    assert client.put(
        f"/api/admin/classes/{class_id}", headers=headers, json=payload
    ).status_code == 409

    assert client.delete(f"/api/admin/classes/{class_id}", headers=headers).status_code == 200
    assert client.get(f"/api/admin/classes/{class_id}", headers=headers).status_code == 404


def test_class_with_relationships_cannot_be_physically_deleted(tmp_path: Path):
    app = build_app(tmp_path)
    client, headers = admin_login(app)
    course_id = seed_course(app)
    class_id = client.post(
        "/api/admin/classes", headers=headers,
        json={"name": "历史班", "course_id": course_id},
    ).json()["id"]
    db = app.state.session_factory()
    try:
        db.add(
            User(
                username="history-student",
                email="history-student@example.com",
                hashed_password="hash",
            )
        )
        db.flush()
        db.add(ClassMember(class_id=class_id, student_id=1))
        db.commit()
    finally:
        db.close()

    assert client.delete(f"/api/admin/classes/{class_id}", headers=headers).status_code == 409
    assert client.get(f"/api/admin/classes/{class_id}", headers=headers).status_code == 200


def test_only_academic_admin_and_super_admin_can_manage_classes(tmp_path: Path):
    app = build_app(tmp_path)
    client, headers = login_as_role(app, "teacher")
    assert client.get("/api/admin/classes", headers=headers).json() == {"items": []}
    assert client.post(
        "/api/admin/classes", headers=headers,
        json={"name": "越权班", "course_id": 1},
    ).status_code == 403

    academic, academic_headers = login_as_role(app, "academic_admin", admin_id=3)
    course_id = seed_course(app)
    response = academic.post(
        "/api/admin/classes", headers=academic_headers,
        json={"name": "教务班", "course_id": course_id},
    )
    assert response.status_code == 201, response.text


def test_teacher_class_reads_are_scoped_and_out_of_scope_is_not_found(
    tmp_path: Path, caplog
):
    app = build_app(tmp_path)
    admin_client, admin_headers = admin_login(app)
    seed_student(app)
    course_id = seed_course(app)
    class_a = admin_client.post(
        "/api/admin/classes", headers=admin_headers,
        json={"name": "教师本班", "course_id": course_id},
    ).json()["id"]
    class_b = admin_client.post(
        "/api/admin/classes", headers=admin_headers,
        json={"name": "教师外班", "course_id": course_id},
    ).json()["id"]
    teacher, teacher_headers = login_as_role(app, "teacher", admin_id=2)

    db = app.state.session_factory()
    try:
        db.add(ClassTeacher(class_id=class_a, admin_user_id=2, role_in_class="teacher"))
        db.add(ClassMember(class_id=class_a, student_id=1))
        db.commit()
    finally:
        db.close()

    listed = teacher.get("/api/admin/classes", headers=teacher_headers)
    assert [row["id"] for row in listed.json()["items"]] == [class_a]
    own_members = teacher.get(
        f"/api/admin/classes/{class_a}/members", headers=teacher_headers
    )
    assert own_members.status_code == 200
    assert [row["student_id"] for row in own_members.json()["items"]] == [1]

    with caplog.at_level("WARNING", logger="app.permissions"):
        foreign = teacher.get(f"/api/admin/classes/{class_b}", headers=teacher_headers)
    missing = teacher.get("/api/admin/classes/99999", headers=teacher_headers)
    assert foreign.status_code == missing.status_code == 404
    assert foreign.json() == missing.json()
    assert any(
        record.getMessage().startswith(f"scope_denied role=teacher admin_user_id=2 resource=class_group:{class_b}")
        for record in caplog.records
    )

    with caplog.at_level("WARNING", logger="app.permissions"):
        foreign_members = teacher.get(
            f"/api/admin/classes/{class_b}/members", headers=teacher_headers
        )
    missing_members = teacher.get(
        "/api/admin/classes/99999/members", headers=teacher_headers
    )
    assert foreign_members.status_code == missing_members.status_code == 404
    assert foreign_members.json() == missing_members.json()


def test_archived_class_allows_withdraw_and_transfer_out_only(tmp_path: Path):
    app = build_app(tmp_path)
    client, headers = admin_login(app)
    seed_student(app, student_id=1)
    seed_student(app, student_id=2)
    course_id = seed_course(app)
    source_id = client.post(
        "/api/admin/classes", headers=headers,
        json={"name": "归档源班", "course_id": course_id},
    ).json()["id"]
    target_id = client.post(
        "/api/admin/classes", headers=headers,
        json={"name": "转入目标班", "course_id": course_id},
    ).json()["id"]
    member_one = client.post(
        f"/api/admin/classes/{source_id}/members", headers=headers,
        json={"student_id": 1},
    ).json()
    member_two = client.post(
        f"/api/admin/classes/{source_id}/members", headers=headers,
        json={"student_id": 2},
    ).json()
    assert client.post(f"/api/admin/classes/{source_id}/archive", headers=headers).status_code == 200

    withdrawn = client.post(
        f"/api/admin/classes/{source_id}/members/{member_one['id']}/withdraw",
        headers=headers,
    )
    assert withdrawn.status_code == 200
    transferred = client.post(
        f"/api/admin/classes/{source_id}/members/{member_two['id']}/transfer",
        headers=headers,
        json={"to_class_id": target_id},
    )
    assert transferred.status_code == 201
    assert client.post(
        f"/api/admin/classes/{source_id}/members",
        headers=headers,
        json={"student_id": 1},
    ).status_code == 409


def test_teacher_assignment_unassignment_and_failure_audit(tmp_path: Path):
    app = build_app(tmp_path)
    client, headers = admin_login(app)
    teacher_id = seed_teacher(app)
    course_id = seed_course(app)
    class_id = client.post(
        "/api/admin/classes", headers=headers,
        json={"name": "带班测试", "course_id": course_id},
    ).json()["id"]

    assigned = client.post(
        f"/api/admin/classes/{class_id}/teachers",
        headers=headers,
        json={"admin_user_id": teacher_id, "role_in_class": "teacher"},
    )
    assert assigned.status_code == 201, assigned.text
    assert assigned.json()["role_in_class_label"] == "主讲教师"
    assignment_id = assigned.json()["id"]

    db = app.state.session_factory()
    try:
        event = db.scalar(
            select(AuditEvent)
            .where(AuditEvent.event_type == "admin_class_teacher_assign")
            .order_by(AuditEvent.id.desc())
        )
        assert event.outcome == "success"
        assert event.admin_user_id == 1
        assert event.resource_type == "class_teacher"
        assert event.resource_id == assignment_id
        summary = json.loads(event.summary_json)
        assert summary["teacher_admin_user_id"] == teacher_id
        assert summary["role_in_class"] == "teacher"
        assert summary["assigned_at"].endswith("Z")
    finally:
        db.close()

    unassigned = client.post(
        f"/api/admin/classes/{class_id}/teachers/{assignment_id}/unassign",
        headers=headers,
    )
    assert unassigned.status_code == 200
    assert unassigned.json()["ended_at"] is not None

    teacher_client, teacher_headers = login_as_role(app, "teacher", admin_id=2)
    denied = teacher_client.post(
        f"/api/admin/classes/{class_id}/teachers",
        headers=teacher_headers,
        json={"admin_user_id": teacher_id, "role_in_class": "assistant"},
    )
    assert denied.status_code == 403
    db = app.state.session_factory()
    try:
        failure = db.scalar(
            select(AuditEvent)
            .where(
                AuditEvent.event_type == "admin_class_teacher_assign",
                AuditEvent.outcome == "failure",
            )
            .order_by(AuditEvent.id.desc())
        )
        assert failure is not None
        assert failure.admin_user_id == 2
        assert json.loads(failure.summary_json)["reason_code"] == "forbidden"
        assert db.scalar(select(ClassTeacher.id).where(ClassTeacher.id == assignment_id)) is not None
    finally:
        db.close()


def test_enroll_withdraw_and_transfer_have_atomic_audit_contract(tmp_path: Path, monkeypatch):
    app = build_app(tmp_path)
    client, headers = admin_login(app)
    seed_student(app)
    course_id = seed_course(app)
    class_a = client.post(
        "/api/admin/classes", headers=headers,
        json={"name": "转出班", "course_id": course_id},
    ).json()["id"]
    class_b = client.post(
        "/api/admin/classes", headers=headers,
        json={"name": "转入班", "course_id": course_id},
    ).json()["id"]

    enrolled = client.post(
        f"/api/admin/classes/{class_a}/members",
        headers=headers,
        json={"student_id": 1},
    )
    assert enrolled.status_code == 201, enrolled.text
    member_id = enrolled.json()["id"]

    transferred = client.post(
        f"/api/admin/classes/{class_a}/members/{member_id}/transfer",
        headers=headers,
        json={"to_class_id": class_b},
    )
    assert transferred.status_code == 201, transferred.text
    new_member_id = transferred.json()["id"]

    db = app.state.session_factory()
    try:
        old = db.get(ClassMember, member_id)
        new = db.get(ClassMember, new_member_id)
        assert old.status == "left" and old.left_at is not None
        assert new.status == "active" and new.left_at is None
        events = db.scalars(
            select(AuditEvent).where(AuditEvent.event_type == "admin_class_member_transfer")
        ).all()
        assert len(events) == 1
        summary = json.loads(events[0].summary_json)
        assert summary["from_membership_id"] == member_id
        assert summary["to_membership_id"] == new_member_id
        assert summary["from_class_id"] == class_a
        assert summary["to_class_id"] == class_b
    finally:
        db.close()

    withdrawn = client.post(
        f"/api/admin/classes/{class_b}/members/{new_member_id}/withdraw",
        headers=headers,
    )
    assert withdrawn.status_code == 200
    assert withdrawn.json()["status"] == "left"

    # A failure after both relationship mutations have been flushed must roll back all three writes.
    seed_student(app, student_id=2)
    second = client.post(
        f"/api/admin/classes/{class_a}/members",
        headers=headers,
        json={"student_id": 2},
    ).json()

    from app.routers import admin_classes

    def fail_after_flush(*_args, **_kwargs):
        raise RuntimeError("injected transfer failure")

    monkeypatch.setattr(admin_classes, "_audit_success", fail_after_flush)
    with pytest.raises(RuntimeError, match="injected transfer failure"):
        client.post(
            f"/api/admin/classes/{class_a}/members/{second['id']}/transfer",
            headers=headers,
            json={"to_class_id": class_b},
        )
    db = app.state.session_factory()
    try:
        old = db.get(ClassMember, second["id"])
        assert old.status == "active" and old.left_at is None
        assert db.scalar(
            select(ClassMember.id).where(
                ClassMember.class_id == class_b, ClassMember.student_id == 2
            )
        ) is None
        assert db.scalar(
            select(AuditEvent.id).where(
                AuditEvent.event_type == "admin_class_member_transfer",
                AuditEvent.resource_id != new_member_id,
            )
        ) is None
    finally:
        db.close()
