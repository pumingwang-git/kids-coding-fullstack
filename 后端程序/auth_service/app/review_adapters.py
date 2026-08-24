"""Review-target adapters for concrete submission sources."""
from __future__ import annotations

import json

from sqlalchemy.orm import Session

from .models import ScratchChallenge, ScratchProjectRevision, ScratchSubmission, User
from .review_domain import review_state_label
from .review_queue import pending_reviews


def _json_object(value: str | None) -> dict:
    try:
        parsed = json.loads(value or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _json_list(value: str | None) -> list:
    try:
        parsed = json.loads(value or "[]")
    except (TypeError, json.JSONDecodeError):
        return []
    return parsed if isinstance(parsed, list) else []


class ScratchReviewAdapter:
    """Expose ``ScratchSubmission`` without leaking its table shape to consumers."""

    source_type = "lesson_scratch"
    target_type = "scratch_submission"

    def pending(
        self, db: Session, student_ids: set[int] | None, page: int, page_size: int
    ) -> list[dict]:
        return [self._target(db, submission) for submission in pending_reviews(db, student_ids, page, page_size)]

    def get(self, db: Session, target_id: int, student_ids: set[int] | None) -> dict | None:
        submission = db.get(ScratchSubmission, target_id)
        if submission is None or (student_ids is not None and submission.user_id not in student_ids):
            return None
        return self._target(db, submission)

    def _target(self, db: Session, submission: ScratchSubmission) -> dict:
        student = db.get(User, submission.user_id)
        revision = db.get(ScratchProjectRevision, submission.project_revision_id)
        challenge = db.get(ScratchChallenge, submission.challenge_id)
        scores = _json_object(submission.rubric_scores_json)
        rubric_snapshot = _json_object(submission.rubric_snapshot)
        if not rubric_snapshot and challenge is not None:
            # Before a decision, the current challenge rubric is what the teacher scores.
            rubric_snapshot = _json_object(challenge.rubric_json)

        actions = []
        if submission.status == "needs_review" and submission.reviewed_at is None:
            actions = [
                {"type": "review", "label": "点评"},
                {"type": "return", "label": "退回重做"},
            ]

        return {
            "target": {
                "target_type": self.target_type,
                "target_id": submission.id,
                "student": {"id": submission.user_id, "username": student.username if student else None},
            },
            "assignment": {
                "source_type": self.source_type,
                "source_id": submission.lesson_block_id,
            },
            "state": submission.status,
            "state_label": review_state_label(submission.status),
            "submitted_at": submission.submitted_at.isoformat() if submission.submitted_at else None,
            "snapshot": {
                "kind": "sb3",
                "download_url": f"/api/admin/scratch/submissions/{submission.id}/project.sb3",
                "revision_id": submission.project_revision_id,
                "revision_no": revision.revision_no if revision else None,
            },
            "rubric": {
                "snapshot": rubric_snapshot,
                "scores": scores,
                "total": submission.manual_score,
                "total_max": submission.manual_score_max,
            },
            "allowed_actions": actions,
            # Existing Scratch clients expose rule evidence separately.  Keep it out of
            # the common DTO so later sources cannot accidentally inherit it.
            "review_comment": submission.review_comment,
            "rules_snapshot": _json_list(submission.rules_snapshot),
        }
