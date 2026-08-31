"""scope 只能收窄数据范围，capability 必须由真实功能闸读取。"""
from __future__ import annotations

import importlib.util
from pathlib import Path

from app.permissions import (
    ALL_MENU_PAGES,
    CAPABILITY_CATALOG,
    KNOWN_ROLE_NAMES,
    NON_MENU_PAGES,
    ROLE_CAPABILITIES,
    ROLE_LABELS,
    ROLE_SCOPES,
)
from test_admin_auth import admin_client
from test_admin_role_change import login_as, login_root, seed_admin


SERVICE_ROOT = Path(__file__).resolve().parents[1]
ADMIN_DIR = SERVICE_ROOT.parents[1] / "前端程序" / "study-blog-vue" / "public" / "admin"

# 已进目录、但功能尚未实现的 capability。功能落地后必须从这里删除，
# 否则守卫会继续允许没有真实闸门的能力存在。
PENDING_CAPABILITY_WIRING = {
    "realtime_assist": "M3 · 《58》§5.1 / 《67》C 线",
    "support_content_request": "M3-H1 · 《58》§2.7",
    "support_content_approve": "M3-H1 · 《58》§2.7",
}

# capability 必须在管理路由中以字面量或真实授权谓词出现；
# help_respond 通过 help_requests.py 调用其专用谓词接线。
ROUTER_CAPABILITY_MARKERS = {
    key: (f'"{key}"', f"'{key}'") for key in CAPABILITY_CATALOG
}
ROUTER_CAPABILITY_MARKERS["help_respond"] = (
    "_require_help_respond(admin, db)",
)


def _load_migration(name: str):
    path = SERVICE_ROOT / "alembic" / "versions" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_every_capability_is_read_by_at_least_one_gate():
    """目录中的每项 capability 都必须被路由功能闸读取，或登记为待接线。"""
    sources = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (SERVICE_ROOT / "app" / "routers").rglob("*.py")
        if "__pycache__" not in str(path)
    )
    unenforced = [
        key
        for key in CAPABILITY_CATALOG
        if key not in PENDING_CAPABILITY_WIRING
        and not any(marker in sources for marker in ROUTER_CAPABILITY_MARKERS[key])
    ]
    assert unenforced == [], f"以下权限只在目录里存在，没有任何闸门读取：{unenforced}"


def test_migration_seeds_equal_code_owned_role_matrix():
    """0072 基线与后续增量的并集必须等于当前内置角色矩阵。"""
    baseline = _load_migration("0072_dynamic_admin_rbac")
    help_contract = _load_migration("0074_help_chat_realtime")
    super_help_contract = _load_migration("0081_grant_super_help_respond")
    code = {
        role: frozenset(key for key, enabled in capabilities.items() if enabled)
        for role, capabilities in ROLE_CAPABILITIES.items()
    }
    seeded = {
        role: frozenset(baseline.ROLE_GRANTS[role])
        | frozenset(help_contract.ROLE_GRANTS.get(role, ()))
        | frozenset(super_help_contract.ROLE_GRANTS.get(role, ()))
        for role in code
    }
    assert seeded == code
    assert set(baseline.CAPABILITIES) | set(help_contract.CAPABILITIES) == set(CAPABILITY_CATALOG)
    assert {key: (label, scope) for key, label, scope, *_ in baseline.ROLE_SEEDS} == {
        role: (ROLE_LABELS[role], ROLE_SCOPES[role]) for role in KNOWN_ROLE_NAMES
    }


def _create_global_role(client, headers, key: str, capabilities: list[str] | None = None):
    response = client.post(
        "/api/admin/roles",
        headers=headers,
        json={
            "key": key,
            "label": "权限守卫测试角色",
            "description": "",
            "scope": "global",
            "capabilities": capabilities or [],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _restore_cookies(client, cookies):
    client.cookies.clear()
    for key, value in cookies.items():
        client.cookies.set(key, value)


def _replace_role_capabilities(client, headers, role, capabilities: list[str]):
    response = client.put(
        f"/api/admin/roles/{role['value']}",
        headers={**headers, "If-Match": str(role["revision"])},
        json={
            "key": role["value"],
            "label": role["label"],
            "description": role["description"],
            "scope": role["scope"],
            "capabilities": capabilities,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_zero_capability_global_role_is_denied_everywhere(tmp_path):
    """global scope 只能定义范围，绝不能单独构成功能授权。"""
    with admin_client(tmp_path) as client:
        root_headers = login_root(client)
        role = _create_global_role(client, root_headers, "no_capability_global")
        seed_admin(client, "no-capability-global", role["value"])
        headers = login_as(client, "no-capability-global")

        for path in (
            "/api/admin/exam-results",
            "/api/admin/lesson-homework-results",
            "/api/admin/students",
            "/api/admin/classes/export",
            "/api/admin/classes",
            "/api/admin/audit/events",
        ):
            response = client.get(path, headers=headers)
            assert response.status_code == 403, f"{path}: {response.status_code} {response.text}"


def test_capability_grant_reopens_the_same_endpoint(tmp_path):
    """授予 capability 后，同一全局角色只恢复对应端点的访问。"""
    with admin_client(tmp_path) as client:
        root_headers = login_root(client)
        root_cookies = dict(client.cookies)
        role = _create_global_role(client, root_headers, "capability_sentinel")
        seed_admin(client, "capability-sentinel", role["value"])
        headers = login_as(client, "capability-sentinel")
        actor_cookies = dict(client.cookies)

        checks = (
            ([], ["results_read"], "/api/admin/students", "application/json"),
            ([], ["results_read"], "/api/admin/exam-results", "application/json"),
            ([], ["class_read"], "/api/admin/classes", "application/json"),
            (["class_read"], ["class_read", "export_class_relationships"], "/api/admin/classes/export", "text/csv"),
            ([], ["audit_events_read"], "/api/admin/audit/events", "application/json"),
        )
        for denied_capabilities, granted_capabilities, path, content_type in checks:
            _restore_cookies(client, root_cookies)
            role = _replace_role_capabilities(client, root_headers, role, denied_capabilities)
            _restore_cookies(client, actor_cookies)
            denied = client.get(path, headers=headers)
            assert denied.status_code == 403, denied.text

            _restore_cookies(client, root_cookies)
            role = _replace_role_capabilities(client, root_headers, role, granted_capabilities)
            _restore_cookies(client, actor_cookies)
            allowed = client.get(path, headers=headers)
            assert allowed.status_code == 200, allowed.text
            assert content_type in allowed.headers["content-type"]


def test_every_admin_page_is_registered():
    """调用 initLayout 的管理页必须可被任一已认证账号直接打开。"""
    known = set(ALL_MENU_PAGES) | set(NON_MENU_PAGES) | {"login.html"}
    orphans = sorted(
        path.name
        for path in ADMIN_DIR.glob("*.html")
        if "initLayout()" in path.read_text(encoding="utf-8") and path.name not in known
    )
    assert orphans == [], f"这些页面对所有角色都会被跳转：{orphans}"
