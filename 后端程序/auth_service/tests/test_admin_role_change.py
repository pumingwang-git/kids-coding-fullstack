"""管理端角色变更接口：授权、非法值、审计与即时生效。

判据来源：
- 《33、E0-ADR-001-身份与权限模型裁决》§2.4：变更 AdminUser.role 仅限 super_admin；
  §6.7 要求非 super_admin 调用返回 403。
- 《37、审计事件字段规范》§3.2 / §4 / §5 / §6：admin_role_change 的字段契约、
  失败审计必须真正落库、敏感信息禁入。

审计断言一律在「新开的数据库会话」里查，避免把请求内未提交的状态当成已持久化。
"""
import json

from sqlalchemy import select

from app.models import AdminUser, AuditEvent
from app.security import hash_ip, password_hash

from test_admin_auth import ADMIN_PASSWORD, admin_client, admin_csrf_headers, admin_login

OTHER_PASSWORD = "Other-pass-123!"


def seed_admin(client, username: str, role: str, display_name: str = "同事") -> int:
    db = client.app.state.session_factory()
    try:
        admin = AdminUser(
            username=username,
            password_hash=password_hash.hash(OTHER_PASSWORD),
            display_name=display_name,
            role=role,
        )
        db.add(admin)
        db.commit()
        return admin.id
    finally:
        db.close()


def login_as(client, username: str, password: str = OTHER_PASSWORD):
    client.cookies.clear()
    headers = admin_csrf_headers(client)
    assert admin_login(client, headers, password=password, username=username).status_code == 200
    return {"X-CSRF-Token": client.cookies.get("admin_csrf_token")}


def login_root(client):
    return login_as(client, "root", ADMIN_PASSWORD)


def put_role(client, headers, admin_user_id: int, role: str):
    return client.put(
        f"/api/admin/admin-users/{admin_user_id}/role",
        headers=headers,
        json={"role": role},
    )


def role_events(client, outcome: str | None = None):
    """在新会话里查 admin_role_change 事件，确认它真的落了库。"""
    db = client.app.state.session_factory()
    try:
        query = select(AuditEvent).where(AuditEvent.event_type == "admin_role_change")
        if outcome is not None:
            query = query.where(AuditEvent.outcome == outcome)
        return list(db.scalars(query.order_by(AuditEvent.id)))
    finally:
        db.close()


def current_role(client, admin_user_id: int) -> str:
    db = client.app.state.session_factory()
    try:
        return db.get(AdminUser, admin_user_id).role
    finally:
        db.close()


def restore_cookies(client, saved):
    """把某条会话的 cookie 换回来，用于在同一个 app 上模拟两个并存的管理员会话。"""
    client.cookies.clear()
    for key, value in saved.items():
        client.cookies.set(key, value)


# ==================== 授权：仅 super_admin ====================


def test_non_super_admin_role_change_returns_403_and_persists_failure_audit(tmp_path):
    """ADR-001 §6.7 + 规范 §4.2：已认证非超管的拒绝必须留下 failure/forbidden。"""
    with admin_client(tmp_path) as client:
        actor_id = seed_admin(client, "editor-1", "editor")
        target_id = seed_admin(client, "target-1", "reviewer")
        headers = login_as(client, "editor-1")

        response = put_role(client, headers, target_id, "teacher")

        assert response.status_code == 403
        assert current_role(client, target_id) == "reviewer"

        events = role_events(client)
        assert len(events) == 1
        event = events[0]
        assert event.outcome == "failure"
        # actor 是发起人、resource 是目标账号，二者不能倒置（规范 §6.2）。
        assert event.admin_user_id == actor_id
        assert event.resource_type == "admin_user"
        assert event.resource_id == target_id
        assert event.user_id is None
        summary = json.loads(event.summary_json)
        assert summary["schema_version"] == 1
        assert summary["reason_code"] == "forbidden"
        assert summary["old_role"] == "reviewer"
        assert summary["new_role"] == "teacher"


def test_every_non_super_role_is_rejected(tmp_path):
    """teacher / assistant / academic_admin / reviewer 都不得改角色。"""
    with admin_client(tmp_path) as client:
        target_id = seed_admin(client, "target-2", "editor")
        roles = ["teacher", "assistant", "academic_admin", "reviewer"]
        for index, role in enumerate(roles):
            username = f"actor-{index}"
            seed_admin(client, username, role)
            headers = login_as(client, username)
            assert put_role(client, headers, target_id, "teacher").status_code == 403

        assert current_role(client, target_id) == "editor"
        assert len(role_events(client, "failure")) == len(roles)


def test_non_super_admin_cannot_list_admin_users(tmp_path):
    with admin_client(tmp_path) as client:
        seed_admin(client, "editor-2", "editor")
        login_as(client, "editor-2")
        assert client.get("/api/admin/admin-users").status_code == 403


def test_role_change_requires_authentication_without_forging_actor(tmp_path):
    """规范 §4.4：未建立可信 actor 的请求不落审计，更不得伪造 admin_user_id。"""
    with admin_client(tmp_path) as client:
        target_id = seed_admin(client, "target-3", "editor")
        headers = admin_csrf_headers(client)
        assert put_role(client, headers, target_id, "teacher").status_code == 401
        assert role_events(client) == []


def test_role_change_requires_csrf(tmp_path):
    with admin_client(tmp_path) as client:
        target_id = seed_admin(client, "target-4", "editor")
        login_root(client)
        response = client.put(
            f"/api/admin/admin-users/{target_id}/role", json={"role": "teacher"}
        )
        assert response.status_code == 403
        assert current_role(client, target_id) == "editor"


# ==================== 非法角色 ====================


def test_invalid_role_is_rejected_and_audited(tmp_path):
    with admin_client(tmp_path) as client:
        target_id = seed_admin(client, "target-5", "editor")
        headers = login_root(client)

        response = put_role(client, headers, target_id, "techer")

        assert response.status_code == 422
        assert "非法管理员角色 'techer'" in response.json()["detail"]
        assert current_role(client, target_id) == "editor"

        events = role_events(client)
        assert len(events) == 1
        summary = json.loads(events[0].summary_json)
        assert events[0].outcome == "failure"
        assert summary["reason_code"] == "invalid_role"
        # 非法值不得作为 new_role 落进审计。
        assert "new_role" not in summary
        assert summary["old_role"] == "editor"


def test_unknown_target_is_audited_as_not_found(tmp_path):
    with admin_client(tmp_path) as client:
        headers = login_root(client)
        assert put_role(client, headers, 9999, "teacher").status_code == 404
        events = role_events(client)
        assert len(events) == 1
        assert json.loads(events[0].summary_json)["reason_code"] == "not_found"


def test_same_role_is_conflict_and_not_a_success_audit(tmp_path):
    """规范 §3.2：幂等请求不得制造「发生过变更」的成功审计。"""
    with admin_client(tmp_path) as client:
        target_id = seed_admin(client, "target-6", "teacher")
        headers = login_root(client)

        assert put_role(client, headers, target_id, "teacher").status_code == 409

        assert role_events(client, "success") == []
        events = role_events(client, "failure")
        assert len(events) == 1
        summary = json.loads(events[0].summary_json)
        assert summary["reason_code"] == "conflict"
        assert summary["old_role"] == summary["new_role"] == "teacher"


# ==================== 成功路径与审计字段 ====================


def test_successful_role_change_writes_full_audit(tmp_path):
    with admin_client(tmp_path) as client:
        target_id = seed_admin(client, "target-7", "editor")
        headers = login_root(client)
        root_id = client.get("/api/admin/me").json()["id"]

        response = put_role(client, headers, target_id, "teacher")

        assert response.status_code == 200
        assert response.json()["role"] == "teacher"
        assert current_role(client, target_id) == "teacher"

        events = role_events(client, "success")
        assert len(events) == 1
        event = events[0]
        assert event.admin_user_id == root_id
        assert event.resource_type == "admin_user"
        assert event.resource_id == target_id
        assert event.user_id is None
        assert event.created_at is not None
        # IP 只能以 HMAC 形式出现，原始 IP 不得落库（规范 §2.1）。
        assert event.ip_hmac == hash_ip(client.app.state.settings, "testclient")
        assert event.ip_hmac != "testclient"

        summary = json.loads(event.summary_json)
        assert summary == {"schema_version": 1, "old_role": "editor", "new_role": "teacher"}


def test_success_audit_summary_has_no_sensitive_or_org_fields(tmp_path):
    """规范 §5：摘要只允许内部 ID、受控枚举与 UTC 时间。"""
    with admin_client(tmp_path) as client:
        target_id = seed_admin(client, "target-8", "editor", display_name="王老师")
        headers = login_root(client)
        assert put_role(client, headers, target_id, "assistant").status_code == 200

        event = role_events(client, "success")[0]
        raw = event.summary_json
        summary = json.loads(raw)
        assert set(summary) == {"schema_version", "old_role", "new_role"}
        for banned in (
            "organization_id",
            "tenant_id",
            "campus_id",
            "username",
            "display_name",
            "password",
            "password_hash",
            "ip",
        ):
            assert banned not in summary
        # 用户名与姓名不得以任何形式出现在整条摘要文本里。
        assert "target-8" not in raw
        assert "王老师" not in raw


def test_role_options_come_from_permissions_single_source(tmp_path):
    """角色下拉的取值域与展示顺序由 permissions.py 提供，前端不得自备一份。"""
    from app.permissions import KNOWN_ROLE_NAMES, ROLE_LABELS

    with admin_client(tmp_path) as client:
        login_root(client)
        body = client.get("/api/admin/admin-users").json()
        assert [role["value"] for role in body["roles"]] == list(KNOWN_ROLE_NAMES)
        assert [role["label"] for role in body["roles"]] == [
            ROLE_LABELS[name] for name in KNOWN_ROLE_NAMES
        ]


# ==================== 最后一名超管不得降级 ====================


def test_last_super_admin_cannot_demote_themselves(tmp_path):
    """降到零个超管就没人能改回来了，只能上服务器重建；接口必须拦住。"""
    with admin_client(tmp_path) as client:
        headers = login_root(client)
        root_id = client.get("/api/admin/me").json()["id"]

        response = put_role(client, headers, root_id, "teacher")

        assert response.status_code == 409
        assert response.json()["detail"] == "系统必须至少保留一名超级管理员。"
        # 拦下了就必须什么都没变，超管仍然是超管。
        assert current_role(client, root_id) == "super_admin"
        assert client.get("/api/admin/me").json()["can_manage_admin_roles"] is True

        assert role_events(client, "success") == []
        events = role_events(client, "failure")
        assert len(events) == 1
        summary = json.loads(events[0].summary_json)
        assert summary["reason_code"] == "invalid_state"
        assert summary["old_role"] == "super_admin"
        assert summary["new_role"] == "teacher"


def test_a_disabled_super_admin_does_not_count_as_a_remaining_super(tmp_path):
    """停用的超管登不进来，不能拿它当「还剩一个」的兜底。"""
    with admin_client(tmp_path) as client:
        spare_id = seed_admin(client, "spare-super", "super_admin")
        db = client.app.state.session_factory()
        try:
            db.get(AdminUser, spare_id).status = "disabled"
            db.commit()
        finally:
            db.close()

        headers = login_root(client)
        root_id = client.get("/api/admin/me").json()["id"]

        assert put_role(client, headers, root_id, "editor").status_code == 409
        assert current_role(client, root_id) == "super_admin"


def test_super_admin_can_step_down_after_appointing_a_successor(tmp_path):
    """守卫拦的是「归零」，不是「改自己」——正常交接必须还能走通。"""
    with admin_client(tmp_path) as client:
        successor_id = seed_admin(client, "successor", "editor")
        headers = login_root(client)
        root_id = client.get("/api/admin/me").json()["id"]

        # 第一步：先把接班人提成超管。
        assert put_role(client, headers, successor_id, "super_admin").status_code == 200
        # 第二步：老超管这时才能退位。
        assert put_role(client, headers, root_id, "teacher").status_code == 200

        assert current_role(client, root_id) == "teacher"
        assert current_role(client, successor_id) == "super_admin"
        assert len(role_events(client, "success")) == 2


def test_demoting_another_super_admin_is_still_allowed(tmp_path):
    """还剩别的活跃超管时，降级照常放行（发起人自己就算一个）。"""
    with admin_client(tmp_path) as client:
        other_id = seed_admin(client, "second-super", "super_admin")
        headers = login_root(client)

        assert put_role(client, headers, other_id, "editor").status_code == 200
        assert current_role(client, other_id) == "editor"


# ==================== 即时生效（不需要重新登录） ====================


def test_promotion_is_effective_on_the_next_request(tmp_path):
    """角色存在 admin_users 行上、每次请求由 current_admin 重新读取。

    因此已签发的 access token 不需要重新登录，也不需要吊销会话。
    """
    with admin_client(tmp_path) as client:
        target_id = seed_admin(client, "promoted", "editor")

        # 目标账号先建立自己的会话：此刻还不是超管。
        login_as(client, "promoted")
        assert client.get("/api/admin/me").json()["can_manage_admin_roles"] is False
        assert client.get("/api/admin/admin-users").status_code == 403
        target_cookies = dict(client.cookies)

        # 超管在另一条会话里提权。
        root_headers = login_root(client)
        assert put_role(client, root_headers, target_id, "super_admin").status_code == 200

        # 回到目标账号那条「旧」会话，下一次请求就已经是超管。
        restore_cookies(client, target_cookies)
        me = client.get("/api/admin/me").json()
        assert me["role"] == "super_admin"
        assert me["can_manage_admin_roles"] is True
        assert client.get("/api/admin/admin-users").status_code == 200


def test_demotion_is_effective_on_the_next_request(tmp_path):
    """降权同样即时：旧会话立刻失去角色变更能力。"""
    with admin_client(tmp_path) as client:
        target_id = seed_admin(client, "demoted", "super_admin")
        other_id = seed_admin(client, "bystander", "editor")

        login_as(client, "demoted")
        assert client.get("/api/admin/admin-users").status_code == 200
        target_cookies = dict(client.cookies)

        root_headers = login_root(client)
        assert put_role(client, root_headers, target_id, "editor").status_code == 200

        restore_cookies(client, target_cookies)
        me = client.get("/api/admin/me").json()
        assert me["role"] == "editor"
        assert me["can_manage_admin_roles"] is False
        assert client.get("/api/admin/admin-users").status_code == 403
        # 降权后再想改别人的角色，同样立刻被拒。
        headers = {"X-CSRF-Token": client.cookies.get("admin_csrf_token")}
        assert put_role(client, headers, other_id, "teacher").status_code == 403
