"""Shared aggregation for the four learning-activity ledgers."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import (
    CourseLesson,
    LessonBlockCompletion,
    LessonCodeRun,
    LessonProblemAttempt,
    LessonVideoWatch,
)

INACTIVE_DAYS_DEFAULT = 7


def activity_status(
    last_seen: datetime | None,
    now: datetime,
    threshold_days: int = INACTIVE_DAYS_DEFAULT,
) -> dict:
    """Return the explicit active/inactive status for one learner."""
    if last_seen is None:
        return {
            "last_activity_at": None,
            "never_active": True,
            "inactive_days": None,
            "active": False,
        }

    inactive_days = (now - last_seen).days
    return {
        "last_activity_at": last_seen,
        "never_active": False,
        "inactive_days": inactive_days,
        "active": inactive_days < threshold_days,
    }


def activity_rows(
    db: Session,
    user_ids: set[int],
    now: datetime,
    threshold_days: int = INACTIVE_DAYS_DEFAULT,
) -> list[dict]:
    """Return one activity-status DTO row for every supplied user ID."""
    latest = last_activity_at(db, user_ids)
    return [
        {
            "user_id": user_id,
            **activity_status(latest.get(user_id), now, threshold_days),
        }
        for user_id in sorted(user_ids)
    ]


def last_activity_at(
    db: Session,
    user_ids: set[int],
    course_id: int | None = None,
    *,
    group_by_lesson: bool = False,
) -> dict[int, datetime]:
    """Return each student's latest activity across the four learning ledgers.

    ``group_by_lesson`` is used by the continue-learning endpoint, whose existing
    contract is ordered by lesson rather than by student.  Both shapes share the
    same ledger definition so a new activity source cannot drift between them.
    """
    if not user_ids:
        return {}

    ledger_specs = (
        (
            LessonVideoWatch,
            func.coalesce(LessonVideoWatch.updated_at, LessonVideoWatch.last_beat_at),
        ),
        (LessonBlockCompletion, LessonBlockCompletion.completed_at),
        (LessonProblemAttempt, LessonProblemAttempt.updated_at),
        (LessonCodeRun, LessonCodeRun.created_at),
    )
    latest: dict[int, datetime] = {}

    for model, time_column in ledger_specs:
        grouped_by = model.lesson_id if group_by_lesson else model.user_id
        statement = select(grouped_by, func.max(time_column)).where(model.user_id.in_(user_ids))
        if course_id is not None:
            statement = statement.join(CourseLesson, CourseLesson.id == model.lesson_id).where(
                CourseLesson.course_id == course_id
            )
        for entity_id, at in db.execute(statement.group_by(grouped_by)):
            if at is not None and (entity_id not in latest or at > latest[entity_id]):
                latest[entity_id] = at
    return latest
