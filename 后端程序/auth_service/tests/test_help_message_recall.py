"""撤回的两条硬约束：只能撤自己发的、只有 2 分钟。

这两条实现是对的，但**曾经一条用例都没有**——把归属判断和时限分别删掉，
整套答疑测试仍然 23 条全绿。没红过的约束等于不存在，这个文件就是补这个洞。
"""

from datetime import UTC, datetime, timedelta

from test_exam import ADMIN_PASSWORD, build_app, scsrf, student_login
from test_help_chat_lines_api import _admin_login, _seed_help_class

from app.models import HelpMessage
from app.security import utcnow


def _instant(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _conversation(app):
    """造一条学生提问 + 教师回复的聊天线，返回两侧客户端与两条消息的 id。"""
    student = student_login(app, "learner")
    seeded = _seed_help_class(app)
    created = student.post(
        "/api/student/help-requests",
        headers={**scsrf(student), "Idempotency-Key": "recall-seed"},
        json={"class_id": seeded["class_id"], "body": "学生这句", "context_type": "general"},
    )
    assert created.status_code == 201, created.text
    request_id = created.json()["id"]

    teacher, headers = _admin_login(app, "line-assignee")
    replied = teacher.post(
        f"/api/admin/help-requests/{request_id}/messages",
        headers={**headers, "Idempotency-Key": "recall-reply"},
        json={"body": "教师这句"},
    )
    assert replied.status_code == 201, replied.text

    db = app.state.session_factory()
    try:
        rows = db.query(HelpMessage).order_by(HelpMessage.id).all()
        student_message = next(m for m in rows if m.sender_user_id is not None)
        teacher_message = next(m for m in rows if m.sender_admin_user_id is not None)
        ids = (student_message.id, teacher_message.id)
    finally:
        db.close()
    return student, teacher, headers, ids


def _backdate(app, message_id: int, minutes: int) -> None:
    db = app.state.session_factory()
    try:
        row = db.get(HelpMessage, message_id)
        row.created_at = utcnow() - timedelta(minutes=minutes)
        db.commit()
    finally:
        db.close()


def test_neither_side_can_recall_the_other_sides_message(tmp_path):
    """双主体各撤各的。学生撤教师的、教师撤学生的，都必须被拒。

    拒绝用 404 而不是 403：换一条 message_id 结论就变，这是范围闸（CLAUDE.md 判据）。
    """
    app = build_app(tmp_path)
    student, teacher, headers, (student_message, teacher_message) = _conversation(app)

    denied = student.post(
        f"/api/student/help-messages/{teacher_message}/recall", headers=scsrf(student)
    )
    assert denied.status_code == 404, denied.text

    denied_admin = teacher.post(
        f"/api/admin/help-messages/{student_message}/recall", headers=headers
    )
    assert denied_admin.status_code == 404, denied_admin.text

    # 哨兵：别拦过头——各自撤自己的必须成功。
    assert student.post(
        f"/api/student/help-messages/{student_message}/recall", headers=scsrf(student)
    ).status_code == 200
    assert teacher.post(
        f"/api/admin/help-messages/{teacher_message}/recall", headers=headers
    ).status_code == 200


def test_recall_window_closes_after_two_minutes(tmp_path):
    """超过 2 分钟不能再撤，时限由服务端时钟判定。"""
    app = build_app(tmp_path)
    student, teacher, headers, (student_message, teacher_message) = _conversation(app)

    _backdate(app, student_message, minutes=3)
    expired = student.post(
        f"/api/student/help-messages/{student_message}/recall", headers=scsrf(student)
    )
    assert expired.status_code == 409, expired.text

    _backdate(app, teacher_message, minutes=3)
    expired_admin = teacher.post(
        f"/api/admin/help-messages/{teacher_message}/recall", headers=headers
    )
    assert expired_admin.status_code == 409, expired_admin.text


def test_recall_is_idempotent_within_the_window(tmp_path):
    """重复撤回不报错，也不产生第二次撤回——网络重试不该变成错误提示。"""
    app = build_app(tmp_path)
    student, _teacher, _headers, (student_message, _t) = _conversation(app)
    first = student.post(
        f"/api/student/help-messages/{student_message}/recall", headers=scsrf(student)
    )
    assert first.status_code == 200, first.text
    second = student.post(
        f"/api/student/help-messages/{student_message}/recall", headers=scsrf(student)
    )
    assert second.status_code == 200, second.text
    # 比对「时刻」而不是字符串：SQLite 读回来的 datetime 不带时区，
    # 而刚写进会话的那个带（`utcnow()` 是 aware）。生产是 PostgreSQL +
    # `DateTime(timezone=True)`，两次都带时区。断言字符串相等等于在测数据库方言。
    assert _instant(second.json()["recalled_at"]) == _instant(first.json()["recalled_at"])
