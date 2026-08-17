"""学习端首页「继续学习」聚合接口（GET /api/courses/continue-learning）的端到端回归。

数据源是四张学习活动账本（lesson_video_watch / lesson_block_completions /
lesson_problem_attempts / lesson_code_runs），按「最近活动时间」聚合到课时。
这里钉的是：无记录返回空、视频续播断点、课时学完后的「下一节」跳转、下架课程过滤、
按最近活动排序，以及课时详情视频块下发续播断点字段（播放器据此 seek）。
"""
from datetime import timedelta
from pathlib import Path

from sqlalchemy import select
from test_admin_course_content import block_payload
from test_exam import build_app, scsrf, student_login
from test_lesson_block_unlock import build_lesson_with_blocks
from test_lesson_video_watch import build_video_lesson, watch

from app.models import CourseLesson, LessonVideoWatch
from app.security import utcnow


def continue_items(client, **query):
    resp = client.get("/api/courses/continue-learning", params=query)
    assert resp.status_code == 200, resp.text
    return resp.json()["items"]


def complete(client, lesson_id, block_id, **body):
    return client.post(
        f"/api/lessons/{lesson_id}/blocks/{block_id}/complete",
        headers=scsrf(client), json=body or {"source": "manual"},
    )


def _add_lesson(app, built, *, title, content_md="正文内容"):
    """在 built 的同一课包/章节里追加一节课时 + 一个必修 markdown 块，返回 (lesson_id, block_id)。

    已发布课包不能直接编辑：先下架、加完再重新发布（发布校验要求至少一个可学课时）。
    """
    client, headers = built["client"], built["headers"]
    course_id = built["course_id"]
    resp = client.post(f"/api/admin/courses/{course_id}/off-shelf", headers=headers)
    assert resp.status_code == 200, resp.text
    db = app.state.session_factory()
    try:
        section_id = db.scalar(
            select(CourseLesson.section_id).where(CourseLesson.id == built["lesson_id"]))
    finally:
        db.close()
    resp = client.post(f"/api/admin/sections/{section_id}/lessons", headers=headers,
                       json={"title": title, "duration_minutes": 20, "open_policy": "whole"})
    assert resp.status_code in (200, 201), resp.text
    lesson_id = resp.json()["id"]
    body = block_payload("markdown", content_md=content_md)
    body.update({"title": title, "required": True, "unlock_rule": "free"})
    resp = client.post(f"/api/admin/lessons/{lesson_id}/blocks", headers=headers, json=body)
    assert resp.status_code in (200, 201), resp.text
    resp = client.post(f"/api/admin/courses/{course_id}/publish", headers=headers)
    assert resp.status_code == 200, resp.text
    return lesson_id, resp.json()["id"]


def _set_activity_time(app, lesson_id, seconds_ago):
    """把该课时账本行的 updated_at 拨回 seconds_ago 秒，模拟更早的学习活动。"""
    db = app.state.session_factory()
    try:
        for row in db.scalars(
            select(LessonVideoWatch).where(LessonVideoWatch.lesson_id == lesson_id)
        ).all():
            row.updated_at = utcnow() - timedelta(seconds=seconds_ago)
        db.commit()
    finally:
        db.close()


def test_empty_when_no_activity(tmp_path: Path):
    app = build_app(tmp_path)
    client = student_login(app)
    assert continue_items(client) == []


def test_video_resume_position_and_progress(tmp_path: Path):
    """平台视频看了 120s：条目返回本课时、续播断点=120、进度 0/1、continue 指向本课时。"""
    app = build_app(tmp_path)
    built = build_video_lesson(app, duration=600, completion_percent=80)
    client = student_login(app)
    resp = watch(client, built["lesson_id"], built["video_block_id"], 120)
    assert resp.status_code == 200, resp.text

    items = continue_items(client)
    assert len(items) == 1
    item = items[0]
    assert item["lesson_id"] == built["lesson_id"]
    assert item["course_id"] == built["course_id"]
    assert item["resume_position_seconds"] == 120
    assert item["completed"] is False
    assert item["continue_lesson_id"] == built["lesson_id"]
    assert item["progress"] == {"total": 1, "done": 0, "percent": 0}
    assert item["last_learned_at"]


def test_completed_lesson_points_to_next(tmp_path: Path):
    """第一节已学完 → continue_lesson_id 指向同课包第二节未学课时。"""
    app = build_app(tmp_path)
    built = build_lesson_with_blocks(app, [{"title": "A"}])
    lid2, bid2 = _add_lesson(app, built, title="课时 2")
    client = student_login(app)

    resp = complete(client, built["lesson_id"], built["block_ids"][0])
    assert resp.status_code == 200, resp.text

    items = continue_items(client)
    assert len(items) == 1
    assert items[0]["lesson_id"] == built["lesson_id"]
    assert items[0]["completed"] is True
    assert items[0]["continue_lesson_id"] == lid2
    assert items[0]["continue_lesson_title"] == "课时 2"
    # 完成态不显示续播断点
    assert items[0]["resume_position_seconds"] == 0


def test_all_lessons_done_returns_no_continue(tmp_path: Path):
    """课包内全部课时学完 → continue_lesson_id 为 None（整门课已学完）。"""
    app = build_app(tmp_path)
    built = build_lesson_with_blocks(app, [{"title": "A"}])
    client = student_login(app)
    assert complete(client, built["lesson_id"], built["block_ids"][0]).status_code == 200
    items = continue_items(client)
    assert len(items) == 1
    assert items[0]["completed"] is True
    assert items[0]["continue_lesson_id"] is None


def test_off_shelf_course_filtered(tmp_path: Path):
    """课程下架后，该课时的学习记录不再出现在继续学习里。"""
    app = build_app(tmp_path)
    built = build_video_lesson(app, duration=600)
    client = student_login(app)
    assert watch(client, built["lesson_id"], built["video_block_id"], 30).status_code == 200
    assert len(continue_items(client)) == 1

    resp = built["client"].post(f"/api/admin/courses/{built['course_id']}/off-shelf",
                                headers=built["headers"])
    assert resp.status_code == 200, resp.text
    assert continue_items(client) == []


def test_ordered_by_recent_activity(tmp_path: Path):
    """两个课包都有学习记录：最近活动的课时排前面。"""
    app = build_app(tmp_path)
    first = build_video_lesson(app, duration=600)
    second = build_video_lesson(app, duration=600)
    client = student_login(app)
    assert watch(client, first["lesson_id"], first["video_block_id"], 10).status_code == 200
    assert watch(client, second["lesson_id"], second["video_block_id"], 20).status_code == 200
    _set_activity_time(app, first["lesson_id"], 3600)  # 第一节拨回 1 小时前

    items = continue_items(client)
    assert [i["lesson_id"] for i in items] == [second["lesson_id"], first["lesson_id"]]


def test_lesson_detail_video_block_has_resume(tmp_path: Path):
    """课时详情：平台视频块下发 resume_position_seconds，播放器据此续播。"""
    app = build_app(tmp_path)
    built = build_video_lesson(app, duration=600)
    client = student_login(app)
    assert watch(client, built["lesson_id"], built["video_block_id"], 42).status_code == 200

    resp = client.get(f"/api/lessons/{built['lesson_id']}")
    assert resp.status_code == 200, resp.text
    video_blocks = [b for b in resp.json()["blocks"] if b["block_type"] == "video"]
    assert video_blocks, "课时里应有一个视频块"
    assert video_blocks[0]["resume_position_seconds"] == 42
