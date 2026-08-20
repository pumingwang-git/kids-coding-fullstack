"""Read-only roster aggregation for a class homework block."""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .class_groups import active_student_ids_for_classes
from .course_access import enrolled_course_ids
from .lesson_homework_kinds import KINDS, HomeworkKind, _counted_submission
from .models import (
    CourseLesson,
    CourseLessonBlock,
    PaperAttempt,
    ScratchSubmission,
    User,
)
from .routers.exam import counted_attempt
from .student_tasks import HOMEWORK_PHASE_LABELS, homework_phase


def _kind(value: HomeworkKind | str) -> HomeworkKind:
    if isinstance(value, HomeworkKind):
        return value
    for item in KINDS:
        if item.key == value or item.student_source_type == value:
            return item
    raise ValueError(f"unknown homework kind: {value}")


def _attempt_counts(db: Session, kind: HomeworkKind, block_id: int,
                    student_ids: set[int]) -> tuple[set[int], int]:
    """Return counted submitters and raw attempt count using the canonical selectors."""
    if not student_ids:
        return set(), 0
    if kind.key == "scratch":
        rows = list(db.scalars(select(ScratchSubmission).where(
            ScratchSubmission.lesson_block_id == block_id,
            ScratchSubmission.user_id.in_(student_ids),
        )))
        by_user: dict[int, list[ScratchSubmission]] = {}
        for row in rows:
            by_user.setdefault(row.user_id, []).append(row)
        counted = {user_id for user_id, user_rows in by_user.items()
                   if _counted_submission(user_rows) is not None}
        return counted, len(rows)

    rows = list(db.scalars(select(PaperAttempt).where(
        PaperAttempt.source_type == kind.student_source_type,
        PaperAttempt.source_id == block_id,
        PaperAttempt.user_id.in_(student_ids),
    )))
    # Lesson homework is currently score_policy=best; the selector remains centralized.
    by_user: dict[int, list[PaperAttempt]] = {}
    for row in rows:
        by_user.setdefault(row.user_id, []).append(row)
    counted = {user_id for user_id, user_rows in by_user.items()
               if counted_attempt(user_rows, "best") is not None}
    return counted, len(rows)


def build_homework_roster(
    db: Session,
    class_id: int,
    homework: HomeworkKind | str,
    block_id: int,
    *,
    now: datetime | None = None,
) -> dict:
    """Build class homework roster data without routing or side effects."""
    kind = _kind(homework)
    now = now or datetime.now(UTC)
    student_ids = active_student_ids_for_classes(db, {class_id})
    users = list(db.scalars(
        select(User).where(User.id.in_(student_ids)).order_by(User.id)
    )) if student_ids else []
    facts = kind.class_facts(db, block_id, student_ids)
    counted_ids, attempts = _attempt_counts(db, kind, block_id, student_ids)

    block = db.get(CourseLessonBlock, block_id)
    lesson = db.get(CourseLesson, block.lesson_id) if block else None
    course_id = lesson.course_id if lesson else None
    rows: list[dict] = []
    submitted: list[dict] = []
    not_submitted: list[dict] = []
    for user in users:
        phase = homework_phase(facts[user.id], now)
        row = {
            "student": {"id": user.id, "username": user.username},
            "phase": phase,
            "phase_label": HOMEWORK_PHASE_LABELS[phase],
            "access_blocked": course_id not in enrolled_course_ids(db, user)
            if course_id is not None else False,
        }
        rows.append(row)
        if phase in {"submitted", "graded"} and user.id in counted_ids:
            submitted.append(row)
        else:
            not_submitted.append(row)

    return {
        "roster": rows,
        "submitted": submitted,
        "not_submitted": not_submitted,
        "roster_people": len(rows),
        "submitted_people": len(submitted),
        "not_submitted_people": len(not_submitted),
        "submitted_attempts": attempts,
    }


homework_roster = build_homework_roster
get_homework_roster = build_homework_roster
