from fastapi.testclient import TestClient

from app.models import AdminUser, ClassGroup, ClassMember, ClassTeacher, Course, User
from app.security import password_hash
from test_exam import ADMIN_PASSWORD, build_app, scsrf, student_login


def _admin_login(app, username: str) -> tuple[TestClient, dict]:
    client = TestClient(app)
    client.get("/api/admin/csrf")
    response = client.post(
        "/api/admin/login",
        headers={"X-CSRF-Token": client.cookies.get("admin_csrf_token")},
        json={"username": username, "password": ADMIN_PASSWORD},
    )
    assert response.status_code == 200, response.text
    return client, {"X-CSRF-Token": client.cookies.get("admin_csrf_token")}


def _assert_message_contract(message: dict) -> None:
    assert message["recalled"] is False
    assert message["recalled_at"] is None
    assert message["attachments"] == []


def test_student_chat_detail_returns_merged_messages_in_ascending_time_order(tmp_path):
    app = build_app(tmp_path)
    student = student_login(app, "learner")
    db = app.state.session_factory()
    try:
        learner = db.query(User).filter_by(username="learner").one()
        teacher = AdminUser(
            username="help-teacher",
            password_hash=password_hash.hash(ADMIN_PASSWORD),
            display_name="答疑教师",
            role="teacher",
        )
        course = Course(title="答疑契约课")
        db.add_all([teacher, course])
        db.flush()
        group = ClassGroup(name="答疑契约班", course_id=course.id, status="active")
        db.add(group)
        db.flush()
        db.add_all([
            ClassMember(class_id=group.id, student_id=learner.id, status="active"),
            ClassTeacher(class_id=group.id, admin_user_id=teacher.id, role_in_class="teacher"),
        ])
        db.commit()
        class_id = group.id
    finally:
        db.close()

    first = student.post(
        "/api/student/help-requests",
        headers={**scsrf(student), "Idempotency-Key": "contract-1"},
        json={"class_id": class_id, "body": "第一条", "context_type": "general"},
    )
    assert first.status_code == 201, first.text
    second = student.post(
        "/api/student/help-requests",
        headers={**scsrf(student), "Idempotency-Key": "contract-2"},
        json={"class_id": class_id, "body": "第二条", "context_type": "general"},
    )
    assert second.status_code == 201, second.text

    line_id = first.json()["chat_line_id"]
    detail = student.get(f"/api/student/help-chat-lines/{line_id}")
    assert detail.status_code == 200, detail.text
    payload = detail.json()
    assert [item["body"] for item in payload["messages"]] == ["第一条", "第二条"]
    assert [item["created_at"] for item in payload["messages"]] == sorted(
        item["created_at"] for item in payload["messages"]
    )
    assert payload["requests"]


def test_chat_message_contract_matches_student_teacher_rest_and_websocket(tmp_path):
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
    db = app.state.session_factory()
    try:
        learner = db.query(User).filter_by(username="learner").one()
        teacher = AdminUser(
            username="contract-teacher",
            password_hash=password_hash.hash(ADMIN_PASSWORD),
            display_name="契约教师",
            role="teacher",
        )
        course = Course(title="消息契约课", status="published")
        db.add_all([teacher, course])
        db.flush()
        group = ClassGroup(name="消息契约班", course_id=course.id, status="active")
        db.add(group)
        db.flush()
        db.add_all([
            ClassMember(class_id=group.id, student_id=learner.id, status="active"),
            ClassTeacher(class_id=group.id, admin_user_id=teacher.id, role_in_class="teacher"),
        ])
        db.commit()
        class_id = group.id
    finally:
        db.close()

    teacher, teacher_headers = _admin_login(app, "contract-teacher")
    previous_redis = help_realtime_hub._redis
    help_realtime_hub._redis = TicketRedis()
    try:
        student_ticket = student.post(
            "/api/student/help-chat-lines/events/ticket", headers=scsrf(student)
        )
        teacher_ticket = teacher.post(
            "/api/admin/help-chat-lines/events/ticket", headers=teacher_headers
        )
        with student.websocket_connect(
            "/api/student/help-chat-lines/events",
            subprotocols=["help-v1", f"help-ticket.{student_ticket.json()['ticket']}"],
        ) as student_events:
            with teacher.websocket_connect(
                "/api/admin/help-chat-lines/events",
                subprotocols=["help-v1", f"help-ticket.{teacher_ticket.json()['ticket']}"],
            ) as teacher_events:
                created = student.post(
                    "/api/student/help-requests",
                    headers={**scsrf(student), "Idempotency-Key": "message-contract"},
                    json={"class_id": class_id, "body": "冻结消息形状", "context_type": "general"},
                )
                assert created.status_code == 201, created.text
                expected_event = {
                    "type": "help_chat_line_changed",
                    "event": "student_message",
                    "chat_line_id": created.json()["chat_line_id"],
                    "payload": created.json(),
                }
                assert student_events.receive_json() == expected_event
                assert teacher_events.receive_json() == expected_event
    finally:
        help_realtime_hub._redis = previous_redis

    line_id = created.json()["chat_line_id"]
    student_detail = student.get(f"/api/student/help-chat-lines/{line_id}")
    teacher_detail = teacher.get(f"/api/admin/help-chat-lines/{line_id}")
    assert student_detail.status_code == 200, student_detail.text
    assert teacher_detail.status_code == 200, teacher_detail.text
    for detail in (student_detail.json(), teacher_detail.json()):
        assert detail["items"] == detail["messages"]
        assert detail["next_cursor"] is None
        assert detail["has_more"] is False
        assert len(detail["items"]) == 1
        _assert_message_contract(detail["items"][0])
    assert student_detail.json()["items"] == teacher_detail.json()["items"]
    _assert_message_contract(created.json()["messages"][0])
