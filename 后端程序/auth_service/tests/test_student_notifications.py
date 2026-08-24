"""Student notification API ownership and read-state contract tests."""

from test_exam import build_app, scsrf, student_login

from app.models import User
from app.notification_service import create_notification


def _notice_for(db, user_id: int, key: str):
    return create_notification(
        db, kind="homework_graded", title="作业已批改", body="请查看结果。",
        target_type="lesson_homework", target_id=1,
        source_type="lesson_homework", source_id=1,
        link_url="/learn/1/homework/1", idempotency_key=key,
        recipients=[{"user_id": user_id, "admin_user_id": None}],
    )


def test_student_notifications_are_private_and_read_state_is_idempotent(tmp_path):
    app = build_app(tmp_path)
    learner = student_login(app, "learner")
    student_login(app, "other")
    db = app.state.session_factory()
    try:
        users = {user.username: user.id for user in db.query(User).all()}
        mine = _notice_for(db, users["learner"], "student-notice:mine")
        other = _notice_for(db, users["other"], "student-notice:other")
        db.commit()
    finally:
        db.close()

    inbox = learner.get("/api/student/notifications?tab=unread")
    assert inbox.status_code == 200
    assert [item["id"] for item in inbox.json()["items"]] == [mine.id]
    assert inbox.json()["total"] == 1
    assert learner.get(f"/api/student/notifications/{other.id}").status_code == 404

    first = learner.post(f"/api/student/notifications/{mine.id}/read", headers=scsrf(learner))
    second = learner.post(f"/api/student/notifications/{mine.id}/read", headers=scsrf(learner))
    assert first.status_code == second.status_code == 200
    assert first.json()["read_at"] is not None
    assert second.json()["read_at"] is not None
    assert learner.get("/api/student/notifications?tab=unread").json()["total"] == 0
