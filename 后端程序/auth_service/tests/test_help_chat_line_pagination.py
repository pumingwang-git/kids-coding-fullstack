from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.models import AdminUser, ClassGroup, ClassMember, ClassTeacher, Course, HelpChatLine, HelpMessage, HelpRequest, User
from app.security import password_hash
from test_exam import ADMIN_PASSWORD, build_app, scsrf, student_login


def _seed_line_with_messages(app, count: int) -> tuple[object, int]:
    student = student_login(app, "learner")
    db = app.state.session_factory()
    try:
        learner = db.query(User).filter_by(username="learner").one()
        teacher = AdminUser(
            username="pagination-teacher",
            password_hash=password_hash.hash(ADMIN_PASSWORD),
            display_name="分页教师",
            role="teacher",
        )
        course = Course(title="分页答疑课", status="published")
        db.add_all([teacher, course])
        db.flush()
        group = ClassGroup(name="分页答疑班", course_id=course.id, status="active")
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

    created = student.post(
        "/api/student/help-requests",
        headers={**scsrf(student), "Idempotency-Key": "pagination-root"},
        json={"class_id": class_id, "body": "消息 0", "context_type": "general"},
    )
    assert created.status_code == 201, created.text

    db = app.state.session_factory()
    try:
        line = db.get(HelpChatLine, created.json()["chat_line_id"])
        request = db.get(HelpRequest, created.json()["help_request_id"])
        # 每十条共享一个时间戳，验证排序必须以唯一 id 收尾。
        start = datetime(2026, 8, 31, tzinfo=UTC)
        db.add_all([
            HelpMessage(
                help_request_id=request.id,
                sender_user_id=line.student_id,
                body=f"消息 {index}",
                created_at=start + timedelta(seconds=index // 10),
            )
            for index in range(1, count)
        ])
        db.commit()
    finally:
        db.close()
    return student, created.json()["chat_line_id"]


def test_student_chat_detail_cursor_paginates_2000_messages_without_gaps_or_duplicates(tmp_path):
    app = build_app(tmp_path)
    student, line_id = _seed_line_with_messages(app, 2000)

    first = student.get(f"/api/student/help-chat-lines/{line_id}?limit=100")
    assert first.status_code == 200, first.text
    page = first.json()
    assert len(page["items"]) == 100
    assert page["items"] == page["messages"]
    assert sum(len(request["messages"]) for request in page["requests"]) == 100
    assert page["has_more"] is True
    assert page["next_cursor"] == page["items"][0]["id"]

    received_ids = []
    while True:
        assert [(item["created_at"], item["id"]) for item in page["items"]] == sorted(
            (item["created_at"], item["id"]) for item in page["items"]
        )
        received_ids.extend(item["id"] for item in page["items"])
        if not page["has_more"]:
            break
        page = student.get(
            f"/api/student/help-chat-lines/{line_id}?limit=100&before_id={page['next_cursor']}"
        ).json()

    assert len(received_ids) == 2000
    assert len(set(received_ids)) == 2000
    assert sorted(received_ids) == list(range(min(received_ids), max(received_ids) + 1))
    assert page["next_cursor"] is None
    assert page["has_more"] is False

    default_page = student.get(f"/api/student/help-chat-lines/{line_id}")
    assert default_page.status_code == 200, default_page.text
    assert len(default_page.json()["items"]) == 20
    assert student.get(f"/api/student/help-chat-lines/{line_id}?limit=101").status_code == 422


def test_cursor_pagination_keeps_unique_id_tiebreaker_sentinel():
    source = Path("app/routers/help_requests.py").read_text(encoding="utf-8")
    assert "HelpMessage.created_at.desc(), HelpMessage.id.desc()" in source
    assert "(HelpMessage.id < cursor.id)" in source
