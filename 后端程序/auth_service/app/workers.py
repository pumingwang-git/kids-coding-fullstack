"""轻量 outbox 重试入口；生产环境应由 systemd/Celery/队列调度器周期执行。"""

from datetime import timedelta

from sqlalchemy import or_, select

from .config import get_settings
from .database import build_database
from .mailer import InMemoryEmailSender, SmtpEmailSender, deliver_outbox
from .models import EmailOutbox
from .security import utcnow


def retry_email_outbox(limit: int = 50) -> int:
    settings = get_settings()
    _, session_factory = build_database(settings.database_url)
    sender = SmtpEmailSender(settings) if settings.smtp_host else InMemoryEmailSender()
    db = session_factory()
    try:
        now = utcnow()
        stale_before = now - timedelta(seconds=settings.outbox_lock_seconds)
        ids = list(
            db.scalars(
                select(EmailOutbox.id)
                .where(
                    EmailOutbox.status.in_(["pending", "retry"]),
                    EmailOutbox.attempts < settings.outbox_max_attempts,
                    EmailOutbox.next_attempt_at <= now,
                    or_(EmailOutbox.locked_at.is_(None), EmailOutbox.locked_at < stale_before),
                )
                .order_by(EmailOutbox.next_attempt_at)
                .limit(limit)
            )
        )
    finally:
        db.close()
    for outbox_id in ids:
        deliver_outbox(session_factory, sender, settings, outbox_id)
    return len(ids)


if __name__ == "__main__":
    print(f"retried={retry_email_outbox()}")
