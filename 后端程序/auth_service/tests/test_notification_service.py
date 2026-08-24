from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models import AdminUser, Base, Course, Enrollment, NotificationReceipt, User
from app.notification_domain import notification_kind_label
from app.notification_reminders import backfill_published_course_receipts
from app.notification_service import create_notification


@pytest.fixture
def session():
    engine = create_engine("sqlite://", future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        student = User(username="student", email="student@example.test", hashed_password="x")
        teacher = AdminUser(username="teacher", password_hash="x", display_name="Teacher")
        db.add_all([student, teacher])
        db.commit()
        yield db, student, teacher
    engine.dispose()


def _create(db, recipients, **extra):
    values = {
        "kind": "class_announcement",
        "title": "课程公告",
        "body": "请完成本周作业。",
        "target_type": "class",
        "target_id": 1,
        "source_type": "class",
        "source_id": 1,
        "link_url": "/student/tasks",
        "idempotency_key": "announcement:1:1",
        "recipients": recipients,
    }
    values.update(extra)
    return create_notification(db, **values)


def test_identical_idempotency_key_returns_existing_notification(session):
    db, student, _ = session
    first = _create(db, [{"user_id": student.id, "admin_user_id": None}])
    db.commit()
    repeated = _create(db, [{"user_id": student.id, "admin_user_id": None}])
    assert repeated.id == first.id


def test_idempotency_key_with_different_input_is_conflict(session):
    db, student, _ = session
    _create(db, [{"user_id": student.id, "admin_user_id": None}])
    db.commit()
    with pytest.raises(HTTPException) as exc:
        _create(db, [{"user_id": student.id, "admin_user_id": None}], title="不同正文")
    assert exc.value.status_code == 409


def test_receipt_deduplication_and_dual_subject_support(session):
    db, student, teacher = session
    notice = _create(db, [
        {"user_id": student.id, "admin_user_id": None},
        {"user_id": student.id, "admin_user_id": None},
        {"user_id": None, "admin_user_id": teacher.id},
    ])
    db.commit()
    assert db.query(NotificationReceipt).filter_by(notification_id=notice.id).count() == 2


def test_future_enrollment_receives_current_publish_notice_once(session):
    db, student, _ = session
    now = datetime.now(UTC)
    course = Course(title="未来开通课程", status="published", publish_generation=1)
    db.add(course)
    db.flush()
    notice = create_notification(
        db, kind="homework_published", title="课程已发布", body="课程已开放。",
        target_type="course", target_id=course.id, source_type="course", source_id=course.id,
        link_url=f"/courses/{course.id}", idempotency_key=f"course-published:{course.id}:1",
        recipients=[],
    )
    db.add(Enrollment(
        student_id=student.id, course_id=course.id, source="admin", status="active",
        opened_at=now + timedelta(hours=1),
    ))
    db.commit()

    assert backfill_published_course_receipts(db, now=now) == 0
    assert backfill_published_course_receipts(db, now=now + timedelta(hours=2)) == 1
    assert backfill_published_course_receipts(db, now=now + timedelta(hours=3)) == 0
    assert db.query(NotificationReceipt).filter_by(notification_id=notice.id, user_id=student.id).count() == 1


def test_notification_kind_labels_are_server_owned():
    assert notification_kind_label("homework_graded") == "作业已批改"
    assert notification_kind_label("unknown_historical_kind") == "unknown_historical_kind"
