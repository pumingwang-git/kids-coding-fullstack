"""Source-neutral contracts for teacher review targets.

Adapters own persistence details.  Consumers receive these dictionaries and must
use the target identity for actions and the assignment identity for navigation.
"""
from __future__ import annotations

from typing import Protocol

from sqlalchemy.orm import Session

REVIEW_STATE_LABELS = {
    "needs_review": "待点评",
    "passed": "已通过",
    "failed": "未通过",
    "returned": "已退回",
}


def review_state_label(state: str) -> str:
    """Return the server-owned label while preserving unknown historical states."""
    return REVIEW_STATE_LABELS.get(state, state)


class ReviewTargetAdapter(Protocol):
    """A source adapter for a submitted work item, never for an assignment itself."""

    source_type: str
    target_type: str

    def pending(
        self, db: Session, student_ids: set[int] | None, page: int, page_size: int
    ) -> list[dict]: ...

    def get(
        self, db: Session, target_id: int, student_ids: set[int] | None
    ) -> dict | None: ...
