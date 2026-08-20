from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from sqlalchemy import select

from app.lesson_homework_kinds import PAPER_KIND, SCRATCH_KIND
from app.models import CourseLessonBlock, LessonPaperBlock, User
from test_admin_results import _lesson_homework, _start_homework, _submit
from test_exam import admin_login, build_exam, student_login
from test_scratch import build_scratch_lesson, create_challenge, scratch_env, work_and_submit


NOW = datetime.now(UTC)


class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows

    def __iter__(self):
        return iter(self._rows)


class _PaperDb:
    def __init__(self, attempts, due_at=None, answer_rows=()):
        self.attempts = attempts
        self.due_at = due_at
        self.answer_rows = answer_rows
        self.calls = 0

    def scalar(self, _statement):
        self.calls += 1
        return self.due_at

    def scalars(self, _statement):
        self.calls += 1
        return self.attempts

    def execute(self, _statement):
        self.calls += 1
        return _Rows(self.answer_rows)


class _ScratchDb:
    def __init__(self, submissions):
        self.submissions = submissions
        self.calls = 0

    def scalars(self, _statement):
        self.calls += 1
        return self.submissions


def test_paper_class_facts_transpose_nonempty_student_facts():
    attempt = SimpleNamespace(
        id=11, user_id=7, source_id=3, status="submitted", submitted_at=NOW,
        created_at=NOW, deadline_at=None,
    )
    student_db = _PaperDb([attempt])
    user = SimpleNamespace(id=7)
    student = PAPER_KIND.student_facts(student_db, user, [3])[3]
    class_facts = PAPER_KIND.class_facts(
        _PaperDb([attempt]), 3, {7}
    )[7]
    assert student == class_facts
    assert student.submitted_at is not None


def test_paper_class_facts_transposes_real_start_submit(tmp_path):
    env = build_exam(tmp_path, only=["choice"])
    built = _lesson_homework(env)
    attempt_id = _start_homework(env.student, built)
    _submit(env, attempt_id)
    db = env.app.state.session_factory()
    try:
        user = db.scalar(select(User).where(User.username == "learner"))
        student = PAPER_KIND.student_facts(db, user, [built["block"]["id"]])[
            built["block"]["id"]
        ]
        class_facts = PAPER_KIND.class_facts(db, built["block"]["id"], {user.id})[user.id]
    finally:
        db.close()
    assert student == class_facts
    assert student.submitted_at is not None


def test_paper_class_facts_filters_attempts_by_block(tmp_path):
    env = build_exam(tmp_path, only=["choice"])
    homework_x = _lesson_homework(env)
    db = env.app.state.session_factory()
    try:
        block_y = CourseLessonBlock(
            lesson_id=homework_x["lesson"]["id"], block_type="homework", title="块 Y",
            sort_order=1, required=True, unlock_rule="free",
        )
        db.add(block_y)
        db.flush()
        db.add(LessonPaperBlock(
            block_id=block_y.id, paper_id=env.paper_id, mode="homework", attempt_limit=2,
            shuffle_questions=False, shuffle_options=False, show_score=True,
            show_analysis=True, due_at=None,
        ))
        db.commit()
        block_y_id = block_y.id
    finally:
        db.close()
    _submit(env, _start_homework(env.student, homework_x))

    db = env.app.state.session_factory()
    try:
        user = db.scalar(select(User).where(User.username == "learner"))
        student = PAPER_KIND.student_facts(db, user, [block_y_id])[block_y_id]
        class_facts = PAPER_KIND.class_facts(db, block_y_id, {user.id})[user.id]
    finally:
        db.close()
    assert class_facts.submitted_at is None
    assert class_facts == student


def test_paper_class_facts_uses_attempt_open_predicate():
    expired = SimpleNamespace(
        id=12, user_id=7, source_id=3, status="ongoing", submitted_at=None,
        created_at=NOW, deadline_at=NOW - timedelta(minutes=1),
    )
    facts = PAPER_KIND.class_facts(_PaperDb([expired]), 3, {7})[7]
    assert facts.has_open_attempt is False


def test_class_facts_query_count_does_not_scale_with_class_size():
    user_ids = set(range(1, 31))
    paper_db = _PaperDb([])
    PAPER_KIND.class_facts(paper_db, 3, user_ids)
    assert paper_db.calls <= 3

    scratch_db = _ScratchDb([])
    SCRATCH_KIND.class_facts(scratch_db, 3, user_ids)
    assert scratch_db.calls == 1


def test_scratch_class_facts_transpose_nonempty_student_facts():
    submission = SimpleNamespace(
        id=21, user_id=7, lesson_block_id=3, submitted_at=NOW,
        status="passed", reviewed_at=None,
    )
    student = SCRATCH_KIND.student_facts(
        _ScratchDb([submission]), SimpleNamespace(id=7), [3]
    )[3]
    class_facts = SCRATCH_KIND.class_facts(_ScratchDb([submission]), 3, {7})[7]
    assert student == class_facts
    assert student.grading_done is True


def test_scratch_class_facts_filters_submissions_by_block(tmp_path):
    app = scratch_env(tmp_path)
    client, headers = admin_login(app)
    challenge = create_challenge(client, headers)
    built = build_scratch_lesson(app, blocks=[
        {"block_type": "scratch", "title": "块 X",
         "detail": {"scratch": {"challenge_id": challenge["id"]}}},
        {"block_type": "scratch", "title": "块 Y",
         "detail": {"scratch": {"challenge_id": challenge["id"]}}},
    ])
    sclient = student_login(app)
    assert work_and_submit(sclient, built["block_ids"][0]).status_code == 200

    db = app.state.session_factory()
    try:
        user = db.scalar(select(User).where(User.username == "learner"))
        student = SCRATCH_KIND.student_facts(db, user, [built["block_ids"][1]])[
            built["block_ids"][1]
        ]
        class_facts = SCRATCH_KIND.class_facts(db, built["block_ids"][1], {user.id})[user.id]
    finally:
        db.close()
    assert class_facts.submitted_at is None
    assert class_facts == student
