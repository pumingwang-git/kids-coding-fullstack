"""课包-课程管理（阶段 1 最小闭环）。

盯住四件事：
1. 课包 CRUD 与发布状态机（draft → published → off_shelf，已发布不可直接删）；
2. 发布前完整性校验——缺章节 / 缺课时 / 课时无内容 都必须拦在发布之外；
3. 章节、课时的拖拽排序（重写 sort_order 的顺序正确性）；
4. 越权——reviewer 只读，不能建课包、不能发布。
"""
from pathlib import Path

from fastapi.testclient import TestClient
from test_exam import ADMIN_PASSWORD, admin_login, build_app

from app.models import AdminUser, Problem
from app.security import password_hash  # 复用现有哈希封装


def reviewer_login(app) -> tuple[TestClient, dict]:
    db = app.state.session_factory()
    try:
        if db.get(AdminUser, 2) is None:
            db.add(AdminUser(id=2, username="reviewer1", password_hash=password_hash.hash(ADMIN_PASSWORD),
                             display_name="reviewer", role="reviewer"))
            db.commit()
    finally:
        db.close()
    client = TestClient(app)
    client.get("/api/admin/csrf")
    headers = {"X-CSRF-Token": client.cookies.get("admin_csrf_token")}
    response = client.post("/api/admin/login", headers=headers,
                           json={"username": "reviewer1", "password": ADMIN_PASSWORD})
    assert response.status_code == 200, response.text
    return client, headers


def create_category(client, headers, name="编程入门"):
    return client.post("/api/admin/course-categories", headers=headers, json={"name": name})


def create_course(client, headers, category_id, title="CSP-J 冲刺营"):
    return client.post("/api/admin/courses", headers=headers, json={
        "title": title,
        "subtitle": "零基础到参赛",
        "description": "# 课程简介\n\n面向初学者的 CSP-J 系统课。",
        "category_id": category_id,
        "difficulty": "beginner",
        "price_cents": 9900,
    })


def add_section(client, headers, course_id, title="第一章"):
    return client.post(f"/api/admin/courses/{course_id}/sections", headers=headers, json={"title": title})


def add_lesson(client, headers, section_id, title="课时 1", content_md="# 你好"):
    return client.post(f"/api/admin/sections/{section_id}/lessons", headers=headers, json={
        "title": title, "content_md": content_md, "duration_minutes": 30,
    })


def test_course_full_lifecycle(tmp_path: Path):
    """建分类 → 建课包 → 加章节 → 加课时 → 发布 → 下架 → 删除。"""
    app = build_app(tmp_path)
    client, headers = admin_login(app)

    cat = create_category(client, headers).json()
    course = create_course(client, headers, cat["id"]).json()
    assert course["status"] == "draft"
    assert course["area_key"] == "kids"
    assert course["course_kind"] == "systematic"
    assert course["category_name"] == "编程入门"

    section = add_section(client, headers, course["id"]).json()
    lesson = add_lesson(client, headers, section["id"]).json()
    assert lesson["section_id"] == section["id"]

    # 发布成功
    assert client.post(f"/api/admin/courses/{course['id']}/publish", headers=headers).status_code == 200
    listed = client.get(f"/api/admin/courses/{course['id']}", headers=headers).json()
    assert listed["status"] == "published"
    assert listed["section_count"] == 1 and listed["lesson_count"] == 1

    # 已发布不可直接删
    assert client.delete(f"/api/admin/courses/{course['id']}", headers=headers).status_code == 409

    # 下架后可删
    assert client.post(f"/api/admin/courses/{course['id']}/off-shelf", headers=headers).status_code == 200
    assert client.delete(f"/api/admin/courses/{course['id']}", headers=headers).status_code == 200
    assert client.get(f"/api/admin/courses/{course['id']}", headers=headers).status_code == 404


def test_publish_validations(tmp_path: Path):
    app = build_app(tmp_path)
    client, headers = admin_login(app)
    cat = create_category(client, headers).json()
    course = create_course(client, headers, cat["id"]).json()
    cid = course["id"]

    # 无章节：拦截（结构化问题列表，code 定位）
    resp = client.post(f"/api/admin/courses/{cid}/publish", headers=headers)
    assert resp.status_code == 422 and resp.json()["detail"] == "课包暂不能发布。"
    assert "no_section" in [p["code"] for p in resp.json()["problems"]]

    # 有章节无课时：拦截
    section = add_section(client, headers, cid).json()
    resp = client.post(f"/api/admin/courses/{cid}/publish", headers=headers)
    assert resp.status_code == 422 and "no_lesson" in [p["code"] for p in resp.json()["problems"]]

    # 课时无内容：拦截
    empty = add_lesson(client, headers, section["id"], title="空课时", content_md=None).json()
    resp = client.post(f"/api/admin/courses/{cid}/publish", headers=headers)
    assert resp.status_code == 422
    assert "no_content" in [p["code"] for p in resp.json()["problems"]]

    # 补齐内容后发布成功
    client.put(f"/api/admin/lessons/{empty['id']}", headers=headers,
               json={"title": "空课时", "content_md": "# 补上内容", "duration_minutes": 10}).status_code == 200
    assert client.post(f"/api/admin/courses/{cid}/publish", headers=headers).status_code == 200


def test_section_and_lesson_reorder(tmp_path: Path):
    """拖拽排序：按 ids 顺序重写 sort_order，且缺一不可（防前端丢行）。"""
    app = build_app(tmp_path)
    client, headers = admin_login(app)
    cat = create_category(client, headers).json()
    course = create_course(client, headers, cat["id"]).json()
    cid = course["id"]

    s1 = add_section(client, headers, cid, "第二章").json()
    s2 = add_section(client, headers, cid, "第一章").json()
    s3 = add_section(client, headers, cid, "第三章").json()

    # 章节倒序
    assert client.post(f"/api/admin/courses/{cid}/sections/reorder", headers=headers,
                       json={"ids": [s3["id"], s1["id"], s2["id"]]}).status_code == 200
    tree = client.get(f"/api/admin/courses/{cid}/sections", headers=headers).json()
    assert [s["title"] for s in tree["sections"]] == ["第三章", "第二章", "第一章"]

    # 缺 id：拒绝（排序列表必须与当前一致）
    resp = client.post(f"/api/admin/courses/{cid}/sections/reorder", headers=headers,
                       json={"ids": [s1["id"], s2["id"]]})
    assert resp.status_code == 400

    # 课时排序
    l1 = add_lesson(client, headers, s1["id"], "B").json()
    l2 = add_lesson(client, headers, s1["id"], "A").json()
    assert client.post(f"/api/admin/sections/{s1['id']}/lessons/reorder", headers=headers,
                       json={"ids": [l2["id"], l1["id"]]}).status_code == 200
    tree = client.get(f"/api/admin/courses/{cid}/sections", headers=headers).json()
    s1_lessons = [s for s in tree["sections"] if s["id"] == s1["id"]][0]["lessons"]
    assert [lesson["title"] for lesson in s1_lessons] == ["A", "B"]


def test_lesson_move_across_sections(tmp_path: Path):
    """跨章节移动：目标章节接收并重排，源章节 sort_order 压实。"""
    app = build_app(tmp_path)
    client, headers = admin_login(app)
    cat = create_category(client, headers).json()
    cid = create_course(client, headers, cat["id"]).json()["id"]

    s1 = add_section(client, headers, cid, "第一章").json()
    s2 = add_section(client, headers, cid, "第二章").json()
    add_lesson(client, headers, s1["id"], "A").json()
    b = add_lesson(client, headers, s1["id"], "B").json()
    c = add_lesson(client, headers, s2["id"], "C").json()

    # 把 B 拖到第二章、放在 C 前面
    resp = client.post(f"/api/admin/lessons/{b['id']}/move", headers=headers,
                       json={"target_section_id": s2["id"], "ordered_ids": [b["id"], c["id"]]})
    assert resp.status_code == 200, resp.text

    tree = client.get(f"/api/admin/courses/{cid}/sections", headers=headers).json()
    by_section = {s["id"]: s for s in tree["sections"]}
    assert [lesson["title"] for lesson in by_section[s1["id"]]["lessons"]] == ["A"]
    assert [lesson["title"] for lesson in by_section[s2["id"]]["lessons"]] == ["B", "C"]
    # 源章节压实：剩下的 A 回到 0
    assert by_section[s1["id"]]["lessons"][0]["sort_order"] == 0
    # 目标章节连续从 0 开始
    assert [lesson["sort_order"] for lesson in by_section[s2["id"]]["lessons"]] == [0, 1]
    # 冗余列 course_id 不受影响
    assert by_section[s2["id"]]["lessons"][0]["section_id"] == s2["id"]


def test_lesson_move_rejects_bad_order_and_rolls_back(tmp_path: Path):
    """ordered_ids 与目标章节对不上 → 400，且课时归属不能被改坏。"""
    app = build_app(tmp_path)
    client, headers = admin_login(app)
    cat = create_category(client, headers).json()
    cid = create_course(client, headers, cat["id"]).json()["id"]
    s1 = add_section(client, headers, cid, "第一章").json()
    s2 = add_section(client, headers, cid, "第二章").json()
    b = add_lesson(client, headers, s1["id"], "B").json()
    add_lesson(client, headers, s2["id"], "C")

    # 漏掉了 C
    resp = client.post(f"/api/admin/lessons/{b['id']}/move", headers=headers,
                       json={"target_section_id": s2["id"], "ordered_ids": [b["id"]]})
    assert resp.status_code == 400

    # 归属必须还在第一章——回滚生效
    tree = client.get(f"/api/admin/courses/{cid}/sections", headers=headers).json()
    by_section = {s["id"]: s for s in tree["sections"]}
    assert [lesson["title"] for lesson in by_section[s1["id"]]["lessons"]] == ["B"]
    assert [lesson["title"] for lesson in by_section[s2["id"]]["lessons"]] == ["C"]


def test_lesson_move_rejects_cross_course_and_reviewer(tmp_path: Path):
    app = build_app(tmp_path)
    client, headers = admin_login(app)
    cat = create_category(client, headers).json()
    c1 = create_course(client, headers, cat["id"], title="课包一").json()["id"]
    c2 = create_course(client, headers, cat["id"], title="课包二").json()["id"]
    s1 = add_section(client, headers, c1, "一章").json()
    s2 = add_section(client, headers, c2, "二章").json()
    lesson = add_lesson(client, headers, s1["id"], "A").json()

    # 跨课包：拒绝
    resp = client.post(f"/api/admin/lessons/{lesson['id']}/move", headers=headers,
                       json={"target_section_id": s2["id"], "ordered_ids": [lesson["id"]]})
    assert resp.status_code == 400 and "同一课包" in resp.json()["detail"]

    # reviewer 只读
    rclient, rheaders = reviewer_login(app)
    resp = rclient.post(f"/api/admin/lessons/{lesson['id']}/move", headers=rheaders,
                        json={"target_section_id": s1["id"], "ordered_ids": [lesson["id"]]})
    assert resp.status_code == 403


def test_reviewer_is_read_only(tmp_path: Path):
    app = build_app(tmp_path)
    client, headers = reviewer_login(app)

    # 读接口可用
    assert client.get("/api/admin/courses", headers=headers).status_code == 200
    assert client.get("/api/admin/course-categories", headers=headers).status_code == 200

    # 写接口全部 403
    assert create_category(client, headers).status_code == 403
    assert client.post("/api/admin/courses", headers=headers,
                       json={"title": "越权课包", "difficulty": "beginner"}).status_code == 403


def test_category_conflict_and_reference(tmp_path: Path):
    app = build_app(tmp_path)
    client, headers = admin_login(app)

    cat = create_category(client, headers, name="同名分类").json()
    # 重名拒绝
    assert create_category(client, headers, name="同名分类").status_code == 409
    # 被课包引用时不可删
    create_course(client, headers, cat["id"])
    assert client.delete(f"/api/admin/course-categories/{cat['id']}", headers=headers).status_code == 409
    # 改名后再删（无引用）成功
    other = create_category(client, headers, name="临时分类").json()
    assert client.delete(f"/api/admin/course-categories/{other['id']}", headers=headers).status_code == 200


def test_course_list_filters(tmp_path: Path):
    app = build_app(tmp_path)
    client, headers = admin_login(app)
    cat = create_category(client, headers).json()
    create_course(client, headers, cat["id"], title="算法基础班")
    create_course(client, headers, cat["id"], title="数据结构班")

    all_rows = client.get("/api/admin/courses", headers=headers).json()
    assert all_rows["total"] == 2

    hit = client.get("/api/admin/courses", headers=headers, params={"keyword": "算法"}).json()
    assert hit["total"] == 1 and hit["items"][0]["title"] == "算法基础班"

    by_status = client.get("/api/admin/courses", headers=headers, params={"status": "published"}).json()
    assert by_status["total"] == 0


def test_published_course_locked_for_editing(tmp_path: Path):
    """发布后编辑保护：已发布课包的属性/章节/课时/排序/跨章移动全部 409，下架后恢复。

    阶段 1 口径：发布校验只在 publish 时跑一次，若发布后仍可改空，学生端会看到
    不完整课程——每个结构修改入口都必须先过 _require_editable。
    """
    app = build_app(tmp_path)
    client, headers = admin_login(app)
    cat = create_category(client, headers).json()
    cid = create_course(client, headers, cat["id"]).json()["id"]
    s1 = add_section(client, headers, cid, "第一章").json()
    s2 = add_section(client, headers, cid, "第二章").json()
    l1 = add_lesson(client, headers, s1["id"], "A").json()
    l2 = add_lesson(client, headers, s2["id"], "B").json()
    assert client.post(f"/api/admin/courses/{cid}/publish", headers=headers).status_code == 200

    # 发布后所有结构修改入口一律 409
    assert client.put(f"/api/admin/courses/{cid}", headers=headers,
                      json={"title": "改", "category_id": None}).status_code == 409
    assert client.post(f"/api/admin/courses/{cid}/sections", headers=headers,
                       json={"title": "新章节"}).status_code == 409
    assert client.put(f"/api/admin/sections/{s1['id']}", headers=headers,
                      json={"title": "改名"}).status_code == 409
    assert client.delete(f"/api/admin/sections/{s1['id']}", headers=headers).status_code == 409
    assert client.post(f"/api/admin/courses/{cid}/sections/reorder", headers=headers,
                       json={"ids": [s1["id"], s2["id"]]}).status_code == 409
    assert client.post(f"/api/admin/sections/{s1['id']}/lessons", headers=headers,
                       json={"title": "新课"}).status_code == 409
    assert client.put(f"/api/admin/lessons/{l1['id']}", headers=headers,
                      json={"title": "改", "content_md": None}).status_code == 409
    assert client.delete(f"/api/admin/lessons/{l1['id']}", headers=headers).status_code == 409
    assert client.post(f"/api/admin/sections/{s1['id']}/lessons/reorder", headers=headers,
                       json={"ids": [l1["id"]]}).status_code == 409
    assert client.post(f"/api/admin/lessons/{l1['id']}/move", headers=headers,
                       json={"target_section_id": s2["id"], "ordered_ids": [l1["id"], l2["id"]]}).status_code == 409

    # 发布状态未被破坏
    assert client.get(f"/api/admin/courses/{cid}", headers=headers).json()["status"] == "published"

    # 下架后恢复可编辑
    assert client.post(f"/api/admin/courses/{cid}/off-shelf", headers=headers).status_code == 200
    assert client.put(f"/api/admin/lessons/{l1['id']}", headers=headers,
                      json={"title": "改", "content_md": "# ok"}).status_code == 200


def test_reorder_rejects_duplicate_ids(tmp_path: Path):
    """排序列表重复 ID（如 [1,1]）必须 400——长度校验拦不住它，会写出重复 sort_order。"""
    app = build_app(tmp_path)
    client, headers = admin_login(app)
    cat = create_category(client, headers).json()
    cid = create_course(client, headers, cat["id"]).json()["id"]
    s1 = add_section(client, headers, cid, "第一章").json()
    add_section(client, headers, cid, "第二章").json()

    resp = client.post(f"/api/admin/courses/{cid}/sections/reorder", headers=headers,
                       json={"ids": [s1["id"], s1["id"]]})
    assert resp.status_code == 400

    l1 = add_lesson(client, headers, s1["id"], "A").json()
    add_lesson(client, headers, s1["id"], "B").json()
    resp = client.post(f"/api/admin/sections/{s1['id']}/lessons/reorder", headers=headers,
                       json={"ids": [l1["id"], l1["id"]]})
    assert resp.status_code == 400


def test_url_scheme_validation(tmp_path: Path):
    """cover_url 收 http/https 与应用内上传的 /course-covers/ 相对路径；
    video_url 只收 http/https。伪协议（javascript: 等）一律 422。"""
    app = build_app(tmp_path)
    client, headers = admin_login(app)
    cat = create_category(client, headers).json()

    bad_cover = client.post("/api/admin/courses", headers=headers, json={
        "title": "课", "category_id": cat["id"], "cover_url": "javascript:alert(1)",
    })
    assert bad_cover.status_code == 422

    # 应用内上传的封面：/course-covers/ 相对路径（admin_media.py 拼出的形状）
    uploaded = client.post("/api/admin/courses", headers=headers, json={
        "title": "课", "category_id": cat["id"],
        "cover_url": "/course-covers/ab/" + "a" * 64 + ".png",
    })
    assert uploaded.status_code == 201

    good = client.post("/api/admin/courses", headers=headers, json={
        "title": "课", "category_id": cat["id"], "cover_url": "https://example.com/cover.png",
    })
    assert good.status_code == 201
    cid = good.json()["id"]
    s = add_section(client, headers, cid, "第一章").json()

    bad_video = client.post(f"/api/admin/sections/{s['id']}/lessons", headers=headers, json={
        "title": "课", "video_url": "file:///etc/passwd",
    })
    assert bad_video.status_code == 422

    assert client.post(f"/api/admin/sections/{s['id']}/lessons", headers=headers, json={
        "title": "课", "video_url": "https://player.bilibili.com/xxx",
    }).status_code == 201


def test_course_list_page_clamped(tmp_path: Path):
    """后台分页参数有上下限：负数 page / 超大 page_size 不炸库。"""
    app = build_app(tmp_path)
    client, headers = admin_login(app)
    cat = create_category(client, headers).json()
    create_course(client, headers, cat["id"])

    resp = client.get("/api/admin/courses", headers=headers, params={"page": -5, "page_size": 999999})
    assert resp.status_code == 200
    body = resp.json()
    assert body["page"] == 1
    assert body["page_size"] == 100


# ---------- 发布检查：课中练习单题分支（v2 §4.2） ----------


def seed_problem(app, *, status: str = "approved", type: str = "choice",
                 problem_id_no: str = "Q100001") -> dict:
    """直接落一道题（approved 用于正例；draft 用于 problem_missing 负例）。"""
    db = app.state.session_factory()
    try:
        p = Problem(type=type, title="题", stem="题面", status=status,
                    problem_id_no=problem_id_no, version_no=1, revision=1)
        db.add(p)
        db.flush()
        p.root_problem_id = p.id
        db.commit()
        return {"problem_id": p.id, "problem_id_no": p.problem_id_no, "type": p.type}
    finally:
        db.close()


def _publish_blocked_problems(client, headers, course_id) -> list[dict]:
    resp = client.post(f"/api/admin/courses/{course_id}/publish", headers=headers)
    assert resp.status_code == 422
    body = resp.json()
    assert body["detail"] == "课包暂不能发布。"
    return body["problems"]


def test_publish_practice_problem_missing(tmp_path: Path):
    """发布检查 practice 单题分支：缺明细 / 题目未审核 / 题目被删 → 全部拦截。"""
    app = build_app(tmp_path)
    client, headers = admin_login(app)
    cat = create_category(client, headers).json()
    course = create_course(client, headers, cat["id"]).json()
    section = add_section(client, headers, course["id"]).json()
    lesson = client.post(f"/api/admin/sections/{section['id']}/lessons", headers=headers,
                         json={"title": "课时 1", "duration_minutes": 30}).json()
    lid = lesson["id"]

    # 1) 缺明细：直接改库制造「practice 块无 lesson_problem_blocks 行」的脏数据（Q6 边界）
    db = app.state.session_factory()
    try:
        from app.models import CourseLessonBlock
        dirty = CourseLessonBlock(lesson_id=lid, block_type="practice", title="脏练习", sort_order=0)
        db.add(dirty)
        db.commit()
    finally:
        db.close()
    problems = _publish_blocked_problems(client, headers, course["id"])
    assert any(p["code"] == "problem_missing_detail" for p in problems)

    # 2) 题目存在但未 approved：绑 approved 题后把题改回 draft
    prob = seed_problem(app)
    b = client.post(f"/api/admin/lessons/{lid}/blocks", headers=headers,
                    json={"block_type": "practice", "title": "课中练习",
                          "detail": {"problem": {"problem_id_no": prob["problem_id_no"], "score": 10}}}).json()
    db = app.state.session_factory()
    try:
        row = db.get(Problem, prob["problem_id"])
        row.status = "draft"
        db.commit()
    finally:
        db.close()
    problems = _publish_blocked_problems(client, headers, course["id"])
    assert any(p["code"] == "problem_missing" and p["block_id"] == b["id"] for p in problems)

    # 3) 题目被删：逻辑引用悬空，发布兜底拦截
    db = app.state.session_factory()
    try:
        row = db.get(Problem, prob["problem_id"])
        db.delete(row)
        db.commit()
    finally:
        db.close()
    problems = _publish_blocked_problems(client, headers, course["id"])
    assert any(p["code"] == "problem_missing" and p["block_id"] == b["id"] for p in problems)


def test_publish_practice_hints_not_blocking(tmp_path: Path):
    """发布检查提示不拦截：problem_type_stale / problem_score_zero 随 200 回传，不拦发布。"""
    app = build_app(tmp_path)
    client, headers = admin_login(app)
    cat = create_category(client, headers).json()
    course = create_course(client, headers, cat["id"]).json()
    section = add_section(client, headers, course["id"]).json()
    lesson = client.post(f"/api/admin/sections/{section['id']}/lessons", headers=headers,
                         json={"title": "课时 1", "duration_minutes": 30}).json()
    lid = lesson["id"]
    prob = seed_problem(app, type="choice")
    b = client.post(f"/api/admin/lessons/{lid}/blocks", headers=headers,
                    json={"block_type": "practice", "title": "课中练习",
                          "detail": {"problem": {"problem_id_no": prob["problem_id_no"],
                                                 "display_no": "1", "score": 10}}}).json()
    # 制造快照过期 + score=0：直接改库（模拟题目修订改型后快照失真 / Q5 默认分值口径）
    db = app.state.session_factory()
    try:
        from app.models import LessonProblemBlock
        row = db.get(LessonProblemBlock, b["id"])
        row.problem_type = "judge"   # 快照与题库实际 choice 不一致
        row.score = 0
        db.commit()
    finally:
        db.close()

    resp = client.post(f"/api/admin/courses/{course['id']}/publish", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "published"
    codes = {h["code"] for h in body["hints"]}
    assert "problem_type_stale" in codes
    assert "problem_score_zero" in codes
