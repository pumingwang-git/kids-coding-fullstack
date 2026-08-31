from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import AdminUser, Base, HelpChatLine, HelpMessage, HelpRequest, User


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
        line = HelpChatLine(class_id=1, student_id=student.id)
        db.add(line)
        db.flush()
        request = HelpRequest(
            class_id=1,
            student_id=student.id,
            assigned_admin_user_id=teacher.id,
            chat_line_id=line.id,
            body="Need help",
            context_type="general",
            context_key="general",
            request_key_hash="key",
            request_hash="input",
        )
        db.add(request)
        db.commit()
        yield db, student, teacher, request
    engine.dispose()


def test_help_message_requires_exactly_one_sender(session):
    db, student, teacher, request = session
    db.add(
        HelpMessage(
            help_request_id=request.id,
            sender_user_id=student.id,
            sender_admin_user_id=teacher.id,
            body="invalid",
        )
    )
    with pytest.raises(IntegrityError):
        db.flush()


def test_help_request_context_is_unique_inside_chat_line(session):
    db, student, teacher, existing = session
    db.add(
        HelpRequest(
            class_id=1,
            student_id=student.id,
            assigned_admin_user_id=teacher.id,
            chat_line_id=existing.chat_line_id,
            body="duplicate",
            context_type="general",
            context_key="general",
            request_key_hash="key-2",
            request_hash="input-2",
        )
    )
    with pytest.raises(IntegrityError):
        db.flush()


def test_only_one_active_chat_line_per_class_student_but_history_is_allowed(session):
    db, student, _, request = session
    db.add(HelpChatLine(class_id=1, student_id=student.id))
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()

    old_line = db.get(HelpChatLine, request.chat_line_id)
    old_line.ended_at = old_line.created_at
    db.flush()
    db.add(HelpChatLine(class_id=1, student_id=student.id))
    db.flush()


def test_concurrent_chat_line_inserts_cannot_create_two_active_lines(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'chat-lines.db'}",
        future=True,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    barrier = Barrier(2)

    def insert_line() -> str:
        with Session(engine) as db:
            db.add(HelpChatLine(class_id=1, student_id=1))
            barrier.wait()
            try:
                db.commit()
            except IntegrityError:
                db.rollback()
                return "conflict"
            return "created"

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = sorted(executor.map(lambda _: insert_line(), range(2)))
        with Session(engine) as db:
            assert db.scalar(select(func.count()).select_from(HelpChatLine)) == 1
        assert outcomes == ["conflict", "created"]
    finally:
        engine.dispose()


def test_student_message_idempotency_is_scoped_to_request_and_sender(session):
    db, student, _, request = session
    db.add(
        HelpMessage(
            help_request_id=request.id,
            sender_user_id=student.id,
            body="first",
            request_key_hash="student-key",
            request_hash="first-input",
        )
    )
    db.flush()
    db.add(
        HelpMessage(
            help_request_id=request.id,
            sender_user_id=student.id,
            body="duplicate",
            request_key_hash="student-key",
            request_hash="second-input",
        )
    )
    with pytest.raises(IntegrityError):
        db.flush()
