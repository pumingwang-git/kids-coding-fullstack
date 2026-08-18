from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import event, select
from test_admin_course_content import block_payload
from test_enrollments import set_enrollment
from test_exam import build_app, student_login
from test_lesson_block_unlock import build_lesson_with_blocks, complete
from test_lesson_problem_blocks import seed_paper
from test_lesson_practice import build_practice, seed_choice_problem
from test_scratch import build_scratch_lesson

from app.models import User
from app.routers.exam import _phase
from app.student_tasks import (
    EXAM_PHASE_GROUPS,
    EXAM_PHASE_LABELS,
    HOMEWORK_PHASE_LABELS,
    TaskFacts,
    _attempt_is_open,
    collect_homework_candidates,
    exam_phase,
    homework_phase,
)
from app.lesson_homework_kinds import PAPER_KIND, SCRATCH_KIND


NOW = datetime(2026, 8, 18, 16, 30, tzinfo=UTC)

ALL_FIVE_CASES = [
    (TaskFacts(due_at=NOW + timedelta(minutes=1), has_open_attempt=False,
               submitted_at=None, grading_done=False), "todo"),
    (TaskFacts(due_at=NOW - timedelta(minutes=1), has_open_attempt=True,
               submitted_at=None, grading_done=False), "in_progress"),
    (TaskFacts(due_at=NOW + timedelta(minutes=1), has_open_attempt=False,
               submitted_at=NOW, grading_done=False), "submitted"),
    (TaskFacts(due_at=NOW + timedelta(minutes=1), has_open_attempt=False,
               submitted_at=NOW, grading_done=True), "graded"),
    (TaskFacts(due_at=NOW - timedelta(minutes=1), has_open_attempt=False,
               submitted_at=None, grading_done=False), "overdue"),
]


@pytest.mark.parametrize(
    ("facts", "expected"),
    ALL_FIVE_CASES,
)
def test_homework_phase_has_all_five_states(facts, expected):
    assert homework_phase(facts, NOW) == expected


@pytest.mark.parametrize("grading_done, expected", [(False, "submitted"), (True, "graded")])
def test_submitted_homework_is_not_overdue(grading_done, expected):
    facts = TaskFacts(due_at=NOW - timedelta(minutes=1), has_open_attempt=False,
                      submitted_at=NOW - timedelta(minutes=2), grading_done=grading_done)
    assert homework_phase(facts, NOW) == expected


def test_open_attempt_is_not_overdue():
    facts = TaskFacts(due_at=NOW - timedelta(minutes=1), has_open_attempt=True,
                      submitted_at=None, grading_done=False)
    assert homework_phase(facts, NOW) == "in_progress"


def test_scratch_without_due_date_is_todo_not_overdue():
    facts = TaskFacts(due_at=None, has_open_attempt=False, submitted_at=None, grading_done=False)
    assert homework_phase(facts, NOW) == "todo"


def test_homework_phase_normalizes_sqlite_naive_due_at_as_utc():
    # 23:00 naive 是 SQLite 读回的 UTC 值，此刻（16:30 UTC）还没到期。
    # 若被误当成东八区，它在 UTC 轴上会提前到 15:00，结论会翻成 overdue。
    facts = TaskFacts(due_at=datetime(2026, 8, 18, 23, 0), has_open_attempt=False,
                      submitted_at=None, grading_done=False)
    assert homework_phase(facts, NOW) == "todo"


def test_labels_cover_every_produced_phase():
    produced = {homework_phase(facts, NOW) for facts, _ in ALL_FIVE_CASES}
    assert produced == set(HOMEWORK_PHASE_LABELS)
    assert set(EXAM_PHASE_GROUPS.values()) == set(EXAM_PHASE_LABELS)


def test_attempt_is_not_open_when_ongoing_attempt_deadline_has_passed():
    attempt = SimpleNamespace(status="ongoing", deadline_at=NOW - timedelta(seconds=1))
    assert _attempt_is_open(attempt, NOW) is False


def test_attempt_without_deadline_remains_open():
    attempt = SimpleNamespace(status="ongoing", deadline_at=None)
    assert _attempt_is_open(attempt, NOW) is True


def test_paper_empty_submission_is_explicitly_grading_done():
    """空卷没有待判题；这不是依赖 Python all() 的偶然行为。"""
    attempt = SimpleNamespace(id=11, source_id=7, status="submitted", submitted_at=NOW,
                              created_at=NOW, deadline_at=None)

    class Result:
        def __init__(self, rows):
            self.rows = rows

        def all(self):
            return self.rows

        def __iter__(self):
            return iter(self.rows)

    class Db:
        execute_calls = 0

        def execute(self, _statement):
            self.execute_calls += 1
            rows = [(7, None)] if self.execute_calls == 1 else []
            return Result(rows)

        def scalars(self, _statement):
            return [attempt]

    facts = PAPER_KIND.student_facts(Db(), SimpleNamespace(id=3), [7])
    assert facts[7].submitted_at == NOW
    assert facts[7].grading_done is True


def test_scratch_returned_submission_stays_in_progress():
    submission = SimpleNamespace(lesson_block_id=9, id=1, submitted_at=NOW,
                                 status="returned", reviewed_at=NOW)

    class Db:
        def scalars(self, _statement):
            return [submission]

    facts = SCRATCH_KIND.student_facts(Db(), SimpleNamespace(id=3), [9])
    assert facts[9].has_open_attempt is True
    assert homework_phase(facts[9], NOW) == "in_progress"


def _learner(app):
    db = app.state.session_factory()
    try:
        return db.scalar(select(User).where(User.username == "learner"))
    finally:
        db.close()


def _candidates(app, user):
    db = app.state.session_factory()
    try:
        return collect_homework_candidates(db, user)
    finally:
        db.close()


def test_unenrolled_course_homework_is_not_a_candidate(tmp_path: Path):
    app = build_app(tmp_path)
    student_login(app)
    paper_id = seed_paper(app)["paper_id"]
    enrolled = build_lesson_with_blocks(
        app, [{"block_type": "homework", "paper_id": paper_id}], open_policy="closed")
    unenrolled = build_lesson_with_blocks(
        app, [{"block_type": "homework", "paper_id": paper_id}], open_policy="whole")
    user = _learner(app)
    set_enrollment(app, student_id=user.id, course_id=enrolled["course_id"])

    rows = _candidates(app, user)
    assert [row["source_id"] for row in rows] == [enrolled["block_ids"][0]]
    assert unenrolled["block_ids"][0] not in {row["source_id"] for row in rows}


def test_candidates_and_entry_agree_after_all_real_prerequisites(tmp_path: Path):
    app = build_app(tmp_path)
    student = student_login(app)
    paper_id = seed_paper(app)["paper_id"]
    built = build_lesson_with_blocks(app, [
        {"block_type": "markdown", "title": "先读这个", "required": True,
         "content_md": "# hi"},
        {"block_type": "homework", "title": "课后作业", "unlock_rule": "sequential",
         "paper_id": paper_id},
    ], open_policy="closed")
    user = _learner(app)
    set_enrollment(app, student_id=user.id, course_id=built["course_id"])

    assert _candidates(app, user) == []
    entry = f"/api/exam/lesson-homework/{built['lesson_id']}/blocks/{built['block_ids'][1]}"
    assert student.get(entry).status_code == 403

    assert complete(student, built["lesson_id"], built["block_ids"][0]).status_code == 200
    rows = _candidates(app, user)
    assert [row["source_id"] for row in rows] == [built["block_ids"][1]]
    for row in rows:
        assert student.get(
            f"/api/exam/lesson-homework/{row['lesson_id']}/blocks/{row['source_id']}"
        ).status_code == 200


def test_mixed_paper_and_scratch_blocks_are_both_candidates(tmp_path: Path):
    app = build_app(tmp_path)
    student_login(app)
    built = build_scratch_lesson(app, open_policy="closed", publish_course=False)
    paper_id = seed_paper(app)["paper_id"]
    homework = built["client"].post(
        f"/api/admin/lessons/{built['lesson_id']}/blocks", headers=built["headers"],
        json=block_payload("homework", paper_id=paper_id),
    )
    assert homework.status_code == 201, homework.text
    assert built["client"].post(
        f"/api/admin/courses/{built['course_id']}/publish", headers=built["headers"]
    ).status_code == 200
    user = _learner(app)
    set_enrollment(app, student_id=user.id, course_id=built["course_id"])

    assert {row["source_type"] for row in _candidates(app, user)} == {
        "lesson_homework", "lesson_scratch"
    }


def test_candidate_collection_uses_bounded_real_sql_queries(tmp_path: Path):
    app = build_app(tmp_path)
    student_login(app)
    paper_id = seed_paper(app)["paper_id"]
    built = [build_lesson_with_blocks(
        app, [{"block_type": "homework", "paper_id": paper_id} for _ in range(3)],
        open_policy="closed",
    ) for _ in range(3)]
    user = _learner(app)
    for lesson in built:
        set_enrollment(app, student_id=user.id, course_id=lesson["course_id"])

    db = app.state.session_factory()
    statements = []
    engine = db.get_bind()
    def count(_conn, _cursor, statement, _parameters, _context, _executemany):
        statements.append(statement)
    event.listen(engine, "before_cursor_execute", count)
    try:
        assert len(collect_homework_candidates(db, user)) == 9
    finally:
        event.remove(engine, "before_cursor_execute", count)
        db.close()
    # 资格、候选、全量 ordered、3×(完成集合+权限谓词)、两类 paper facts = 11。
    # 块数从 1 增至 3 不增加查询，防止把课时级事实写回块级循环。
    assert len(statements) == 11


def test_homework_endpoint_returns_contract_and_validates_filters(tmp_path: Path):
    app = build_app(tmp_path)
    student = student_login(app)
    paper_id = seed_paper(app)["paper_id"]
    built = build_lesson_with_blocks(app, [{"block_type": "homework", "paper_id": paper_id}],
                                     open_policy="closed")
    user = _learner(app)
    set_enrollment(app, student_id=user.id, course_id=built["course_id"])

    response = student.get("/api/student/homework")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 1 and body["page_size"] == 20
    item = body["items"][0]
    assert set(item) == {"source_type", "source_id", "scope", "phase", "phase_label",
                         "due_at", "origin", "entry"}
    assert item["source_type"] == "lesson_homework"
    assert item["due_at"] is None
    assert item["entry"] == {"kind": "lesson_homework", "lesson_id": built["lesson_id"],
                              "block_id": built["block_ids"][0]}
    assert student.get("/api/student/homework?status=bad").status_code == 422
    assert student.get("/api/student/homework?sort=created_at").status_code == 422
    assert student.get("/api/student/homework?page_size=101").status_code == 422


def test_practice_endpoint_has_three_phases_and_no_problem_identity(tmp_path: Path):
    app = build_app(tmp_path)
    student = student_login(app)
    built = []
    for index in range(3):
        no = seed_choice_problem(app, problem_id_no=f"Q{index + 300000:06d}")["problem_id_no"]
        lesson = build_practice(app, problem_id_no=no)
        built.append(lesson)
    user = _learner(app)
    db = app.state.session_factory()
    try:
        for lesson in built:
            set_enrollment(app, student_id=user.id, course_id=lesson["course_id"])
        from app.models import LessonBlockCompletion, LessonProblemAttempt
        db.add(LessonProblemAttempt(user_id=user.id, block_id=built[1]["block_ids"][-1],
                                    lesson_id=built[1]["lesson_id"], tries=1))
        db.add(LessonBlockCompletion(user_id=user.id, block_id=built[2]["block_ids"][-1],
                                     lesson_id=built[2]["lesson_id"], source="practice"))
        db.commit()
    finally:
        db.close()
    response = student.get("/api/student/practice")
    assert response.status_code == 200, response.text
    body = response.json()
    assert {item["phase"] for item in body["items"]} == {"todo", "in_progress", "done"}
    assert all("due_at" not in item for item in body["items"])
    def walk(value):
        if isinstance(value, dict):
            for key, child in value.items():
                assert key not in {"problem_id_no", "paper_id", "answer", "questions"}
                yield from walk(child)
        elif isinstance(value, list):
            for child in value:
                yield from walk(child)
    list(walk(body))


def test_exam_phase_groups_every_existing_exam_window():
    source = SimpleNamespace(
        open_at=NOW + timedelta(hours=2), close_at=NOW + timedelta(hours=3), entry_open_minutes=30,
    )
    windows = {
        "waiting": NOW,
        "entry_open": NOW + timedelta(hours=1, minutes=30),
        "open": NOW + timedelta(hours=2),
        "closed": NOW + timedelta(hours=3),
    }

    phases = {_phase(source, instant) for instant in windows.values()}
    assert phases == set(EXAM_PHASE_GROUPS)
    assert {exam_phase(source, instant) for instant in windows.values()} == {
        "upcoming", "running", "ended"
    }
