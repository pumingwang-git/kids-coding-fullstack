from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from app.lesson_homework_kinds import PAPER_KIND, SCRATCH_KIND


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
