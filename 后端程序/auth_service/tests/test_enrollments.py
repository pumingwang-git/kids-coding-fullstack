"""E3a 个人课程开通与统一课程资格门控的少量回归。"""
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select
from test_admin_classes import login_as_role, seed_student
from test_admin_course_content import block_payload
from test_admin_courses import add_section, create_category, create_course
from test_exam import admin_login, build_app, scsrf, student_login
from test_student_learning import build_published_course, seed_ready_video

from app.models import AuditEvent, Enrollment, User


def learner_id(app) -> int:
    db = app.state.session_factory()
    try:
        return db.scalar(select(User.id).where(User.username == "learner"))
    finally:
        db.close()


def set_enrollment(app, *, student_id: int, course_id: int, **values) -> None:
    db = app.state.session_factory()
    try:
        row = db.scalar(
            select(Enrollment).where(
                Enrollment.student_id == student_id,
                Enrollment.course_id == course_id,
            )
        )
        if row is None:
            row = Enrollment(
                student_id=student_id,
                course_id=course_id,
                source="admin",
                opened_at=datetime.now(UTC) - timedelta(days=1),
            )
            db.add(row)
        for key, value in values.items():
            setattr(row, key, value)
        db.commit()
    finally:
        db.close()


def test_admin_grant_is_admin_only_idempotent_and_closed_source_contract(tmp_path: Path):
    app = build_app(tmp_path)
    built = build_published_course(app, trial=False, bind_video=True)
    admin, headers = built["client"], built["headers"]
    student_id = seed_student(app, 7)

    payload = {"student_id": student_id, "course_id": built["course_id"]}
    first = admin.post("/api/admin/enrollments", headers=headers, json=payload)
    assert first.status_code == 201, first.text
    assert first.json()["source"] == "admin"
    assert first.json()["status"] == "active"

    second = admin.post(
        "/api/admin/enrollments",
        headers=headers,
        json={**payload, "expires_at": "2030-01-01T00:00:00Z"},
    )
    assert second.status_code == 201, second.text
    db = app.state.session_factory()
    try:
        rows = db.scalars(
            select(Enrollment).where(
                Enrollment.student_id == student_id,
                Enrollment.course_id == built["course_id"],
            )
        ).all()
        assert len(rows) == 2
        assert any(row.expires_at is not None for row in rows)
    finally:
        db.close()

    listed = admin.get(
        "/api/admin/enrollments",
        headers=headers,
        params={"student_id": student_id, "course_id": built["course_id"]},
    )
    assert listed.status_code == 200
    assert listed.json()["total"] == 2
    enrollment_id = listed.json()["items"][0]["id"]
    disabled = admin.put(
        f"/api/admin/enrollments/{enrollment_id}/status",
        headers=headers,
        json={"status": "disabled"},
    )
    assert disabled.status_code == 200
    assert disabled.json()["status"] == "disabled"
    assert disabled.json()["status_label"] == "已停用"

    rejected = admin.post(
        "/api/admin/enrollments",
        headers=headers,
        json={**payload, "source": "class_batch"},
    )
    assert rejected.status_code == 422

    editor, editor_headers = login_as_role(app, "editor", admin_id=21)
    assert editor.post("/api/admin/enrollments", headers=editor_headers, json=payload).status_code == 403

    db = app.state.session_factory()
    try:
        events = db.scalars(
            select(AuditEvent).where(
                AuditEvent.event_type.in_(
                    ["admin_enrollment_grant", "admin_enrollment_status_change"]
                )
            ).order_by(AuditEvent.id)
        ).all()
        assert [event.event_type for event in events] == [
            "admin_enrollment_grant",
            "admin_enrollment_grant",
            "admin_enrollment_status_change",
            "admin_enrollment_grant",
        ]
        assert all(event.admin_user_id == 1 for event in events[:3])
        assert events[-1].outcome == "failure"
        assert json.loads(events[0].summary_json)["student_user_id"] == student_id
        assert json.loads(events[2].summary_json)["new_status"] == "disabled"
        assert json.loads(events[-1].summary_json)["reason_code"] == "forbidden"
    finally:
        db.close()


@pytest.mark.parametrize(
    ("label", "values", "granted"),
    [
        ("valid", {"opened_at": datetime.now(UTC) - timedelta(minutes=1)}, True),
        ("not_started", {"opened_at": datetime.now(UTC) + timedelta(days=1)}, False),
        ("expired", {"opened_at": datetime.now(UTC) - timedelta(days=2), "expires_at": datetime.now(UTC) - timedelta(days=1)}, False),
        ("disabled", {"opened_at": datetime.now(UTC) - timedelta(days=1), "status": "disabled"}, False),
    ],
)
def test_enrollment_time_and_status_gate_course_lesson_and_video(tmp_path: Path, values, granted: bool, label: str):
    app = build_app(tmp_path)
    built = build_published_course(app, trial=False, bind_video=True)
    student = student_login(app)
    sid = learner_id(app)
    set_enrollment(app, student_id=sid, course_id=built["course_id"], **values)

    detail = student.get(f"/api/courses/{built['course_id']}")
    assert detail.status_code == 200, label
    assert detail.json()["enrolled"] is granted

    lesson = student.get(f"/api/lessons/{built['lesson_id']}")
    assert lesson.status_code == 200, label
    assert lesson.json()["unlocked"] is granted
    assert (lesson.json()["content_md"] == "# 你好") is granted

    play = student.post(f"/api/lessons/{built['lesson_id']}/play", headers=scsrf(student))
    assert play.status_code == (200 if granted else 403), label


def test_enrollment_opens_markdown_and_video_blocks(tmp_path: Path):
    app = build_app(tmp_path)
    admin, headers = admin_login(app)
    category = create_category(admin, headers).json()
    course = create_course(admin, headers, category["id"], title="块级开通").json()
    section = add_section(admin, headers, course["id"]).json()
    lesson = admin.post(
        f"/api/admin/sections/{section['id']}/lessons", headers=headers,
        json={"title": "块级课时", "open_policy": "closed", "duration_minutes": 10},
    ).json()
    admin.post(
        f"/api/admin/lessons/{lesson['id']}/blocks", headers=headers,
        json=block_payload("markdown", content_md="# 已开通"),
    )
    video = seed_ready_video(app)
    video_block = admin.post(
        f"/api/admin/lessons/{lesson['id']}/blocks", headers=headers,
        json=block_payload("video", source_type="platform", video_id=video["video_id"]),
    ).json()
    assert admin.post(f"/api/admin/courses/{course['id']}/publish", headers=headers).status_code == 200

    student = student_login(app)
    sid = learner_id(app)
    set_enrollment(app, student_id=sid, course_id=course["id"])
    body = student.get(f"/api/lessons/{lesson['id']}").json()
    assert body["unlocked"] is True
    assert body["blocks"][0]["content_md"] == "# 已开通"
    assert body["blocks"][1]["can_access"] is True
    play = student.post(
        f"/api/lessons/{lesson['id']}/play",
        headers=scsrf(student), json={"block_id": video_block["id"]},
    )
    assert play.status_code == 200, play.text


def test_enrollment_phase_partition_filters_and_expired_disabled_restore_guard(tmp_path: Path):
    app = build_app(tmp_path)
    built = build_published_course(app, trial=False, bind_video=False)
    admin, headers = built["client"], built["headers"]
    now = datetime.now(UTC)
    active_id = seed_student(app, 7)
    not_started_id = seed_student(app, 10)
    expired_id = seed_student(app, 8)
    disabled_id = seed_student(app, 9)
    disabled_expired_id = seed_student(app, 11)
    set_enrollment(
        app,
        student_id=active_id,
        course_id=built["course_id"],
        opened_at=now - timedelta(days=1),
    )
    set_enrollment(
        app,
        student_id=not_started_id,
        course_id=built["course_id"],
        opened_at=now + timedelta(days=1),
    )
    set_enrollment(
        app,
        student_id=expired_id,
        course_id=built["course_id"],
        opened_at=now - timedelta(days=2),
        expires_at=now - timedelta(days=1),
    )
    set_enrollment(
        app,
        student_id=disabled_id,
        course_id=built["course_id"],
        opened_at=now - timedelta(days=1),
        status="disabled",
    )
    set_enrollment(
        app,
        student_id=disabled_expired_id,
        course_id=built["course_id"],
        opened_at=now - timedelta(days=2),
        expires_at=now - timedelta(days=1),
        status="disabled",
    )

    expected_phase = {
        active_id: "active",
        not_started_id: "not_started",
        expired_id: "expired",
        disabled_id: "disabled",
        disabled_expired_id: "expired",
    }
    expected_actions = {
        active_id: ["disable"],
        not_started_id: [],
        expired_id: [],
        disabled_id: ["restore"],
        disabled_expired_id: [],
    }

    unfiltered = admin.get(
        "/api/admin/enrollments",
        headers=headers,
        params={"course_id": built["course_id"]},
    )
    assert unfiltered.status_code == 200, unfiltered.text
    rows_by_student = {row["student_id"]: row for row in unfiltered.json()["items"]}
    assert {student_id: row["status"] for student_id, row in rows_by_student.items()} == expected_phase
    assert {student_id: row["allowed_actions"] for student_id, row in rows_by_student.items()} == expected_actions

    memberships = {student_id: [] for student_id in expected_phase}
    for phase in ("active", "not_started", "expired", "disabled"):
        response = admin.get(
            "/api/admin/enrollments",
            headers=headers,
            params={"course_id": built["course_id"], "status": phase},
        )
        assert response.status_code == 200, response.text
        for row in response.json()["items"]:
            memberships[row["student_id"]].append(phase)

    assert {student_id: phases[0] for student_id, phases in memberships.items() if len(phases) == 1} == expected_phase
    assert all(len(phases) == 1 for phases in memberships.values())

    expired_disabled_row = rows_by_student[disabled_expired_id]
    restore = admin.put(
        f"/api/admin/enrollments/{expired_disabled_row['id']}/status",
        headers=headers,
        json={"status": "active"},
    )
    assert restore.status_code == 409, restore.text
    assert admin.get("/api/admin/enrollments", headers=headers, params={"page": 0}).status_code == 422
    assert admin.get("/api/admin/enrollments", headers=headers, params={"page_size": 101}).status_code == 422
