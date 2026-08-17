"""内容块解锁体系（两道闸门）+ 完成上报回归。

对应《14、单课时学习界面-开发交接》第四/五节与 §6 P6 测试清单：

Gate A 权限闸（既有 open_policy）与 Gate B 路径闸（新增 unlock_rule）正交，
合成 lock_reason 供前端选文案与出口。本文件覆盖：

- free 块不受前置影响；sequential 块要求前置全完成；
- **选学块（required=False）不阻塞闯关**（否则老师加一个「拓展阅读」全班卡住）；
- **无权限块不能当前置条件**（否则 first_n 的未开通学生会被永久卡死在一条
  「回去学前面」的死循环里——本文件最重要的一条回归）；
- 判定顺序 A 先于 B：两道都不满足时返回 not_enrolled；
- 顺序锁的块不下发正文（can_access=true 也不行，防提前读走）；
- 完成上报：幂等 / 越权 403 且不写库 / 视频阈值 / unlocked_block_ids / progress 分母。
"""
from pathlib import Path

from sqlalchemy import select
from test_admin_course_content import block_payload
from test_admin_courses import add_section, create_category, create_course
from test_exam import admin_login, build_app, scsrf, student_login

from app.models import LessonBlockCompletion

# ---------- 辅助 ----------


_seq = {"n": 0}


def build_lesson_with_blocks(app, blocks, *, open_policy="whole", trial_block_count=0,
                             publish=True):
    """建分类→课包→章节→课时→按 blocks 建内容块→发布。

    blocks: [{"block_type"?, "title"?, "required"?, "unlock_rule"?, **明细字段}, ...]
    明细拼装复用 test_admin_course_content.block_payload，不另造一套。
    返回 {"client", "headers", "course_id", "lesson_id", "block_ids": [...]}。
    """
    client, headers = admin_login(app)
    _seq["n"] += 1
    n = _seq["n"]  # 同一个 app 里可以建多个课包：分类名/课包名唯一，否则 409
    cat = create_category(client, headers, name=f"分类{n}").json()
    course = create_course(client, headers, cat["id"], title=f"课包{n}").json()
    section = add_section(client, headers, course["id"]).json()
    # 注意：**不能传 is_trial**。admin_courses._resolve_open_policy 规定「显式传 is_trial
    # 时以它为准（True→whole / False→closed）」，传了会把 open_policy 覆盖掉。
    lesson = client.post(
        f"/api/admin/sections/{section['id']}/lessons",
        headers=headers,
        json={
            "title": "课时 1", "duration_minutes": 30,
            "open_policy": open_policy,
            "trial_block_count": trial_block_count,
        },
    ).json()
    block_ids = []
    for spec in blocks:
        spec = dict(spec)
        block_type = spec.pop("block_type", "markdown")
        title = spec.pop("title", "块")
        required = spec.pop("required", True)
        unlock_rule = spec.pop("unlock_rule", "free")
        body = block_payload(block_type, **spec)
        body.update({"title": title, "required": required, "unlock_rule": unlock_rule})
        resp = client.post(f"/api/admin/lessons/{lesson['id']}/blocks", headers=headers, json=body)
        assert resp.status_code in (200, 201), resp.text
        block_ids.append(resp.json()["id"])
    if publish:
        pub = client.post(f"/api/admin/courses/{course['id']}/publish", headers=headers)
        assert pub.status_code == 200, pub.text
    return {"client": client, "headers": headers, "course_id": course["id"],
            "lesson_id": lesson["id"], "block_ids": block_ids}


def reasons(sclient, lesson_id):
    """取课时详情里每块的 lock_reason 列表。"""
    resp = sclient.get(f"/api/lessons/{lesson_id}")
    assert resp.status_code == 200, resp.text
    return [b["lock_reason"] for b in resp.json()["blocks"]]


def complete(sclient, lesson_id, block_id, **body):
    return sclient.post(
        f"/api/lessons/{lesson_id}/blocks/{block_id}/complete",
        headers=scsrf(sclient), json=body or {"source": "manual"},
    )


# ---------- Gate B 基本行为 ----------


def test_free_blocks_never_locked_by_order(tmp_path: Path):
    """unlock_rule=free：无论前置是否完成，永远不是顺序锁。"""
    app = build_app(tmp_path)
    built = build_lesson_with_blocks(app, [
        {"title": "A"}, {"title": "B"}, {"title": "C"},
    ])
    sclient = student_login(app)
    assert reasons(sclient, built["lesson_id"]) == [None, None, None]


def test_sequential_block_requires_all_previous_done(tmp_path: Path):
    """sequential：前置未完成 → sequential；逐个完成后 → 解锁。"""
    app = build_app(tmp_path)
    built = build_lesson_with_blocks(app, [
        {"title": "A"}, {"title": "B"}, {"title": "C", "unlock_rule": "sequential"},
    ])
    lid, bids = built["lesson_id"], built["block_ids"]
    sclient = student_login(app)
    assert reasons(sclient, lid) == [None, None, "sequential"]

    assert complete(sclient, lid, bids[0]).status_code == 200
    assert reasons(sclient, lid) == [None, None, "sequential"]  # B 还没完成

    resp = complete(sclient, lid, bids[1])
    assert resp.status_code == 200
    # 本次上报把 C 解锁了，接口直接告诉前端，免得为一个锁图标重拉整节课
    assert resp.json()["unlocked_block_ids"] == [bids[2]]
    assert reasons(sclient, lid) == [None, None, None]


def test_optional_block_does_not_block_unlock(tmp_path: Path):
    """坑 1：required=False 的选学块不阻塞闯关。

    否则老师加一个「拓展阅读（选学）」，没人点它，后面的闯关块就永远开不了。
    """
    app = build_app(tmp_path)
    built = build_lesson_with_blocks(app, [
        {"title": "A"},
        {"title": "拓展阅读（选学）", "required": False},
        {"title": "C", "unlock_rule": "sequential"},
    ])
    lid, bids = built["lesson_id"], built["block_ids"]
    sclient = student_login(app)
    assert reasons(sclient, lid) == [None, None, "sequential"]

    # 只完成必修的 A，选学块不管 → C 直接解锁
    assert complete(sclient, lid, bids[0]).status_code == 200
    assert reasons(sclient, lid) == [None, None, None]


def test_completed_block_never_relocks(tmp_path: Path):
    """已学完的块不会被闸门重新锁上。

    真实场景：学生学完整节课后，老师把中间某块改成 sequential（或把前置块从选学改成
    必修）。若不豁免已完成的块，学生已经学过的块会突然显示「按顺序解锁 · 回去学前面」，
    界面上还会出现「已完成 + 锁定」的自相矛盾态。
    """
    app = build_app(tmp_path)
    built = build_lesson_with_blocks(app, [
        {"title": "A"}, {"title": "B"}, {"title": "C", "unlock_rule": "sequential"},
    ], publish=False)
    client, headers = built["client"], built["headers"]
    lid, bids = built["lesson_id"], built["block_ids"]
    assert client.post(f"/api/admin/courses/{built['course_id']}/publish",
                       headers=headers).status_code == 200

    sclient = student_login(app)
    complete(sclient, lid, bids[0])
    complete(sclient, lid, bids[1])
    complete(sclient, lid, bids[2])            # C 也学完了
    assert reasons(sclient, lid) == [None, None, None]

    # 老师事后把 B 也改成按顺序解锁，并且学生的 A 完成记录因故不在了
    db = app.state.session_factory()
    try:
        db.query(LessonBlockCompletion).filter_by(block_id=bids[0]).delete()
        db.commit()
    finally:
        db.close()

    # B 没学完 → 按顺序仍锁；C 已学完 → 保持开放，不会被赶回去
    assert reasons(sclient, lid) == [None, None, None]
    blocks = sclient.get(f"/api/lessons/{lid}").json()["blocks"]
    assert blocks[2]["completed"] is True and blocks[2]["is_unlocked"] is True


def test_progress_denominator_counts_required_only(tmp_path: Path):
    """进度分母只数 required=True 的块（选学块完成了照样记录，但不计入分母）。"""
    app = build_app(tmp_path)
    built = build_lesson_with_blocks(app, [
        {"title": "A"}, {"title": "B（选学）", "required": False}, {"title": "C"},
    ])
    lid, bids = built["lesson_id"], built["block_ids"]
    sclient = student_login(app)
    assert sclient.get(f"/api/lessons/{lid}").json()["progress"] == {
        "total": 2, "done": 0, "percent": 0}

    complete(sclient, lid, bids[1])  # 完成选学块
    prog = sclient.get(f"/api/lessons/{lid}").json()["progress"]
    assert prog == {"total": 2, "done": 0, "percent": 0}, "选学块不该进分子分母"
    # 但记录本身要落库（将来学情分析要用）
    assert sclient.get(f"/api/lessons/{lid}").json()["blocks"][1]["completed"] is True

    complete(sclient, lid, bids[0])
    assert sclient.get(f"/api/lessons/{lid}").json()["progress"] == {
        "total": 2, "done": 1, "percent": 50}


# ---------- 两道闸门的交互（最容易写错的部分） ----------


def test_paywalled_block_is_not_a_sequential_prerequisite(tmp_path: Path):
    """坑 2（本文件最重要）：没权限的块不能当 sequential 的前置条件。

    first_n=2 的未开通学生：第 3 块没权限 → 永远完成不了。若把它当作前置条件，
    第 4 块的 sequential 就永远不满足 → 显示成「顺序锁」并给出「回去学前面」的出口，
    而学生**根本没有权限去学第 3 块** —— 死循环。
    正确行为：第 3、4 块一律是权限锁，出口指向开通页。
    """
    app = build_app(tmp_path)
    built = build_lesson_with_blocks(app, [
        {"title": "A"}, {"title": "B"},
        {"title": "C"}, {"title": "D", "unlock_rule": "sequential"},
    ], open_policy="first_n", trial_block_count=2)
    lid, bids = built["lesson_id"], built["block_ids"]
    sclient = student_login(app)

    # 未开通：前 2 块可学，后 2 块是**权限锁**而不是顺序锁
    assert reasons(sclient, lid) == [None, None, "not_enrolled", "not_enrolled"]

    # 把有权限的前 2 块都学完，D 仍然是权限锁（不会退化成顺序锁的死循环）
    complete(sclient, lid, bids[0])
    complete(sclient, lid, bids[1])
    assert reasons(sclient, lid) == [None, None, "not_enrolled", "not_enrolled"]


def test_gate_order_permission_wins(tmp_path: Path):
    """判定顺序不可颠倒：两道闸门都不满足时返回 not_enrolled 而不是 sequential。

    颠倒之后未开通学生会先撞上「完成前面的内容块」这条错误引导。
    """
    app = build_app(tmp_path)
    built = build_lesson_with_blocks(app, [
        {"title": "A"}, {"title": "B", "unlock_rule": "sequential"},
    ], open_policy="closed")
    sclient = student_login(app)
    # closed：两块都没权限；B 同时也不满足顺序条件 —— 但返回的必须是 not_enrolled
    assert reasons(sclient, built["lesson_id"]) == ["not_enrolled", "not_enrolled"]


def test_sequential_locked_block_hides_content(tmp_path: Path):
    """顺序锁的块不下发正文：can_access=true 也不行，防止提前把内容读走。"""
    app = build_app(tmp_path)
    built = build_lesson_with_blocks(app, [
        {"title": "A"}, {"title": "B", "unlock_rule": "sequential"},
    ])
    sclient = student_login(app)
    blocks = sclient.get(f"/api/lessons/{built['lesson_id']}").json()["blocks"]
    locked = blocks[1]
    assert locked["lock_reason"] == "sequential"
    assert locked["can_access"] is True, "Gate A 是通过的，锁在 Gate B"
    assert locked["is_unlocked"] is False
    assert "content_md" not in locked, "顺序锁的块不能下发正文"
    assert locked["title"] == "B", "标题仍然可见（要在导航里显示）"


def test_anonymous_cannot_read_lesson_detail(tmp_path: Path):
    """未登录取课时详情是 401——闸门之前先撞登录墙。

    course_access 里 `user is None` 的分支不是死代码：video_play 等调用方可能拿到
    匿名 user，那里 sequential 一律锁。但 GET /api/lessons/{id} 本身要求登录。
    """
    app = build_app(tmp_path)
    built = build_lesson_with_blocks(app, [
        {"title": "A"}, {"title": "B", "unlock_rule": "sequential"},
    ])
    from fastapi.testclient import TestClient

    anon = TestClient(app)
    assert anon.get(f"/api/lessons/{built['lesson_id']}").status_code == 401


# ---------- 完成上报 ----------


def test_complete_is_idempotent(tmp_path: Path):
    """重复上报返回 200 且只写一行（幂等，§5.3）。"""
    app = build_app(tmp_path)
    built = build_lesson_with_blocks(app, [{"title": "A"}])
    lid, bid = built["lesson_id"], built["block_ids"][0]
    sclient = student_login(app)

    assert complete(sclient, lid, bid).status_code == 200
    assert complete(sclient, lid, bid).status_code == 200

    db = app.state.session_factory()
    try:
        rows = db.query(LessonBlockCompletion).filter_by(block_id=bid).all()
        assert len(rows) == 1, f"重复上报写了 {len(rows)} 行"
    finally:
        db.close()


def test_complete_rejected_when_locked_and_writes_nothing(tmp_path: Path):
    """越权上报 403，且**不写入任何记录**。

    否则学生可以直接 POST 把没权限/没轮到的块刷成已完成，整条闸门被绕过去。
    """
    app = build_app(tmp_path)
    built = build_lesson_with_blocks(app, [
        {"title": "A"}, {"title": "B"},
        {"title": "C"}, {"title": "D", "unlock_rule": "sequential"},
    ], open_policy="first_n", trial_block_count=2)
    lid, bids = built["lesson_id"], built["block_ids"]
    sclient = student_login(app)

    r = complete(sclient, lid, bids[2])  # 权限锁
    assert r.status_code == 403 and "开放" in r.json()["detail"]

    db = app.state.session_factory()
    try:
        assert db.query(LessonBlockCompletion).count() == 0, "被拒绝的上报不该落库"
    finally:
        db.close()

    # 顺序锁（整节开放的另一节课时）
    built2 = build_lesson_with_blocks(app, [
        {"title": "A"}, {"title": "B", "unlock_rule": "sequential"},
    ])
    r2 = complete(sclient, built2["lesson_id"], built2["block_ids"][1])
    assert r2.status_code == 403 and "前面" in r2.json()["detail"]


def test_complete_video_respects_completion_percent(tmp_path: Path):
    """视频块：进度达不到块配置的 completion_percent 就不写记录，只回中间态。"""
    app = build_app(tmp_path)
    built = build_lesson_with_blocks(app, [{
        "block_type": "video", "title": "视频块",
        "source_type": "embed", "video_url": "https://example.com/v.mp4",
        "completion_percent": 80,
    }])
    lid, bid = built["lesson_id"], built["block_ids"][0]
    sclient = student_login(app)

    r = complete(sclient, lid, bid, source="video", progress_percent=50)
    assert r.status_code == 200 and r.json()["completed"] is False
    assert r.json()["progress"]["done"] == 0

    r = complete(sclient, lid, bid, source="video", progress_percent=80)
    assert r.status_code == 200 and r.json()["completed"] is True
    assert r.json()["progress"]["done"] == 1


def test_video_threshold_cannot_be_bypassed_by_source(tmp_path: Path):
    """视频块的完成阈值按 block_type 判，不按客户端自报的 source 判。

    阈值检查曾经写成 `if source == "video":`——于是把 source 换成 "manual" 就整段
    跳过了检查，completion_percent 连同依赖它的 sequential 闯关闸一起被绕过。
    客户端能决定的只是"报什么进度"，不该由它决定"要不要过这道闸"。
    """
    app = build_app(tmp_path)
    built = build_lesson_with_blocks(app, [{
        "block_type": "video", "title": "视频块",
        "source_type": "embed", "video_url": "https://example.com/v.mp4",
        "completion_percent": 80,
    }])
    lid, bid = built["lesson_id"], built["block_ids"][0]
    sclient = student_login(app)

    # 换个 source 不该让阈值失效
    r = complete(sclient, lid, bid, source="manual", progress_percent=0)
    assert r.status_code == 200 and r.json()["progress"]["done"] == 0, "source=manual 绕过了阈值"

    # 空 body 也不行：没报进度按 0 算，不能靠缺省值蒙混过关
    r = complete(sclient, lid, bid)
    assert r.status_code == 200 and r.json()["progress"]["done"] == 0, "缺省进度绕过了阈值"

    # 达标才算数，且完成来源如实记成 video
    r = complete(sclient, lid, bid, source="manual", progress_percent=90)
    assert r.status_code == 200 and r.json()["progress"]["done"] == 1
    db = app.state.session_factory()
    try:
        row = db.scalar(select(LessonBlockCompletion).where(LessonBlockCompletion.block_id == bid))
        assert row.source == "video"
    finally:
        db.close()


def test_complete_unknown_block_404(tmp_path: Path):
    """块不属于该课时 → 404（不能拿别的课时的块 id 来刷完成）。"""
    app = build_app(tmp_path)
    a = build_lesson_with_blocks(app, [{"title": "A"}])
    b = build_lesson_with_blocks(app, [{"title": "B"}])
    sclient = student_login(app)
    r = complete(sclient, a["lesson_id"], b["block_ids"][0])
    assert r.status_code == 404


def test_admin_block_api_round_trips_unlock_rule(tmp_path: Path):
    """管理端能读写 unlock_rule，且非法值被拒。（不发布：已发布课包的内容块不可编辑）"""
    app = build_app(tmp_path)
    built = build_lesson_with_blocks(app, [{"title": "A", "unlock_rule": "sequential"}],
                                     publish=False)
    client, headers = built["client"], built["headers"]
    bid = built["block_ids"][0]

    data = client.get(f"/api/admin/lessons/{built['lesson_id']}/blocks", headers=headers).json()
    assert data["blocks"][0]["unlock_rule"] == "sequential"

    body = block_payload("markdown", content_md="# 正文内容")
    up = client.put(f"/api/admin/lesson-blocks/{bid}", headers=headers,
                    json={**body, "unlock_rule": "free"})
    assert up.status_code == 200 and up.json()["unlock_rule"] == "free"

    bad = client.put(f"/api/admin/lesson-blocks/{bid}", headers=headers,
                     json={**body, "unlock_rule": "whatever"})
    assert bad.status_code == 422
