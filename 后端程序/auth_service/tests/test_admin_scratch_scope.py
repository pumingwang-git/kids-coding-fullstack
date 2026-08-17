"""Scratch 提交读端点的角色闸（E0 对账文档 §3.2 / §5 问题 1、2 的修复验证）。

背景：`/api/admin/scratch/submissions` 及其三条子路径原先只调 `current_admin`，
只做身份认证、没有任何授权——任何后台登录态都能列出并下载全站学生的作品源文件，
`keyword` 还等于一个全站学生姓名搜索接口。写端点（`/review`、`/return`）却卡了
`_require_editor`，读写口径不一致说明这是遗漏。本文件钉死修复后的口径：

- reviewer（只该审题）→ 四条读端点一律 403；
- editor / super_admin → 照常 200（回归，别把闸门收得比写端点还紧）；
- 未登录 → 401（认证仍先于授权，不能因为加了角色闸就把匿名也报成 403）。

**本期只到角色闸。** 数据范围（老师只看自己带的班）要等 E2 的 `class_teachers`，
届时这里应补"teacher 看不到他班学生"的用例，见 `_require_submission_reader` 注释与
《32、E0-权限矩阵与数据范围对账-2026-08-17》§6.2。
"""
from pathlib import Path

from fastapi.testclient import TestClient
from test_admin_courses import reviewer_login
from test_exam import ADMIN_PASSWORD, admin_login, student_login
from test_scratch import (
    build_scratch_lesson,
    open_block,
    save_project,
    sb3_bytes,
    scratch_env,
    submit,
)

from app.models import AdminUser
from app.security import password_hash


def _submitted(tmp_path: Path):
    """建好一条真实提交，返回 (app, submission_id, 学生用户名)。

    用真实提交而不是直接塞库：这四条端点的越权后果就是"能不能拿到别人的作品文件"，
    快照文件必须真的落盘，否则 403 之外的分支（200 拿到 sb3 字节）没法断言。
    """
    app = scratch_env(tmp_path)
    built = build_scratch_lesson(app)
    sclient = student_login(app, "scopekid")
    block_id = built["block_ids"][0]
    project_id = open_block(sclient, block_id).json()["project"]["id"]
    save_project(sclient, project_id, sb3_bytes())
    sid = submit(sclient, block_id).json()["submission_id"]
    return app, sid, "scopekid"


def _editor_login(app) -> tuple[TestClient, dict]:
    """普通 editor（不是 super_admin）：确认闸门放行的是角色本身，不是超管豁免。"""
    db = app.state.session_factory()
    try:
        db.add(AdminUser(username="editor1", password_hash=password_hash.hash(ADMIN_PASSWORD),
                         display_name="editor", role="editor"))
        db.commit()
    finally:
        db.close()
    client = TestClient(app)
    client.get("/api/admin/csrf")
    headers = {"X-CSRF-Token": client.cookies.get("admin_csrf_token")}
    resp = client.post("/api/admin/login", headers=headers,
                       json={"username": "editor1", "password": ADMIN_PASSWORD})
    assert resp.status_code == 200, resp.text
    return client, headers


def _read_paths(sid: int) -> list[str]:
    return [
        "/api/admin/scratch/submissions",
        f"/api/admin/scratch/submissions/{sid}",
        f"/api/admin/scratch/submissions/{sid}/project.sb3",
        f"/api/admin/scratch/submissions/{sid}/project.json",
    ]


def test_reviewer_denied_on_all_submission_reads(tmp_path: Path):
    """reviewer 拿到的是合法后台登录态，四条读端点仍须 403（问题 1 的修复验证）。"""
    app, sid, _ = _submitted(tmp_path)
    rclient, rheaders = reviewer_login(app)
    for path in _read_paths(sid):
        resp = rclient.get(path, headers=rheaders)
        assert resp.status_code == 403, f"{path} 放行了 reviewer：{resp.status_code} {resp.text}"


def test_reviewer_cannot_download_sb3_by_guessing_id(tmp_path: Path):
    """.sb3 越权路径单独钉一条：泄露面最大的是整份作品源文件。

    连"猜一个不存在的 id"也必须先撞角色闸（403），不能靠 404 把"这条提交存不存在"
    这一位信息漏出去——否则 reviewer 能用 404/403 的差异枚举全站提交。
    """
    app, sid, _ = _submitted(tmp_path)
    rclient, rheaders = reviewer_login(app)
    denied = rclient.get(f"/api/admin/scratch/submissions/{sid}/project.sb3", headers=rheaders)
    assert denied.status_code == 403
    assert denied.content[:2] != b"PK", "被拒的响应里不该带着 sb3 字节"

    ghost = rclient.get("/api/admin/scratch/submissions/999999/project.sb3", headers=rheaders)
    assert ghost.status_code == 403, "授权应先于存在性判断，否则可枚举 submission_id"


def test_reviewer_cannot_search_students_by_keyword(tmp_path: Path):
    """`keyword` 是全站学生用户名模糊搜索，reviewer 连空结果都不该拿到。"""
    app, _, username = _submitted(tmp_path)
    rclient, rheaders = reviewer_login(app)
    resp = rclient.get("/api/admin/scratch/submissions",
                       params={"keyword": username[:4]}, headers=rheaders)
    assert resp.status_code == 403, resp.text


def test_editor_still_reads_submissions(tmp_path: Path):
    """回归：普通 editor 是批改台的正常使用者，四条读端点须照常放行。"""
    app, sid, username = _submitted(tmp_path)
    client, headers = _editor_login(app)

    listed = client.get("/api/admin/scratch/submissions", headers=headers)
    assert listed.status_code == 200, listed.text
    assert listed.json()["total"] >= 1

    searched = client.get("/api/admin/scratch/submissions",
                          params={"keyword": username[:4]}, headers=headers)
    assert searched.status_code == 200, searched.text
    assert searched.json()["total"] >= 1

    detail = client.get(f"/api/admin/scratch/submissions/{sid}", headers=headers)
    assert detail.status_code == 200, detail.text
    assert detail.json()["id"] == sid

    sb3 = client.get(f"/api/admin/scratch/submissions/{sid}/project.sb3", headers=headers)
    assert sb3.status_code == 200, sb3.text
    assert sb3.content[:2] == b"PK"  # 真的是 zip，不是被闸门吞成空响应

    pjson = client.get(f"/api/admin/scratch/submissions/{sid}/project.json", headers=headers)
    assert pjson.status_code == 200, pjson.text
    assert "targets" in pjson.json()


def test_super_admin_still_reads_submissions(tmp_path: Path):
    """回归：super_admin 由 `is_editor()` 豁免，不能被新闸门误伤。"""
    app, sid, _ = _submitted(tmp_path)
    client, headers = admin_login(app)
    for path in _read_paths(sid):
        resp = client.get(path, headers=headers)
        assert resp.status_code == 200, f"{path} 把超管拒了：{resp.status_code} {resp.text}"


def test_anonymous_still_gets_401_not_403(tmp_path: Path):
    """认证仍先于授权：没登录是 401，不是 403（前端据此决定跳登录页还是提示无权限）。"""
    app, sid, _ = _submitted(tmp_path)
    guest = TestClient(app)
    for path in _read_paths(sid):
        assert guest.get(path).status_code == 401, path
