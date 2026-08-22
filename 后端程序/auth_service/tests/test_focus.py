"""专注星球后端最小回归（2026-08-15，见《开发文档/26》§7.5/7.6）：

只覆盖核心路径 + 本次改动的最小回归：
- bootstrap 空态 / 有数据态
- sessions 批量幂等（断网补送安全网）
- settings 整体覆盖（含大小上限）
- tasks 逐条 upsert + 软删（陈旧设备不抹服务端数据）
- stats 统计口径：今日含 catchup、连续天数只算真实在场段
"""
import tempfile
from pathlib import Path
from datetime import datetime, timedelta, timezone

from test_exam import build_app, student_login, scsrf

FOCUS_ROUTES = ["/api/focus/bootstrap", "/api/focus/sessions",
                "/api/focus/stats", "/api/focus/settings", "/api/focus/tasks"]


def _setup():
    app = build_app(Path(tempfile.mkdtemp()))
    client = student_login(app, username="focuslearner")
    return client


def _session(client_uuid: str, **kw) -> dict:
    base = {
        "client_uuid": client_uuid,
        "section_type": "work",
        "planned_ms": 25 * 60 * 1000,
        "actual_ms": 24 * 60 * 1000,
        "started_at": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
        "ended_at": (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(),
        "outcome": "completed",
        "focus_lost_count": 3,
        "source": "toolbox",
    }
    base.update(kw)
    return base


def test_routes_registered():
    """5 个端点都注册（防止 include_router 漏挂）。"""
    from app.main import app
    schema = app.openapi()
    for route in FOCUS_ROUTES:
        assert route in schema["paths"], f"缺少 {route}"


def test_bootstrap_empty_state():
    client = _setup()
    r = client.get("/api/focus/bootstrap")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["settings"] is None
    assert body["tasks"] == []
    assert body["stats"]["today_ms"] == 0
    assert body["stats"]["streak_days"] == 0


def test_sessions_idempotent():
    client = _setup()
    item = _session("uuid-aaa-111")
    r = client.post("/api/focus/sessions", headers=scsrf(client), json={"items": [item, item]})
    assert r.status_code == 200, r.text
    assert r.json() == {"accepted": 1, "skipped": 1}
    # 断网补送：同一批再发一次，全部跳过
    r = client.post("/api/focus/sessions", headers=scsrf(client), json={"items": [item]})
    assert r.json() == {"accepted": 0, "skipped": 1}
    # 补算段（catchup）也计入今日时长
    r = client.post("/api/focus/sessions", headers=scsrf(client),
                    json={"items": [_session("uuid-bbb-222", outcome="catchup", actual_ms=5 * 60 * 1000)]})
    assert r.json() == {"accepted": 1, "skipped": 0}
    stats = client.get("/api/focus/stats").json()
    assert stats["today_ms"] == (24 + 5) * 60 * 1000, stats


def test_sessions_rejects_bad_payload():
    client = _setup()
    # 未知计时段类型 → 400
    r = client.post("/api/focus/sessions", headers=scsrf(client),
                    json={"items": [_session("uuid-ccc", section_type="naptime")]})
    assert r.status_code == 400
    # ended 早于 started → 400
    r = client.post("/api/focus/sessions", headers=scsrf(client),
                    json={"items": [_session("uuid-ddd", started_at="2026-08-15T10:00:00Z",
                                             ended_at="2026-08-15T09:00:00Z")]})
    assert r.status_code == 400


def test_settings_roundtrip_and_limit():
    client = _setup()
    payload = {"visuals": {"theme": {"work": "ft-work"}}, "schedule": {"lengths": {"work": 900000}}}
    assert client.put("/api/focus/settings", headers=scsrf(client),
                      json={"payload": payload}).status_code == 200
    body = client.get("/api/focus/bootstrap").json()
    assert body["settings"] == payload
    # 超过 32KB → 400
    big = {"blob": "x" * (40 * 1024)}
    assert client.put("/api/focus/settings", headers=scsrf(client),
                      json={"payload": big}).status_code == 400


def test_tasks_upsert_and_soft_delete():
    client = _setup()
    items = [
        {"client_uuid": "t-1", "title": "读英语", "priority": 1, "state": 0, "is_deleted": False},
        {"client_uuid": "t-2", "title": "写作业", "priority": 0, "state": 1, "is_deleted": False},
    ]
    r = client.put("/api/focus/tasks", headers=scsrf(client), json={"items": items})
    assert r.json() == {"synced": 2}
    body = client.get("/api/focus/bootstrap").json()
    assert {t["client_uuid"] for t in body["tasks"]} == {"t-1", "t-2"}
    # 软删 t-1：行保留但 is_deleted=True；缺席的 t-2 不受影响
    r = client.put("/api/focus/tasks", headers=scsrf(client),
                   json={"items": [{"client_uuid": "t-1", "title": "读英语", "is_deleted": True}]})
    assert r.json() == {"synced": 1}
    body = client.get("/api/focus/bootstrap").json()
    by_uuid = {t["client_uuid"]: t for t in body["tasks"]}
    assert by_uuid["t-1"]["is_deleted"] is True
    assert "t-2" in by_uuid, "缺席行应保留（陈旧设备不抹服务端数据）"


def test_stats_streak_only_realtime():
    client = _setup()
    now = datetime.now(timezone.utc)
    # 昨天一条真实段 + 今天一条真实段 + 今天一条 catchup。
    # 使用同一上海自然日内的时间，避免 UTC 凌晨跨过上海日界后夹具漂移。
    days = [
        _session("sess-y1-xxx", started_at=(now - timedelta(days=1, hours=2)).isoformat(),
                 ended_at=(now - timedelta(days=1, hours=1)).isoformat(), actual_ms=10 * 60 * 1000),
        _session("sess-t1-xxx", started_at=(now - timedelta(minutes=30)).isoformat(),
                 ended_at=(now - timedelta(minutes=20)).isoformat(), actual_ms=10 * 60 * 1000),
        _session("sess-t2-xxx", started_at=(now - timedelta(minutes=10)).isoformat(),
                 ended_at=(now - timedelta(minutes=5)).isoformat(),
                 outcome="catchup", actual_ms=10 * 60 * 1000),
    ]
    assert client.post("/api/focus/sessions", headers=scsrf(client), json={"items": days}).status_code == 200
    stats = client.get("/api/focus/stats").json()
    assert stats["today_ms"] == 20 * 60 * 1000, stats  # 今天两条都算
    assert stats["streak_days"] == 2, stats  # 昨天+今天，真实在场
