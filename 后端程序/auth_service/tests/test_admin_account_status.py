"""管理端账号启用/停用：授权、守卫、会话吊销与审计。

判据来源：《41、管理端账号管理范围裁决》§2 与 §7。
公共字段契约沿用《37、审计事件字段规范》，本文件不重复其通用断言。

审计断言一律在新开的数据库会话里查，确认失败审计真的落了库。
"""
import json

from sqlalchemy import select

from app.models import AdminSession, AdminUser, AuditEvent
from app.security import password_hash

from test_admin_auth import ADMIN_PASSWORD, admin_client, admin_csrf_headers, admin_login
from test_admin_role_change import (
    OTHER_PASSWORD,
    current_role,
    login_as,
    login_root,
    put_role,
    restore_cookies,
    seed_admin,
)


def put_status(client, headers, admin_user_id: int, status: str):
    return client.put(
        f"/api/admin/admin-users/{admin_user_id}/status",
        headers=headers,
        json={"status": status},
    )


def status_events(client, outcome: str | None = None):
    db = client.app.state.session_factory()
    try:
        query = select(AuditEvent).where(
            AuditEvent.event_type == "admin_account_status_change"
        )
        if outcome is not None:
            query = query.where(AuditEvent.outcome == outcome)
        return list(db.scalars(query.order_by(AuditEvent.id)))
    finally:
        db.close()


def current_status(client, admin_user_id: int) -> str:
    db = client.app.state.session_factory()
    try:
        return db.get(AdminUser, admin_user_id).status
    finally:
        db.close()


def live_sessions(client, admin_user_id: int) -> int:
    db = client.app.state.session_factory()
    try:
        return len(
            list(
                db.scalars(
                    select(AdminSession).where(
                        AdminSession.admin_user_id == admin_user_id,
                        AdminSession.revoked_at.is_(None),
                    )
                )
            )
        )
    finally:
        db.close()


# ==================== 授权 ====================


def test_non_super_admin_cannot_change_status_and_failure_is_audited(tmp_path):
    with admin_client(tmp_path) as client:
        actor_id = seed_admin(client, "editor-s1", "editor")
        target_id = seed_admin(client, "target-s1", "teacher")
        headers = login_as(client, "editor-s1")

        response = put_status(client, headers, target_id, "disabled")

        assert response.status_code == 403
        assert current_status(client, target_id) == "active"

        events = status_events(client)
        assert len(events) == 1
        event = events[0]
        assert event.outcome == "failure"
        assert event.admin_user_id == actor_id
        assert event.resource_type == "admin_user"
        assert event.resource_id == target_id
        assert event.user_id is None
        summary = json.loads(event.summary_json)
        assert summary["schema_version"] == 1
        assert summary["reason_code"] == "forbidden"
        assert summary["old_status"] == "active"
        assert summary["new_status"] == "disabled"


def test_status_change_requires_csrf(tmp_path):
    with admin_client(tmp_path) as client:
        target_id = seed_admin(client, "target-s2", "editor")
        login_root(client)
        response = client.put(
            f"/api/admin/admin-users/{target_id}/status", json={"status": "disabled"}
        )
        assert response.status_code == 403
        assert current_status(client, target_id) == "active"


def test_unknown_status_value_is_rejected_by_the_schema(tmp_path):
    """状态是闭集，非法值在入参层就被挡掉（§2.1）。"""
    with admin_client(tmp_path) as client:
        target_id = seed_admin(client, "target-s3", "editor")
        headers = login_root(client)
        assert put_status(client, headers, target_id, "archived").status_code == 422
        assert current_status(client, target_id) == "active"


def test_unknown_target_is_audited_as_not_found(tmp_path):
    with admin_client(tmp_path) as client:
        headers = login_root(client)
        assert put_status(client, headers, 9999, "disabled").status_code == 404
        events = status_events(client)
        assert len(events) == 1
        assert json.loads(events[0].summary_json)["reason_code"] == "not_found"


def test_same_status_is_a_conflict(tmp_path):
    with admin_client(tmp_path) as client:
        target_id = seed_admin(client, "target-s4", "editor")
        headers = login_root(client)
        assert put_status(client, headers, target_id, "active").status_code == 409
        assert status_events(client, "success") == []
        assert json.loads(status_events(client, "failure")[0].summary_json)["reason_code"] == "conflict"


# ==================== 停用的实际效果 ====================


def test_disabling_locks_the_account_out_immediately_and_revokes_sessions(tmp_path):
    with admin_client(tmp_path) as client:
        target_id = seed_admin(client, "victim", "editor")

        # 目标先建立自己的会话。
        login_as(client, "victim")
        assert client.get("/api/admin/me").status_code == 200
        assert live_sessions(client, target_id) == 1
        victim_cookies = dict(client.cookies)

        headers = login_root(client)
        assert put_status(client, headers, target_id, "disabled").status_code == 200

        assert current_status(client, target_id) == "disabled"
        # 会话被显式吊销，且旧 token 立刻失效。
        assert live_sessions(client, target_id) == 0
        restore_cookies(client, victim_cookies)
        assert client.get("/api/admin/me").status_code == 401


def test_disabled_account_cannot_log_in(tmp_path):
    with admin_client(tmp_path) as client:
        target_id = seed_admin(client, "blocked", "editor")
        headers = login_root(client)
        assert put_status(client, headers, target_id, "disabled").status_code == 200

        client.cookies.clear()
        headers = admin_csrf_headers(client)
        response = admin_login(client, headers, password=OTHER_PASSWORD, username="blocked")
        assert response.status_code == 401


def test_disabling_preserves_history_and_audit(tmp_path):
    """§2.4：停用只改一列，历史数据与审计一条都不能少。"""
    with admin_client(tmp_path) as client:
        target_id = seed_admin(client, "keeper", "editor")
        headers = login_root(client)
        # 先制造一条以该账号为资源的审计记录。
        assert put_role(client, headers, target_id, "teacher").status_code == 200

        def rows_about_target():
            db = client.app.state.session_factory()
            try:
                return len(
                    list(
                        db.scalars(
                            select(AuditEvent).where(
                                AuditEvent.resource_type == "admin_user",
                                AuditEvent.resource_id == target_id,
                            )
                        )
                    )
                )
            finally:
                db.close()

        before = rows_about_target()
        assert put_status(client, headers, target_id, "disabled").status_code == 200
        # 停用只会新增审计，绝不减少；账号行本身也还在。
        assert rows_about_target() == before + 1
        assert current_role(client, target_id) == "teacher"


def test_disabled_account_can_be_re_enabled(tmp_path):
    with admin_client(tmp_path) as client:
        target_id = seed_admin(client, "returning", "editor")
        headers = login_root(client)

        assert put_status(client, headers, target_id, "disabled").status_code == 200
        assert put_status(client, headers, target_id, "active").status_code == 200
        assert current_status(client, target_id) == "active"

        # 重新启用后可以正常登录。
        client.cookies.clear()
        csrf = admin_csrf_headers(client)
        assert admin_login(
            client, csrf, password=OTHER_PASSWORD, username="returning"
        ).status_code == 200


def test_successful_status_change_writes_full_audit(tmp_path):
    with admin_client(tmp_path) as client:
        target_id = seed_admin(client, "target-s5", "editor", display_name="李老师")
        headers = login_root(client)
        root_id = client.get("/api/admin/me").json()["id"]

        response = put_status(client, headers, target_id, "disabled")

        assert response.status_code == 200
        assert response.json()["status"] == "disabled"

        events = status_events(client, "success")
        assert len(events) == 1
        event = events[0]
        assert event.admin_user_id == root_id
        assert event.resource_id == target_id
        assert event.user_id is None
        raw = event.summary_json
        assert json.loads(raw) == {
            "schema_version": 1,
            "old_status": "active",
            "new_status": "disabled",
        }
        # 规范 §5：姓名与用户名不得进摘要。
        assert "李老师" not in raw
        assert "target-s5" not in raw


# ==================== 最后一名超管守卫（与降级同源） ====================


def test_last_active_super_admin_cannot_be_disabled(tmp_path):
    with admin_client(tmp_path) as client:
        headers = login_root(client)
        root_id = client.get("/api/admin/me").json()["id"]

        response = put_status(client, headers, root_id, "disabled")

        assert response.status_code == 409
        assert response.json()["detail"] == "系统必须至少保留一名启用状态的超级管理员。"
        assert current_status(client, root_id) == "active"
        assert status_events(client, "success") == []
        summary = json.loads(status_events(client, "failure")[0].summary_json)
        assert summary["reason_code"] == "invalid_state"


def test_a_disabled_super_does_not_keep_the_last_active_super_disableable(tmp_path):
    """停用的超管不算兜底——两条路都得按 active 计数。"""
    with admin_client(tmp_path) as client:
        spare_id = seed_admin(client, "spare", "super_admin")
        headers = login_root(client)
        root_id = client.get("/api/admin/me").json()["id"]

        assert put_status(client, headers, spare_id, "disabled").status_code == 200
        # 备用超管已停用，root 就成了最后一个活跃超管。
        assert put_status(client, headers, root_id, "disabled").status_code == 409
        assert current_status(client, root_id) == "active"


def test_disabling_a_super_is_allowed_while_another_active_super_remains(tmp_path):
    with admin_client(tmp_path) as client:
        other_id = seed_admin(client, "co-super", "super_admin")
        headers = login_root(client)
        assert put_status(client, headers, other_id, "disabled").status_code == 200
        assert current_status(client, other_id) == "disabled"


def test_role_change_and_status_change_agree_on_the_last_super(tmp_path):
    """§7.5：两条路必须共用同一份计数，行为不能分叉。"""
    with admin_client(tmp_path) as client:
        headers = login_root(client)
        root_id = client.get("/api/admin/me").json()["id"]

        # 唯一的活跃超管：降级和停用都必须被拦。
        assert put_role(client, headers, root_id, "editor").status_code == 409
        assert put_status(client, headers, root_id, "disabled").status_code == 409

        # 补一个活跃超管后，两条路都应放行。
        successor_id = seed_admin(client, "successor-s", "super_admin")
        assert put_status(client, headers, successor_id, "active").status_code == 409  # 本来就是 active
        assert put_role(client, headers, root_id, "editor").status_code == 200

        # root 已不是超管，改用接班人继续操作。
        client.cookies.clear()
        headers = login_as(client, "successor-s")
        assert put_status(client, headers, successor_id, "disabled").status_code == 409
