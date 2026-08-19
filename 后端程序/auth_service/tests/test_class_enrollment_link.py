"""E3b: class membership owns only its own enrollment history."""
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import select
from test_admin_classes import seed_course, seed_student
from test_exam import admin_login, build_app

from app.models import Enrollment
from app.security import as_utc


def create_class(client, headers, course_id: int, name: str, **window) -> int:
    response = client.post(
        "/api/admin/classes", headers=headers, json={"name": name, "course_id": course_id, **window}
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def enrollments(app, student_id: int) -> list[Enrollment]:
    db = app.state.session_factory()
    try:
        return db.scalars(select(Enrollment).where(Enrollment.student_id == student_id)).all()
    finally:
        db.close()


def test_withdraw_disables_only_its_class_source(tmp_path: Path):
    app = build_app(tmp_path)
    client, headers = admin_login(app)
    seed_student(app)
    course_id = seed_course(app)
    class_id = create_class(client, headers, course_id, "来源隔离班")
    member = client.post(
        f"/api/admin/classes/{class_id}/members", headers=headers, json={"student_id": 1}
    ).json()

    db = app.state.session_factory()
    try:
        db.add(Enrollment(student_id=1, course_id=course_id, source="admin", status="active"))
        db.commit()
    finally:
        db.close()

    response = client.post(
        f"/api/admin/classes/{class_id}/members/{member['id']}/withdraw", headers=headers
    )
    assert response.status_code == 200, response.text
    rows = enrollments(app, 1)
    assert {(row.source, row.class_id, row.status) for row in rows} == {
        ("class_batch", class_id, "disabled"),
        ("admin", None, "active"),
    }


def test_transfer_replaces_source_class_enrollment(tmp_path: Path):
    app = build_app(tmp_path)
    client, headers = admin_login(app)
    seed_student(app)
    course_a = seed_course(app)
    course_b = seed_course(app)
    source = create_class(client, headers, course_a, "源班")
    target = create_class(client, headers, course_b, "目标班")
    member = client.post(
        f"/api/admin/classes/{source}/members", headers=headers, json={"student_id": 1}
    ).json()

    response = client.post(
        f"/api/admin/classes/{source}/members/{member['id']}/transfer",
        headers=headers,
        json={"to_class_id": target},
    )
    assert response.status_code == 201, response.text
    assert {(row.class_id, row.course_id, row.status) for row in enrollments(app, 1)} == {
        (source, course_a, "disabled"),
        (target, course_b, "active"),
    }


def test_withdraw_disables_a_future_class_enrollment(tmp_path: Path):
    app = build_app(tmp_path)
    client, headers = admin_login(app)
    seed_student(app)
    course_id = seed_course(app)
    class_id = create_class(
        client, headers, course_id, "未来开通班", start_at=(datetime.now(UTC) + timedelta(days=1)).isoformat()
    )
    member = client.post(
        f"/api/admin/classes/{class_id}/members", headers=headers, json={"student_id": 1}
    ).json()
    rows = enrollments(app, 1)
    assert rows[0].status == "active" and as_utc(rows[0].opened_at) > datetime.now(UTC)

    response = client.post(
        f"/api/admin/classes/{class_id}/members/{member['id']}/withdraw", headers=headers
    )
    assert response.status_code == 200, response.text
    assert enrollments(app, 1)[0].status == "disabled"


def test_manual_sync_replaces_an_expired_active_class_enrollment(tmp_path: Path):
    app = build_app(tmp_path)
    client, headers = admin_login(app)
    seed_student(app)
    course_id = seed_course(app)
    class_id = create_class(
        client, headers, course_id, "窗口内班级", end_at=(datetime.now(UTC) + timedelta(days=5)).isoformat()
    )
    client.post(
        f"/api/admin/classes/{class_id}/members", headers=headers, json={"student_id": 1}
    )

    db = app.state.session_factory()
    try:
        row = db.scalar(
            select(Enrollment).where(
                Enrollment.student_id == 1,
                Enrollment.class_id == class_id,
                Enrollment.status == "active",
            )
        )
        row.expires_at = datetime.now(UTC) - timedelta(minutes=1)
        db.commit()
    finally:
        db.close()

    response = client.post(f"/api/admin/classes/{class_id}/enrollments/sync", headers=headers)
    assert response.status_code == 200, response.text
    assert response.json() == {"granted": 1, "skipped": 0}
    rows = enrollments(app, 1)
    assert len(rows) == 2 and all(row.status == "active" for row in rows)
    assert any(row.expires_at is not None and as_utc(row.expires_at) < datetime.now(UTC) for row in rows)
    assert any(row.expires_at is None or as_utc(row.expires_at) > datetime.now(UTC) for row in rows)


def test_end_date_sync_replaces_history_and_manual_sync_is_idempotent(tmp_path: Path):
    app = build_app(tmp_path)
    client, headers = admin_login(app)
    seed_student(app)
    course_id = seed_course(app)
    old_end = datetime.now(UTC) + timedelta(days=5)
    class_id = create_class(client, headers, course_id, "改期班", end_at=old_end.isoformat())
    client.post(f"/api/admin/classes/{class_id}/members", headers=headers, json={"student_id": 1})
    new_end = datetime.now(UTC) + timedelta(days=10)
    response = client.put(
        f"/api/admin/classes/{class_id}",
        headers=headers,
        json={"name": "改期班", "course_id": course_id, "end_at": new_end.isoformat()},
    )
    assert response.status_code == 200, response.text
    rows = enrollments(app, 1)
    assert [row.status for row in rows] == ["disabled", "active"]
    assert as_utc(rows[-1].expires_at) == new_end

    first = client.post(f"/api/admin/classes/{class_id}/enrollments/sync", headers=headers)
    second = client.post(f"/api/admin/classes/{class_id}/enrollments/sync", headers=headers)
    assert first.json() == {"granted": 0, "skipped": 1}
    assert second.json() == {"granted": 0, "skipped": 1}
