from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from test_exam import ADMIN_PASSWORD, build_app, scsrf, student_login

from app.models import (
    AdminRole,
    AdminUser,
    ClassGroup,
    ClassMember,
    ClassTeacher,
    Course,
    CourseLesson,
    CourseLessonBlock,
    CourseSection,
    Enrollment,
    HelpChatLine,
    HelpMessage,
    HelpRequest,
    LessonBlockCompletion,
    LessonPaperBlock,
    LessonProblemAttempt,
    Paper,
    PaperAttempt,
    User,
)
from app.routers import help_requests as help_requests_router
from app.security import password_hash, utcnow


def _admin_login(app, username: str) -> tuple[TestClient, dict]:
    client = TestClient(app)
    client.get("/api/admin/csrf")
    headers = {"X-CSRF-Token": client.cookies.get("admin_csrf_token")}
    response = client.post(
        "/api/admin/login",
        headers=headers,
        json={"username": username, "password": ADMIN_PASSWORD},
    )
    assert response.status_code == 200, response.text
    return client, {"X-CSRF-Token": client.cookies.get("admin_csrf_token")}


def _seed_help_class(app):
    db = app.state.session_factory()
    try:
        learner = db.query(User).filter_by(username="learner").one()
        assignee = AdminUser(
            username="line-assignee",
            password_hash=password_hash.hash(ADMIN_PASSWORD),
            display_name="承办教师",
            role="teacher",
        )
        peer = AdminUser(
            username="line-peer",
            password_hash=password_hash.hash(ADMIN_PASSWORD),
            display_name="同班助教",
            role="assistant",
        )
        outsider = AdminUser(
            username="line-outsider",
            password_hash=password_hash.hash(ADMIN_PASSWORD),
            display_name="外班教师",
            role="teacher",
        )
        no_cap_role = AdminRole(key="line_no_cap", label="无答疑权限", scope="class")
        no_cap = AdminUser(
            username="line-no-cap",
            password_hash=password_hash.hash(ADMIN_PASSWORD),
            display_name="无权限同班人员",
            role=no_cap_role.key,
        )
        disabled = AdminUser(
            username="line-disabled",
            password_hash=password_hash.hash(ADMIN_PASSWORD),
            display_name="已停用教师",
            role="teacher",
            status="disabled",
        )
        course = Course(title="答疑课", status="published")
        other_course = Course(title="外班课", status="published")
        db.add_all(
            [
                no_cap_role,
                assignee,
                peer,
                outsider,
                no_cap,
                disabled,
                course,
                other_course,
            ]
        )
        db.flush()
        group = ClassGroup(name="答疑班", course_id=course.id, status="active")
        other_group = ClassGroup(name="外班", course_id=other_course.id, status="active")
        db.add_all([group, other_group])
        db.flush()
        membership = ClassMember(class_id=group.id, student_id=learner.id, status="active")
        db.add_all(
            [
                membership,
                ClassTeacher(class_id=group.id, admin_user_id=assignee.id, role_in_class="teacher"),
                ClassTeacher(class_id=group.id, admin_user_id=peer.id, role_in_class="assistant"),
                ClassTeacher(class_id=group.id, admin_user_id=no_cap.id, role_in_class="assistant"),
                ClassTeacher(class_id=group.id, admin_user_id=disabled.id, role_in_class="teacher"),
                ClassTeacher(
                    class_id=other_group.id, admin_user_id=outsider.id, role_in_class="teacher"
                ),
            ]
        )
        db.commit()
        return {
            "class_id": group.id,
            "course_id": course.id,
            "membership_id": membership.id,
            "assignee_id": assignee.id,
            "peer_id": peer.id,
            "outsider_id": outsider.id,
            "no_cap_id": no_cap.id,
            "disabled_id": disabled.id,
        }
    finally:
        db.close()


def test_student_reuses_context_group_and_can_read_history_after_leaving(tmp_path):
    app = build_app(tmp_path)
    student = student_login(app, "learner")
    seeded = _seed_help_class(app)

    payload = {"class_id": seeded["class_id"], "body": "第一次提问", "context_type": "general"}
    first = student.post(
        "/api/student/help-requests",
        headers={**scsrf(student), "Idempotency-Key": "line-first"},
        json=payload,
    )
    assert first.status_code == 201, first.text
    second = student.post(
        "/api/student/help-requests",
        headers={**scsrf(student), "Idempotency-Key": "line-second"},
        json={**payload, "body": "同一上下文继续问"},
    )
    assert second.status_code == 201, second.text
    assert second.json()["help_request_id"] == first.json()["help_request_id"]
    assert second.json()["chat_line_id"] == first.json()["chat_line_id"]

    lines = student.get("/api/student/help-chat-lines?page=1&page_size=1")
    assert lines.status_code == 200
    assert lines.json()["total"] == 1
    assert len(lines.json()["available_classes"]) == 1
    assert lines.json()["available_classes"][0]["class_id"] == seeded["class_id"]
    assert lines.json()["available_classes"][0]["class_name"] == "答疑班"
    assert lines.json()["available_classes"][0]["course_title"] == "答疑课"
    assert lines.json()["items"][0]["id"] == first.json()["chat_line_id"]
    detail = student.get(f"/api/student/help-chat-lines/{first.json()['chat_line_id']}")
    assert [item["body"] for item in detail.json()["requests"][0]["messages"]] == [
        "第一次提问",
        "同一上下文继续问",
    ]
    profile = detail.json()["student_profile"]
    assert profile["course_progress"] == {"completed_lessons": 0, "total_lessons": 0, "percent": 0}
    assert profile["learning_activity"]["last_activity_at"] is None
    assert profile["weekly_practice_completed"] == 0
    assert profile["pending_homework_count"] == 0

    db = app.state.session_factory()
    try:
        membership = db.get(ClassMember, seeded["membership_id"])
        membership.status = "left"
        membership.left_at = utcnow()
        db.commit()
    finally:
        db.close()

    assert (
        student.get(f"/api/student/help-chat-lines/{first.json()['chat_line_id']}").status_code
        == 200
    )
    denied = student.post(
        "/api/student/help-requests",
        headers={**scsrf(student), "Idempotency-Key": "line-after-left"},
        json=payload,
    )
    assert denied.status_code == 404


def test_admin_chat_line_detail_includes_class_scoped_student_profile(tmp_path, monkeypatch):
    app = build_app(tmp_path)
    student = student_login(app, "learner")
    seeded = _seed_help_class(app)
    frozen = datetime(2026, 8, 31, 4, tzinfo=UTC)  # 周一中午，上海自然周已开始。
    monkeypatch.setattr("app.routers.help_requests.utcnow", lambda: frozen)

    created = student.post(
        "/api/student/help-requests",
        headers={**scsrf(student), "Idempotency-Key": "profile-contract-root"},
        json={"class_id": seeded["class_id"], "body": "档案测试提问", "context_type": "general"},
    )
    assert created.status_code == 201, created.text

    db = app.state.session_factory()
    try:
        learner = db.query(User).filter_by(username="learner").one()
        line = db.get(HelpChatLine, created.json()["chat_line_id"])
        section = CourseSection(course_id=seeded["course_id"], title="档案章节")
        db.add(section)
        db.flush()
        lessons = [
            CourseLesson(course_id=seeded["course_id"], section_id=section.id, title=f"课时 {index}", sort_order=index)
            for index in range(4)
        ]
        db.add_all(lessons)
        db.flush()
        completed_block = CourseLessonBlock(lesson_id=lessons[0].id, block_type="markdown", title="已完成", sort_order=0)
        practice_block = CourseLessonBlock(lesson_id=lessons[1].id, block_type="practice", title="本周练习", sort_order=0)
        wrong_practice = CourseLessonBlock(lesson_id=lessons[2].id, block_type="practice", title="未完成练习", sort_order=0)
        homework_block = CourseLessonBlock(lesson_id=lessons[3].id, block_type="homework", title="待交作业", sort_order=0)
        db.add_all([completed_block, practice_block, wrong_practice, homework_block])
        paper = Paper(title="档案待交作业", status="published")
        db.add(paper)
        db.flush()
        db.add_all([
            Enrollment(student_id=learner.id, course_id=seeded["course_id"], source="class", class_id=seeded["class_id"], opened_at=frozen - timedelta(days=1)),
            LessonBlockCompletion(user_id=learner.id, block_id=completed_block.id, lesson_id=lessons[0].id, completed_at=frozen - timedelta(days=1)),
            LessonBlockCompletion(user_id=learner.id, block_id=practice_block.id, lesson_id=lessons[1].id, completed_at=frozen),
            LessonProblemAttempt(user_id=learner.id, block_id=wrong_practice.id, lesson_id=lessons[2].id, tries=3, last_correct=False, updated_at=frozen),
            LessonPaperBlock(block_id=homework_block.id, paper_id=paper.id, mode="homework", due_at=frozen + timedelta(days=1)),
        ])
        db.flush()
        for index in range(11):
            at = frozen + timedelta(minutes=index + 1)
            request = HelpRequest(
                class_id=seeded["class_id"], student_id=learner.id, chat_line_id=line.id,
                assigned_admin_user_id=seeded["assignee_id"], body=f"上下文 {index}",
                context_type="general", context_key=f"profile-context-{index}",
                request_key_hash=f"profile-key-{index}", request_hash=f"profile-request-{index}",
                status="answered", answered_at=at, created_at=at, last_message_at=at,
            )
            db.add(request)
            db.flush()
            db.add(HelpMessage(help_request_id=request.id, sender_user_id=learner.id, body=f"上下文消息 {index}", created_at=at))
        db.commit()
    finally:
        db.close()

    teacher, _ = _admin_login(app, "line-assignee")
    detail = teacher.get(f"/api/admin/help-chat-lines/{created.json()['chat_line_id']}")
    assert detail.status_code == 200, detail.text
    payload = detail.json()
    profile = payload["student_profile"]
    assert profile["course_progress"] == {"completed_lessons": 2, "total_lessons": 4, "percent": 50}
    assert profile["learning_activity"]["last_activity_at"] is not None
    assert profile["weekly_practice_completed"] == 1
    assert profile["pending_homework_count"] == 1
    assert profile["help_request_count"] == 12
    assert len(profile["context_history"]) == 10
    assert profile["context_history"][0]["context_label"] == "通用问题"
    assert profile["context_history"][0]["first_message_id"] is not None
    assert all("body" not in item for item in profile["context_history"])
    assert all(item["help_request_id"] for item in payload["messages"])


def test_super_admin_can_open_help_queue_and_see_student_message(tmp_path):
    app = build_app(tmp_path)
    student = student_login(app, "learner")
    seeded = _seed_help_class(app)
    created = student.post(
        "/api/student/help-requests",
        headers={**scsrf(student), "Idempotency-Key": "super-help-queue"},
        json={"class_id": seeded["class_id"], "body": "管理员也应能看到", "context_type": "general"},
    )
    assert created.status_code == 201, created.text

    root, _ = _admin_login(app, "root")
    queue = root.get("/api/admin/help-chat-lines?filter=all")
    assert queue.status_code == 200, queue.text
    assert created.json()["chat_line_id"] in {item["id"] for item in queue.json()["items"]}


def test_teacher_can_reply_twice_but_not_after_close(tmp_path):
    app = build_app(tmp_path)
    student = student_login(app, "learner")
    seeded = _seed_help_class(app)
    created = student.post(
        "/api/student/help-requests",
        headers={**scsrf(student), "Idempotency-Key": "reply-twice"},
        json={"class_id": seeded["class_id"], "body": "请解答", "context_type": "general"},
    )
    assert created.status_code == 201
    teacher, headers = _admin_login(app, "line-assignee")
    request_id = created.json()["id"]
    for index, (key, body) in enumerate((("reply-1", "第一句"), ("reply-2", "第二句"))):
        response = teacher.post(
            f"/api/admin/help-requests/{request_id}/messages",
            headers={**headers, "Idempotency-Key": key},
            json={"body": body},
        )
        assert response.status_code == 201, response.text
        if index == 0:
            line_detail = teacher.get(
                f"/api/admin/help-chat-lines/{created.json()['chat_line_id']}"
            )
            assert line_detail.status_code == 200, line_detail.text
            assert line_detail.json()["can_reply"] is True
    detail = student.get(f"/api/student/help-requests/{request_id}")
    assert [item["body"] for item in detail.json()["messages"]][-2:] == ["第一句", "第二句"]
    assert teacher.post(
        f"/api/admin/help-requests/{request_id}/close", headers=headers
    ).status_code == 200
    blocked = teacher.post(
        f"/api/admin/help-requests/{request_id}/messages",
        headers={**headers, "Idempotency-Key": "reply-closed"},
        json={"body": "不应发送"},
    )
    assert blocked.status_code == 409


def test_help_chat_events_notify_the_student_and_visible_teacher(tmp_path):
    from app.help_realtime import help_realtime_hub

    class TicketRedis:
        def __init__(self):
            self.values = {}

        def setex(self, key, seconds, value):
            self.values[key] = value

        def getdel(self, key):
            return self.values.pop(key, None)

        def publish(self, channel, payload):
            return 1

    app = build_app(tmp_path)
    student = student_login(app, "learner")
    seeded = _seed_help_class(app)
    teacher, teacher_headers = _admin_login(app, "line-assignee")
    previous_redis = help_realtime_hub._redis
    help_realtime_hub._redis = TicketRedis()
    try:
        student_ticket = student.post(
            "/api/student/help-chat-lines/events/ticket", headers=scsrf(student)
        )
        teacher_ticket = teacher.post(
            "/api/admin/help-chat-lines/events/ticket", headers=teacher_headers
        )
        assert student_ticket.status_code == 200, student_ticket.text
        assert teacher_ticket.status_code == 200, teacher_ticket.text
        student_protocols = ["help-v1", f"help-ticket.{student_ticket.json()['ticket']}"]
        teacher_protocols = ["help-v1", f"help-ticket.{teacher_ticket.json()['ticket']}"]
        with student.websocket_connect(
            "/api/student/help-chat-lines/events", subprotocols=student_protocols
        ) as student_events:
            with teacher.websocket_connect(
                "/api/admin/help-chat-lines/events", subprotocols=teacher_protocols
            ) as teacher_events:
                created = student.post(
                    "/api/student/help-requests",
                    headers={**scsrf(student), "Idempotency-Key": "realtime-event"},
                    json={
                        "class_id": seeded["class_id"],
                        "body": "应实时通知",
                        "context_type": "general",
                    },
                )
                assert created.status_code == 201, created.text
                expected = {
                    "type": "help_chat_line_changed",
                    "event": "student_message",
                    "chat_line_id": created.json()["chat_line_id"],
                    "payload": created.json(),
                }
                assert student_events.receive_json() == expected
                assert teacher_events.receive_json() == expected
    finally:
        help_realtime_hub._redis = previous_redis


def test_student_opening_teacher_reply_records_read_receipt(tmp_path):
    app = build_app(tmp_path)
    student = student_login(app, "learner")
    seeded = _seed_help_class(app)
    created = student.post(
        "/api/student/help-requests",
        headers={**scsrf(student), "Idempotency-Key": "typing-and-read"},
        json={"class_id": seeded["class_id"], "body": "请帮忙", "context_type": "general"},
    )
    teacher, headers = _admin_login(app, "line-assignee")
    reply = teacher.post(
        f"/api/admin/help-requests/{created.json()['id']}/messages",
        headers={**headers, "Idempotency-Key": "typing-reply"},
        json={"body": "已经回复"},
    )
    assert reply.status_code == 201, reply.text

    student_detail = student.get(f"/api/student/help-chat-lines/{created.json()['chat_line_id']}")
    assert student_detail.status_code == 200, student_detail.text
    teacher_detail = teacher.get(f"/api/admin/help-chat-lines/{created.json()['chat_line_id']}")
    assert teacher_detail.status_code == 200, teacher_detail.text
    reply_row = next(item for item in teacher_detail.json()["messages"] if item["id"] == reply.json()["id"])
    assert reply_row["read_by_student"] is True


def test_exam_in_progress_does_not_block_homepage_help(tmp_path):
    app = build_app(tmp_path)
    student = student_login(app, "learner")
    seeded = _seed_help_class(app)
    db = app.state.session_factory()
    try:
        paper = Paper(title="闸门试卷", status="published", paper_type="exam", total_score=10)
        db.add(paper)
        db.flush()
        attempt = PaperAttempt(
            source_type="exam_link", source_id=999, exam_link_id=None, paper_id=paper.id,
            user_id=db.query(User).filter_by(username="learner").one().id,
            status="ongoing", deadline_at=utcnow() + timedelta(minutes=10),
        )
        db.add(attempt)
        db.commit()
    finally:
        db.close()
    allowed_during_exam = student.post(
        "/api/student/help-requests",
        headers={**scsrf(student), "Idempotency-Key": "exam-block"},
        json={"class_id": seeded["class_id"], "body": "考试中", "context_type": "general"},
    )
    assert allowed_during_exam.status_code == 201, allowed_during_exam.text
    db = app.state.session_factory()
    try:
        db.get(PaperAttempt, attempt.id).status = "submitted"
        homework_attempt = PaperAttempt(
            source_type="lesson_homework", source_id=998, exam_link_id=None, paper_id=paper.id,
            user_id=db.query(User).filter_by(username="learner").one().id,
            status="ongoing", deadline_at=utcnow() + timedelta(minutes=10),
        )
        db.add(homework_attempt)
        db.commit()
    finally:
        db.close()
    allowed = student.post(
        "/api/student/help-requests",
        headers={**scsrf(student), "Idempotency-Key": "exam-after"},
        json={"class_id": seeded["class_id"], "body": "交卷后", "context_type": "general"},
    )
    assert allowed.status_code == 201, allowed.text


def test_student_payload_rejects_assignee_and_rejoining_starts_a_new_line(tmp_path):
    app = build_app(tmp_path)
    student = student_login(app, "learner")
    seeded = _seed_help_class(app)
    payload = {"class_id": seeded["class_id"], "body": "求助", "context_type": "general"}
    forbidden = student.post(
        "/api/student/help-requests",
        headers={**scsrf(student), "Idempotency-Key": "forged-assignee"},
        json={**payload, "assigned_admin_user_id": seeded["peer_id"]},
    )
    assert forbidden.status_code == 422

    first = student.post(
        "/api/student/help-requests",
        headers={**scsrf(student), "Idempotency-Key": "before-rejoin"},
        json=payload,
    ).json()
    db = app.state.session_factory()
    try:
        membership = db.get(ClassMember, seeded["membership_id"])
        membership.status = "left"
        membership.left_at = utcnow()
        db.flush()
        db.add(
            ClassMember(
                class_id=seeded["class_id"], student_id=membership.student_id, status="active"
            )
        )
        db.commit()
    finally:
        db.close()
    second = student.post(
        "/api/student/help-requests",
        headers={**scsrf(student), "Idempotency-Key": "after-rejoin"},
        json=payload,
    )
    assert second.status_code == 201, second.text
    assert second.json()["chat_line_id"] != first["chat_line_id"]
    third = student.post(
        "/api/student/help-requests",
        headers={**scsrf(student), "Idempotency-Key": "after-rejoin-course"},
        json={
            **payload,
            "body": "重入后的课程问题",
            "context_type": "course",
            "context_id": seeded["course_id"],
        },
    )
    assert third.status_code == 201, third.text
    assert third.json()["chat_line_id"] == second.json()["chat_line_id"]

    db = app.state.session_factory()
    try:
        lines = db.query(HelpChatLine).order_by(HelpChatLine.id).all()
        assert len(lines) == 2
        assert lines[0].ended_at is not None
        assert lines[1].ended_at is None
    finally:
        db.close()


def test_admin_queue_only_builds_payloads_for_the_requested_page(tmp_path, monkeypatch):
    app = build_app(tmp_path)
    student = student_login(app, "learner")
    seeded = _seed_help_class(app)
    created = student.post(
        "/api/student/help-requests",
        headers={**scsrf(student), "Idempotency-Key": "queue-page-root"},
        json={"class_id": seeded["class_id"], "body": "当前待答疑", "context_type": "general"},
    )
    assert created.status_code == 201, created.text

    db = app.state.session_factory()
    try:
        learner = db.query(User).filter_by(username="learner").one()
        start = utcnow() - timedelta(days=1)
        for index in range(25):
            at = start + timedelta(minutes=index)
            line = HelpChatLine(
                class_id=seeded["class_id"], student_id=learner.id,
                created_at=at, last_message_at=at, ended_at=at,
            )
            db.add(line)
            db.flush()
            db.add(HelpRequest(
                class_id=seeded["class_id"], student_id=learner.id, chat_line_id=line.id,
                body=f"历史答疑 {index}", context_type="general", context_key=f"queue-page-{index}",
                request_key_hash=f"queue-page-key-{index}", request_hash=f"queue-page-request-{index}",
                status="answered", answered_at=at, created_at=at, last_message_at=at,
            ))
        db.commit()
    finally:
        db.close()

    calls = 0
    original = help_requests_router._line_payload

    def counted_payload(*args, **kwargs):
        nonlocal calls
        calls += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(help_requests_router, "_line_payload", counted_payload)
    root, _ = _admin_login(app, "root")
    response = root.get("/api/admin/help-chat-lines?filter=all&page=1&page_size=20")
    assert response.status_code == 200, response.text
    assert response.json()["total"] == 26
    assert len(response.json()["items"]) == 20
    assert calls == 20


def test_admin_queue_derives_waiting_state_and_assignment_is_revision_guarded(tmp_path, caplog):
    app = build_app(tmp_path)
    student = student_login(app, "learner")
    seeded = _seed_help_class(app)
    created = student.post(
        "/api/student/help-requests",
        headers={**scsrf(student), "Idempotency-Key": "queue-item"},
        json={"class_id": seeded["class_id"], "body": "等回复", "context_type": "general"},
    )
    assert created.status_code == 201, created.text

    db = app.state.session_factory()
    try:
        old = utcnow() - timedelta(minutes=11)
        row = db.get(HelpRequest, created.json()["help_request_id"])
        line = db.get(HelpChatLine, created.json()["chat_line_id"])
        row.last_message_at = line.last_message_at = old
        db.commit()
    finally:
        db.close()

    assignee, headers = _admin_login(app, "line-assignee")
    queue = assignee.get("/api/admin/help-chat-lines?page=1&page_size=20")
    assert queue.status_code == 200, queue.text
    item = queue.json()["items"][0]
    assert item["waiting_seconds"] >= 660
    assert item["waiting_level"] == "red"
    assert item["waiting_label"] == "等待超过 10 分钟"
    assert item["student_name"] == "learner"
    assert item["class_name"] == "答疑班"
    assert item["last_student_message_body"] == "等回复"
    assert item["context_label"] == "通用问题"
    detail = assignee.get(f"/api/admin/help-chat-lines/{created.json()['chat_line_id']}")
    assert detail.status_code == 200, detail.text
    assert detail.json()["active_help_request"]["messages"][0]["body"] == "等回复"
    assert {candidate["id"] for candidate in detail.json()["assignment_candidates"]} == {
        seeded["assignee_id"],
        seeded["peer_id"],
    }

    request_id = created.json()["help_request_id"]
    stale = assignee.patch(
        f"/api/admin/help-requests/{request_id}/assignment",
        headers={**headers, "If-Match": "9"},
        json={"target_admin_user_id": seeded["peer_id"]},
    )
    assert stale.status_code == 409, stale.text
    missing = assignee.patch(
        f"/api/admin/help-requests/{request_id}/assignment",
        headers={**headers, "If-Match": "0"},
        json={"target_admin_user_id": 999999},
    )
    outsider = assignee.patch(
        f"/api/admin/help-requests/{request_id}/assignment",
        headers={**headers, "If-Match": "0"},
        json={"target_admin_user_id": seeded["outsider_id"]},
    )
    assert missing.status_code == outsider.status_code == 404
    assert missing.json() == outsider.json()
    assert "scope_denied" in caplog.text
    for ineligible_id in (seeded["no_cap_id"], seeded["disabled_id"]):
        rejected = assignee.patch(
            f"/api/admin/help-requests/{request_id}/assignment",
            headers={**headers, "If-Match": "0"},
            json={"target_admin_user_id": ineligible_id},
        )
        assert rejected.status_code == 404
        assert rejected.json() == missing.json()

    transferred = assignee.patch(
        f"/api/admin/help-requests/{request_id}/assignment",
        headers={**headers, "If-Match": "0"},
        json={"target_admin_user_id": seeded["peer_id"]},
    )
    assert transferred.status_code == 200, transferred.text
    assert transferred.json()["assigned_admin_user_id"] == seeded["peer_id"]
    assert transferred.json()["assignment_revision"] == 1

    peer, peer_headers = _admin_login(app, "line-peer")
    old_assignee_detail = assignee.get(
        f"/api/admin/help-chat-lines/{created.json()['chat_line_id']}"
    )
    assert old_assignee_detail.status_code == 200
    assert old_assignee_detail.json()["can_reply"] is False
    assert old_assignee_detail.json()["can_reassign"] is False
    new_assignee_detail = peer.get(f"/api/admin/help-chat-lines/{created.json()['chat_line_id']}")
    assert new_assignee_detail.status_code == 200
    assert new_assignee_detail.json()["can_reply"] is True
    assert new_assignee_detail.json()["can_reassign"] is True
    old_reply = assignee.post(
        f"/api/admin/help-requests/{request_id}/messages",
        headers={**headers, "Idempotency-Key": "old-assignee-reply"},
        json={"body": "不应允许旧承办人回复"},
    )
    assert old_reply.status_code == 404
    assert old_reply.json() == {"detail": "联系记录不存在。"}

    replied = peer.post(
        f"/api/admin/help-requests/{request_id}/messages",
        headers={**peer_headers, "Idempotency-Key": "peer-reply-1"},
        json={"body": "我来回答"},
    )
    assert replied.status_code == 201, replied.text
    repeated = peer.post(
        f"/api/admin/help-requests/{request_id}/messages",
        headers={**peer_headers, "Idempotency-Key": "peer-reply-1"},
        json={"body": "我来回答"},
    )
    assert repeated.status_code == 201
    assert repeated.json()["id"] == replied.json()["id"]
    student_detail = student.get(f"/api/student/help-requests/{request_id}").json()
    assert student_detail["status"] == "answered"
    assert [message["body"] for message in student_detail["messages"]] == ["等回复", "我来回答"]


def test_teacher_events_survive_an_unknown_chat_line_in_a_typing_frame(tmp_path):
    """一帧坏数据不能掐断整条连接。

    教师侧曾经在 `while True` 里直接调 `_admin_line_or_404`，它抛的 404 被循环外的
    `except HTTPException` 接住，结果是**一个过期或越界的 chat_line_id 就能让教师掉线**。
    学生侧同一位置用的是「查不到则跳过」，两侧必须一致。
    """
    from app.help_realtime import help_realtime_hub

    class TicketRedis:
        def __init__(self):
            self.values = {}

        def setex(self, key, seconds, value):
            self.values[key] = value

        def getdel(self, key):
            return self.values.pop(key, None)

        def publish(self, channel, payload):
            return 1

    app = build_app(tmp_path)
    student = student_login(app, "learner")
    seeded = _seed_help_class(app)
    teacher, teacher_headers = _admin_login(app, "line-assignee")
    previous_redis = help_realtime_hub._redis
    help_realtime_hub._redis = TicketRedis()
    try:
        teacher_ticket = teacher.post(
            "/api/admin/help-chat-lines/events/ticket", headers=teacher_headers
        )
        assert teacher_ticket.status_code == 200, teacher_ticket.text
        protocols = ["help-v1", f"help-ticket.{teacher_ticket.json()['ticket']}"]
        with teacher.websocket_connect(
            "/api/admin/help-chat-lines/events", subprotocols=protocols
        ) as teacher_events:
            # 不存在的聊天线：这一帧应当被静默跳过，连接必须活着。
            teacher_events.send_json(
                {"type": "typing", "chat_line_id": 987654321, "is_typing": True}
            )
            created = student.post(
                "/api/student/help-requests",
                headers={**scsrf(student), "Idempotency-Key": "survive-bad-line"},
                json={
                    "class_id": seeded["class_id"],
                    "body": "坏帧之后仍应收到事件",
                    "context_type": "general",
                },
            )
            assert created.status_code == 201, created.text
            # 收得到 = 连接没被那一帧掐断（这是本用例的判据）。
            received = teacher_events.receive_json()
            assert received["event"] == "student_message"
            assert received["chat_line_id"] == created.json()["chat_line_id"]
    finally:
        help_realtime_hub._redis = previous_redis
