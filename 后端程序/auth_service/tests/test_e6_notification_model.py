import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import AdminUser, Base, Notification, NotificationReceipt, User
from app.notification_domain import (
    validate_notification_kind,
    validate_recipient,
    validate_source_pair,
)


@pytest.fixture
def session():
    engine = create_engine("sqlite://", future=True)

    @event.listens_for(engine, "connect")
    def _fk(dbapi_connection, _record):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    with Session(engine) as db:
        yield db
    engine.dispose()


def _actors(db):
    student = User(username="student", email="student@example.test", hashed_password="x")
    admin = AdminUser(username="teacher", password_hash="x", display_name="Teacher")
    db.add_all([student, admin])
    db.flush()
    return student, admin


def _notification(db):
    row = Notification(
        kind="class_announcement",
        title="Notice",
        body="Body",
        target_type="class",
        target_id=1,
        idempotency_key="announcement:1",
    )
    db.add(row)
    db.flush()
    return row


def test_student_and_admin_receipts_are_supported(session):
    student, admin = _actors(session)
    notification = _notification(session)
    session.add_all(
        [
            NotificationReceipt(notification_id=notification.id, user_id=student.id),
            NotificationReceipt(notification_id=notification.id, admin_user_id=admin.id),
        ]
    )
    session.commit()
    assert session.query(NotificationReceipt).count() == 2


def test_receipt_requires_exactly_one_subject(session):
    student, admin = _actors(session)
    notification = _notification(session)
    for kwargs in (
        {"user_id": None, "admin_user_id": None},
        {"user_id": student.id, "admin_user_id": admin.id},
    ):
        session.add(NotificationReceipt(notification_id=notification.id, **kwargs))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()


def test_receipt_unique_per_notification_and_subject(session):
    student, _ = _actors(session)
    notification = _notification(session)
    session.add(NotificationReceipt(notification_id=notification.id, user_id=student.id))
    session.commit()
    session.add(NotificationReceipt(notification_id=notification.id, user_id=student.id))
    with pytest.raises(IntegrityError):
        session.commit()


def test_notification_source_pair_and_idempotency_are_constrained(session):
    _actors(session)
    session.add(
        Notification(
            kind="class_announcement",
            title="A",
            body="B",
            target_type="class",
            target_id=1,
            source_type="course",
            idempotency_key="one",
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()
    _notification(session)
    session.commit()
    session.add(
        Notification(
            kind="class_announcement",
            title="A2",
            body="B2",
            target_type="class",
            target_id=1,
            idempotency_key="announcement:1",
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()


def test_revocation_preserves_notification_and_receipt_history(session):
    student, _ = _actors(session)
    notification = _notification(session)
    receipt = NotificationReceipt(notification_id=notification.id, user_id=student.id)
    session.add(receipt)
    session.commit()

    notification.revoked_at = notification.created_at
    session.commit()

    assert session.get(Notification, notification.id).revoked_at is not None
    assert session.get(NotificationReceipt, receipt.id) is not None


def test_domain_validators_reject_invalid_values():
    with pytest.raises(ValueError):
        validate_recipient(user_id=1, admin_user_id=2)
    with pytest.raises(ValueError):
        validate_recipient(user_id=None, admin_user_id=None)
    with pytest.raises(ValueError):
        validate_source_pair("course", None)
    with pytest.raises(ValueError):
        validate_notification_kind("custom")
