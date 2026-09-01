"""前端调用的每条答疑接口，后端必须真实存在。

这条守卫补的是一个**测试全绿但功能是空转**的洞：前端把撤回、附件都写完了，
打的却是后端根本没注册的路径，点下去只会 404。两侧单测各自绿，没人对过账。

两端的写法不一样，必须分开采：
  学生端 `services/help.js` 写的是完整路径（`/api/student/...`）；
  管理端 `help-desk.js` 走注入的 `request()`（默认 `adminRequest`），只写
  `/help-...` 相对段，由 `admin-api.js` 拼上 `/api/admin` 前缀。
**只采一种就会留下盲区** —— 初版只认完整路径，教师端的撤回调用整条漏掉了。
"""

import re
from pathlib import Path

from test_exam import build_app

SERVICE_ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = SERVICE_ROOT.parents[1] / "前端程序" / "study-blog-vue"

STUDENT_SOURCE = WEB_ROOT / "src" / "services" / "help.js"
ADMIN_SOURCE = WEB_ROOT / "public" / "admin" / "help-desk.js"
ADMIN_PREFIX = "/api/admin"

# `/api/x/${id}/y` 与 FastAPI 的 `/api/x/{id}/y` 归一成同一形状后再比对。
_ABSOLUTE = re.compile(r"/api/[A-Za-z0-9_\-/{}$.\[\]()]*")
_ADMIN_CALL = re.compile(r"\b(?:request|adminRequest|adminUpload)\(\s*[`\"']([^`\"']*)")
_INTERPOLATION = re.compile(r"\$\{[^}]*\}")
_PARAM = re.compile(r"\{[^}]*\}")
_ADVERTISED_URL = re.compile(r"[\"']url[\"']\s*:\s*[^\n]*?f?[\"'](/api/[^\"']*)")


def _normalize(path: str) -> str:
    path = _INTERPOLATION.sub("{}", path)
    path = _PARAM.sub("{}", path)
    return path.split("?")[0].rstrip("/")


def _frontend_paths() -> set[str]:
    assert STUDENT_SOURCE.is_file() and ADMIN_SOURCE.is_file(), "前端源文件不见了"
    found = set()
    for raw in _ABSOLUTE.findall(STUDENT_SOURCE.read_text(encoding="utf-8")):
        found.add(_normalize(raw))
    admin_text = ADMIN_SOURCE.read_text(encoding="utf-8")
    for raw in _ABSOLUTE.findall(admin_text):
        found.add(_normalize(raw))
    for relative in _ADMIN_CALL.findall(admin_text):
        if relative.startswith("/"):
            found.add(_normalize(ADMIN_PREFIX + relative))
    return {path for path in found if path.count("/") >= 3}


def _collect_routes(routes, prefix: str = "") -> list[str]:
    """展开 FastAPI 的 include 包装，拿到最终路径（含 WebSocket 路由）。

    这一版 FastAPI 把 `include_router()` 的结果包成 `_IncludedRouter`，
    `app.routes` 里直接看不到最终路径，必须钻进 `original_router`。
    """
    collected = []
    for route in routes:
        if type(route).__name__ == "_IncludedRouter":
            nested = prefix + getattr(route.include_context, "prefix", "")
            collected += _collect_routes(route.original_router.routes, nested)
            continue
        path = getattr(route, "path", None)
        if path:
            collected.append(prefix + path)
    return collected


def _backend_paths(app) -> set[str]:
    paths = {_normalize(p) for p in _collect_routes(app.routes) if p.startswith("/api/")}
    # 自保：上面钻的是 FastAPI 内部结构，版本一变就可能采集为空。
    # 没有这条断言，本守卫会在「后端集合为空」时**静默退化成恒绿**——
    # 那时它不再证明任何事，却还挂着一个通过标记。
    assert len(paths) > 50, f"路由采集失败（只拿到 {len(paths)} 条），FastAPI 内部结构可能变了"
    return paths


def test_every_help_path_called_by_the_frontend_exists_on_the_backend(tmp_path):
    app = build_app(tmp_path)
    backend = _backend_paths(app)
    called = _frontend_paths()
    # 哨兵：采不到前端调用同样是失效，别让"没找到"冒充"全都对得上"。
    assert len([p for p in called if "help" in p]) >= 8, f"前端答疑调用采集异常：{sorted(called)}"
    missing = sorted(path for path in called if "help" in path and path not in backend)
    assert missing == [], (
        "前端调用了后端不存在的答疑接口（点下去就是 404）：\n  " + "\n  ".join(missing)
    )


def test_backend_never_advertises_a_url_it_does_not_serve(tmp_path):
    """后端下发给前端的 `url`，自己必须真的能服务。

    这是与上一条**方向相反**的一类断裂，上一条抓不到：
    上一条查的是「前端调了后端没有的路径」，这条查的是
    「后端在响应里许诺了一个自己没注册的地址」——前端照着点，一样是 404。

    现实例子：附件序列化里写了 `url: /api/help-attachments/{id}`，
    而全后端没有任何路由服务这个前缀。
    """
    app = build_app(tmp_path)
    backend = _backend_paths(app)
    source = (SERVICE_ROOT / "app" / "routers" / "help_requests.py").read_text(encoding="utf-8")

    advertised = set()
    # 只采响应对象实际下发的 `url` 值，不能把 APIRouter(prefix="/api/...")
    # 这样的路由声明误判成“后端向前端承诺的 URL”。
    for raw in _ADVERTISED_URL.findall(source):
        normalized = _normalize(raw)
        # f-string 里的 `{attachment.id}` 归一后就是 `{}`，与路由参数同形。
        if normalized.count("/") >= 3:
            advertised.add(normalized)

    unserved = sorted(path for path in advertised if path not in backend)
    assert unserved == [], (
        "后端在响应里下发了自己没有注册的地址（前端点了就是 404）：\n  "
        + "\n  ".join(unserved)
    )
