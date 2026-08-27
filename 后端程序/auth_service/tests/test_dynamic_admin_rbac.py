"""Database-managed RBAC policies, concurrency and protected-role invariants."""

from sqlalchemy import select
from sqlalchemy.dialects import postgresql
from test_admin_auth import admin_client
from test_admin_role_change import login_as, login_root, seed_admin

from app.models import AdminUser, AuditEvent
from app.permissions import assignable_role
from app.routers import admin_auth


def _create_role(client, headers, **overrides):
    payload = {
        "key": "course_operator",
        "label": "课包运营",
        "description": "维护课包内容",
        "scope": "none",
        "capabilities": ["content_edit"],
    }
    payload.update(overrides)
    return client.post("/api/admin/roles", headers=headers, json=payload)


def _replace_role(client, headers, role, **overrides):
    payload = {
        "key": role["value"],
        "label": role["label"],
        "description": role["description"],
        "scope": role["scope"],
        "capabilities": [
            key for key, enabled in role["capabilities"].items() if enabled
        ],
    }
    payload.update(overrides)
    return client.put(
        f"/api/admin/roles/{role['value']}",
        headers={**headers, "If-Match": str(role["revision"])},
        json=payload,
    )


def _role(client, key):
    return next(item for item in client.get("/api/admin/roles").json()["items"] if item["value"] == key)


def test_assignable_role_write_query_uses_postgres_row_lock():
    class CapturingDb:
        statement = None

        def scalar(self, statement):
            self.statement = statement
            return None

    db = CapturingDb()
    assert assignable_role(db, "teacher", for_update=True) is None
    sql = str(db.statement.compile(dialect=postgresql.dialect()))
    assert sql.rstrip().endswith("FOR UPDATE")


def test_account_write_paths_lock_role_before_assigning(tmp_path, monkeypatch):
    calls = []
    original = admin_auth.assignable_role

    def tracking_assignable_role(db, role_key, *, for_update=False):
        calls.append((role_key, for_update))
        return original(db, role_key, for_update=for_update)

    monkeypatch.setattr(admin_auth, "assignable_role", tracking_assignable_role)
    with admin_client(tmp_path) as client:
        headers = login_root(client)
        role = _create_role(client, headers).json()

        created = client.post(
            "/api/admin/admin-users",
            headers=headers,
            json={
                "username": "locked-role-create",
                "display_name": "Locked role create",
                "role": role["value"],
            },
        )
        assert created.status_code == 201, created.text

        target_id = seed_admin(client, "locked-role-assign", "editor")
        changed = client.put(
            f"/api/admin/admin-users/{target_id}/role",
            headers={**headers, "If-Match": "1"},
            json={"role": role["value"]},
        )
        assert changed.status_code == 200, changed.text

    assert calls == [(role["value"], True), (role["value"], True)]


def test_retired_role_cannot_be_assigned_to_new_or_existing_account(tmp_path):
    with admin_client(tmp_path) as client:
        headers = login_root(client)
        role = _create_role(client, headers).json()
        retired = client.delete(
            f"/api/admin/roles/{role['value']}",
            headers={**headers, "If-Match": str(role["revision"])},
        )
        assert retired.status_code == 204

        created = client.post(
            "/api/admin/admin-users",
            headers=headers,
            json={
                "username": "retired-role-create",
                "display_name": "Retired role create",
                "role": role["value"],
            },
        )
        assert created.status_code == 422

        target_id = seed_admin(client, "retired-role-assign", "editor")
        changed = client.put(
            f"/api/admin/admin-users/{target_id}/role",
            headers={**headers, "If-Match": "1"},
            json={"role": role["value"]},
        )
        assert changed.status_code == 422


def test_custom_role_capability_is_effective_and_revoked_on_next_request(tmp_path):
    with admin_client(tmp_path) as client:
        root_headers = login_root(client)
        created = _create_role(client, root_headers)
        assert created.status_code == 201, created.text
        role = created.json()
        assert role["capabilities"]["content_edit"] is True
        assert "courses.html" in role["allowed_pages"]

        seed_admin(client, "course-operator", role["value"])
        headers = login_as(client, "course-operator")
        allowed = client.post(
            "/api/admin/course-categories",
            headers=headers,
            json={"name": "动态角色分类", "sort_order": 1},
        )
        assert allowed.status_code == 201, allowed.text
        target_cookies = dict(client.cookies)

        root_headers = login_root(client)
        updated = _replace_role(client, root_headers, role, capabilities=[])
        assert updated.status_code == 200, updated.text
        assert updated.json()["revision"] == 2
        assert "courses.html" not in updated.json()["allowed_pages"]

        client.cookies.clear()
        for key, value in target_cookies.items():
            client.cookies.set(key, value)
        headers = {"X-CSRF-Token": client.cookies.get("admin_csrf_token")}
        denied = client.post(
            "/api/admin/course-categories",
            headers=headers,
            json={"name": "不应创建", "sort_order": 2},
        )
        assert denied.status_code == 403


def test_custom_role_with_audit_capability_can_read_global_audit(tmp_path):
    with admin_client(tmp_path) as client:
        root_headers = login_root(client)
        role = _create_role(
            client,
            root_headers,
            key="audit_reader",
            label="审计查看员",
            description="查看全局审计事件",
            capabilities=["audit_events_read"],
        ).json()
        seed_admin(client, "audit-reader", role["value"])

        login_as(client, "audit-reader")
        response = client.get("/api/admin/audit/events")

        assert response.status_code == 200, response.text
        assert "audit-logs.html" in client.get("/api/admin/me").json()["allowed_pages"]


def test_role_policy_requires_current_revision_and_protects_system_roles(tmp_path):
    with admin_client(tmp_path) as client:
        headers = login_root(client)
        role = _create_role(client, headers).json()

        missing = client.put(
            f"/api/admin/roles/{role['value']}",
            headers=headers,
            json={
                "key": role["value"], "label": role["label"], "description": "",
                "scope": "none", "capabilities": [],
            },
        )
        assert missing.status_code == 428

        assert _replace_role(client, headers, role, label="课包管理员").status_code == 200
        stale = _replace_role(client, headers, role, label="旧页面覆盖")
        assert stale.status_code == 409
        assert stale.json()["detail"]["current_revision"] == 2

        protected = _role(client, "super_admin")
        assert _replace_role(client, headers, protected, capabilities=[]).status_code == 409


def test_role_key_is_never_reused_and_in_use_role_cannot_be_retired(tmp_path):
    with admin_client(tmp_path) as client:
        headers = login_root(client)
        role = _create_role(client, headers).json()
        seed_admin(client, "uses-custom-role", role["value"])

        in_use = client.delete(
            f"/api/admin/roles/{role['value']}",
            headers={**headers, "If-Match": str(role["revision"])},
        )
        assert in_use.status_code == 409

        db = client.app.state.session_factory()
        try:
            db.get(AdminUser, 2).role = "editor"
            db.commit()
        finally:
            db.close()
        retired = client.delete(
            f"/api/admin/roles/{role['value']}",
            headers={**headers, "If-Match": str(role["revision"])},
        )
        assert retired.status_code == 204
        duplicate = _create_role(client, headers)
        assert duplicate.status_code == 409


def test_account_role_assignment_uses_revision_and_dynamic_catalog(tmp_path):
    with admin_client(tmp_path) as client:
        headers = login_root(client)
        role = _create_role(client, headers).json()
        target_id = seed_admin(client, "assignment-target", "editor")

        changed = client.put(
            f"/api/admin/admin-users/{target_id}/role",
            headers={**headers, "If-Match": "1"},
            json={"role": role["value"]},
        )
        assert changed.status_code == 200, changed.text
        assert changed.json()["role"] == role["value"]
        assert changed.json()["role_revision"] == 2

        stale = client.put(
            f"/api/admin/admin-users/{target_id}/role",
            headers={**headers, "If-Match": "1"},
            json={"role": "teacher"},
        )
        assert stale.status_code == 409
        assert stale.json()["detail"]["current_revision"] == 2


def test_role_policy_changes_write_redacted_audit_events(tmp_path):
    with admin_client(tmp_path) as client:
        headers = login_root(client)
        role = _create_role(client, headers).json()
        assert _replace_role(client, headers, role, capabilities=[]).status_code == 200
        role = _role(client, role["value"])
        assert client.delete(
            f"/api/admin/roles/{role['value']}",
            headers={**headers, "If-Match": str(role["revision"])},
        ).status_code == 204

        db = client.app.state.session_factory()
        try:
            events = list(db.scalars(select(AuditEvent).where(
                AuditEvent.event_type.in_({
                    "admin_role_create", "admin_role_update", "admin_role_delete",
                })
            ).order_by(AuditEvent.id)))
        finally:
            db.close()
        assert [event.event_type for event in events] == [
            "admin_role_create", "admin_role_update", "admin_role_delete",
        ]
        assert all("password" not in (event.summary_json or "").lower() for event in events)
