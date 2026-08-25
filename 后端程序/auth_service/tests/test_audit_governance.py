"""E7 T1/T2 contract guards."""

import ast
import json
import logging
from pathlib import Path

import pytest
from sqlalchemy import select

from app.audit_summary import diff_summary
from app.audit_summary import EVENT_CATEGORY, RETENTION_DAYS, ensure_known_event_type, CATEGORY_GRADE
from app.models import AuditEvent
from test_admin_auth import ADMIN_PASSWORD, admin_client, admin_csrf_headers, admin_login
from test_admin_classes import seed_course
from test_exam import admin_login as root_login, build_app
from test_admin_role_change import login_as, seed_admin

APP = Path(__file__).resolve().parents[1] / "app"
HISTORICAL_EVENT_TYPES = {
    "admin_problem_clone", "admin_problem_offline",
    "exam_judge_failed",
}
NON_ROUTER_EVENT_TYPES = {"audit_retention_purge"}


def test_diff_summary_is_allowlisted_versioned_and_redacted():
    result = diff_summary(
        {"title": "old", "email": "secret@example.test", "updated_at": None},
        {"title": "new", "email": "other@example.test", "updated_at": None},
        ("title", "email", "updated_at"),
    )
    assert result == {"schema_version": 1, "changed": {"title": {"old": "old", "new": "new"}}}


def test_diff_summary_keeps_noop_event_as_empty_changed():
    assert diff_summary({"status": "active"}, {"status": "active"}, ("status",)) == {
        "schema_version": 1, "changed": {}
    }


def test_diff_summary_is_bounded_and_stable():
    result = diff_summary({}, {"z": "x" * 3000, "a": "y" * 3000}, ("z", "a"))
    encoded = json.dumps(result, ensure_ascii=False).encode("utf-8")
    assert len(encoded) <= 4096
    assert result["schema_version"] == 1
    assert result["truncated"] is True


def test_audit_event_has_no_delete_or_update_mutation_in_app():
    for path in APP.rglob("*.py"):
        source = path.read_text(encoding="utf-8-sig")
        tree = ast.parse(source)
        assert "DELETE /api/admin/audit/events" not in source
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                for decorator in node.decorator_list:
                    if isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute):
                        assert not (decorator.func.attr == "delete" and decorator.args and
                                    isinstance(decorator.args[0], ast.Constant) and
                                    "/events" in str(decorator.args[0].value))
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr == "delete" and node.args:
                    assert not (isinstance(node.args[0], ast.Name) and node.args[0].id == "AuditEvent")
                if node.func.attr == "update" and node.args:
                    assert not (isinstance(node.args[0], ast.Name) and node.args[0].id == "AuditEvent")


def test_every_audit_event_constructor_is_guarded():
    constructors = []
    for path in APP.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        if path.name == "models.py":
            continue
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id == "AuditEvent"):
                continue
            owner = next((candidate for candidate in ast.walk(tree)
                          if isinstance(candidate, (ast.FunctionDef, ast.AsyncFunctionDef))
                          and candidate.lineno <= node.lineno <= getattr(candidate, "end_lineno", node.lineno)), None)
            constructors.append((path, node, owner))
    # 四条写入路径：admin_auth.audit / auth_secure.audit / exam._audit /
    # purge_audit_events。钉死数量是绊线——新增第五条必须在这里显式承认，
    # 不许改成 >= 把提醒关掉（N7 同类教训）。
    assert len(constructors) == 4
    assert all(owner and any(isinstance(call, ast.Name) and call.id == "ensure_known_event_type"
                             for call in ast.walk(owner))
               for _, _, owner in constructors)


# 动态事件名里允许出现的变量及其**全部**取值。新变量必须先登记，否则
# _expand_event_name() 直接报错——不允许静默漏掉一个事件名（N7）。
DYNAMIC_EVENT_VALUES = {
    "kind": {"starter", "demo"},
    "action": {"submit", "approve", "reject"},
}


def _expand_event_name(node: ast.JoinedStr, path: Path) -> set[str]:
    """按插值的真实位置逐段展开 f-string 事件名。

    旧实现有两个坑，都是 N7 暴露的：
    1. 它把取值恒定拼到首个字面量后面，不看插值位置——`f"{kind}_challenge"`
       会被算成 `_challengestarter` 这种不存在的名字，反而假性满足守卫；
    2. 展不开就返回空集，静默放行。于是缺漏不在守卫处红，而是等运行时断言
       在毫不相干的业务测试里炸（N5 就是这么漏出去的）。
    """
    segments: list[set[str]] = []
    for value in node.values:
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            segments.append({value.value})
        elif isinstance(value, ast.FormattedValue) and isinstance(value.value, ast.Name):
            name = value.value.id
            choices = DYNAMIC_EVENT_VALUES.get(name)
            assert choices, (
                f"{path.name}:{node.lineno} 的审计事件名插了未登记的变量 {name!r}；"
                "请把它的全部取值登记进 DYNAMIC_EVENT_VALUES，或改用字面量事件名。"
            )
            segments.append(set(choices))
        else:
            raise AssertionError(
                f"{path.name}:{node.lineno} 的审计事件名含无法静态展开的表达式；"
                "事件名必须是字面量，或仅由字面量与已登记变量拼接。"
            )
    names = {""}
    for segment in segments:
        names = {prefix + choice for prefix in names for choice in segment}
    return names


def _literal_audit_event_types() -> set[str]:
    events = set()
    for path in (APP / "routers").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
                continue
            event_positions = {"audit": 2, "_audit": 2, "_audit_success": 2,
                               "_audit_admin_user_event": 2, "_audit_paper": 2,
                               "_audit_problem": 2}
            event_position = event_positions.get(node.func.id)
            if event_position is None or len(node.args) <= event_position:
                continue
            event = node.args[event_position]
            prefix = "" if path.name in ("auth_secure.py", "exam.py") else "admin_"
            if isinstance(event, ast.Constant) and isinstance(event.value, str):
                events.add(f"{prefix}{event.value}")
            elif isinstance(event, ast.JoinedStr):
                events.update(f"{prefix}{name}" for name in _expand_event_name(event, path))
    return events


def test_every_literal_router_audit_event_has_a_retention_category():
    events = _literal_audit_event_types()
    assert events <= EVENT_CATEGORY.keys()
    assert set(EVENT_CATEGORY.values()) <= RETENTION_DAYS.keys()
    assert (set(EVENT_CATEGORY) - HISTORICAL_EVENT_TYPES - NON_ROUTER_EVENT_TYPES) <= events


def test_exam_events_are_grade_retained():
    assert EVENT_CATEGORY["exam_start"] == CATEGORY_GRADE
    assert EVENT_CATEGORY["exam_entry_denied"] == CATEGORY_GRADE
    assert EVENT_CATEGORY["exam_submit"] == CATEGORY_GRADE


def test_runtime_audit_category_guard_raises_outside_production_and_warns_in_production(caplog):
    with pytest.raises(AssertionError, match="未归类的审计 event_type：admin_unknown"):
        ensure_known_event_type("admin_unknown", "test")
    with caplog.at_level(logging.WARNING):
        ensure_known_event_type("admin_unknown", "production")
    assert "admin_unknown" in caplog.text


def test_export_download_uses_five_year_authorization_retention():
    assert EVENT_CATEGORY["admin_export_download"] == "authz"
    assert RETENTION_DAYS[EVENT_CATEGORY["admin_export_download"]] == 5 * 365


def test_reviewer_keeps_existing_resource_audit_access(tmp_path):
    with admin_client(tmp_path) as client:
        seed_admin(client, "audit-reviewer", "reviewer")
        login_as(client, "audit-reviewer")
        assert client.get("/api/admin/papers/999/audit").status_code == 200
        assert client.get("/api/admin/problems/999/audit").status_code == 200


def test_export_download_is_audited(tmp_path):
    with admin_client(tmp_path) as client:
        headers = admin_csrf_headers(client)
        assert admin_login(client, headers).status_code == 200
        response = client.get("/api/admin/classes/export")
        assert response.status_code == 200
        db = client.app.state.session_factory()
        try:
            event = db.scalar(select(AuditEvent).where(AuditEvent.event_type == "admin_export_download"))
            assert event is not None and event.outcome == "success"
            assert json.loads(event.summary_json)["export_type"] == "class_relationships"
        finally:
            db.close()


def test_teaching_export_download_is_audited(tmp_path):
    app = build_app(tmp_path)
    client, headers = root_login(app)
    class_id = client.post("/api/admin/classes", headers=headers, json={
        "name": "审计导出班", "course_id": seed_course(app),
    }).json()["id"]
    response = client.get(f"/api/admin/teaching/classes/{class_id}/export", headers=headers)
    assert response.status_code == 200
    db = app.state.session_factory()
    try:
        event = db.scalar(select(AuditEvent).where(
            AuditEvent.event_type == "admin_export_download",
            AuditEvent.resource_type == "class_insight_export",
            AuditEvent.resource_id == class_id,
        ))
        assert event is not None
        assert json.loads(event.summary_json)["export_type"] == "class_insight"
    finally:
        db.close()


def test_global_audit_is_super_only_and_caps_page_size(tmp_path):
    with admin_client(tmp_path) as client:
        editor_id = seed_admin(client, "audit-editor", "editor")
        seed_admin(client, "audit-teacher", "teacher")
        headers = admin_csrf_headers(client)
        assert admin_login(client, headers).status_code == 200
        response = client.get("/api/admin/audit/events", params={"page_size": 100000})
        assert response.status_code == 200
        assert response.json()["page_size"] == 100
        client.post("/api/admin/logout", headers={"X-CSRF-Token": client.cookies.get("admin_csrf_token")})
        login_as(client, "audit-editor")
        denied = client.get("/api/admin/audit/events")
        assert denied.status_code == 403
        db = client.app.state.session_factory()
        try:
            rows = list(db.execute(__import__("sqlalchemy").text(
                "select event_type, outcome, admin_user_id from audit_events where event_type='admin_audit_events_read'"
            )))
            assert rows and rows[-1][1] == "failure" and rows[-1][2] == editor_id
        finally:
            db.close()
        client.post("/api/admin/logout", headers={"X-CSRF-Token": client.cookies.get("admin_csrf_token")})
        login_as(client, "audit-teacher")
        assert client.get("/api/admin/audit/events").status_code == 403
