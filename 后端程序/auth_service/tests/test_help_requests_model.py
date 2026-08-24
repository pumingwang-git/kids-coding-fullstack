import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import AdminUser, Base, HelpMessage, HelpRequest, User


@pytest.fixture
def session():
    engine = create_engine("sqlite://", future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        student = User(username="student", email="student@example.test", hashed_password="x")
        teacher = AdminUser(username="teacher", password_hash="x", display_name="Teacher")
        db.add_all([student, teacher])
        db.flush()
        # Foreign-key IDs are irrelevant to these two CHECK contracts because
        # SQLite's test fixture intentionally mirrors the model-level boundary.
        request = HelpRequest(class_id=1, student_id=student.id, assigned_admin_user_id=teacher.id,
                              body="Need help", context_type="general", request_key_hash="key", request_hash="input")
        db.add(request)
        db.flush()
        yield db, student, teacher, request
    engine.dispose()


def test_help_message_requires_exactly_one_sender(session):
    db, student, teacher, request = session
    db.add(HelpMessage(help_request_id=request.id, sender_user_id=student.id,
                       sender_admin_user_id=teacher.id, body="invalid"))
    with pytest.raises(IntegrityError):
        db.flush()


def test_help_request_key_is_unique_per_student(session):
    db, student, teacher, _ = session
    db.add(HelpRequest(class_id=2, student_id=student.id, assigned_admin_user_id=teacher.id,
                       body="duplicate", context_type="general", request_key_hash="key", request_hash="input-2"))
    with pytest.raises(IntegrityError):
        db.flush()
