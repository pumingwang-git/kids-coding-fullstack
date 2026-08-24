"""E6 notification unread-count and revoked-navigation contracts."""

from datetime import timedelta
from pathlib import Path

from sqlalchemy import select

from test_exam import admin_login, build_app, student_login

from app.models import AdminUser, User
from app.notification_service import create_notification
from app.security import utcnow


VUE_VIEW = (
    Path(__file__).resolve().parents[3]
    / "前端程序"
    / "study-blog-vue"
    / "src"
    / "views"
    / "NotificationsView.vue"
)


def _notice_for(db, *, key: str, user_id: int | None = None, admin_user_id: int | None = None):
    return create_notification(
        db,
        kind="homework_graded",
        title="作业已批改",
        body="请查看结果。",
        target_type="lesson_homework",
        target_id=1,
        source_type="lesson_homework",
        source_id=1,
        link_url="/learn/1/homework/1",
        idempotency_key=key,
        recipients=[{"user_id": user_id, "admin_user_id": admin_user_id}],
    )


def test_student_unread_count_excludes_revoked_notifications(tmp_path):
    app = build_app(tmp_path)
    learner = student_login(app)
    db = app.state.session_factory()
    try:
        student = db.scalar(select(User).where(User.username == "learner"))
        active = _notice_for(db, key="student-active", user_id=student.id)
        revoked = _notice_for(db, key="student-revoked", user_id=student.id)
        revoked.revoked_at = utcnow() - timedelta(seconds=1)
        db.commit()
        assert active.id != revoked.id
    finally:
        db.close()

    assert learner.get("/api/student/notifications/unread-count").json() == {"count": 1}


def test_admin_unread_count_excludes_revoked_notifications(tmp_path):
    app = build_app(tmp_path)
    admin, _headers = admin_login(app)
    db = app.state.session_factory()
    try:
        root = db.scalar(select(AdminUser).where(AdminUser.username == "root"))
        active = _notice_for(db, key="admin-active", admin_user_id=root.id)
        revoked = _notice_for(db, key="admin-revoked", admin_user_id=root.id)
        revoked.revoked_at = utcnow() - timedelta(seconds=1)
        db.commit()
        assert active.id != revoked.id
    finally:
        db.close()

    assert admin.get("/api/admin/notifications/unread-count").json() == {"count": 1}


def test_student_revoked_notification_stays_in_all_but_not_unread(tmp_path):
    app = build_app(tmp_path)
    learner = student_login(app)
    db = app.state.session_factory()
    try:
        student = db.scalar(select(User).where(User.username == "learner"))
        notice = _notice_for(db, key="student-history-revoked", user_id=student.id)
        notice.revoked_at = utcnow()
        db.commit()
    finally:
        db.close()
    item = learner.get("/api/student/notifications?tab=all").json()["items"][0]
    assert item["id"] == notice.id
    assert item["actions"] == []
    assert learner.get("/api/student/notifications?tab=unread").json()["total"] == 0
    assert learner.get("/api/student/notifications/unread-count").json() == {"count": 0}


def test_admin_revoked_notification_stays_in_all_but_not_unread(tmp_path):
    app = build_app(tmp_path)
    admin, _headers = admin_login(app)
    db = app.state.session_factory()
    try:
        root = db.scalar(select(AdminUser).where(AdminUser.username == "root"))
        notice = _notice_for(db, key="admin-history-revoked", admin_user_id=root.id)
        notice.revoked_at = utcnow()
        db.commit()
    finally:
        db.close()
    item = admin.get("/api/admin/notifications?box=inbox&tab=all").json()["items"][0]
    assert item["id"] == notice.id
    assert item["actions"] == []
    assert admin.get("/api/admin/notifications?box=inbox&tab=unread").json()["total"] == 0
    assert admin.get("/api/admin/notifications/unread-count").json() == {"count": 0}


def test_revoked_student_notification_never_marks_read_or_navigates():
    source = VUE_VIEW.read_text(encoding="utf-8")
    start = source.index("async function openNotice(item) {")
    end = source.index("\n}\n\nasync function markAll", start)
    handler = source[start:end]

    assert "if (item.revoked_at) return;" in handler
    assert handler.index("if (item.revoked_at) return;") < handler.index("markNotificationRead")
    assert handler.index("if (item.revoked_at) return;") < handler.index("router.push")
