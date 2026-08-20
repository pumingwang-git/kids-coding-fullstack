from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models import Base, ScratchSubmission
from app.review_queue import pending_review_count, pending_reviews


def _submission(
    *, id: int, user_id: int, status: str, submitted_at: datetime, reviewed_at=None,
    attempt_no: int = 1,
):
    return ScratchSubmission(
        id=id,
        user_id=user_id,
        lesson_block_id=1,
        lesson_id=1,
        project_id=1,
        project_revision_id=1,
        challenge_id=1,
        attempt_no=attempt_no,
        status=status,
        submitted_at=submitted_at,
        reviewed_at=reviewed_at,
    )


def test_pending_review_queue_filters_status_review_time_and_scope(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'review-queue.db'}")
    Base.metadata.create_all(engine, tables=[ScratchSubmission.__table__])

    with Session(engine) as db:
        rows = [
            _submission(id=1, user_id=10, status="needs_review", submitted_at=datetime(2026, 1, 1, tzinfo=UTC)),
            _submission(id=2, user_id=10, status="returned", submitted_at=datetime(2026, 1, 2, tzinfo=UTC), attempt_no=2),
            _submission(id=3, user_id=10, status="passed", submitted_at=datetime(2026, 1, 3, tzinfo=UTC), attempt_no=3),
            _submission(id=4, user_id=10, status="needs_review", reviewed_at=datetime(2026, 1, 4, tzinfo=UTC), submitted_at=datetime(2026, 1, 4, tzinfo=UTC), attempt_no=4),
            _submission(id=5, user_id=11, status="needs_review", submitted_at=datetime(2026, 1, 5, tzinfo=UTC)),
        ]
        db.add_all(rows)
        db.commit()

        assert [row.id for row in pending_reviews(db, {10}, 1, 20)] == [1]
        assert pending_review_count(db, {10}) == 1
        assert pending_reviews(db, set(), 1, 20) == []

    engine.dispose()


def test_pending_reviews_are_oldest_first_with_id_tiebreaker(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'review-queue-order.db'}")
    Base.metadata.create_all(engine, tables=[ScratchSubmission.__table__])

    submitted_at = datetime(2026, 1, 1, tzinfo=UTC)
    with Session(engine) as db:
        db.add_all(
            [
                _submission(id=2, user_id=10, status="needs_review", submitted_at=submitted_at, attempt_no=2),
                _submission(id=1, user_id=10, status="needs_review", submitted_at=submitted_at, attempt_no=1),
                _submission(id=3, user_id=10, status="needs_review", submitted_at=submitted_at + timedelta(days=1), attempt_no=3),
            ]
        )
        db.commit()

        assert [row.id for row in pending_reviews(db, None, 1, 2)] == [1, 2]
        assert [row.id for row in pending_reviews(db, None, 2, 2)] == [3]

    engine.dispose()
