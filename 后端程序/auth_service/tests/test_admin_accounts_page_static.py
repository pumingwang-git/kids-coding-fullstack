"""管理端「账号与角色」页的静态契约校验。

管理端是原生 HTML/JS，没有构建期类型检查，页面与后端的约定只能靠静态断言兜住。
这里只做「读文件 + 断言」，不起浏览器；覆盖三件最容易悄悄走偏的事：

1. 页面调用的路径确实是后端注册的路由（改了一端、忘了另一端时直接失败）；
2. 角色集合没有被前端抄第二份（ADR-001 §2.2.1 的失败模式）；
3. 角色变更入口受 can_manage_admin_roles 控制，且默认不渲染出来。

第 3 条只是体验层面的收口——真正拦住越权的是后端 403，见 test_admin_role_change.py。
"""
import re
from pathlib import Path

import pytest

from app.config import DEV_FERNET_KEY, Settings
from app.main import create_app
from app.permissions import KNOWN_ROLE_NAMES

ADMIN_DIR = Path(__file__).resolve().parents[3] / "前端程序" / "study-blog-vue" / "public" / "admin"

# 「admin」既是历史角色名，也出现在 admin.css / admin-api.js / can_manage_admin_roles 里，
# 无法用纯文本区分，这里只查那些一旦出现就一定是抄了角色集合的名字。
DISTINCTIVE_ROLES = [role for role in KNOWN_ROLE_NAMES if role != "admin"]


def read(name: str) -> str:
    path = ADMIN_DIR / name
    assert path.is_file(), f"缺少管理端文件：{path}"
    return path.read_text(encoding="utf-8")


def strip_comments(source: str) -> str:
    """去掉 // 与 /* */ 注释：注释里引用 ADR 原文提到角色名是正当的。"""
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.S)
    return re.sub(r"^\s*//.*$", "", source, flags=re.M)


@pytest.fixture(scope="module")
def accounts_js():
    return read("accounts.js")


@pytest.fixture(scope="module")
def accounts_html():
    return read("accounts.html")


@pytest.fixture(scope="module")
def layout_js():
    return read("admin-layout.js")


# ==================== 1. 路径与后端路由一致 ====================


def registered_routes():
    """从 OpenAPI 取路由表：app.routes 在当前 FastAPI 版本里是未展开的 _IncludedRouter。"""
    settings = Settings(
        environment="test",
        database_url="sqlite://",
        outbox_encryption_key=DEV_FERNET_KEY,
        smtp_host=None,
        smtp_username=None,
        smtp_password=None,
        smtp_from=None,
        redis_url=None,
    )
    paths = create_app(settings).openapi()["paths"]
    return {(path, method.upper()) for path, methods in paths.items() for method in methods}


def test_page_calls_paths_that_the_backend_actually_registers(accounts_js):
    routes = registered_routes()
    assert ("/api/admin/admin-users", "GET") in routes
    assert ("/api/admin/admin-users/{admin_user_id}/role", "PUT") in routes

    # adminRequest 会自动补 /api/admin 前缀，所以页面里写的是相对路径。
    assert '"/admin-users"' in accounts_js
    assert re.search(r"`/admin-users/\$\{[^}]+\}/role`", accounts_js), "角色变更路径与后端路由不一致"
    assert re.search(r'method:\s*"PUT"', accounts_js), "角色变更必须用 PUT"
    assert re.search(r'JSON\.stringify\(\{\s*role\s*[,}]', accounts_js), "请求体字段名必须是 role"


def test_every_named_import_is_actually_exported(accounts_js):
    """页面是 <script type="module">，导入名写错只会在运行时白屏，这里静态兜住。"""
    imports = re.findall(r"import\s*\{([^}]+)\}\s*from\s*\"\./([^\"]+)\"", accounts_js)
    assert imports, "accounts.js 应当从共享模块导入"
    for names, module in imports:
        exported = set(re.findall(r"export\s+(?:async\s+)?(?:function|const|let|class)\s+(\w+)", read(module)))
        for name in (part.strip() for part in names.split(",")):
            assert name in exported, f"{module} 没有导出 {name}"


def test_status_endpoint_matches_the_backend_route(accounts_js):
    routes = registered_routes()
    assert ("/api/admin/admin-users/{admin_user_id}/status", "PUT") in routes
    assert re.search(r"`/admin-users/\$\{[^}]+\}/status`", accounts_js), "启用/停用路径与后端路由不一致"
    assert re.search(r'JSON\.stringify\(\{\s*status:', accounts_js), "请求体字段名必须是 status"


def test_status_labels_match_the_backend_enum(accounts_js):
    """状态是闭集，前端的文案表必须与后端 Literal 的取值完全对齐。"""
    from typing import get_args

    from app.schemas import AdminStatusUpdateRequest

    backend = set(get_args(AdminStatusUpdateRequest.model_fields["status"].annotation))
    table = re.search(r"const STATUS_LABEL = \{(.*?)\};", accounts_js, flags=re.S)
    assert table, "accounts.js 缺少 STATUS_LABEL"
    frontend = set(re.findall(r"(\w+):", table.group(1)))
    assert frontend == backend, f"前端状态 {frontend} 与后端 {backend} 不一致"


def test_page_uses_the_shared_admin_request_wrapper(accounts_js):
    """必须走 adminRequest：CSRF、401 续期、错误文案都在里面，绕开就得各抄一份。"""
    assert 'from "./admin-api.js"' in accounts_js
    assert "adminRequest(" in accounts_js
    assert "fetch(" not in strip_comments(accounts_js), "不要在页面里直接 fetch"


# ==================== 2. 角色集合不得在前端抄第二份 ====================


@pytest.mark.parametrize("role", DISTINCTIVE_ROLES)
def test_frontend_does_not_hardcode_role_names(role, accounts_js, accounts_html, layout_js):
    for name, source in (
        ("accounts.js", strip_comments(accounts_js)),
        ("accounts.html", accounts_html),
        ("admin-layout.js", strip_comments(layout_js)),
    ):
        for literal in (f'"{role}"', f"'{role}'", f"`{role}`"):
            assert literal not in source, f"{name} 硬编码了角色 {role}；角色集合只能来自后端"


def test_role_options_are_rendered_from_the_api_payload(accounts_js):
    body = strip_comments(accounts_js)
    # 下拉项来自列表接口的 roles，label/value 都不自造。
    assert "data.roles" in body
    assert "roleOptions" in body
    assert re.search(r"roleOptions\s*\n?\s*\.map\(|roleOptions\.map\(", body), "下拉必须由 roleOptions 渲染"


def test_role_select_is_empty_in_markup(accounts_html):
    """静态标记里不能预置 option，否则就是又一份角色集合。"""
    select = re.search(r'<select id="roleSelect">(.*?)</select>', accounts_html, flags=re.S)
    assert select, "缺少角色下拉 #roleSelect"
    assert select.group(1).strip() == "", "角色下拉的 option 必须运行时从接口渲染"


# ==================== 3. 入口受 can_manage_admin_roles 控制 ====================


def test_page_gates_on_can_manage_admin_roles(accounts_js):
    body = strip_comments(accounts_js)
    assert "can_manage_admin_roles" in body
    assert "forbiddenCard" in body and "listCard" in body


def test_list_and_editor_are_hidden_until_the_gate_passes(accounts_html):
    """两张卡片默认 hidden：/me 返回前不得先闪出一帧角色变更入口。"""
    for card in ("listCard", "forbiddenCard"):
        assert re.search(rf'id="{card}"[^>]*\shidden', accounts_html), f"#{card} 必须默认 hidden"
    assert re.search(r'id="roleMask"[^>]*\shidden', accounts_html), "角色变更 Modal 必须默认 hidden"


def test_menu_entry_is_marked_super_only_and_rendered_hidden(layout_js):
    body = strip_comments(layout_js)
    entry = re.search(r"\{[^{}]*accounts\.html[^{}]*\}", body)
    assert entry, "admin-layout.js 的菜单里缺少 accounts.html"
    assert "superOnly: true" in entry.group(0), "账号与角色入口必须标记 superOnly"
    # 渲染时默认带 hidden，确认是超管后才由 loadAdmin 摘掉。
    assert "data-super-only hidden" in body
    assert re.search(r"can_manage_admin_roles[^\n]*\n?[^\n]*data-super-only|data-super-only", body)


def test_role_change_entry_is_not_exposed_on_the_ungated_dashboard():
    """index.html 的功能入口表是静态的、没有角色判断，不能把授权入口放进去。"""
    assert "accounts.html" not in read("index.html")
