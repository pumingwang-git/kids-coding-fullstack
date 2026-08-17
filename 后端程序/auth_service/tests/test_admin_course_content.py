"""课包内容块（积木化编排）管理端链路：块 CRUD / 排序 / 权限 / 发布校验 / 删除保护。

对应交接文档 §6 接口契约与 §11 验收清单：
- 一节课时可有多个视频块（平台/外链混排）、图文块夹在视频之间，顺序可保存可还原；
- 排序失败（缺 id / 重复 id / 跨课时块）必须拒绝，不产生脏顺序；
- 块类型是骨架，更新不允许改类型；明细与 block_type 必须匹配；
- 发布检查返回结构化 problems（stage/lesson_id/block_id/code/message），可定位到具体块；
- 删除块只解除引用；删除被块引用的试卷被后端明确拒绝；
- 旧课时字段（content_md/video_id/video_url）在无块时仍可发布（过渡兜底）。
"""
from datetime import UTC, datetime, timedelta
from pathlib import Path

from test_admin_courses import (
    add_section,
    create_category,
    create_course,
    reviewer_login,
)
from test_exam import admin_login, build_app, scsrf, student_login
from test_student_learning import seed_ready_video

import app.routers.admin_course_content as admin_course_content
from app.models import (
    AuditEvent,
    CourseLessonBlock,
    LessonPaperBlock,
    Paper,
    PaperAttempt,
    Problem,
    User,
)

# ---------- 辅助 ----------


def seed_paper(app, title="练习卷A", status="published") -> dict:
    """直接落一张试卷。发布状态由调用方指定（草稿卷用于发布校验负例）。"""
    db = app.state.session_factory()
    try:
        paper = Paper(title=title, status=status, paper_type="练习卷", subject="cpp")
        db.add(paper)
        db.commit()
        return {"paper_id": paper.id}
    finally:
        db.close()

def seed_problem(app, *, status: str = "approved", type: str = "choice",
                 problem_id_no: str = "Q100001") -> dict:
    """直接落一道题（approved 用于绑题正例；draft 用于发布校验负例）。"""
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


def build_lesson_without_content(app) -> tuple:
    """建分类→课包→章节→无内容课时，返回 (client, headers, ids)。"""
    client, headers = admin_login(app)
    cat = create_category(client, headers).json()
    course = create_course(client, headers, cat["id"]).json()
    section = add_section(client, headers, course["id"]).json()
    lesson = client.post(
        f"/api/admin/sections/{section['id']}/lessons", headers=headers,
        json={"title": "课时 1", "duration_minutes": 30},
    ).json()
    return client, headers, course, section, lesson


def block_payload(block_type: str, **detail) -> dict:
    """按块类型拼 POST/PUT 载荷。detail 的键直接进对应类型明细。

    v2 单题化（实现计划 §4.1）：practice 块走 `detail.problem`（绑单题），
    homework 块保持 `detail.paper`（绑卷）。
    """
    body = {"block_type": block_type, "title": f"{block_type} 块"}
    if block_type == "markdown":
        body["detail"] = {"markdown": {"content_md": detail.get("content_md", "# 标题")}}
    elif block_type == "video":
        body["detail"] = {"video": detail}
    elif block_type == "practice":
        body["detail"] = {"problem": detail}
    else:  # homework
        body["detail"] = {"paper": detail}
    return body


# ---------- CRUD 与顺序 ----------


def test_lesson_two_videos_with_markdown_between(tmp_path: Path):
    """PR 1 验收点：一课时两个视频、中间插图文，顺序完整保存。"""
    app = build_app(tmp_path)
    client, headers, course, section, lesson = build_lesson_without_content(app)
    lid = lesson["id"]
    video = seed_ready_video(app)

    b1 = client.post(f"/api/admin/lessons/{lid}/blocks", headers=headers,
                     json=block_payload("video", source_type="platform", video_id=video["video_id"],
                                        completion_percent=80)).json()
    b2 = client.post(f"/api/admin/lessons/{lid}/blocks", headers=headers,
                     json=block_payload("markdown", content_md="# 讲解")).json()
    b3 = client.post(f"/api/admin/lessons/{lid}/blocks", headers=headers,
                     json=block_payload("video", source_type="embed",
                                        video_url="https://example.com/lesson.mp4")).json()

    data = client.get(f"/api/admin/lessons/{lid}/blocks", headers=headers).json()
    assert [b["block_type"] for b in data["blocks"]] == ["video", "markdown", "video"]
    assert [b["sort_order"] for b in data["blocks"]] == [0, 1, 2]
    # 平台视频块带管理端状态
    assert data["blocks"][0]["video"]["video_id"] == video["video_id"]
    assert data["blocks"][0]["video"]["playable"] is True
    assert data["blocks"][0]["video"]["completion_percent"] == 80
    assert data["blocks"][2]["video"]["video_url"] == "https://example.com/lesson.mp4"
    assert data["blocks"][1]["markdown"]["content_md"] == "# 讲解"

    # 更新图文内容（全量覆盖）
    up = client.put(f"/api/admin/lesson-blocks/{b2['id']}", headers=headers,
                    json=block_payload("markdown", content_md="# 讲解（修订）")).json()
    assert up["markdown"]["content_md"] == "# 讲解（修订）"

    # 排序：markdown 挪到最前
    assert client.post(f"/api/admin/lessons/{lid}/blocks/reorder", headers=headers,
                       json={"ids": [b2["id"], b1["id"], b3["id"]]}).status_code == 200
    data = client.get(f"/api/admin/lessons/{lid}/blocks", headers=headers).json()
    assert [b["block_type"] for b in data["blocks"]] == ["markdown", "video", "video"]

    # 删除中间视频块，剩余 sort_order 压实
    assert client.delete(f"/api/admin/lesson-blocks/{b1['id']}", headers=headers).status_code == 200
    data = client.get(f"/api/admin/lessons/{lid}/blocks", headers=headers).json()
    assert [b["id"] for b in data["blocks"]] == [b2["id"], b3["id"]]
    assert [b["sort_order"] for b in data["blocks"]] == [0, 1]


def test_reorder_validation(tmp_path: Path):
    """排序集合必须与当前课时块完全一致：缺 id / 重复 id / 跨课时块全部拒绝。"""
    app = build_app(tmp_path)
    client, headers, course, section, lesson = build_lesson_without_content(app)
    l1 = lesson["id"]
    b1 = client.post(f"/api/admin/lessons/{l1}/blocks", headers=headers,
                     json=block_payload("markdown")).json()
    b2 = client.post(f"/api/admin/lessons/{l1}/blocks", headers=headers,
                     json=block_payload("markdown")).json()

    # 缺一个 id
    resp = client.post(f"/api/admin/lessons/{l1}/blocks/reorder", headers=headers,
                       json={"ids": [b1["id"]]})
    assert resp.status_code == 400

    # 重复 id
    resp = client.post(f"/api/admin/lessons/{l1}/blocks/reorder", headers=headers,
                       json={"ids": [b1["id"], b1["id"]]})
    assert resp.status_code == 400

    # 跨课时偷块：另一个课时的块混进来
    lesson2 = client.post(f"/api/admin/sections/{section['id']}/lessons", headers=headers,
                          json={"title": "课时 2"}).json()
    foreign = client.post(f"/api/admin/lessons/{lesson2['id']}/blocks", headers=headers,
                          json=block_payload("markdown")).json()
    resp = client.post(f"/api/admin/lessons/{l1}/blocks/reorder", headers=headers,
                       json={"ids": [b1["id"], b2["id"], foreign["id"]]})
    assert resp.status_code == 400

    # 排序后顺序正确
    assert client.post(f"/api/admin/lessons/{l1}/blocks/reorder", headers=headers,
                       json={"ids": [b2["id"], b1["id"]]}).status_code == 200
    data = client.get(f"/api/admin/lessons/{l1}/blocks", headers=headers).json()
    assert [b["id"] for b in data["blocks"]] == [b2["id"], b1["id"]]


def test_block_create_validation(tmp_path: Path):
    """创建时块类型与明细必须匹配，引用必须存在。"""
    app = build_app(tmp_path)
    client, headers, course, section, lesson = build_lesson_without_content(app)
    lid = lesson["id"]

    # 平台视频块缺 video_id
    assert client.post(f"/api/admin/lessons/{lid}/blocks", headers=headers,
                       json=block_payload("video", source_type="platform")).status_code == 400
    # 平台视频块绑不存在的视频
    assert client.post(f"/api/admin/lessons/{lid}/blocks", headers=headers,
                       json=block_payload("video", source_type="platform", video_id=999999)).status_code == 400
    # 外链视频块缺地址
    assert client.post(f"/api/admin/lessons/{lid}/blocks", headers=headers,
                       json=block_payload("video", source_type="embed")).status_code == 400
    # 外链只收 http/https（伪协议在请求模型层被 422 拦下，与课时 video_url 同口径）
    assert client.post(f"/api/admin/lessons/{lid}/blocks", headers=headers,
                       json=block_payload("video", source_type="embed",
                                          video_url="javascript:alert(1)")).status_code == 422
    # 课中练习块缺题目明细（detail 缺失 → 业务层 400）
    assert client.post(f"/api/admin/lessons/{lid}/blocks", headers=headers,
                       json={"block_type": "practice", "title": "practice 块", "detail": None}).status_code == 400
    # 课中练习块 detail 里缺 problem_id_no（请求模型层 422）
    assert client.post(f"/api/admin/lessons/{lid}/blocks", headers=headers,
                       json=block_payload("practice")).status_code == 422
    # 课中练习块传 paper（v2 非法组合）→ 400「课中练习块请绑定题目」
    paper = seed_paper(app)
    assert client.post(f"/api/admin/lessons/{lid}/blocks", headers=headers,
                       json={"block_type": "practice", "title": "practice 块",
                             "detail": {"paper": {"paper_id": paper["paper_id"], "mode": "practice"}}}).status_code == 400
    # 课后练习块 mode 与 block_type 不一致（homework 分支保留强校验）
    assert client.post(f"/api/admin/lessons/{lid}/blocks", headers=headers,
                       json=block_payload("homework", paper_id=paper["paper_id"],
                                          mode="practice")).status_code == 400
    # 非法块类型
    assert client.post(f"/api/admin/lessons/{lid}/blocks", headers=headers,
                       json=block_payload("ai_node")).status_code == 422

    # 更新不允许改类型
    b = client.post(f"/api/admin/lessons/{lid}/blocks", headers=headers,
                    json=block_payload("markdown")).json()
    resp = client.put(f"/api/admin/lesson-blocks/{b['id']}", headers=headers,
                      json=block_payload("video", source_type="embed",
                                         video_url="https://x.com/v.mp4"))
    assert resp.status_code == 400


def test_reviewer_readonly(tmp_path: Path):
    """reviewer 可读块列表，不可写。"""
    app = build_app(tmp_path)
    client, headers, course, section, lesson = build_lesson_without_content(app)
    lid = lesson["id"]
    assert client.get(f"/api/admin/lessons/{lid}/blocks", headers=headers).status_code == 200
    rclient, rheaders = reviewer_login(app)
    assert rclient.get(f"/api/admin/lessons/{lid}/blocks", headers=rheaders).status_code == 200
    assert rclient.post(f"/api/admin/lessons/{lid}/blocks", headers=rheaders,
                        json=block_payload("markdown")).status_code == 403
    assert rclient.delete(f"/api/admin/lesson-blocks/{lid}", headers=rheaders).status_code == 403


def test_published_course_blocks_readonly(tmp_path: Path):
    """已发布课包：块不可改，必须先下架。"""
    app = build_app(tmp_path)
    client, headers, course, section, lesson = build_lesson_without_content(app)
    lid = lesson["id"]
    client.post(f"/api/admin/lessons/{lid}/blocks", headers=headers,
                json=block_payload("markdown")).status_code == 201
    assert client.post(f"/api/admin/courses/{course['id']}/publish", headers=headers).status_code == 200
    assert client.post(f"/api/admin/lessons/{lid}/blocks", headers=headers,
                       json=block_payload("markdown")).status_code == 409
    assert client.post(f"/api/admin/courses/{course['id']}/off-shelf", headers=headers).status_code == 200
    assert client.post(f"/api/admin/lessons/{lid}/blocks", headers=headers,
                       json=block_payload("markdown")).status_code == 201


# ---------- 发布校验（结构化 problems） ----------


def _publish_problems(client, headers, course_id) -> list[dict]:
    resp = client.post(f"/api/admin/courses/{course_id}/publish", headers=headers)
    assert resp.status_code == 422
    body = resp.json()
    assert body["detail"] == "课包暂不能发布。"
    return body["problems"]


def test_publish_checks_blocks(tmp_path: Path):
    """发布检查逐块定位：空图文、未转码视频、单题块题目未审核、未发布试卷都拦在发布外。"""
    app = build_app(tmp_path)
    client, headers, course, section, lesson = build_lesson_without_content(app)
    lid = lesson["id"]

    # 空图文块：API 创建即拒绝（400），发布检查的 markdown_empty 是防御分支，
    # 这里直接改库制造「空正文块」来验证发布拦截。
    md_block = client.post(f"/api/admin/lessons/{lid}/blocks", headers=headers,
                           json=block_payload("markdown", content_md="# 正文")).json()
    db = app.state.session_factory()
    try:
        from app.models import LessonMarkdownBlock
        row = db.get(LessonMarkdownBlock, md_block["id"])
        row.content_md = "   "
        db.commit()
    finally:
        db.close()
    problems = _publish_problems(client, headers, course["id"])
    assert any(p["code"] == "markdown_empty" and p["block_id"] == md_block["id"] for p in problems)

    # 未转码视频（uploaded、无主档）
    seed_ready_video(app)  # 先建 ready 备用，再造一个未就绪的
    db = app.state.session_factory()
    try:
        from app.models import Video
        rough = Video(title="未转码", status="uploaded")
        db.add(rough)
        db.commit()
        rough_id = rough.id
    finally:
        db.close()
    client.post(f"/api/admin/lessons/{lid}/blocks", headers=headers,
                json=block_payload("video", source_type="platform", video_id=rough_id))
    problems = _publish_problems(client, headers, course["id"])
    assert any(p["code"] == "video_not_ready" and p["block_id"] is not None for p in problems)

    # practice 单题块：先绑 approved 题，再把题改回 draft 制造「未审核通过」→ problem_missing 拦截
    prob = seed_problem(app)
    practice_block = client.post(f"/api/admin/lessons/{lid}/blocks", headers=headers,
                                 json=block_payload("practice", problem_id_no=prob["problem_id_no"],
                                                    display_no="1", score=10)).json()
    db = app.state.session_factory()
    try:
        row = db.get(Problem, prob["problem_id"])
        row.status = "draft"
        db.commit()
    finally:
        db.close()
    problems = _publish_problems(client, headers, course["id"])
    assert any(p["code"] == "problem_missing" and p["block_id"] == practice_block["id"] for p in problems)

    # homework 绑草稿卷 → paper_not_published（homework 分支回归）
    draft_paper = seed_paper(app, title="草稿卷", status="draft")
    homework_block = client.post(f"/api/admin/lessons/{lid}/blocks", headers=headers,
                                 json=block_payload("homework", paper_id=draft_paper["paper_id"],
                                                    mode="homework")).json()
    problems = _publish_problems(client, headers, course["id"])
    assert any(p["code"] == "paper_not_published" and p["block_id"] == homework_block["id"] for p in problems)

    # 全部修复后发布成功：删空图文块、删未转码视频块、practice 换已审核题、homework 换已发布卷
    blocks = client.get(f"/api/admin/lessons/{lid}/blocks", headers=headers).json()["blocks"]
    for b in blocks:
        if b["block_type"] == "markdown" and not b["markdown"]["content_md"].strip():
            client.delete(f"/api/admin/lesson-blocks/{b['id']}", headers=headers)
        if b["block_type"] == "video" and b["video"]["playable"] is False:
            client.delete(f"/api/admin/lesson-blocks/{b['id']}", headers=headers)
    published = seed_paper(app, title="正式卷", status="published")
    client.post(f"/api/admin/lessons/{lid}/blocks", headers=headers,
                json=block_payload("markdown", content_md="# 正文"))
    approved_problem = seed_problem(app, problem_id_no="Q100002")
    client.put(f"/api/admin/lesson-blocks/{practice_block['id']}", headers=headers,
               json=block_payload("practice", problem_id_no=approved_problem["problem_id_no"],
                                  display_no="1", score=10))
    client.put(f"/api/admin/lesson-blocks/{homework_block['id']}", headers=headers,
               json=block_payload("homework", paper_id=published["paper_id"], mode="homework"))
    assert client.post(f"/api/admin/courses/{course['id']}/publish", headers=headers).status_code == 200


def test_publish_homework_due_past(tmp_path: Path):
    """作业截止时间早于当前时间：发布被拦。"""
    app = build_app(tmp_path)
    client, headers, course, section, lesson = build_lesson_without_content(app)
    lid = lesson["id"]
    paper = seed_paper(app)
    past = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    client.post(f"/api/admin/lessons/{lid}/blocks", headers=headers,
                json=block_payload("homework", paper_id=paper["paper_id"], mode="homework",
                                   due_at=past))
    problems = _publish_problems(client, headers, course["id"])
    assert any(p["code"] == "homework_due_past" for p in problems)


def test_legacy_fields_still_publishable(tmp_path: Path):
    """无块但旧字段有内容：发布放行（过渡兜底，§5.3 第 7 条）。"""
    app = build_app(tmp_path)
    client, headers = admin_login(app)
    cat = create_category(client, headers).json()
    course = create_course(client, headers, cat["id"]).json()
    section = add_section(client, headers, course["id"]).json()
    video = seed_ready_video(app)
    client.post(f"/api/admin/sections/{section['id']}/lessons", headers=headers,
                json={"title": "旧课时", "content_md": "# 旧图文", "video_id": video["video_id"],
                      "duration_minutes": 10})
    assert client.post(f"/api/admin/courses/{course['id']}/publish", headers=headers).status_code == 200


# ---------- 试卷删除保护 ----------


def test_paper_delete_blocked_by_lesson_block(tmp_path: Path):
    """被课时块引用的试卷不可删除；解绑后可删。"""
    app = build_app(tmp_path)
    client, headers, course, section, lesson = build_lesson_without_content(app)
    lid = lesson["id"]
    paper = seed_paper(app, status="draft")  # 删除权要求 draft/archived（已发布卷要先归档）

    b = client.post(f"/api/admin/lessons/{lid}/blocks", headers=headers,
                    json=block_payload("homework", paper_id=paper["paper_id"], mode="homework")).json()
    resp = client.delete(f"/api/admin/papers/{paper['paper_id']}", headers={**headers, "If-Match": "1"})
    assert resp.status_code == 409
    assert "课时块引用" in resp.json()["detail"]

    # 解绑（删块）后可删
    assert client.delete(f"/api/admin/lesson-blocks/{b['id']}", headers=headers).status_code == 200
    resp = client.delete(f"/api/admin/papers/{paper['paper_id']}", headers={**headers, "If-Match": "1"})
    assert resp.status_code == 200


def test_homework_block_delete_blocked_after_attempt_exists(tmp_path: Path):
    """作业已有成绩时不能删除来源块，否则历史 attempt 会变成不可解析的孤儿记录。"""
    app = build_app(tmp_path)
    client, headers, course, section, lesson = build_lesson_without_content(app)
    paper = seed_paper(app, status="published")
    block = client.post(
        f"/api/admin/lessons/{lesson['id']}/blocks", headers=headers,
        json=block_payload("homework", paper_id=paper["paper_id"], mode="homework"),
    ).json()
    student_login(app)
    db = app.state.session_factory()
    try:
        user = db.query(User).filter_by(username="learner").one()
        db.add(PaperAttempt(source_type="lesson_homework", source_id=block["id"],
                            exam_link_id=None, paper_id=paper["paper_id"],
                            user_id=user.id, attempt_no=1))
        db.commit()
    finally:
        db.close()

    denied = client.delete(f"/api/admin/lesson-blocks/{block['id']}", headers=headers)
    assert denied.status_code == 409
    assert "作答记录" in denied.json()["detail"]
    db = app.state.session_factory()
    try:
        assert db.get(CourseLessonBlock, block["id"]) is not None
        event = db.query(AuditEvent).filter_by(
            event_type="admin_course_block_delete", resource_id=block["id"], outcome="failure"
        ).order_by(AuditEvent.id.desc()).first()
        import json
        assert event is not None and json.loads(event.summary_json)["attempt_count"] == 1
    finally:
        db.close()


def test_homework_deadline_requires_explicit_extension_after_attempt(tmp_path: Path):
    """已有作答后普通保存不能改截止时间；显式延长会同步 ongoing 作答并审计。"""
    app = build_app(tmp_path)
    client, headers, course, section, lesson = build_lesson_without_content(app)
    paper = seed_paper(app, status="published")
    old_due_at = datetime.now(UTC) + timedelta(days=1)
    new_due_at = old_due_at + timedelta(days=2)
    block = client.post(
        f"/api/admin/lessons/{lesson['id']}/blocks", headers=headers,
        json=block_payload("homework", paper_id=paper["paper_id"], mode="homework",
                           due_at=old_due_at.isoformat()),
    ).json()
    student_login(app)
    db = app.state.session_factory()
    try:
        user = db.query(User).filter_by(username="learner").one()
        attempt = PaperAttempt(source_type="lesson_homework", source_id=block["id"],
                               exam_link_id=None, paper_id=paper["paper_id"], user_id=user.id,
                               attempt_no=1, status="ongoing", deadline_at=old_due_at)
        db.add(attempt)
        db.commit()
        attempt_id = attempt.id
    finally:
        db.close()
    ordinary = client.put(
        f"/api/admin/lesson-blocks/{block['id']}", headers=headers,
        json=block_payload("homework", paper_id=paper["paper_id"], mode="homework",
                           due_at=new_due_at.isoformat()),
    )
    assert ordinary.status_code == 409
    assert "延长截止时间" in ordinary.json()["detail"]

    published = client.post(f"/api/admin/courses/{course['id']}/publish", headers=headers)
    assert published.status_code == 200, published.text

    extended = client.post(
        f"/api/admin/lesson-blocks/{block['id']}/extend-deadline", headers=headers,
        json={"due_at": new_due_at.isoformat()},
    )
    assert extended.status_code == 200, extended.text
    assert extended.json()["updated_ongoing_attempts"] == 1
    db = app.state.session_factory()
    try:
        detail = db.get(LessonPaperBlock, block["id"])
        attempt = db.get(PaperAttempt, attempt_id)
        assert detail.due_at.replace(tzinfo=UTC) == new_due_at
        assert attempt.deadline_at.replace(tzinfo=UTC) == new_due_at
        event = db.query(AuditEvent).filter_by(
            event_type="admin_course_homework_deadline_extend", resource_id=block["id"], outcome="success"
        ).one()
        assert event is not None
    finally:
        db.close()


def test_empty_student_scope_keeps_block_create_and_rejects_extension_before_write(
        tmp_path: Path, monkeypatch):
    app = build_app(tmp_path)
    client, headers, course, _section, lesson = build_lesson_without_content(app)
    paper = seed_paper(app, status="published")
    old_due_at = datetime.now(UTC) + timedelta(days=1)
    new_due_at = old_due_at + timedelta(days=1)
    monkeypatch.setattr(admin_course_content, "visible_student_ids",
                        lambda _admin, _db: set())

    created = client.post(
        f"/api/admin/lessons/{lesson['id']}/blocks", headers=headers,
        json=block_payload("homework", paper_id=paper["paper_id"], mode="homework",
                           due_at=old_due_at.isoformat()),
    )
    assert created.status_code == 201, created.text
    block_id = created.json()["id"]
    assert client.post(f"/api/admin/courses/{course['id']}/publish",
                       headers=headers).status_code == 200

    denied = client.post(
        f"/api/admin/lesson-blocks/{block_id}/extend-deadline", headers=headers,
        json={"due_at": new_due_at.isoformat()},
    )
    assert denied.status_code == 403, denied.text
    db = app.state.session_factory()
    try:
        stored = db.get(LessonPaperBlock, block_id)
        assert stored.due_at.replace(tzinfo=UTC) == old_due_at
    finally:
        db.close()


def test_deadline_extension_updates_only_ongoing_attempts_in_nonempty_scope(
        tmp_path: Path, monkeypatch):
    app = build_app(tmp_path)
    client, headers, course, _section, lesson = build_lesson_without_content(app)
    paper = seed_paper(app, status="published")
    old_due_at = datetime.now(UTC) + timedelta(days=1)
    new_due_at = old_due_at + timedelta(days=1)
    block = client.post(
        f"/api/admin/lessons/{lesson['id']}/blocks", headers=headers,
        json=block_payload("homework", paper_id=paper["paper_id"], mode="homework",
                           due_at=old_due_at.isoformat()),
    ).json()
    student_login(app, "visible-student")
    student_login(app, "hidden-student")
    db = app.state.session_factory()
    try:
        visible = db.query(User).filter_by(username="visible-student").one()
        hidden = db.query(User).filter_by(username="hidden-student").one()
        attempts = [
            PaperAttempt(source_type="lesson_homework", source_id=block["id"],
                         exam_link_id=None, paper_id=paper["paper_id"], user_id=user.id,
                         attempt_no=1, status="ongoing", deadline_at=old_due_at)
            for user in (visible, hidden)
        ]
        db.add_all(attempts)
        db.commit()
        visible_id, hidden_id = visible.id, hidden.id
    finally:
        db.close()
    monkeypatch.setattr(admin_course_content, "visible_student_ids",
                        lambda _admin, _db: {visible_id})
    assert client.post(f"/api/admin/courses/{course['id']}/publish",
                       headers=headers).status_code == 200

    extended = client.post(
        f"/api/admin/lesson-blocks/{block['id']}/extend-deadline", headers=headers,
        json={"due_at": new_due_at.isoformat()},
    )
    assert extended.status_code == 200, extended.text
    assert extended.json()["updated_ongoing_attempts"] == 1
    db = app.state.session_factory()
    try:
        by_user = {attempt.user_id: attempt for attempt in db.query(PaperAttempt).all()}
        assert by_user[visible_id].deadline_at.replace(tzinfo=UTC) == new_due_at
        assert by_user[hidden_id].deadline_at.replace(tzinfo=UTC) == old_due_at
    finally:
        db.close()

# ---------- 试卷素材选择器 ----------


def test_paper_options(tmp_path: Path):
    """素材选择器：默认只回已发布卷，支持分页与关键词。"""
    app = build_app(tmp_path)
    client, headers, course, section, lesson = build_lesson_without_content(app)
    p1 = seed_paper(app, title="发布的卷", status="published")
    seed_paper(app, title="草稿卷", status="draft")

    data = client.get("/api/admin/papers/options", headers=headers).json()
    assert data["total"] == 1
    assert [p["title"] for p in data["items"]] == ["发布的卷"]
    assert data["items"][0]["id"] == p1["paper_id"]

    # 关键词过滤
    data = client.get("/api/admin/papers/options", headers=headers,
                      params={"keyword": "草稿", "status": "draft"}).json()
    assert data["total"] == 1 and data["items"][0]["title"] == "草稿卷"

    # 内容编排可直接输入数据库 ID，不必把大量试卷全部拉到下拉框。
    data = client.get("/api/admin/papers/options", headers=headers,
                      params={"keyword": str(p1["paper_id"])}).json()
    assert data["total"] == 1 and data["items"][0]["id"] == p1["paper_id"]


# ---------- 学生端块 DTO ----------


def test_student_lesson_blocks_dto(tmp_path: Path):
    """学生端：解锁课时按顺序返回块，不泄露 video_id、paper_id 与 problem_id_no。"""
    app = build_app(tmp_path)
    client, headers, course, section, lesson = build_lesson_without_content(app)
    lid = lesson["id"]
    video = seed_ready_video(app)
    paper = seed_paper(app)
    prob = seed_problem(app)

    # 先设试看（已发布课包只读），再补块、再发布
    client.put(f"/api/admin/lessons/{lid}", headers=headers,
               json={"title": "课时 1", "is_trial": True, "duration_minutes": 30})
    client.post(f"/api/admin/lessons/{lid}/blocks", headers=headers,
                json=block_payload("markdown", content_md="# 开场"))
    client.post(f"/api/admin/lessons/{lid}/blocks", headers=headers,
                json=block_payload("video", source_type="platform", video_id=video["video_id"]))
    client.post(f"/api/admin/lessons/{lid}/blocks", headers=headers,
                json=block_payload("practice", problem_id_no=prob["problem_id_no"],
                                   display_no="1", score=10))
    client.post(f"/api/admin/lessons/{lid}/blocks", headers=headers,
                json=block_payload("homework", paper_id=paper["paper_id"], mode="homework"))
    # 非试看课时（发布前建好，学生端应处于未解锁）
    lesson2 = client.post(f"/api/admin/sections/{section['id']}/lessons", headers=headers,
                          json={"title": "非试看"}).json()
    client.post(f"/api/admin/lessons/{lesson2['id']}/blocks", headers=headers,
                json=block_payload("markdown", content_md="# 隐藏"))
    assert client.post(f"/api/admin/courses/{course['id']}/publish", headers=headers).status_code == 200

    sclient = student_login(app)
    data = sclient.get(f"/api/lessons/{lid}").json()
    assert data["unlocked"] is True
    assert [b["block_type"] for b in data["blocks"]] == ["markdown", "video", "practice", "homework"]
    assert data["blocks"][1]["source_type"] == "platform"
    assert "video_id" not in data["blocks"][1]          # 平台视频不下发 id
    assert "ready" in data["blocks"][1]
    # 课中练习单题块：只下发投放规则，绝不下发 problem_id_no（保密红线 §4.4）
    pb = data["blocks"][2]
    assert pb["problem"]["problem_type"] == "choice"
    assert pb["problem"]["display_no"] == "1"
    assert pb["problem"]["score"] == 10
    assert "problem_id_no" not in pb["problem"]
    assert "problem_id_no" not in pb
    # 课后练习块：保持现状，不下发 paper_id
    hw = data["blocks"][3]
    assert hw["mode"] == "homework"
    assert "paper_id" not in hw

    # 未解锁课时：逐块锁定（2026-08-10 起）——块骨架可见（标题 + can_access=false），内容不下发
    locked = sclient.get(f"/api/lessons/{lesson2['id']}").json()
    assert locked["unlocked"] is False
    assert [b["block_type"] for b in locked["blocks"]] == ["markdown"]
    assert locked["blocks"][0]["can_access"] is False
    assert "content_md" not in locked["blocks"][0]
    assert locked["content_md"] is None


def test_student_play_by_block(tmp_path: Path):
    """学生端播放：block_id 指定视频块；不属于该课时的块 404。"""
    app = build_app(tmp_path)
    client, headers, course, section, lesson = build_lesson_without_content(app)
    lid = lesson["id"]
    video = seed_ready_video(app)
    client.put(f"/api/admin/lessons/{lid}", headers=headers,
               json={"title": "课时 1", "is_trial": True, "duration_minutes": 30})
    b = client.post(f"/api/admin/lessons/{lid}/blocks", headers=headers,
                    json=block_payload("video", source_type="platform", video_id=video["video_id"])).json()
    client.post(f"/api/admin/lessons/{lid}/blocks", headers=headers,
                json=block_payload("markdown", content_md="# 开场"))
    # 另一个课时的块（发布前建好，用于「跨课时偷块」负例）
    lesson2 = client.post(f"/api/admin/sections/{section['id']}/lessons", headers=headers,
                          json={"title": "课时 2"}).json()
    foreign = client.post(f"/api/admin/lessons/{lesson2['id']}/blocks", headers=headers,
                          json=block_payload("video", source_type="platform",
                                             video_id=video["video_id"])).json()
    assert client.post(f"/api/admin/courses/{course['id']}/publish", headers=headers).status_code == 200

    sclient = student_login(app)
    resp = sclient.post(f"/api/lessons/{lid}/play", headers=scsrf(sclient),
                        json={"block_id": b["id"]})
    assert resp.status_code == 200, resp.text
    # P2-5：地址是「稳定路径 + query 签名」，不再有 token/base_url 字段。
    # 断言指向的是**这个块绑定的那个视频**——block_id 解析错了，这里就会指到别的 id。
    assert resp.json()["master_playlist"].startswith(
        f"/v/{video['video_id']}/master.m3u8?"
    )

    # 别的课时的块：拒绝
    resp = sclient.post(f"/api/lessons/{lid}/play", headers=scsrf(sclient),
                        json={"block_id": foreign["id"]})
    assert resp.status_code == 404
