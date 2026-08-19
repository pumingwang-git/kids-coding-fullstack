"""Regression coverage for the shared four-ledger learning-activity aggregate."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import event, select
from test_exam import build_app, student_login
from test_lesson_block_unlock import build_lesson_with_blocks

from app.learning_activity import last_activity_at
from app.models import (
    LessonBlockCompletion,
    LessonCodeRun,
    LessonProblemAttempt,
    LessonVideoWatch,
    User,
)
from app.security import as_utc

ACTIVITY_AT = datetime(2026, 8, 19, 8, 30, tzinfo=UTC)


def _student_and_lesson(app):
    built = build_lesson_with_blocks(app, [{"title": "activity"}])
    student_login(app)
    db = app.state.session_factory()
    try:
        user = db.scalar(select(User).where(User.username == "learner"))
        return user.id, built, db
    except Exception:
        db.close()
        raise


def _assert_only_ledger_activity(tmp_path: Path, activity):
    app = build_app(tmp_path)
    user_id, built, db = _student_and_lesson(app)
    try:
        db.add(activity(user_id, built))
        db.commit()
        actual = last_activity_at(db, {user_id})
        assert as_utc(actual[user_id]) == ACTIVITY_AT
    finally:
        db.close()


def test_video_watch_is_learning_activity(tmp_path: Path):
    _assert_only_ledger_activity(
        tmp_path,
        lambda user_id, built: LessonVideoWatch(
            user_id=user_id,
            lesson_id=built["lesson_id"],
            block_id=built["block_ids"][0],
            updated_at=ACTIVITY_AT,
            last_beat_at=ACTIVITY_AT,
        ),
    )


def test_block_completion_is_learning_activity(tmp_path: Path):
    _assert_only_ledger_activity(
        tmp_path,
        lambda user_id, built: LessonBlockCompletion(
            user_id=user_id,
            lesson_id=built["lesson_id"],
            block_id=built["block_ids"][0],
            completed_at=ACTIVITY_AT,
        ),
    )


def test_problem_attempt_is_learning_activity(tmp_path: Path):
    _assert_only_ledger_activity(
        tmp_path,
        lambda user_id, built: LessonProblemAttempt(
            user_id=user_id,
            lesson_id=built["lesson_id"],
            block_id=built["block_ids"][0],
            updated_at=ACTIVITY_AT,
        ),
    )


def test_code_run_is_learning_activity(tmp_path: Path):
    _assert_only_ledger_activity(
        tmp_path,
        lambda user_id, built: LessonCodeRun(
            user_id=user_id,
            lesson_id=built["lesson_id"],
            block_id=built["block_ids"][0],
            language="python",
            created_at=ACTIVITY_AT,
        ),
    )


def test_course_filter_excludes_activity_from_other_courses(tmp_path: Path):
    app = build_app(tmp_path)
    user_id, first, db = _student_and_lesson(app)
    try:
        second = build_lesson_with_blocks(app, [{"title": "other"}])
        db.add_all(
            [
                LessonBlockCompletion(
                    user_id=user_id,
                    lesson_id=first["lesson_id"],
                    block_id=first["block_ids"][0],
                    completed_at=ACTIVITY_AT,
                ),
                LessonBlockCompletion(
                    user_id=user_id,
                    lesson_id=second["lesson_id"],
                    block_id=second["block_ids"][0],
                    completed_at=ACTIVITY_AT + timedelta(days=1),
                ),
            ]
        )
        db.commit()
        assert as_utc(last_activity_at(db, {user_id}, first["course_id"])[user_id]) == ACTIVITY_AT
    finally:
        db.close()


def test_empty_user_ids_returns_without_querying(tmp_path: Path):
    app = build_app(tmp_path)
    db = app.state.session_factory()
    statements = []
    engine = db.get_bind()

    def count(_conn, _cursor, statement, _parameters, _context, _executemany):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", count)
    try:
        assert last_activity_at(db, set()) == {}
    finally:
        event.remove(engine, "before_cursor_execute", count)
        db.close()
    assert statements == []


def test_collection_uses_four_queries_for_thirty_students(tmp_path: Path):
    app = build_app(tmp_path)
    _, built, db = _student_and_lesson(app)
    try:
        students = [
            User(
                username=f"activity-{index}",
                email=f"activity-{index}@example.com",
                hashed_password="unused",
                status="active",
            )
            for index in range(30)
        ]
        db.add_all(students)
        db.flush()
        db.add_all(
            [
                LessonBlockCompletion(
                    user_id=user.id,
                    lesson_id=built["lesson_id"],
                    block_id=built["block_ids"][0],
                    completed_at=ACTIVITY_AT,
                )
                for user in students
            ]
        )
        db.commit()

        statements = []
        engine = db.get_bind()

        def count(_conn, _cursor, statement, _parameters, _context, _executemany):
            statements.append(statement)

        event.listen(engine, "before_cursor_execute", count)
        try:
            actual = last_activity_at(db, {user.id for user in students})
        finally:
            event.remove(engine, "before_cursor_execute", count)
        assert len(actual) == 30
        assert len(statements) == 4
    finally:
        db.close()
