from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.audit_summary import EVENT_CATEGORY, RETENTION_DAYS
from app.models import AuditEvent
from app.purge_audit_events import purge_audit_events
from test_exam import build_app


def _seed(app, rows):
    db = app.state.session_factory()
    try:
        db.add_all(rows)
        db.commit()
    finally:
        db.close()


def test_purge_keeps_each_category_inside_retention_and_removes_expired(tmp_path):
    app = build_app(tmp_path)
    now = datetime(2030, 1, 1, tzinfo=UTC)
    rows = []
    for category, days in RETENTION_DAYS.items():
        event_type = next(event for event, value in EVENT_CATEGORY.items() if value == category)
        rows.extend([
            AuditEvent(event_type=event_type, outcome="success",
                       created_at=now - timedelta(days=days) + timedelta(seconds=1)),
            AuditEvent(event_type=event_type, outcome="success",
                       created_at=now - timedelta(days=days) - timedelta(seconds=1)),
        ])
    rows.extend(AuditEvent(event_type=event_type, outcome="success",
                           created_at=now - timedelta(days=365 * 10))
                for event_type in ("admin_problem_clone", "admin_problem_offline", "exam_judge_failed"))
    _seed(app, rows)

    db = app.state.session_factory()
    try:
        assert purge_audit_events(db, now=now, environment="test") == len(RETENTION_DAYS) + 3
        kept = list(db.scalars(select(AuditEvent)).all())
        assert len(kept) == len(RETENTION_DAYS) + 1  # 每类一条边界内记录 + 本次 purge 审计
        assert any(row.event_type == "audit_retention_purge" for row in kept)
        assert not {row.event_type for row in kept} & {
            "admin_problem_clone", "admin_problem_offline", "exam_judge_failed"
        }
    finally:
        db.close()


def test_purge_respects_retention_days_mutation(tmp_path, monkeypatch):
    app = build_app(tmp_path)
    now = datetime(2030, 1, 1, tzinfo=UTC)
    category = "session"
    event_type = next(event for event, value in EVENT_CATEGORY.items() if value == category)
    original = RETENTION_DAYS[category]
    _seed(app, [AuditEvent(event_type=event_type, outcome="success",
                            created_at=now - timedelta(days=original + 1))])
    monkeypatch.setitem(RETENTION_DAYS, category, original * 2)
    db = app.state.session_factory()
    try:
        assert purge_audit_events(db, now=now, environment="test") == 0
        assert db.scalar(select(AuditEvent).where(AuditEvent.event_type == event_type)) is not None
    finally:
        db.close()
