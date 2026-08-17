"""收掉超时未交的作答。

为什么必须有这个脚本：惰性封卷挂在学员的请求上，学员关掉浏览器就再也不发请求了，
attempt 会永远挂在 ongoing，成绩永远不出。部署后挂 cron，每 5 分钟一次：

    */5 * * * * cd /srv/auth_service && .venv/bin/python -m app.close_expired_attempts

先看会动哪些：python -m app.close_expired_attempts --dry-run
"""

from __future__ import annotations

import argparse

from sqlalchemy import select

from .config import get_settings
from .database import build_database
from .models import Paper, PaperAttempt
from .routers.exam import _as_utc, _seal
from .security import utcnow


def seal_expired(db, *, dry_run: bool = False, verbose: bool = True) -> int:
    """把所有已过期的 ongoing 作答收掉判分，返回处理条数。

    与 main() 分开是为了能在测试里直接用测试会话调它——CLI 那层只负责读配置、
    开连接、打印，不该是唯一的入口。
    """
    now = utcnow()
    sealed = 0
    candidates = db.scalars(
        select(PaperAttempt).where(PaperAttempt.status == "ongoing",
                                   PaperAttempt.deadline_at.is_not(None))
    ).all()
    for attempt in candidates:
        deadline = _as_utc(attempt.deadline_at)
        if not deadline or now <= deadline:
            continue
        sealed += 1
        if dry_run:
            if verbose:
                print(f"[dry-run] attempt #{attempt.id} 学员 {attempt.user_id} 截止于 {deadline.isoformat()}")
            continue
        paper = db.get(Paper, attempt.paper_id)
        if paper is None:
            # 卷没了就直接标过期，别把 attempt 永远挂在 ongoing。
            attempt.status, attempt.submitted_at, attempt.submit_kind = "expired", now, "auto_close"
            continue
        _seal(db, attempt, paper, "auto_close")
    if not dry_run:
        db.commit()
    return sealed


def main() -> None:
    parser = argparse.ArgumentParser(description="封存已超时的考试作答并判分。")
    parser.add_argument("--dry-run", action="store_true", help="只列出将被收掉的作答，不写库")
    args = parser.parse_args()

    settings = get_settings()
    engine, factory = build_database(settings.database_url)
    db = factory()
    try:
        sealed = seal_expired(db, dry_run=args.dry_run)
    finally:
        db.close()
        engine.dispose()
    prefix = "将收掉" if args.dry_run else "已收掉"
    print(f"{prefix} {sealed} 条超时作答。")


if __name__ == "__main__":
    main()
