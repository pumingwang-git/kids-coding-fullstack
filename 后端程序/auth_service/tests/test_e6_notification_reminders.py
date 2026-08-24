"""E6 cron reminder contracts."""

from pathlib import Path


SOURCE = (Path(__file__).parents[1] / "app" / "notification_reminders.py").read_text(
    encoding="utf-8"
)


def test_due_reminders_use_configured_window_and_real_idempotent_count():
    assert "timedelta(hours=DUE_SOON_HOURS)" in SOURCE
    assert "exists = db.scalar(select(Notification.id)" in SOURCE
    assert ":hours{DUE_SOON_HOURS}" in SOURCE
    assert "lesson_homework_link(lesson.id, block.id)" in SOURCE


def test_after_close_reuses_score_visibility_and_blocks_pending_judges():
    assert "_score_visible(source, now)" in SOURCE
    assert "judge_status.in_([\"pending\", \"queued\", \"judging\"])" in SOURCE
    assert "exam_attempt_link(link.access_token)" in SOURCE
