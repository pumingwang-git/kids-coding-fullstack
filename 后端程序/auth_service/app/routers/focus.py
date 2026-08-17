"""专注星球：专注段记录、设置、任务清单的学生端接口。

设计见《开发文档/26》§7.5/7.6。与 `scratch_works.py` 同口径的三条红线：

1. **写请求一律学生端 CSRF**（`csrf_token` Cookie + `require_csrf`）。
2. **专注段是 append-only 事件流**：靠 `client_uuid` 幂等，已存在的直接跳过，
   重复提交不产生脏数据（断网补送、双设备并发的安全网）。
3. **配置与任务是当前状态**：`updated_at` 后写覆盖，服务端不做任何业务判定
   （整体 JSON 存，字段只被子应用自己消费）。

统计口径（`/stats`、`/bootstrap.stats`）：
- 今日/本周按 **Asia/Shanghai** 日界切分（产品面向国内学生，UTC 日界会
  把"今天早上 8 点前的专注"算成昨天）；服务端其它时间戳惯例是 UTC，这条
  是本模块的刻意例外，写死 +8 且不带 tzdata 依赖。
- 连续专注天数只统计 `outcome in (completed, aborted)` 的真实在场段；
  `catchup`（客户端补算的历史段）**不计入**，见模型 docstring。
- 统计不建表，实时聚合 `focus_sessions`；一人一天几十条的量级下
  `(student_id, started_at)` 索引足够。

端点：

    GET   /api/focus/bootstrap            设置 + 任务清单 + 今日统计（子应用启动只发这一个）
    POST  /api/focus/sessions             批量提交专注段（幂等）
    GET   /api/focus/stats                ?days=1|7 区间统计
    PUT   /api/focus/settings             整体覆盖配置（≤32KB）
    PUT   /api/focus/tasks                逐条 upsert 任务清单（软删，不删行）
"""
from __future__ import annotations

import json

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import FocusSession, FocusSetting, FocusTask, User
from ..security import as_utc
from .auth_secure import current_user, db_session, limit, require_csrf

router = APIRouter(prefix="/api/focus", tags=["student-focus"])

# 统计日界：Asia/Shanghai（UTC+8，无夏令时）。硬编码，避免 Windows 上 zoneinfo 的 tzdata 依赖。
SHANGHAI_OFFSET = timedelta(hours=8)

SESSION_TYPES = {"work", "shortpause", "longpause"}
OUTCOMES = {"completed", "aborted", "catchup"}
SOURCES = {"toolbox", "lesson"}
SETTINGS_MAX_BYTES = 32 * 1024
SESSIONS_BATCH_MAX = 200
TASKS_BATCH_MAX = 500


# ---------- 请求模型 ----------


class FocusSessionIn(BaseModel):
    client_uuid: str = Field(min_length=8, max_length=36)
    section_type: str
    planned_ms: int = Field(gt=0, le=24 * 60 * 60 * 1000)
    actual_ms: int = Field(ge=0, le=24 * 60 * 60 * 1000)
    started_at: datetime
    ended_at: datetime
    outcome: str = "completed"
    focus_lost_count: int = Field(default=0, ge=0, le=10000)
    source: str = "toolbox"


class SessionsIn(BaseModel):
    items: list[FocusSessionIn] = Field(max_length=SESSIONS_BATCH_MAX)


class SettingsIn(BaseModel):
    payload: dict


class TaskIn(BaseModel):
    client_uuid: str = Field(min_length=1, max_length=36)
    title: str = Field(min_length=1, max_length=200)
    priority: int = Field(default=0, ge=-10, le=10)
    state: int = Field(default=0, ge=0, le=2)
    is_deleted: bool = False
    updated_at: datetime | None = None


class TasksIn(BaseModel):
    items: list[TaskIn] = Field(max_length=TASKS_BATCH_MAX)


# ---------- 公共辅助 ----------


def _session_payload(s: FocusSession) -> dict:
    return {
        "client_uuid": s.client_uuid,
        "section_type": s.section_type,
        "planned_ms": s.planned_ms,
        "actual_ms": s.actual_ms,
        "started_at": as_utc(s.started_at).isoformat(),
        "ended_at": as_utc(s.ended_at).isoformat(),
        "outcome": s.outcome,
        "focus_lost_count": s.focus_lost_count,
        "source": s.source,
    }


def _day_start_shanghai(dt: datetime) -> datetime:
    """把任意时间换算到 Asia/Shanghai 的当日 00:00，再转回 UTC。"""
    sh = dt.astimezone(timezone(SHANGHAI_OFFSET))
    return (sh.replace(hour=0, minute=0, second=0, microsecond=0)
            .astimezone(timezone.utc))


def _streak_days(db: Session, student_id: int, now: datetime) -> int:
    """连续专注天数：从今天（无则从昨天）往回数，每天至少一条真实在场段。

    按 **Asia/Shanghai 日期**分桶（与今日/本周同口径）：把每条真实段的
    started_at 换到上海时区后取 date()。数据量小（一人一天几十条、只扫 400 天），
    直接拉到 Python 分桶，避免 SQLite/Postgres 上 func.date 的时区口径分歧。
    """
    started = db.scalars(
        select(FocusSession.started_at)
        .where(
            FocusSession.student_id == student_id,
            FocusSession.outcome.in_(("completed", "aborted")),
            FocusSession.started_at >= now - timedelta(days=400),
        )
    ).all()
    sh_tz = timezone(SHANGHAI_OFFSET)
    day_set = {as_utc(s).astimezone(sh_tz).date() for s in started}
    streak = 0
    cursor_date = (now.astimezone(sh_tz) - timedelta(days=1)).date()
    if now.astimezone(sh_tz).date() in day_set:
        cursor_date = now.astimezone(sh_tz).date()
    while cursor_date in day_set:
        streak += 1
        cursor_date -= timedelta(days=1)
    return streak


def _stats(db: Session, student_id: int, now: datetime) -> dict:
    """今日/本周专注毫秒（按 Asia/Shanghai 日界）与连续天数。"""
    today_start = _day_start_shanghai(now)
    week_start = _day_start_shanghai(now - timedelta(days=now.weekday()))

    def sum_ms(since: datetime) -> int:
        total = db.scalar(
            select(func.coalesce(func.sum(FocusSession.actual_ms), 0))
            .where(
                FocusSession.student_id == student_id,
                FocusSession.started_at >= since,
                FocusSession.outcome.in_(("completed", "aborted", "catchup")),
            )
        )
        return int(total or 0)

    return {
        "today_ms": sum_ms(today_start),
        "week_ms": sum_ms(week_start),
        "streak_days": _streak_days(db, student_id, now),
    }


def _task_payload(t: FocusTask) -> dict:
    return {
        "client_uuid": t.client_uuid,
        "title": t.title,
        "priority": t.priority,
        "state": t.state,
        "is_deleted": t.is_deleted,
        "updated_at": as_utc(t.updated_at).isoformat() if t.updated_at else None,
    }


# ---------- 端点 ----------


@router.get("/bootstrap")
def bootstrap(request: Request, db: Session = Depends(db_session)):
    """子应用启动只发这一个请求：设置 + 任务清单 + 今日统计。"""
    user = current_user(request, db)
    setting = db.get(FocusSetting, user.id)
    tasks = db.scalars(
        select(FocusTask)
        .where(FocusTask.student_id == user.id)
        .order_by(FocusTask.updated_at.desc())
    ).all()
    return {
        "settings": setting.payload if setting else None,
        "tasks": [_task_payload(t) for t in tasks],
        "stats": _stats(db, user.id, datetime.now(timezone.utc)),
    }


@router.post("/sessions")
def post_sessions(payload: SessionsIn, request: Request, db: Session = Depends(db_session)):
    """批量提交专注段。按 `client_uuid` 幂等：已存在跳过，返回接受/跳过条数。"""
    require_csrf(request)
    user = current_user(request, db)
    limit(request, "focus-write", str(user.id), 120, 60)

    now = datetime.now(timezone.utc)
    items = []
    for item in payload.items:
        if item.section_type not in SESSION_TYPES:
            raise HTTPException(400, f"未知的计时段类型：{item.section_type}")
        if item.outcome not in OUTCOMES:
            raise HTTPException(400, f"未知的 outcome：{item.outcome}")
        if item.source not in SOURCES:
            raise HTTPException(400, f"未知的 source：{item.source}")
        started, ended = as_utc(item.started_at), as_utc(item.ended_at)
        if ended < started:
            raise HTTPException(400, "ended_at 早于 started_at。")
        if started > now + timedelta(minutes=5):
            raise HTTPException(400, "started_at 在将来，时钟不同步？")
        items.append((item, started, ended))

    uuids = [it.client_uuid for it, _, _ in items]
    existing = set(
        db.scalars(
            select(FocusSession.client_uuid).where(FocusSession.client_uuid.in_(uuids))
        ).all()
    )
    accepted = 0
    for item, started, ended in items:
        if item.client_uuid in existing:
            continue
        existing.add(item.client_uuid)  # 本批内去重：同一批出现两次只插一条
        db.add(FocusSession(
            student_id=user.id,
            client_uuid=item.client_uuid,
            section_type=item.section_type,
            planned_ms=item.planned_ms,
            actual_ms=item.actual_ms,
            started_at=started,
            ended_at=ended,
            outcome=item.outcome,
            focus_lost_count=item.focus_lost_count,
            source=item.source,
        ))
        accepted += 1
    db.commit()
    return {"accepted": accepted, "skipped": len(items) - accepted}


@router.get("/stats")
def stats(request: Request, days: int = 7, db: Session = Depends(db_session)):
    """区间统计。`days` 预留：本期固定给今日/本周/连续天数。"""
    if days not in (1, 7, 30):
        raise HTTPException(400, "days 只支持 1 / 7 / 30。")
    user = current_user(request, db)
    return _stats(db, user.id, datetime.now(timezone.utc))


@router.put("/settings")
def put_settings(payload: SettingsIn, request: Request, db: Session = Depends(db_session)):
    """整体覆盖配置。服务端只校验 payload 大小，不做业务判定。"""
    require_csrf(request)
    user = current_user(request, db)
    limit(request, "focus-write", str(user.id), 120, 60)

    raw = json.dumps(payload.payload, ensure_ascii=False)
    if len(raw.encode("utf-8")) > SETTINGS_MAX_BYTES:
        raise HTTPException(400, f"配置超过 {SETTINGS_MAX_BYTES // 1024}KB 上限。")

    setting = db.get(FocusSetting, user.id)
    if setting is None:
        setting = FocusSetting(student_id=user.id, payload=payload.payload)
        db.add(setting)
    else:
        setting.payload = payload.payload
    db.commit()
    return {"ok": True}


@router.put("/tasks")
def put_tasks(payload: TasksIn, request: Request, db: Session = Depends(db_session)):
    """任务清单逐条 upsert（按 client_uuid），软删不删行。

    不做"整表替换"：缺席的行保留（可能是另一台设备的记录），只按行合并，
    天然避免"陈旧设备带着空清单上线把服务端任务全抹掉"。
    """
    require_csrf(request)
    user = current_user(request, db)
    limit(request, "focus-write", str(user.id), 120, 60)

    uuids = [t.client_uuid for t in payload.items]
    existing = {
        t.client_uuid: t
        for t in db.scalars(
            select(FocusTask).where(
                FocusTask.student_id == user.id,
                FocusTask.client_uuid.in_(uuids),
            )
        ).all()
    }
    synced = 0
    for item in payload.items:
        row = existing.get(item.client_uuid)
        if row is None:
            row = FocusTask(student_id=user.id, client_uuid=item.client_uuid)
            db.add(row)
        row.title = item.title.strip() or "未命名任务"
        row.priority = item.priority
        row.state = item.state
        row.is_deleted = item.is_deleted
        if item.updated_at is not None:
            row.updated_at = as_utc(item.updated_at)
        synced += 1
    db.commit()
    return {"synced": synced}
