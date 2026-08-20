"""Queries for the teacher's pending manual-review queue."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import ScratchSubmission


def _pending_statement(student_ids: set[int] | None):
    conditions = [
        ScratchSubmission.status == "needs_review",
        ScratchSubmission.reviewed_at.is_(None),
    ]
    if student_ids is not None:
        conditions.append(ScratchSubmission.user_id.in_(student_ids))
    return select(ScratchSubmission).where(*conditions)


def pending_reviews(
    db: Session, student_ids: set[int] | None, page: int, page_size: int
) -> list[ScratchSubmission]:
    """Return the paged Scratch submissions awaiting teacher review.

    ``student_ids`` must already be narrowed by ``permissions.visible_student_ids``;
    ``None`` means the caller has an unrestricted student scope.
    """
    statement = (
        _pending_statement(student_ids)
        .order_by(ScratchSubmission.submitted_at, ScratchSubmission.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list(db.scalars(statement).all())


def pending_review_count(db: Session, student_ids: set[int] | None) -> int:
    """Count the same rows returned by :func:`pending_reviews`."""
    conditions = _pending_statement(student_ids).whereclause
    return int(
        db.scalar(
            select(func.count(ScratchSubmission.id)).where(conditions)
        )
        or 0
    )
