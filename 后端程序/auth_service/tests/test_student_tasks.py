from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import event, select
from test_admin_course_content import block_payload
from test_enrollments import set_enrollment
from test_exam import build_app, scsrf, student_login
from test_lesson_block_unlock import build_lesson_with_blocks, complete
from test_lesson_problem_blocks import seed_paper
from test_lesson_practice import answer, build_practice, seed_choice_problem
from test_scratch import build_scratch_lesson

from app.models import LessonPaperBlock, PaperAttempt, Problem, ProblemTag, Tag, User
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
import app.routers.student_tasks as student_tasks_router
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
        from app.models import LessonProblemAttempt
        db.add(LessonProblemAttempt(user_id=user.id, block_id=built[1]["block_ids"][-1],
                                    lesson_id=built[1]["lesson_id"], tries=1))
        db.commit()
    finally:
        db.close()

    # done 必须由真实作答链路产生：提交会在同一事务中写 tries 和 completion。
    # 手工只写 completion 会构造线上不可能出现的 completed=True, tries=0，
    # 从而测不到 practice_phase 的两个分支顺序。
    done = answer(student, built[2]["lesson_id"], built[2]["block_ids"][-1], {"picked": "A"})
    assert done.status_code == 200, done.text
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


def test_practice_endpoint_excludes_unenrolled_and_sequentially_locked_blocks(tmp_path: Path):
    app = build_app(tmp_path)
    student = student_login(app)
    enrolled_problem = seed_choice_problem(app, problem_id_no="Q310001")["problem_id_no"]
    locked_problem = seed_choice_problem(app, problem_id_no="Q310002")["problem_id_no"]
    hidden_problem = seed_choice_problem(app, problem_id_no="Q310003")["problem_id_no"]
    enrolled = build_practice(app, problem_id_no=enrolled_problem)
    locked = build_lesson_with_blocks(app, [
        {"block_type": "markdown", "title": "前置", "required": True},
        {"block_type": "practice", "problem_id_no": locked_problem,
         "unlock_rule": "sequential"},
    ])
    unenrolled = build_practice(app, problem_id_no=hidden_problem)
    user = _learner(app)
    set_enrollment(app, student_id=user.id, course_id=enrolled["course_id"])
    set_enrollment(app, student_id=user.id, course_id=locked["course_id"])

    body = student.get("/api/student/practice").json()
    assert [item["source_id"] for item in body["items"]] == [enrolled["block_ids"][-1]]
    assert unenrolled["block_ids"][-1] not in {item["source_id"] for item in body["items"]}

    assert complete(student, locked["lesson_id"], locked["block_ids"][0]).status_code == 200
    body = student.get("/api/student/practice").json()
    assert {item["source_id"] for item in body["items"]} == {
        enrolled["block_ids"][-1], locked["block_ids"][-1],
    }


def test_practice_endpoint_filters_knowledge_course_and_lesson(tmp_path: Path):
    app = build_app(tmp_path)
    student = student_login(app)
    matching_no = seed_choice_problem(app, problem_id_no="Q320001")["problem_id_no"]
    other_no = seed_choice_problem(app, problem_id_no="Q320002")["problem_id_no"]
    matching = build_practice(app, problem_id_no=matching_no)
    other = build_practice(app, problem_id_no=other_no)
    user = _learner(app)
    set_enrollment(app, student_id=user.id, course_id=matching["course_id"])
    set_enrollment(app, student_id=user.id, course_id=other["course_id"])
    db = app.state.session_factory()
    try:
        problem = db.scalar(select(Problem).where(Problem.problem_id_no == matching_no))
        tag = Tag(name="任务中心知识点", category="knowledge")
        db.add(tag)
        db.flush()
        db.add(ProblemTag(problem_id=problem.id, tag_id=tag.id))
        db.commit()
    finally:
        db.close()

    for query in (
        "knowledge=%E4%BB%BB%E5%8A%A1%E4%B8%AD%E5%BF%83%E7%9F%A5%E8%AF%86%E7%82%B9",
        f"course_id={matching['course_id']}",
        f"lesson_id={matching['lesson_id']}",
    ):
        body = student.get(f"/api/student/practice?{query}").json()
        assert [item["source_id"] for item in body["items"]] == [matching["block_ids"][-1]]


def test_practice_endpoint_paginates_second_page_and_keeps_total(tmp_path: Path):
    app = build_app(tmp_path)
    student = student_login(app)
    specs = []
    for index in range(25):
        problem_id_no = seed_choice_problem(app, problem_id_no=f"Q330{index:03d}")["problem_id_no"]
        specs.append({"block_type": "practice", "title": f"练习 {index}",
                      "problem_id_no": problem_id_no, "score": 10, "display_no": str(index + 1)})
    built = build_lesson_with_blocks(app, specs, open_policy="closed")
    user = _learner(app)
    set_enrollment(app, student_id=user.id, course_id=built["course_id"])

    body = student.get("/api/student/practice?page=2").json()
    assert body["total"] == 25
    assert body["page"] == 2 and body["page_size"] == 20
    assert [item["source_id"] for item in body["items"]] == built["block_ids"][20:]


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


def test_tasks_overview_empty_student_has_five_empty_groups(tmp_path: Path):
    app = build_app(tmp_path)
    student = student_login(app)

    response = student.get("/api/student/tasks/overview")
    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {"in_progress", "due_soon", "to_review", "unfinished", "next_up"}
    assert all(group == {"items": [], "total": 0} for group in body.values())


def test_tasks_overview_due_soon_uses_homework_dto_and_72_hour_boundary(tmp_path: Path):
    app = build_app(tmp_path)
    student = student_login(app)
    paper_id = seed_paper(app)["paper_id"]
    built = build_lesson_with_blocks(app, [
        {"block_type": "homework", "title": "窗内", "paper_id": paper_id},
        {"block_type": "homework", "title": "窗外", "paper_id": paper_id},
    ], open_policy="closed")
    user = _learner(app)
    set_enrollment(app, student_id=user.id, course_id=built["course_id"])
    db = app.state.session_factory()
    try:
        rows = list(db.scalars(
            select(LessonPaperBlock).where(LessonPaperBlock.block_id.in_(built["block_ids"]))
        ))
        due_by_block = {row.block_id: row for row in rows}
        now = datetime.now(UTC)
        due_by_block[built["block_ids"][0]].due_at = now + timedelta(hours=71)
        due_by_block[built["block_ids"][1]].due_at = now + timedelta(hours=73)
        db.commit()
    finally:
        db.close()

    homework = student.get("/api/student/homework").json()["items"]
    overview = student.get("/api/student/tasks/overview").json()
    due_soon = overview["due_soon"]
    assert due_soon["total"] == 1
    assert [item["source_id"] for item in due_soon["items"]] == [built["block_ids"][0]]
    listed = next(item for item in homework if item["source_id"] == built["block_ids"][0])
    assert due_soon["items"][0] == listed


def test_tasks_overview_group_limit_is_five():
    assert student_tasks_router._group([{} for _ in range(8)]) == {
        "items": [{}, {}, {}, {}, {}], "total": 8,
    }


def test_tasks_overview_includes_running_exam_and_classifies_remaining_groups(tmp_path: Path, monkeypatch):
    app = build_app(tmp_path)
    student = student_login(app)
    now = datetime.now(UTC)

    def candidate(block_id, phase, due=None):
        return ({"source_id": block_id, "facts": TaskFacts(
            due_at=due, has_open_attempt=False, submitted_at=now if phase == "graded" else None,
            grading_done=phase == "graded"), "completed": False, "tries": 0}, phase)

    homework = [candidate(1, "graded"), candidate(2, "overdue", now - timedelta(hours=1))]
    practice = [{"source_id": 3, "completed": False, "tries": 1}]
    monkeypatch.setattr(student_tasks_router, "collect_homework_candidates",
                        lambda db, user: [row[0] for row in homework])
    monkeypatch.setattr(student_tasks_router, "collect_practice_candidates",
                        lambda db, user: practice)
    monkeypatch.setattr(student_tasks_router, "homework_phase",
                        lambda facts, now: next(row[1] for row in homework if row[0]["facts"] is facts))
    monkeypatch.setattr(student_tasks_router, "build_homework_item",
                        lambda candidate, phase: {"id": candidate["source_id"], "phase": phase})
    monkeypatch.setattr(student_tasks_router, "build_practice_item",
                        lambda candidate, phase: {"id": candidate["source_id"], "phase": phase})
    monkeypatch.setattr(student_tasks_router, "_exam_rows",
                        lambda db, user, now: [({"source_id": 9, "phase": "running"}, "running")])
    body = student.get("/api/student/tasks/overview").json()
    assert body["in_progress"]["items"] == [{"source_id": 9, "phase": "running"}]
    assert body["to_review"]["items"] == [{"id": 1, "phase": "graded"}]
    assert body["unfinished"]["items"] == [
        {"id": 3, "phase": "in_progress"}, {"id": 2, "phase": "overdue"}
    ]


def test_lesson_homework_start_resumes_the_same_attempt(tmp_path: Path):
    app = build_app(tmp_path)
    student = student_login(app)
    paper_id = seed_paper(app)["paper_id"]
    built = build_lesson_with_blocks(
        app, [{"block_type": "homework", "paper_id": paper_id}], open_policy="closed"
    )
    user = _learner(app)
    set_enrollment(app, student_id=user.id, course_id=built["course_id"])
    path = f"/api/exam/lesson-homework/{built['lesson_id']}/blocks/{built['block_ids'][0]}/start"

    first = student.post(path, headers=scsrf(student))
    second = student.post(path, headers=scsrf(student))
    assert first.status_code == second.status_code == 201
    assert second.json()["resumed"] is True
    assert second.json()["attempt_id"] == first.json()["attempt_id"]


def test_lesson_homework_start_unique_conflict_is_409(tmp_path: Path, monkeypatch):
    app = build_app(tmp_path)
    student = student_login(app)
    paper_id = seed_paper(app)["paper_id"]
    built = build_lesson_with_blocks(
        app, [{"block_type": "homework", "paper_id": paper_id}], open_policy="closed"
    )
    user = _learner(app)
    block_id = built["block_ids"][0]
    set_enrollment(app, student_id=user.id, course_id=built["course_id"])
    db = app.state.session_factory()
    try:
        db.add(PaperAttempt(source_type="lesson_homework", source_id=block_id, paper_id=paper_id,
                            user_id=user.id, attempt_no=1, status="ongoing"))
        db.commit()
    finally:
        db.close()

    import app.routers.exam as exam_router
    monkeypatch.setattr(exam_router, "_ongoing_attempt", lambda *_args: None)
    monkeypatch.setattr(exam_router, "_used_attempts", lambda *_args: 0)
    response = student.post(
        f"/api/exam/lesson-homework/{built['lesson_id']}/blocks/{block_id}/start",
        headers=scsrf(student),
    )
    assert response.status_code == 409
    assert "其他窗口" in response.json()["detail"]
