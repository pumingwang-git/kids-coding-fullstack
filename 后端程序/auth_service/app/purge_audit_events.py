"""按审计事件类别清理到期记录。

部署后可由 cron 周期调用，例如每天一次：
    0 3 * * * cd /srv/auth_service && .venv/bin/python -m app.purge_audit_events

预览删除范围：``python -m app.purge_audit_events --dry-run``。
保留期唯一来自 :mod:`app.audit_summary`，避免脚本复制第二套口径。
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timedelta

from sqlalchemy import delete, select

from .audit_summary import EVENT_CATEGORY, RETENTION_DAYS, ensure_known_event_type
from .config import get_settings
from .database import build_database
from .models import AuditEvent
from .security import utcnow


def purge_audit_events(db, *, now: datetime | None = None, dry_run: bool = False,
                       verbose: bool = True, environment: str = "test") -> int:
    """删除各类别已超过保留期的审计记录，返回删除条数。"""
    now = now or utcnow()
    deleted_by_category: Counter[str] = Counter()
    for category, retention_days in RETENTION_DAYS.items():
        event_types = [event for event, value in EVENT_CATEGORY.items() if value == category]
        if not event_types:
            continue
        cutoff = now - timedelta(days=retention_days)
        statement = select(AuditEvent.id).where(
            AuditEvent.event_type.in_(event_types), AuditEvent.created_at < cutoff
        )
        ids = list(db.scalars(statement).all())
        deleted_by_category[category] = len(ids)
        if not dry_run and ids:
            db.execute(delete(AuditEvent).where(AuditEvent.id.in_(ids)))

    total = sum(deleted_by_category.values())
    if not dry_run:
        # D-E9：系统/cron 事件不带 admin_ 前缀。`admin_` 的语义是「哪个管理端账号
        # 干的」，而这条记录既无 admin_user_id 也无 user_id——没有人做这个动作。
        # 今后所有定时任务发出的审计事件一律照此办理，不必再逐条讨论。
        event_type = "audit_retention_purge"
        ensure_known_event_type(event_type, environment)
        db.add(AuditEvent(
            event_type=event_type,
            outcome="success",
            resource_type="audit_events",
            summary_json=json.dumps({
                "schema_version": 1,
                "deleted_total": total,
                "deleted_by_category": dict(sorted(deleted_by_category.items())),
            }, ensure_ascii=False, sort_keys=True),
            created_at=now,
        ))
        db.commit()
    elif verbose:
        print(f"[dry-run] 将清理 {total} 条审计记录。")
    return total


# 与其他 cron 脚本的命名保持兼容，便于部署脚本/测试按“过期清理”语义调用。
purge_expired_audit_events = purge_audit_events


def main() -> None:
    parser = argparse.ArgumentParser(description="按类别清理到期审计记录。")
    parser.add_argument("--dry-run", action="store_true", help="只统计将删除的记录，不写库")
    args = parser.parse_args()
    settings = get_settings()
    engine, factory = build_database(settings.database_url)
    db = factory()
    try:
        total = purge_audit_events(db, dry_run=args.dry_run, environment=settings.environment)
    finally:
        db.close()
        engine.dispose()
    print(("将清理" if args.dry_run else "已清理") + f" {total} 条审计记录。")


if __name__ == "__main__":
    main()
