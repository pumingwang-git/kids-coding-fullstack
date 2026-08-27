import json

from sqlalchemy import select
from test_admin_auth import ADMIN_PASSWORD, admin_client, admin_csrf_headers, admin_login
from test_admin_role_change import OTHER_PASSWORD, login_as, seed_admin

from app.models import AdminSession, AdminUser, AuditEvent
from app.security import password_hash


def _headers(client):
    return {"X-CSRF-Token": client.cookies.get("admin_csrf_token")}


def _events(client, event_type):
    db = client.app.state.session_factory()
    try:
        return list(db.scalars(select(AuditEvent).where(AuditEvent.event_type == event_type)))
    finally:
        db.close()


def test_super_admin_creates_account_with_one_time_password_and_assignable_role(tmp_path):
    with admin_client(tmp_path) as client:
        headers = admin_csrf_headers(client)
        assert admin_login(client, headers).status_code == 200
        headers = _headers(client)

        response = client.post(
            "/api/admin/admin-users",
            headers=headers,
            json={"username": "new-teacher", "display_name": "新教师", "role": "teacher"},
        )
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["must_change_password"] is True
        assert body["initial_password"]

        db = client.app.state.session_factory()
        try:
            row = db.get(AdminUser, body["id"])
            assert row.must_change_password is True
            assert password_hash.verify(body["initial_password"], row.password_hash)
        finally:
            db.close()

        event = _events(client, "admin_account_create")[0]
        assert event.resource_id == body["id"]
        assert "password" not in (event.summary_json or "").lower()
        assert json.loads(event.summary_json) == {
            "new_role": "teacher", "new_status": "active", "schema_version": 1,
        }


def test_create_rejects_legacy_role_and_non_super(tmp_path):
    with admin_client(tmp_path) as client:
        editor_id = seed_admin(client, "editor-create", "editor")
        headers = login_as(client, "editor-create")
        forbidden = client.post(
            "/api/admin/admin-users", headers=headers,
            json={"username": "blocked-user", "display_name": "Blocked", "role": "teacher"},
        )
        assert forbidden.status_code == 403
        assert _events(client, "admin_account_create")[-1].admin_user_id == editor_id

        headers = login_as(client, "root", ADMIN_PASSWORD)
        legacy = client.post(
            "/api/admin/admin-users", headers=headers,
            json={"username": "legacy-user", "display_name": "Legacy", "role": "admin"},
        )
        assert legacy.status_code == 422


def test_forced_password_change_blocks_business_routes_then_unlocks_account(tmp_path):
    with admin_client(tmp_path) as client:
        target_id = seed_admin(client, "forced-user", "teacher")
        db = client.app.state.session_factory()
        try:
            target = db.get(AdminUser, target_id)
            target.must_change_password = True
            db.commit()
        finally:
            db.close()

        headers = login_as(client, "forced-user")
        me = client.get("/api/admin/me")
        assert me.status_code == 200
        assert me.json()["must_change_password"] is True
        blocked = client.get("/api/admin/students")
        assert blocked.status_code == 403
        assert blocked.json()["detail"] == "password_change_required"

        changed = client.put(
            "/api/admin/password-change", headers=headers,
            json={"current_password": OTHER_PASSWORD, "new_password": "Fresh-admin-pass-456!"},
        )
        assert changed.status_code == 204, changed.text
        assert client.get("/api/admin/me").json()["must_change_password"] is False
        assert client.get("/api/admin/students").status_code == 200
        assert len(_events(client, "admin_account_password_change")) == 1


def test_password_reset_returns_once_revokes_sessions_and_requires_change(tmp_path):
    with admin_client(tmp_path) as client:
        target_id = seed_admin(client, "reset-user", "teacher")
        login_as(client, "reset-user")
        assert client.get("/api/admin/me").status_code == 200

        root_headers = login_as(client, "root", ADMIN_PASSWORD)
        response = client.post(
            f"/api/admin/admin-users/{target_id}/password-reset", headers=root_headers,
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["initial_password"]
        assert body["must_change_password"] is True

        db = client.app.state.session_factory()
        try:
            sessions = list(db.scalars(select(AdminSession).where(AdminSession.admin_user_id == target_id)))
            assert sessions and all(session.revoked_at is not None for session in sessions)
            assert all(session.revocation_reason == "password_reset" for session in sessions)
        finally:
            db.close()

        client.cookies.clear()
        headers = admin_csrf_headers(client)
        assert admin_login(
            client, headers, username="reset-user", password=body["initial_password"],
        ).status_code == 200
        assert client.get("/api/admin/me").json()["must_change_password"] is True
        assert len(_events(client, "admin_account_password_reset")) == 1
