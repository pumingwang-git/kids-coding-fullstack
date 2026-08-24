from fastapi.testclient import TestClient
from test_exam import ADMIN_PASSWORD, build_app, scsrf, student_login

from app.models import (
    AdminUser, ClassGroup, ClassMember, ClassTeacher, Course, CourseLesson,
    CourseSection, Enrollment, User,
)
from app.security import password_hash, utcnow


def _admin_login(app, username: str) -> tuple[TestClient, dict]:
    client = TestClient(app)
    client.get("/api/admin/csrf")
    headers = {"X-CSRF-Token": client.cookies.get("admin_csrf_token")}
    response = client.post("/api/admin/login", headers=headers,
                           json={"username": username, "password": ADMIN_PASSWORD})
    assert response.status_code == 200, response.text
    return client, {"X-CSRF-Token": client.cookies.get("admin_csrf_token")}


def test_help_request_is_visible_to_assignee_not_other_class_teacher(tmp_path):
    app = build_app(tmp_path)
    student = student_login(app, "learner")
    db = app.state.session_factory()
    try:
        peer = AdminUser(username="peer", password_hash=password_hash.hash(ADMIN_PASSWORD),
                         display_name="peer", role="teacher")
        course = Course(title="协作课")
        learner = db.query(User).filter_by(username="learner").one()
        db.add_all([peer, course])
        db.flush()
        group = ClassGroup(name="一班", course_id=course.id, status="active")
        db.add(group)
        db.flush()
        db.add_all([
            ClassMember(class_id=group.id, student_id=learner.id, status="active"),
            ClassTeacher(class_id=group.id, admin_user_id=1, role_in_class="teacher"),
            ClassTeacher(class_id=group.id, admin_user_id=peer.id, role_in_class="teacher"),
        ])
        db.commit()
        class_id = group.id
    finally:
        db.close()

    assert student.post("/api/student/help-requests", headers={**scsrf(student), "Idempotency-Key": "help-context"},
                        json={"class_id": class_id, "body": "上下文", "context_type": "course", "context_id": 1}).status_code == 422
    created = student.post("/api/student/help-requests", headers={**scsrf(student), "Idempotency-Key": "help-1"},
                           json={"class_id": class_id, "body": "需要帮助", "context_type": "general"})
    assert created.status_code == 201, created.text
    request_id = created.json()["id"]
    for index in range(2, 11):
        response = student.post(
            "/api/student/help-requests",
            headers={**scsrf(student), "Idempotency-Key": f"help-{index}"},
            json={"class_id": class_id, "body": f"需要帮助 {index}", "context_type": "general"},
        )
        assert response.status_code == 201, response.text
    assert student.post(
        "/api/student/help-requests",
        headers={**scsrf(student), "Idempotency-Key": "help-11"},
        json={"class_id": class_id, "body": "超过频控", "context_type": "general"},
    ).status_code == 429

    assignee, assignee_headers = _admin_login(app, "root")
    peer, peer_headers = _admin_login(app, "peer")
    assert assignee.get("/api/admin/notifications").json()["total"] == 10
    assert assignee.get(f"/api/admin/help-requests/{request_id}").status_code == 200
    assert peer.get(f"/api/admin/help-requests/{request_id}").status_code == 404

    payload = {"title": "课堂通知", "body": "明天带好作业本。", "link_url": "/courses/1"}
    missing_csrf = assignee.post(
        f"/api/admin/teaching/classes/{class_id}/announcements",
        headers={"Idempotency-Key": "announcement-no-csrf"}, json=payload,
    )
    assert missing_csrf.status_code == 403
    announcement = assignee.post(
        f"/api/admin/teaching/classes/{class_id}/announcements",
        headers={**assignee_headers, "Idempotency-Key": "announcement-1"}, json=payload,
    )
    assert announcement.status_code == 201, announcement.text
    assert assignee.post(
        f"/api/admin/teaching/classes/{class_id}/announcements",
        headers={**assignee_headers, "Idempotency-Key": "announcement-1"}, json=payload,
    ).json()["id"] == announcement.json()["id"]
    assert assignee.post(
        f"/api/admin/teaching/classes/{class_id}/announcements",
        headers={**assignee_headers, "Idempotency-Key": "announcement-unsafe"},
        json={**payload, "link_url": "https://invalid.example"},
    ).status_code == 422
    assert assignee.post(
        f"/api/admin/teaching/classes/{class_id}/announcements",
        headers={**assignee_headers, "Idempotency-Key": "announcement-js"},
        json={**payload, "link_url": "javascript:alert(1)"},
    ).status_code == 422
    assert assignee.post(f"/api/admin/notifications/{announcement.json()['id']}/revoke",
                         headers=assignee_headers).status_code == 200


def test_help_request_accepts_accessible_course_and_lesson_context(tmp_path):
    app = build_app(tmp_path)
    student = student_login(app, "learner")
    db = app.state.session_factory()
    try:
        learner = db.query(User).filter_by(username="learner").one()
        teacher = db.query(AdminUser).filter_by(username="root").one()
        course = Course(title="可访问上下文课", status="published")
        db.add(course)
        db.flush()
        section = CourseSection(course_id=course.id, title="第一章", sort_order=0)
        db.add(section)
        db.flush()
        lesson = CourseLesson(course_id=course.id, section_id=section.id,
                              title="第一课", open_policy="whole", is_trial=True)
        db.add(lesson)
        db.flush()
        group = ClassGroup(name="上下文班", course_id=course.id, status="active")
        db.add(group)
        db.flush()
        db.add_all([
            ClassMember(class_id=group.id, student_id=learner.id, status="active"),
            ClassTeacher(class_id=group.id, admin_user_id=teacher.id, role_in_class="teacher"),
            Enrollment(student_id=learner.id, course_id=course.id, class_id=group.id,
                       source="class", status="active"),
        ])
        db.commit()
        class_id, course_id, lesson_id = group.id, course.id, lesson.id
    finally:
        db.close()

    course_ticket = student.post(
        "/api/student/help-requests",
        headers={**scsrf(student), "Idempotency-Key": "context-course"},
        json={"class_id": class_id, "body": "课程上下文", "context_type": "course",
              "context_id": course_id},
    )
    assert course_ticket.status_code == 201, course_ticket.text
    lesson_ticket = student.post(
        "/api/student/help-requests",
        headers={**scsrf(student), "Idempotency-Key": "context-lesson"},
        json={"class_id": class_id, "body": "课时上下文", "context_type": "lesson",
              "context_id": lesson_id},
    )
    assert lesson_ticket.status_code == 201, lesson_ticket.text


def test_teacher_loses_sent_announcement_access_after_assignment_ends(tmp_path):
    app = build_app(tmp_path)
    student = student_login(app, "learner")
    db = app.state.session_factory()
    try:
        teacher = AdminUser(username="scoped-teacher", password_hash=password_hash.hash(ADMIN_PASSWORD),
                            display_name="Scoped teacher", role="teacher")
        course = Course(title="范围公告课")
        learner = db.query(User).filter_by(username="learner").one()
        db.add_all([teacher, course])
        db.flush()
        group = ClassGroup(name="范围班", course_id=course.id, status="active")
        db.add(group)
        db.flush()
        assignment = ClassTeacher(class_id=group.id, admin_user_id=teacher.id, role_in_class="teacher")
        db.add_all([ClassMember(class_id=group.id, student_id=learner.id, status="active"), assignment])
        db.commit()
        class_id = group.id
    finally:
        db.close()

    client, headers = _admin_login(app, "scoped-teacher")
    payload = {"title": "范围公告", "body": "仅当前带班教师可管理。"}
    response = client.post(
        f"/api/admin/teaching/classes/{class_id}/announcements",
        headers={**headers, "Idempotency-Key": "scoped-announcement-1"},
        json=payload,
    )
    assert response.status_code == 201, response.text
    notification_id = response.json()["id"]

    db = app.state.session_factory()
    try:
        assignment.ended_at = utcnow()
        db.merge(assignment)
        db.commit()
    finally:
        db.close()

    assert client.get("/api/admin/notifications?box=sent").json()["total"] == 0
    assert client.get(f"/api/admin/notifications/{notification_id}").status_code == 404
    assert client.post(
        f"/api/admin/notifications/{notification_id}/revoke", headers=headers
    ).status_code == 404
