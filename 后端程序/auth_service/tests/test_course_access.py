"""学生端课程接口的门控与信息泄露防线。

盯住四件事：
1. 未发布课包对学生等同不存在（404，不是 403）；
2. deny by default——非试看课时 unlocked=false，且正文一个字都不下发；
3. **目录树永不携带正文与 video_id**（这条靠人工验收看不出来，必须有回归用例）；
4. 试看课时放行，且上下节导航按整包展平顺序正确。
"""
from pathlib import Path

from fastapi.testclient import TestClient

from test_admin_courses import add_lesson, add_section, create_category, create_course
from test_admin_course_content import block_payload
from test_exam import admin_login, build_app, scsrf, student_login
from test_student_learning import seed_ready_video


def publish_course_with_lessons(client, headers):
    """建一个已发布课包：第一章（试看课时 A、非试看课时 B）、第二章（课时 C）。"""
    cat = create_category(client, headers).json()
    cid = create_course(client, headers, cat["id"]).json()["id"]
    s1 = add_section(client, headers, cid, "第一章").json()
    s2 = add_section(client, headers, cid, "第二章").json()

    a = client.post(f"/api/admin/sections/{s1['id']}/lessons", headers=headers, json={
        "title": "A 试看", "content_md": "# 免费内容", "duration_minutes": 10, "is_trial": True,
    }).json()
    b = add_lesson(client, headers, s1["id"], "B 付费", content_md="# 付费内容").json()
    c = add_lesson(client, headers, s2["id"], "C 付费", content_md="# 第二章内容").json()

    assert client.post(f"/api/admin/courses/{cid}/publish", headers=headers).status_code == 200
    return cid, a, b, c


def test_unpublished_course_is_404_for_students(tmp_path: Path):
    app = build_app(tmp_path)
    admin, headers = admin_login(app)
    cat = create_category(admin, headers).json()
    cid = create_course(admin, headers, cat["id"]).json()["id"]  # 停在 draft

    student = student_login(app)
    assert student.get(f"/api/courses/{cid}").status_code == 404
    # 列表里也不出现
    assert student.get("/api/courses").json()["total"] == 0


def test_unpublished_course_video_block_cannot_mint_play_token(tmp_path: Path):
    """块级 first_n 判定不能绕过课包发布状态。"""
    app = build_app(tmp_path)
    admin, headers = admin_login(app)
    cat = create_category(admin, headers).json()
    cid = create_course(admin, headers, cat["id"]).json()["id"]
    section = add_section(admin, headers, cid, "第一章").json()
    video = seed_ready_video(app)
    lesson = admin.post(
        f"/api/admin/sections/{section['id']}/lessons",
        headers=headers,
        json={"title": "草稿试看", "open_policy": "first_n", "trial_block_count": 1},
    ).json()
    block = admin.post(
        f"/api/admin/lessons/{lesson['id']}/blocks",
        headers=headers,
        json=block_payload("video", source_type="platform", video_id=video["video_id"]),
    ).json()

    student = student_login(app)
    resp = student.post(
        f"/api/lessons/{lesson['id']}/play",
        headers=scsrf(student),
        json={"block_id": block["id"]},
    )
    assert resp.status_code == 404


def test_catalog_never_carries_content_or_video_id(tmp_path: Path):
    """目录树的防泄露回归线。"""
    app = build_app(tmp_path)
    admin, headers = admin_login(app)
    cid, a, b, _ = publish_course_with_lessons(admin, headers)

    student = student_login(app)
    detail = student.get(f"/api/courses/{cid}")
    assert detail.status_code == 200
    body = detail.json()

    raw = detail.text
    assert "付费内容" not in raw and "免费内容" not in raw, "目录树不得携带任何正文"
    for section in body["sections"]:
        for lesson in section["lessons"]:
            assert "content_md" not in lesson
            assert "video_id" not in lesson
            assert "video_url" not in lesson

    # unlocked 标记：试看 true，其余 false
    flat = {l["title"]: l for s in body["sections"] for l in s["lessons"]}
    assert flat["A 试看"]["unlocked"] is True
    assert flat["B 付费"]["unlocked"] is False
    assert body["enrolled"] is False


def test_locked_lesson_returns_no_body(tmp_path: Path):
    app = build_app(tmp_path)
    admin, headers = admin_login(app)
    _, a, b, _ = publish_course_with_lessons(admin, headers)
    student = student_login(app)

    locked = student.get(f"/api/lessons/{b['id']}")
    assert locked.status_code == 200
    assert locked.json()["unlocked"] is False
    assert locked.json()["content_md"] is None
    assert "付费内容" not in locked.text

    opened = student.get(f"/api/lessons/{a['id']}")
    assert opened.json()["unlocked"] is True
    assert "免费内容" in opened.json()["content_md"]


def test_lesson_navigation_follows_flattened_order(tmp_path: Path):
    app = build_app(tmp_path)
    admin, headers = admin_login(app)
    _, a, b, c = publish_course_with_lessons(admin, headers)
    student = student_login(app)

    first = student.get(f"/api/lessons/{a['id']}").json()
    assert first["prev_lesson_id"] is None and first["next_lesson_id"] == b["id"]

    middle = student.get(f"/api/lessons/{b['id']}").json()
    assert middle["prev_lesson_id"] == a["id"] and middle["next_lesson_id"] == c["id"]

    last = student.get(f"/api/lessons/{c['id']}").json()
    assert last["prev_lesson_id"] == b["id"] and last["next_lesson_id"] is None


def test_play_endpoint_respects_the_same_gate(tmp_path: Path):
    """播放接口与目录用同一份规则：未解锁课时一律 403，不透露有没有视频。"""
    app = build_app(tmp_path)
    admin, headers = admin_login(app)
    _, a, b, _ = publish_course_with_lessons(admin, headers)
    student = student_login(app)

    locked = student.post(f"/api/lessons/{b['id']}/play", headers=scsrf(student), json={})
    assert locked.status_code == 403

    # 试看课时通过门控，但没绑视频 → 404（而不是 403），两种拒绝原因不混淆
    trial = student.post(f"/api/lessons/{a['id']}/play", headers=scsrf(student), json={})
    assert trial.status_code == 404


def test_first_n_blocks_trial_policy(tmp_path: Path):
    """试看前 N 块（open_policy=first_n）：第 1..N 块开放可学，第 N+1 块起锁定。

    权限必须后端逐块判定：锁定块的正文不下发、视频块拿不到播放令牌。
    """
    app = build_app(tmp_path)
    client, headers = admin_login(app)
    cat = create_category(client, headers).json()
    cid = create_course(client, headers, cat["id"]).json()["id"]
    section = add_section(client, headers, cid, "第一章").json()
    video = seed_ready_video(app)

    lesson = client.post(f"/api/admin/sections/{section['id']}/lessons", headers=headers, json={
        "title": "前 2 块试看", "open_policy": "first_n", "trial_block_count": 2,
        "duration_minutes": 10,
    }).json()
    lid = lesson["id"]
    # 块顺序：图文（开放）→ 视频（开放）→ 视频（锁定）
    client.post(f"/api/admin/lessons/{lid}/blocks", headers=headers,
                json=block_payload("markdown", content_md="# 开场白"))
    open_video = client.post(f"/api/admin/lessons/{lid}/blocks", headers=headers,
                             json=block_payload("video", source_type="platform",
                                                video_id=video["video_id"])).json()
    locked_video = client.post(f"/api/admin/lessons/{lid}/blocks", headers=headers,
                               json=block_payload("video", source_type="platform",
                                                  video_id=video["video_id"])).json()
    assert client.post(f"/api/admin/courses/{cid}/publish", headers=headers).status_code == 200

    student = student_login(app)
    data = student.get(f"/api/lessons/{lid}").json()
    # 课时级不算完整解锁，但前 2 个块可以学
    assert data["unlocked"] is False
    assert data["open_policy"] == "first_n"
    assert data["trial_block_count"] == 2
    assert data["blocks"][0]["can_access"] is True
    assert data["blocks"][0]["content_md"] == "# 开场白"
    assert data["blocks"][1]["can_access"] is True
    assert data["blocks"][2]["can_access"] is False
    assert "video_url" not in data["blocks"][2]
    assert data["content_md"] is None  # 旧字段不因前 N 块开放而下发（内容一律走 blocks）

    # 播放门控同口径：前 N 块内的视频能拿令牌，锁定的视频块 403
    opened = student.post(f"/api/lessons/{lid}/play", headers=scsrf(student),
                          json={"block_id": open_video["id"]})
    assert opened.status_code == 200, opened.text
    locked = student.post(f"/api/lessons/{lid}/play", headers=scsrf(student),
                          json={"block_id": locked_video["id"]})
    assert locked.status_code == 403
