"""E7 T1/T2 contract guards."""

import ast
import json
from pathlib import Path

from sqlalchemy import select

from app.audit_summary import diff_summary
from app.audit_summary import EVENT_CATEGORY, RETENTION_DAYS
from app.models import AuditEvent
from test_admin_auth import ADMIN_PASSWORD, admin_client, admin_csrf_headers, admin_login
from test_admin_classes import seed_course
from test_exam import admin_login as root_login, build_app
from test_admin_role_change import login_as, seed_admin

APP = Path(__file__).resolve().parents[1] / "app"


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


def test_every_literal_router_audit_event_has_a_retention_category():
    events = set()
    for path in (APP / "routers").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or getattr(node.func, "id", None) != "audit":
                continue
            if len(node.args) >= 3 and isinstance(node.args[2], ast.Constant):
                events.add(node.args[2].value)
    assert events <= EVENT_CATEGORY.keys()
    assert set(EVENT_CATEGORY.values()) <= RETENTION_DAYS.keys()


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
