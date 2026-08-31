from fastapi.testclient import TestClient

from app.models import AdminUser, ClassGroup, ClassMember, ClassTeacher, Course, User
from app.security import password_hash
from test_exam import ADMIN_PASSWORD, build_app, scsrf, student_login


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
