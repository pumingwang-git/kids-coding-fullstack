import json
from datetime import UTC, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models import Base, ScratchChallenge, ScratchProjectRevision, ScratchSubmission, User
from app.review_adapters import ScratchReviewAdapter


def _submission(id: int, user_id: int, *, status="needs_review", reviewed_at=None):
    return ScratchSubmission(
        id=id,
        user_id=user_id,
        lesson_block_id=44,
        lesson_id=9,
        project_id=2,
        project_revision_id=3,
        challenge_id=4,
        attempt_no=id,
        status=status,
        submitted_at=datetime(2026, 8, 23, tzinfo=UTC),
        reviewed_at=reviewed_at,
    )


def _engine(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'review-adapter.db'}")
    Base.metadata.create_all(
        engine,
        tables=[
            User.__table__,
            ScratchChallenge.__table__,
            ScratchProjectRevision.__table__,
            ScratchSubmission.__table__,
        ],
    )
    return engine


def test_scratch_adapter_keeps_target_and_assignment_identities_distinct(tmp_path):
    engine = _engine(tmp_path)
    with Session(engine) as db:
        db.add_all([
            User(id=7, username="student", email="student@example.test", hashed_password="x"),
            ScratchChallenge(id=4, title="变量", rubric_json=json.dumps({"criteria": [{"id": "logic"}]})),
            ScratchProjectRevision(id=3, project_id=2, revision_no=5, sb3_key="a.sb3", sha256="a" * 64),
            _submission(123, 7),
        ])
        db.commit()

        target = ScratchReviewAdapter().get(db, 123, {7})

    assert target["target"] == {
        "target_type": "scratch_submission",
        "target_id": 123,
        "student": {"id": 7, "username": "student"},
    }
    assert target["assignment"] == {"source_type": "lesson_scratch", "source_id": 44}
    assert target["state_label"] == "待点评"
    assert target["snapshot"]["kind"] == "sb3"
    assert target["snapshot"]["download_url"].endswith("/123/project.sb3")
    assert target["rubric"]["snapshot"] == {"criteria": [{"id": "logic"}]}
    assert [action["type"] for action in target["allowed_actions"]] == ["review", "return"]
    engine.dispose()


def test_scratch_adapter_pending_and_detail_enforce_visible_student_scope(tmp_path):
    engine = _engine(tmp_path)
    with Session(engine) as db:
        db.add_all([
            User(id=7, username="inside", email="inside@example.test", hashed_password="x"),
            User(id=8, username="outside", email="outside@example.test", hashed_password="x"),
            _submission(1, 7),
            _submission(2, 8),
            _submission(3, 7, status="returned", reviewed_at=datetime(2026, 8, 23, tzinfo=UTC)),
        ])
        db.commit()

        adapter = ScratchReviewAdapter()
        assert [item["target"]["target_id"] for item in adapter.pending(db, {7}, 1, 20)] == [1]
        assert adapter.get(db, 2, {7}) is None
        returned = adapter.get(db, 3, {7})

    assert returned["state_label"] == "已退回"
    assert returned["allowed_actions"] == []
    engine.dispose()
