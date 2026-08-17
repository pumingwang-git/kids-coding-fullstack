"""学生端学习链路回归：课包浏览 + 课时播放门控（评审 P0-1 绑定口径 / P0-2 播放鉴权）。

覆盖：
- 后台课时绑定的视频（course_lessons.video_id）能被学员端播放接口解析——不读 Video.lesson_id；
- 试看课时已发布可播；非试看课时未开通一律 403（deny by default）；
- 未发布课包课时 403；未绑定视频课时 404；
- GET /api/courses 只列已发布课包；详情课时内容按试看/开通门控；
- GET /api/course-categories 只回关联已发布课包的分类（带 course_count）；
- 课中练习单题块 DTO 保密回归（v2 §9.1）：practice 块只下发投放规则，
  **递归断言不含 problem_id_no / paper_id**（延续 test_exam.py「答案零下发」回归传统）。
"""
from pathlib import Path

from test_admin_courses import add_lesson, add_section, create_category, create_course
from test_exam import admin_login, build_app, scsrf, student_login, walk_keys
from test_lesson_problem_blocks import seed_paper, seed_problem

from app import video_sign
from app.models import Video, VideoVariant


def seed_ready_video(app, title="示例视频") -> dict:
    """直接落一条 ready 视频（含主档 master.m3u8），模拟转码完成。

    Video↔VideoVariant 是单向引用（primary_variant_id 不建回向外键），
    顺序必须是：先建 Video → 建 Variant(video_id) → 回填 primary_variant_id。
    """
    db = app.state.session_factory()
    try:
        video = Video(title=title, status="uploaded", duration_seconds=60)
        db.add(video)
        db.flush()
        variant = VideoVariant(
            video_id=video.id, bucket="videos-play", object_key="demo/1080p/master.m3u8",
            resolution="1080p", bitrate_kbps=2500, status="ready",
        )
        db.add(variant)
        db.flush()
        video.status = "ready"
        video.primary_variant_id = variant.id
        db.commit()
        return {"video_id": video.id, "variant_id": variant.id}
    finally:
        db.close()


def build_published_course(app, *, trial: bool, bind_video: bool) -> dict:
    """建分类→课包→章节→课时（可绑视频/试看）→发布，返回各 id。"""
    client, headers = admin_login(app)
    cat = create_category(client, headers).json()
    course = create_course(client, headers, cat["id"]).json()
    section = add_section(client, headers, course["id"]).json()
    lesson_payload = {
        "title": "课时 1", "content_md": "# 你好", "duration_minutes": 30,
        "is_trial": trial,
    }
    video = None
    if bind_video:
        video = seed_ready_video(app)
        lesson_payload["video_id"] = video["video_id"]
    lesson = client.post(
        f"/api/admin/sections/{section['id']}/lessons",
        headers=headers, json=lesson_payload,
    ).json()
    assert client.post(f"/api/admin/courses/{course['id']}/publish", headers=headers).status_code == 200
    return {"client": client, "headers": headers, "course_id": course["id"],
            "section_id": section["id"], "lesson_id": lesson["id"], "video": video}


def test_trial_lesson_bound_video_plays(tmp_path: Path):
    """评审 P0-1：后台绑到 course_lessons.video_id 的视频，学员端能播（不读 Video.lesson_id）。"""
    app = build_app(tmp_path)
    built = build_published_course(app, trial=True, bind_video=True)
    sclient = student_login(app)
    resp = sclient.post(f"/api/lessons/{built['lesson_id']}/play", headers=scsrf(sclient))
    assert resp.status_code == 200, resp.text
    data = resp.json()
    # P2-5：地址改成「稳定路径 + query 签名」，不再有 token/base_url 字段。
    # 路径必须是 /v/{video_id}/master.m3u8——它与对象键 video-{id}/master.m3u8 一一对应，
    # nginx 靠这个映射不查库就能直连 MinIO（部署配置/nginx-cache.conf）。
    path, query = data["master_playlist"].split("?", 1)
    assert path == f"/v/{built['video']['video_id']}/master.m3u8"
    params = dict(p.split("=", 1) for p in query.split("&"))
    assert set(params) == {"e", "u", "s"}
    assert video_sign.verify(
        app.state.settings.minio_play_secret, path, params["u"], params["e"], params["s"]
    ) is True


def test_non_trial_lesson_locked(tmp_path: Path):
    """评审 P0-2：非试看课时未开通 → 403（enrollments 落地前的 deny by default）。"""
    app = build_app(tmp_path)
    built = build_published_course(app, trial=False, bind_video=True)
    sclient = student_login(app)
    resp = sclient.post(f"/api/lessons/{built['lesson_id']}/play", headers=scsrf(sclient))
    assert resp.status_code == 403


def test_unpublished_course_lesson_denied(tmp_path: Path):
    """未发布课包的课时一律 403（draft/off_shelf 不放行）。"""
    app = build_app(tmp_path)
    client, headers = admin_login(app)
    cat = create_category(client, headers).json()
    course = create_course(client, headers, cat["id"]).json()
    section = add_section(client, headers, course["id"]).json()
    lesson = client.post(f"/api/admin/sections/{section['id']}/lessons", headers=headers,
                         json={"title": "课时 1", "content_md": "# 你好", "is_trial": True}).json()
    sclient = student_login(app)
    resp = sclient.post(f"/api/lessons/{lesson['id']}/play", headers=scsrf(sclient))
    assert resp.status_code == 403


def test_lesson_without_video_404(tmp_path: Path):
    """已发布但课时未绑视频 → 404。"""
    app = build_app(tmp_path)
    built = build_published_course(app, trial=True, bind_video=False)
    sclient = student_login(app)
    resp = sclient.post(f"/api/lessons/{built['lesson_id']}/play", headers=scsrf(sclient))
    assert resp.status_code == 404


def test_student_course_listing_and_gating(tmp_path: Path):
    """学生端课包接口：列表只见已发布；**目录树永不携带正文/video_id**；正文走 /lessons/{id} 门控下发。"""
    app = build_app(tmp_path)
    client, headers = admin_login(app)
    cat = create_category(client, headers).json()
    course = create_course(client, headers, cat["id"]).json()
    section = add_section(client, headers, course["id"]).json()
    # 两个课时都要在发布前建好——已发布课包禁止再增改课时（护栏）
    trial = client.post(f"/api/admin/sections/{section['id']}/lessons", headers=headers,
                        json={"title": "课时 1", "content_md": "# 你好", "is_trial": True}).json()
    locked = client.post(f"/api/admin/sections/{section['id']}/lessons", headers=headers,
                         json={"title": "课时 2", "content_md": "# 秘密", "is_trial": False}).json()
    assert client.post(f"/api/admin/courses/{course['id']}/publish", headers=headers).status_code == 200

    sclient = student_login(app)
    resp = sclient.get("/api/courses")
    assert resp.status_code == 200
    assert any(c["id"] == course["id"] for c in resp.json()["items"])

    detail = sclient.get(f"/api/courses/{course['id']}")
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert body["enrolled"] is False
    lessons = {lesson["id"]: lesson for sec in body["sections"] for lesson in sec["lessons"]}
    # 目录树防泄漏：试看与非试看课时都不带正文与 video_id
    for lid in (trial["id"], locked["id"]):
        assert "content_md" not in lessons[lid]
        assert "video_id" not in lessons[lid]
    assert lessons[trial["id"]]["unlocked"] is True
    assert lessons[locked["id"]]["unlocked"] is False

    # 正文只能通过 GET /api/lessons/{id} 获取，且按门控下发
    trial_body = sclient.get(f"/api/lessons/{trial['id']}").json()
    assert trial_body["unlocked"] is True
    assert trial_body["content_md"] == "# 你好"
    locked_body = sclient.get(f"/api/lessons/{locked['id']}").json()
    assert locked_body["unlocked"] is False
    assert locked_body["content_md"] is None
    assert locked_body["video_url"] is None


def test_student_course_categories(tmp_path: Path):
    """分类接口：只返回关联了**已发布课包**的分类，带 course_count。

    草稿/下架课包不计数（分类整体不下发）；无课包的分类不下发。
    """
    app = build_app(tmp_path)
    client, headers = admin_login(app)
    cat_a = create_category(client, headers, name="编程基础").json()
    cat_b = create_category(client, headers, name="专项训练").json()
    create_category(client, headers, name="竞赛课程").json()

    # A 分类：两个已发布课包
    for i in range(2):
        cid = create_course(client, headers, cat_a["id"], title=f"课{i}").json()["id"]
        section = add_section(client, headers, cid, "第一章").json()
        add_lesson(client, headers, section["id"], "课时").json()
        assert client.post(f"/api/admin/courses/{cid}/publish", headers=headers).status_code == 200
    # B 分类：只有一个草稿课包（不计数）
    create_course(client, headers, cat_b["id"], title="草稿课").json()
    # C 分类：无课包

    sclient = student_login(app)
    resp = sclient.get("/api/course-categories")
    assert resp.status_code == 200
    items = {c["name"]: c for c in resp.json()["items"]}
    assert items["编程基础"]["course_count"] == 2
    assert "专项训练" not in items  # 只有草稿 → 分类不下发
    assert "竞赛课程" not in items  # 无课包 → 不下发


def test_course_area_kind_filters_and_lesson_context(tmp_path: Path):
    """专区、课程类型和学科分类保持独立，并把专区上下文带到课时响应。"""
    app = build_app(tmp_path)
    client, headers = admin_login(app)
    kids_cat = create_category(client, headers, name="图形化").json()
    programmer_taxonomy = client.get("/api/admin/learning-catalog/categories?area_key=programmer",
                                     headers=headers).json()
    python_cat = next(item for item in programmer_taxonomy if item["name"] == "网络爬虫")

    kids_course = create_course(client, headers, kids_cat["id"], title="少儿系统课").json()
    kids_section = add_section(client, headers, kids_course["id"]).json()
    kids_lesson = add_lesson(client, headers, kids_section["id"], "认识顺序").json()
    assert client.post(f"/api/admin/courses/{kids_course['id']}/publish", headers=headers).status_code == 200

    special = client.post("/api/admin/courses", headers=headers, json={
        "title": "Python 专题课",
        "category_id": python_cat["id"],
        "area_key": "programmer",
        "course_kind": "special",
        "difficulty": "beginner",
    }).json()
    special_section = add_section(client, headers, special["id"]).json()
    add_lesson(client, headers, special_section["id"], "变量专题").json()
    assert client.post(f"/api/admin/courses/{special['id']}/publish", headers=headers).status_code == 200

    student = student_login(app)
    kids = student.get("/api/courses?area_key=kids&course_kind=systematic").json()
    assert [item["id"] for item in kids["items"]] == [kids_course["id"]]
    assert kids["items"][0]["area_key"] == "kids"
    assert kids["items"][0]["course_kind"] == "systematic"

    categories = student.get("/api/course-categories?area_key=programmer&course_kind=special").json()
    assert [item["name"] for item in categories["items"]] == ["网络爬虫"]

    lesson = student.get(f"/api/lessons/{kids_lesson['id']}").json()
    assert lesson["area_key"] == "kids"
    assert lesson["course_kind"] == "systematic"

    assert student.get("/api/courses?area_key=unknown").status_code == 400
    assert student.get("/api/course-categories?course_kind=unknown").status_code == 400


def _practice_payload(**detail) -> dict:
    return {"block_type": "practice", "title": "课中练习", "detail": {"problem": detail}}


def _homework_payload(**detail) -> dict:
    return {"block_type": "homework", "title": "课后练习", "detail": {"paper": detail}}


def test_lesson_homework_reuses_exam_attempt_flow(tmp_path: Path):
    app = build_app(tmp_path)
    client, headers = admin_login(app)
    category = create_category(client, headers).json()
    course = create_course(client, headers, category["id"]).json()
    section = add_section(client, headers, course["id"]).json()
    lesson = client.post(
        f"/api/admin/sections/{section['id']}/lessons", headers=headers,
        json={"title": "课时作业", "content_md": "# 作业", "duration_minutes": 30, "is_trial": True},
    ).json()
    paper_id = seed_paper(app)["paper_id"]
    # 空卷没有大纲可言，给这张卷绑一道题再断言题目列表字段。
    problem = seed_problem(app, problem_id_no="Q900101", type="programming")
    db = app.state.session_factory()
    try:
        from app.models import PaperQuestion
        db.add(PaperQuestion(paper_id=paper_id, problem_id_no=problem["problem_id_no"],
                             sort_order=1, score=10))
        db.commit()
    finally:
        db.close()
    block = client.post(
        f"/api/admin/lessons/{lesson['id']}/blocks", headers=headers,
        json={"block_type": "homework", "title": "课后作业", "detail": {"paper": {
            "paper_id": paper_id, "mode": "homework", "attempt_limit": 2,
            "shuffle_questions": True, "shuffle_options": True,
            "show_score": True, "show_analysis": True, "due_at": None,
        }}},
    ).json()
    assert client.post(f"/api/admin/courses/{course['id']}/publish", headers=headers).status_code == 200

    student = student_login(app)
    base = f"/api/exam/lesson-homework/{lesson['id']}/blocks/{block['id']}"
    entry = student.get(base)
    assert entry.status_code == 200, entry.text
    assert entry.json()["paper"]["title"]

    # 题目列表看板的大纲：只含展示元数据，题干/选项/答案仍零下发。
    outline = entry.json()["paper"]["questions"]
    assert len(outline) >= 1
    first = outline[0]
    assert {"sort_order", "problem_id_no", "score", "title", "type",
            "difficulty", "source", "knowledge"} <= set(first)
    assert isinstance(first["knowledge"], list)
    assert "stem" not in first and "options" not in first and "answer" not in first
    started = student.post(f"{base}/start", headers=scsrf(student))
    assert started.status_code == 201, started.text
    attempt_id = started.json()["attempt_id"]
    # 题目、保存、交卷和结果仍走既有 /api/exam/attempts 接口。
    assert student.get(f"/api/exam/attempts/{attempt_id}").status_code == 200
    assert student.post(f"/api/exam/attempts/{attempt_id}/submit", headers=scsrf(student)).status_code == 200
    result = student.get(f"/api/exam/attempts/{attempt_id}/result")
    assert result.status_code == 200, result.text

    # 课时作业的来源策略关闭排行榜；前端展示只是服务端字段的投影。
    assert result.json()["leaderboard_enabled"] is False
    board = student.get(f"/api/exam/attempts/{attempt_id}/leaderboard")
    assert board.status_code == 403, board.text

    # 逐题通过状态是「任何一次已交卷作答判对过」的累计口径：交卷后直接改库
    # 模拟第一次作答判对，再拉 entry 验证聚合；ongoing 那次的不算。
    assert outline[0]["passed"] is False and outline[0]["answered"] is False
    db = app.state.session_factory()
    try:
        from app.models import AttemptAnswer
        row = db.query(AttemptAnswer).filter_by(
            attempt_id=attempt_id, problem_id_no="Q900101").one()
        row.is_correct, row.score, row.judge_status = True, 10, "judged"
        db.commit()
    finally:
        db.close()
    again = student.get(base).json()["paper"]["questions"][0]
    assert again["passed"] is True and again["answered"] is True

    db = app.state.session_factory()
    try:
        from app.models import LessonBlockCompletion
        assert db.query(LessonBlockCompletion).filter_by(block_id=block["id"]).count() == 1
    finally:
        db.close()


def test_student_practice_block_dto_secrecy(tmp_path: Path):
    """保密回归（v2 §9.1 / §4.4）：学生端 GET /api/lessons/{id} 的 practice 块只下发
    「渲染骨架 + 投放规则」，**递归断言不含 problem_id_no / paper_id**。

    延续 test_exam.py「答案零下发」回归传统（walk_keys 递归查键名）：
    谁往学生端 DTO 里加字段都逃不过这张网；homework 块保持现状零回归。
    """
    app = build_app(tmp_path)
    client, headers = admin_login(app)
    cat = create_category(client, headers).json()
    course = create_course(client, headers, cat["id"]).json()
    section = add_section(client, headers, course["id"]).json()
    lesson = client.post(f"/api/admin/sections/{section['id']}/lessons", headers=headers,
                         json={"title": "课时 1", "content_md": "# 你好",
                               "is_trial": True}).json()  # 试看课时 → can_access 才下发明细

    no_choice = seed_problem(app, problem_id_no="Q900001", type="choice")["problem_id_no"]
    no_judge = seed_problem(app, problem_id_no="Q900002", type="judge")["problem_id_no"]
    paper_id = seed_paper(app)["paper_id"]

    # practice × 2（display_no 有值 / NULL）+ homework × 1
    p1 = client.post(f"/api/admin/lessons/{lesson['id']}/blocks", headers=headers,
                     json=_practice_payload(problem_id_no=no_choice, display_no="1",
                                            score=10, attempt_limit=0)).json()
    p2 = client.post(f"/api/admin/lessons/{lesson['id']}/blocks", headers=headers,
                     json=_practice_payload(problem_id_no=no_judge, display_no=None,
                                            score=5)).json()
    h1 = client.post(f"/api/admin/lessons/{lesson['id']}/blocks", headers=headers,
                     json=_homework_payload(paper_id=paper_id, mode="homework",
                                            attempt_limit=2)).json()
    # 发布：题目均 approved、paper published → 无拦截项，200 且无 hints
    resp = client.post(f"/api/admin/courses/{course['id']}/publish", headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["hints"] == []

    sclient = student_login(app)
    body = sclient.get(f"/api/lessons/{lesson['id']}").json()

    # 递归键名保密：学生端任何层级不得出现题号 / 卷 id（答案/解析键由 X2 前的 DTO 天然不含，
    # 一并放进禁键表防回潮）。
    walk_keys(body, {"problem_id_no", "paper_id", "is_correct", "analysis", "ref_code", "blanks"})

    blocks = {b["id"]: b for b in body["blocks"]}
    # practice 块：只下发 problem 投放规则，problem 键集合严格等于白名单
    p1_dto, p2_dto = blocks[p1["id"]], blocks[p2["id"]]
    assert p1_dto["block_type"] == "practice"
    assert p1_dto["can_access"] is True
    assert "paper" not in p1_dto and "mode" not in p1_dto
    assert set(p1_dto["problem"]) == {
        "problem_type", "display_no", "score", "attempt_limit",
        "shuffle_options", "show_analysis",
    }
    assert p1_dto["problem"]["problem_type"] == "choice"      # 快照由服务端从题库回填
    assert p1_dto["problem"]["display_no"] == "1"
    assert p1_dto["problem"]["score"] == 10
    assert p1_dto["problem"]["attempt_limit"] is None         # 0 → NULL（Q5 口径）
    assert p1_dto["problem"]["shuffle_options"] is True       # 默认 True
    # display_no NULL 原样下发：回退序号是前端行为，后端不下发「该课时内 practice 块间序号」
    assert p2_dto["problem"]["display_no"] is None
    assert p2_dto["problem"]["problem_type"] == "judge"
    # homework 块：保持现状（平铺投放规则，无 paper_id）；题目数只给数字，给入口卡片显示用
    h_dto = blocks[h1["id"]]
    assert h_dto["block_type"] == "homework"
    assert h_dto["mode"] == "homework"
    assert h_dto["attempt_limit"] == 2
    assert h_dto["question_count"] == 0  # seed_paper 是空卷
    assert "paper_id" not in h_dto
