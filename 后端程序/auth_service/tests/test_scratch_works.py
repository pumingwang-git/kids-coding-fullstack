"""Scratch 自由作品与作品广场后端回归。

覆盖（与 scratch_works.py 文件头四条红线逐条对应）：

- 未登录：作品 CRUD / 分享 / 画廊全部 401；
- 归属：别人的作品读写一律 **404 不是 403**（防枚举）；
- 保存：结构检查（坏 ZIP 400）、限流（429）、同内容去重（unchanged=true）、
  内容寻址取回一致；
- 分享：闯关作品 → 广场快照（source=challenge、标题取挑战标题、字节一致），
  幂等（already_shared=true），未保存过先 400；
- 公开纪律：画廊只出 is_public 作品，私密作品在画廊里按 404 处理；公开切换后
  立即生效；views 在详情接口递增、popular 排序按 views；
- 元数据：PATCH 只更新提供的字段；DELETE 后本人也 404。

`.sb3` 夹具复用 test_scratch 的内存现造方案，不放二进制进仓库。
"""
import json
import zipfile
from io import BytesIO
from pathlib import Path

from test_exam import scsrf, student_login
from test_scratch import (
    build_scratch_lesson,
    sb3_bytes,
    scratch_env,
    scripted_sprite,
    stage_target,
)

# ---------- 小工具 ----------


def new_work(sclient, title="我的第一个作品"):
    resp = sclient.post("/api/scratch/works", headers=scsrf(sclient), json={"title": title})
    assert resp.status_code == 201, resp.text
    return resp.json()


def save_work(sclient, work_id, data, *, source="manual"):
    return sclient.put(
        f"/api/scratch/works/{work_id}", headers=scsrf(sclient),
        files={"file": ("work.sb3", data, "application/zip")}, data={"source": source},
    )


def patch_work(sclient, work_id, **fields):
    return sclient.patch(f"/api/scratch/works/{work_id}", headers=scsrf(sclient),
                         json=fields)


def gallery(sclient, **params):
    query = "&".join(f"{k}={v}" for k, v in params.items())
    return sclient.get(f"/api/scratch/gallery?{query}" if query else "/api/scratch/gallery")


def two_students(app):
    """返回 (student_a, student_b)。"""
    return student_login(app, "alice"), student_login(app, "bob")


# ---------- 未登录 ----------


def test_anonymous_gets_401_everywhere(tmp_path: Path):
    app = scratch_env(tmp_path)
    from fastapi.testclient import TestClient
    guest = TestClient(app)
    assert guest.get("/api/scratch/works").status_code == 401
    # 写操作先过 CSRF（require_csrf 在鉴权之前，与闯关提交同口径）：未登录无令牌 → 403
    assert guest.post("/api/scratch/works", json={"title": "x"}).status_code in (401, 403)
    assert guest.get("/api/scratch/gallery").status_code == 401
    assert guest.get("/api/scratch/gallery/1").status_code == 401
    assert guest.get("/api/scratch/gallery/1/content.sb3").status_code == 401


# ---------- 我的作品 CRUD ----------


def test_create_list_and_detail(tmp_path: Path):
    app = scratch_env(tmp_path)
    sclient = student_login(app)
    work = new_work(sclient, title="小猫散步")
    assert work["title"] == "小猫散步"
    assert work["is_public"] is True            # 默认公开（展出）
    assert work["has_content"] is False          # 还没保存任何内容
    assert work["content_url"] is None

    listing = sclient.get("/api/scratch/works").json()
    assert [w["id"] for w in listing["items"]] == [work["id"]]

    detail = sclient.get(f"/api/scratch/works/{work['id']}").json()
    assert detail["title"] == "小猫散步"
    assert detail["limits"]["max_bytes"] > 0     # Studio 需要的保存上限
    assert detail["content_url"] is None


def test_work_round_trip_and_dedup(tmp_path: Path):
    app = scratch_env(tmp_path)
    sclient = student_login(app)
    work = new_work(sclient)
    data = sb3_bytes([stage_target(), scripted_sprite(name="小黄鸭")])

    saved = save_work(sclient, work["id"], data)
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert body["unchanged"] is False

    # 取回的内容与上传字节一致（内容寻址存的是原字节）
    fetched = sclient.get(f"/api/scratch/works/{work['id']}/content.sb3")
    assert fetched.status_code == 200
    assert fetched.content == data
    assert fetched.headers["content-type"] == "application/x.scratch.sb3"

    # 同内容再存一次 → unchanged，不产生新落盘
    again = save_work(sclient, work["id"], data)
    assert again.json()["unchanged"] is True

    # 详情回填了结构摘要
    detail = sclient.get(f"/api/scratch/works/{work['id']}").json()
    assert detail["sprite_count"] == 1
    assert detail["has_content"] is True
    assert detail["content_url"] == f"/api/scratch/works/{work['id']}/content.sb3"


def test_save_rejects_broken_zip(tmp_path: Path):
    app = scratch_env(tmp_path)
    sclient = student_login(app)
    work = new_work(sclient)
    bad = b"this is not a zip"
    resp = save_work(sclient, work["id"], bad)
    assert resp.status_code == 400
    assert "sb3" in resp.json()["detail"]

    # 坏的没落库：作品保持没有内容
    detail = sclient.get(f"/api/scratch/works/{work['id']}").json()
    assert detail["has_content"] is False


def test_save_rate_limited(tmp_path: Path):
    app = scratch_env(tmp_path)
    sclient = student_login(app)
    work = new_work(sclient)
    data = sb3_bytes()
    # 默认 30 次 / 60 秒；第 31 次触发 429
    for _ in range(30):
        save_work(sclient, work["id"], data)
    resp = save_work(sclient, work["id"], data)
    assert resp.status_code == 429


def test_patch_updates_only_provided_fields(tmp_path: Path):
    app = scratch_env(tmp_path)
    sclient = student_login(app)
    work = new_work(sclient, title="原名")
    patched = patch_work(sclient, work["id"], is_public=False)
    assert patched.status_code == 200, patched.text
    body = patched.json()
    assert body["is_public"] is False
    assert body["title"] == "原名"          # 没传的字段不动

    patched = patch_work(sclient, work["id"], title="新名", description="  描述  ")
    body = patched.json()
    assert body["title"] == "新名"
    assert body["description"] == "描述"    # 两端去空白
    assert body["is_public"] is False


def test_delete_then_gone(tmp_path: Path):
    app = scratch_env(tmp_path)
    sclient = student_login(app)
    work = new_work(sclient)
    resp = sclient.delete(f"/api/scratch/works/{work['id']}", headers=scsrf(sclient))
    assert resp.status_code == 204
    assert sclient.get(f"/api/scratch/works/{work['id']}").status_code == 404
    assert sclient.get(f"/api/scratch/works/{work['id']}/content.sb3").status_code == 404


# ---------- 归属：跨学生一律 404 ----------


def test_cross_student_work_is_404(tmp_path: Path):
    app = scratch_env(tmp_path)
    alice, bob = two_students(app)
    work = new_work(alice)
    data = sb3_bytes()

    assert bob.get(f"/api/scratch/works/{work['id']}").status_code == 404
    assert save_work(bob, work["id"], data).status_code == 404
    assert bob.get(f"/api/scratch/works/{work['id']}/content.sb3").status_code == 404
    assert patch_work(bob, work["id"], title="篡改").status_code == 404
    assert bob.delete(f"/api/scratch/works/{work['id']}",
                      headers=scsrf(bob)).status_code == 404

    # alice 的作品列表里只有自己的
    bob_list = bob.get("/api/scratch/works").json()["items"]
    assert bob_list == []
    alice_list = alice.get("/api/scratch/works").json()["items"]
    assert [w["id"] for w in alice_list] == [work["id"]]


# ---------- 分享闯关作品到广场 ----------


def _shared_work(app, sclient):
    """学生完成一次闯关保存，把项目分享到广场。返回 (share_resp, project_id)。"""
    built = build_scratch_lesson(app)
    block_id = built["block_ids"][0]
    ctx = sclient.get(f"/api/scratch/lesson-blocks/{block_id}").json()
    project_id = ctx["project"]["id"]
    save = sclient.put(
        f"/api/scratch/projects/{project_id}", headers=scsrf(sclient),
        files={"file": ("p.sb3", sb3_bytes([stage_target(), scripted_sprite(name="闯关猫")]),
                        "application/zip")},
        data={"source": "manual", "challenge_id": str(ctx["challenge"]["id"])},
    )
    assert save.status_code == 200, save.text
    resp = sclient.post("/api/scratch/works/share", headers=scsrf(sclient),
                        json={"project_id": project_id})
    assert resp.status_code == 200, resp.text
    return resp.json(), project_id


def test_share_project_snapshots_work(tmp_path: Path):
    app = scratch_env(tmp_path)
    sclient = student_login(app)
    shared, project_id = _shared_work(app, sclient)

    assert shared["source"] == "challenge"
    assert shared["source_challenge_id"] is not None
    assert shared["already_shared"] is False
    assert shared["is_public"] is True
    assert shared["title"] == "绿旗动一动"      # 标题取挑战标题
    assert shared["sprite_count"] == 1

    # 广场副本能取回内容，且与闯关工作副本同一份字节
    content = sclient.get(f"/api/scratch/works/{shared['id']}/content.sb3")
    assert content.status_code == 200
    project_content = sclient.get(f"/api/scratch/projects/{project_id}/content.sb3")
    assert content.content == project_content.content


def test_share_is_idempotent(tmp_path: Path):
    app = scratch_env(tmp_path)
    sclient = student_login(app)
    _shared, project_id = _shared_work(app, sclient)
    again = sclient.post("/api/scratch/works/share", headers=scsrf(sclient),
                         json={"project_id": project_id}).json()
    assert again["already_shared"] is True
    works = sclient.get("/api/scratch/works").json()["items"]
    assert len(works) == 1                     # 不产生第二份


def test_share_requires_saved_content(tmp_path: Path):
    app = scratch_env(tmp_path)
    built = build_scratch_lesson(app)
    sclient = student_login(app)
    block_id = built["block_ids"][0]
    # 打开挑战会建档，但没保存任何版本
    ctx = sclient.get(f"/api/scratch/lesson-blocks/{block_id}").json()
    project_id = ctx["project"]["id"]
    resp = sclient.post("/api/scratch/works/share", headers=scsrf(sclient),
                        json={"project_id": project_id})
    assert resp.status_code == 400
    assert "保存" in resp.json()["detail"]


def test_share_cross_student_project_is_404(tmp_path: Path):
    app = scratch_env(tmp_path)
    built = build_scratch_lesson(app)
    alice, bob = two_students(app)
    block_id = built["block_ids"][0]
    ctx = alice.get(f"/api/scratch/lesson-blocks/{block_id}").json()
    project_id = ctx["project"]["id"]
    resp = bob.post("/api/scratch/works/share", headers=scsrf(bob),
                    json={"project_id": project_id})
    assert resp.status_code == 404


def test_editing_shared_work_does_not_affect_challenge(tmp_path: Path):
    app = scratch_env(tmp_path)
    sclient = student_login(app)
    shared, project_id = _shared_work(app, sclient)
    # 在广场副本上继续创作（存另一份内容）
    save_work(sclient, shared["id"], sb3_bytes([stage_target(), scripted_sprite(name="新角色")]))
    # 闯关工作副本不被回流（.sb3 是 zip，解出 project.json 读角色名）
    project_content = sclient.get(f"/api/scratch/projects/{project_id}/content.sb3")
    with zipfile.ZipFile(BytesIO(project_content.content)) as archive:
        project_payload = json.loads(archive.read("project.json").decode("utf-8"))
    sprite_names = [t["name"] for t in project_payload["targets"] if not t.get("isStage")]
    assert "新角色" not in sprite_names


# ---------- 画廊 ----------


def _gallery_env(tmp_path: Path):
    """两个学生、每人若干作品，控制公开/私密与浏览数。a1 保存过内容。"""
    app = scratch_env(tmp_path)
    alice, bob = two_students(app)
    a1 = new_work(alice, title="小猫的冒险")
    a2 = new_work(alice, title="小猫的冒险 2 代")
    b1 = new_work(bob, title="小黄鸭乐园")
    save_work(alice, a1["id"], sb3_bytes([stage_target(), scripted_sprite(name="冒险猫")]))
    # a2 设为私密
    patch_work(alice, a2["id"], is_public=False)
    # 给 a1 造 2 次浏览（画廊详情接口 +1）
    for _ in range(2):
        alice.get(f"/api/scratch/gallery/{a1['id']}")
    return app, alice, bob, {"a1": a1, "b1": b1, "a2": a2}


def test_gallery_lists_only_public(tmp_path: Path):
    app, alice, _bob, works = _gallery_env(tmp_path)
    body = gallery(alice).json()
    ids = {w["id"] for w in body["items"]}
    assert ids == {works["a1"]["id"], works["b1"]["id"]}     # 私密的 a2 不在
    assert body["total"] == 2
    # 列表项带作者信息，且不泄露取回路径（content_url 只在"我的作品"视图里给）
    for item in body["items"]:
        assert item["author"]["username"] in ("alice", "bob")
        assert "content_url" not in item


def test_gallery_pagination_and_keyword(tmp_path: Path):
    app, alice, _bob, works = _gallery_env(tmp_path)
    body = gallery(alice, page=1, size=1).json()
    assert body["total"] == 2
    assert len(body["items"]) == 1
    body = gallery(alice, page=2, size=1).json()
    assert len(body["items"]) == 1
    assert body["page"] == 2

    kw = gallery(alice, keyword="小黄鸭").json()
    assert [w["id"] for w in kw["items"]] == [works["b1"]["id"]]


def test_gallery_detail_counts_views_and_popular_sort(tmp_path: Path):
    app, alice, _bob, works = _gallery_env(tmp_path)
    detail = alice.get(f"/api/scratch/gallery/{works['a1']['id']}").json()
    assert detail["views"] >= 3                 # 环境里打开过 2 次 + 这一次
    assert detail["mine"] is True               # 自己的作品也能在画廊看到（公开的）

    popular = gallery(alice, sort="popular").json()
    assert popular["items"][0]["id"] == works["a1"]["id"]   # 浏览最多排最前

    latest = gallery(alice, sort="latest").json()
    assert latest["items"][0]["id"] == works["b1"]["id"]    # 后创建的排前


def test_gallery_hides_private_and_content(tmp_path: Path):
    app, alice, bob, works = _gallery_env(tmp_path)
    assert alice.get(f"/api/scratch/gallery/{works['a2']['id']}").status_code == 404
    assert bob.get(f"/api/scratch/gallery/{works['a2']['id']}/content.sb3").status_code == 404
    # 公开作品的内容，另一个学生可读
    content = bob.get(f"/api/scratch/gallery/{works['a1']['id']}/content.sb3")
    assert content.status_code == 200
    # 详情接口也能看到作者
    detail = bob.get(f"/api/scratch/gallery/{works['a1']['id']}").json()
    assert detail["author"]["username"] == "alice"
    assert detail["mine"] is False


def test_gallery_missing_is_404(tmp_path: Path):
    app, alice, _bob, _works = _gallery_env(tmp_path)
    assert alice.get("/api/scratch/gallery/99999").status_code == 404
    assert alice.get("/api/scratch/gallery/99999/content.sb3").status_code == 404


def test_gallery_only_after_public_toggle(tmp_path: Path):
    """公开/私密切换即时生效：切私密后从画廊消失，切回公开后重新出现。"""
    app = scratch_env(tmp_path)
    sclient = student_login(app)
    work = new_work(sclient)
    assert [w["id"] for w in gallery(sclient).json()["items"]] == [work["id"]]
    patch_work(sclient, work["id"], is_public=False)
    assert gallery(sclient).json()["items"] == []
    patch_work(sclient, work["id"], is_public=True)
    assert [w["id"] for w in gallery(sclient).json()["items"]] == [work["id"]]


def test_db_rows_survive_project_delete(tmp_path: Path):
    """闯关副本删除后，分享出来的广场作品不受牵连（外键 SET NULL 溯源）。"""
    app = scratch_env(tmp_path)
    sclient = student_login(app)
    shared, project_id = _shared_work(app, sclient)
    # 学生端没有删除闯关项目的端点（这本来就不该有）；这里直接验证外键语义：
    # 删除闯关项目行后作品仍在。手动删行模拟。
    db = app.state.session_factory()
    try:
        from app.models import ScratchProject
        project = db.get(ScratchProject, project_id)
        db.delete(project)
        db.commit()
    finally:
        db.close()
    assert sclient.get(f"/api/scratch/works/{shared['id']}").status_code == 200
