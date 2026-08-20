from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.homework_roster import build_homework_roster
from app.student_tasks import TaskFacts


class _Db:
    def __init__(self, users):
        self.users = users

    def scalars(self, _statement):
        return self.users

    def get(self, model, _id):
        if model.__name__ == "CourseLessonBlock":
            return SimpleNamespace(lesson_id=10)
        if model.__name__ == "CourseLesson":
            return SimpleNamespace(course_id=20)
        return None


@pytest.mark.parametrize("kind_key", ["paper", "scratch"])
def test_homework_roster_keeps_blocked_students_and_excludes_submitted(
    monkeypatch, kind_key
):
    import app.homework_roster as roster

    users = [SimpleNamespace(id=1, username="blocked"),
             SimpleNamespace(id=2, username="submitted")]
    facts = {
        1: TaskFacts(None, False, None, False),
        2: TaskFacts(None, False, datetime(2026, 1, 1, tzinfo=UTC), False),
    }
    kind = SimpleNamespace(
        key=kind_key,
        student_source_type="lesson_scratch" if kind_key == "scratch" else "lesson_homework",
        class_facts=lambda db, block_id, ids: facts,
    )
    monkeypatch.setattr(roster, "KINDS", [kind])
    monkeypatch.setattr(roster, "active_student_ids_for_classes", lambda db, ids: {1, 2})
    monkeypatch.setattr(roster, "enrolled_course_ids", lambda db, user: {20} if user.id == 2 else set())
    monkeypatch.setattr(roster, "_attempt_counts", lambda *args: ({2}, 3))

    result = build_homework_roster(_Db(users), 7, kind_key, 99,
                                   now=datetime(2026, 1, 2, tzinfo=UTC))

    assert result["roster_people"] == 2
    assert result["submitted_people"] == 1
    assert result["not_submitted_people"] == 1
    assert result["submitted_attempts"] == 3
    assert [row["student"]["id"] for row in result["not_submitted"]] == [1]
    assert result["not_submitted"][0]["access_blocked"] is True

