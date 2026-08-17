"""Scratch 挑战后端回归（任务书 21b 验收清单）。

覆盖顺序与任务书「验收」一致：

- 未登录 / 未选课 / 未解锁 / 挑战未发布 → 各自的失败姿态（401 / 403 / 403 / 404）；
- 跨学生项目：拿到别人的 project_id 也读不到、写不进（**404 不是 403**）；
- 伪造通过：学生端 `/complete` 对 scratch 块一律只读，提交请求里塞 passed 无效；
- 重复提交：attempt_no 递增，历史可查；
- 版本冻结：交完再改作品，提交仍指向当时那一版；规则改了也不改写历史判定；
- 判定通过后解锁：走既有完成流程，progress 与 unlocked_block_ids 与 /complete 同形状。

外加结构检查（坏 ZIP / 超大 / 缺 project.json）、保存限流、扩展白名单、
运行型规则转人工，以及管理端的发布检查与删除保护。

`.sb3` 全部在内存里现造（`sb3_bytes`）：不放二进制夹具进仓库，用例读起来也能直接
看出"这个项目里有哪些积木"——判定断言的可读性全靠它。
"""
import json
import zipfile
from io import BytesIO
from pathlib import Path

from sqlalchemy import select
from test_admin_courses import add_section, create_category, create_course, reviewer_login
from test_exam import admin_login, build_app, scsrf, student_login

from app.models import (
    CourseLessonBlock,
    LessonBlockCompletion,
    ScratchChallenge,
    ScratchProject,
    ScratchProjectRevision,
    ScratchSubmission,
)

# ---------- .sb3 夹具 ----------


def stage_target(variables=None, broadcasts=None) -> dict:
    return {
        "isStage": True, "name": "Stage", "blocks": {},
        "variables": variables or {}, "broadcasts": broadcasts or {},
        "x": 0, "y": 0,
    }


def scripted_sprite(*, name="小猫", steps="10", message="你好", x=0, y=0,
                    with_flag=True) -> dict:
    """一个"绿旗 → 移动 N 步 → 说一句话"的角色。

    积木字典的形状照 `scratch-vm` 的 sb3 序列化：inputs 里 `[1, [4, "10"]]` 是数字
    字面值、`[1, [10, "你好"]]` 是文本字面值，next 串起同一段脚本。
    """
    blocks = {
        "b_move": {
            "opcode": "motion_movesteps", "next": "b_say", "parent": "b_hat",
            "inputs": {"STEPS": [1, [4, steps]]}, "fields": {},
            "shadow": False, "topLevel": False,
        },
        "b_say": {
            "opcode": "looks_say", "next": None, "parent": "b_move",
            "inputs": {"MESSAGE": [1, [10, message]]}, "fields": {},
            "shadow": False, "topLevel": False,
        },
    }
    if with_flag:
        blocks["b_hat"] = {
            "opcode": "event_whenflagclicked", "next": "b_move", "parent": None,
            "inputs": {}, "fields": {}, "shadow": False, "topLevel": True, "x": 0, "y": 0,
        }
    else:
        # 同样的积木，但没有绿旗帽子：require_after_hat 必须判不通过。
        blocks["b_move"]["parent"] = None
        blocks["b_move"]["topLevel"] = True
    return {"isStage": False, "name": name, "blocks": blocks, "variables": {},
            "broadcasts": {}, "x": x, "y": y}


def sb3_bytes(targets=None, extensions=None, *, project_json=True, extra=None) -> bytes:
    project = {
        "targets": targets if targets is not None else [stage_target(), scripted_sprite()],
        "extensions": extensions or [],
        "meta": {"semver": "3.0.0", "vm": "1.0.0", "agent": "test"},
    }
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        if project_json:
            archive.writestr("project.json", json.dumps(project, ensure_ascii=False))
        for name, payload in (extra or {}).items():
            archive.writestr(name, payload)
    return buffer.getvalue()


PASSING_RULES = [
    {"type": "require_after_hat", "hat": "event_whenflagclicked",
     "opcode": "motion_movesteps", "label": "绿旗被点击后让角色移动"},
    {"type": "require_input_value", "opcode": "motion_movesteps", "input": "STEPS",
     "equals": 10, "label": "移动 10 步"},
    {"type": "require_say_text", "text": "你好", "label": "让角色说「你好」"},
]


# ---------- 环境搭建 ----------


_seq = {"n": 0}


DEMO_SB3 = sb3_bytes([stage_target(), scripted_sprite(name="示范小猫")])


def create_challenge(client, headers, *, rules=None, title="绿旗动一动",
                     starter=True, publish=True, extensions=None, hints=None,
                     demo=False, rubric=None):
    body = {
        "title": title,
        "instructions_md": "# 任务\n\n点击绿旗后，让小猫移动 10 步并说「你好」。",
        "rules": PASSING_RULES if rules is None else rules,
        "allowed_extensions": extensions or [],
        "hints": hints or ["先从「事件」分类里拖出绿旗积木"],
        "rubric": rubric or {},
    }
    resp = client.post("/api/admin/scratch/challenges", headers=headers, json=body)
    assert resp.status_code == 201, resp.text
    challenge = resp.json()
    if starter:
        up = client.post(
            f"/api/admin/scratch/challenges/{challenge['id']}/starter", headers=headers,
            files={"file": ("starter.sb3", sb3_bytes([stage_target()]), "application/zip")},
        )
        assert up.status_code == 200, up.text
    if demo:
        up = client.post(
            f"/api/admin/scratch/challenges/{challenge['id']}/demo-project", headers=headers,
            files={"file": ("demo.sb3", DEMO_SB3, "application/zip")},
        )
        assert up.status_code == 200, up.text
    if publish:
        pub = client.post(f"/api/admin/scratch/challenges/{challenge['id']}/publish",
                          headers=headers)
        assert pub.status_code == 200, pub.text
        challenge = pub.json()["challenge"]
    return challenge


def build_scratch_lesson(app, *, open_policy="whole", blocks=None, challenge=None,
                         publish_course=True, unlock_rule="free"):
    """分类 → 课包 → 章节 → 课时 → 挑战 → scratch 块（默认再补一个 sequential 后继块）。

    返回 {"client","headers","course_id","lesson_id","block_ids","challenge"}。
    """
    client, headers = admin_login(app)
    _seq["n"] += 1
    n = _seq["n"]
    cat = create_category(client, headers, name=f"分类{n}").json()
    course = create_course(client, headers, cat["id"], title=f"课包{n}").json()
    section = add_section(client, headers, course["id"]).json()
    lesson = client.post(
        f"/api/admin/sections/{section['id']}/lessons", headers=headers,
        json={"title": "课时 1", "duration_minutes": 30, "open_policy": open_policy},
    ).json()
    challenge = challenge or create_challenge(client, headers)

    specs = blocks or [
        {"block_type": "scratch", "title": "闯关：绿旗动一动", "unlock_rule": unlock_rule,
         "detail": {"scratch": {"challenge_id": challenge["id"]}}},
        {"block_type": "markdown", "title": "小结", "unlock_rule": "sequential",
         "detail": {"markdown": {"content_md": "# 恭喜过关"}}},
    ]
    block_ids = []
    for spec in specs:
        body = {"title": "块", "required": True, "unlock_rule": "free", **spec}
        resp = client.post(f"/api/admin/lessons/{lesson['id']}/blocks", headers=headers,
                           json=body)
        assert resp.status_code in (200, 201), resp.text
        block_ids.append(resp.json()["id"])
    if publish_course:
        pub = client.post(f"/api/admin/courses/{course['id']}/publish", headers=headers)
        assert pub.status_code == 200, pub.text
    return {"client": client, "headers": headers, "course_id": course["id"],
            "lesson_id": lesson["id"], "block_ids": block_ids, "challenge": challenge}


def save_project(sclient, project_id, data, *, challenge_id=None, source="manual"):
    form = {"source": source}
    if challenge_id is not None:
        form["challenge_id"] = str(challenge_id)
    return sclient.put(
        f"/api/scratch/projects/{project_id}", headers=scsrf(sclient),
        files={"file": ("project.sb3", data, "application/zip")}, data=form,
    )


def open_block(sclient, block_id):
    return sclient.get(f"/api/scratch/lesson-blocks/{block_id}")


def submit(sclient, block_id, **body):
    return sclient.post(f"/api/scratch/lesson-blocks/{block_id}/submit",
                        headers=scsrf(sclient), json=body or None)


def fetch_demo(sclient, block_id):
    return sclient.get(f"/api/scratch/lesson-blocks/{block_id}/demo.sb3")


def work_and_submit(sclient, block_id, data=None):
    """保存一版再提交，返回判定状态。示范项目的用例只关心"交没交、出没出结果"。"""
    project_id = open_block(sclient, block_id).json()["project"]["id"]
    save_project(sclient, project_id, data if data is not None else sb3_bytes())
    return submit(sclient, block_id)


def scratch_env(tmp_path: Path, **overrides):
    """带独立 SCRATCH_UPLOAD_ROOT 的测试 app：作品落盘不能写进仓库目录。"""
    return build_app(tmp_path, scratch_upload_root=str(tmp_path / "scratch"), **overrides)


# ---------- 门控 ----------


def test_anonymous_cannot_read_challenge(tmp_path: Path):
    """未登录：挑战详情、初始项目、提交一律 401。"""
    app = scratch_env(tmp_path)
    built = build_scratch_lesson(app)
    from fastapi.testclient import TestClient
    guest = TestClient(app)
    block_id = built["block_ids"][0]
    assert guest.get(f"/api/scratch/lesson-blocks/{block_id}").status_code == 401
    assert guest.get(f"/api/scratch/lesson-blocks/{block_id}/starter.sb3").status_code == 401
    assert guest.post(f"/api/scratch/lesson-blocks/{block_id}/submit").status_code in (401, 403)


def test_locked_lesson_hides_starter(tmp_path: Path):
    """未选课（open_policy=closed）：403，且**读不到初始项目**。"""
    app = scratch_env(tmp_path)
    built = build_scratch_lesson(app, open_policy="closed")
    sclient = student_login(app)
    block_id = built["block_ids"][0]
    assert open_block(sclient, block_id).status_code == 403
    assert sclient.get(f"/api/scratch/lesson-blocks/{block_id}/starter.sb3").status_code == 403
    assert submit(sclient, block_id).status_code == 403


def test_sequential_lock_blocks_scratch(tmp_path: Path):
    """未解锁（Gate B 顺序锁）：403，文案与既有课中练习一致。"""
    app = scratch_env(tmp_path)
    client, headers = admin_login(app)
    challenge = create_challenge(client, headers)
    built = build_scratch_lesson(app, challenge=challenge, blocks=[
        {"block_type": "markdown", "title": "先看这个",
         "detail": {"markdown": {"content_md": "# 前置"}}},
        {"block_type": "scratch", "title": "闯关", "unlock_rule": "sequential",
         "detail": {"scratch": {"challenge_id": challenge["id"]}}},
    ])
    sclient = student_login(app)
    resp = open_block(sclient, built["block_ids"][1])
    assert resp.status_code == 403
    assert "前面" in resp.json()["detail"]


def test_unpublished_challenge_is_invisible(tmp_path: Path):
    """挑战未发布 → 404（草稿关卡对学生等同不存在，不泄露题面与初始项目）。

    发布检查已经拦住了"绑草稿挑战的课包上架"，所以这里直接把库里的状态改回
    draft，模拟"课包在售期间挑战被归档"的脏状态——这条路径必须也是 404。
    """
    app = scratch_env(tmp_path)
    built = build_scratch_lesson(app)
    db = app.state.session_factory()
    try:
        challenge = db.get(ScratchChallenge, built["challenge"]["id"])
        challenge.status = "draft"
        db.commit()
    finally:
        db.close()
    sclient = student_login(app)
    block_id = built["block_ids"][0]
    assert open_block(sclient, block_id).status_code == 404
    assert sclient.get(f"/api/scratch/lesson-blocks/{block_id}/starter.sb3").status_code == 404
    # 课时详情里也不该再出现这个块（与"视频块没绑定"同口径：明细缺失=不存在）
    detail = sclient.get(f"/api/lessons/{built['lesson_id']}").json()
    assert [b["block_type"] for b in detail["blocks"]] == ["markdown"]


def test_non_scratch_block_id_is_404(tmp_path: Path):
    """拿一个 markdown 块的 id 打 Scratch 接口 → 404，不是 400。"""
    app = scratch_env(tmp_path)
    built = build_scratch_lesson(app)
    sclient = student_login(app)
    assert open_block(sclient, built["block_ids"][1]).status_code == 404


# ---------- 挑战详情与初始项目 ----------


def test_block_detail_gives_checklist_but_not_rule_params(tmp_path: Path):
    """详情下发任务清单文案，**不下发规则参数**（参数里带着期望值 = 答案）。"""
    app = scratch_env(tmp_path)
    built = build_scratch_lesson(app)
    sclient = student_login(app)
    payload = open_block(sclient, built["block_ids"][0]).json()

    assert payload["challenge"]["title"] == "绿旗动一动"
    assert payload["challenge"]["checklist"] == [
        "绿旗被点击后让角色移动", "移动 10 步", "让角色说「你好」",
    ]
    assert payload["challenge"]["has_starter"] is True
    assert payload["project"]["current_revision_no"] == 0
    assert payload["project"]["content_url"] is None
    assert payload["last_submission"] is None
    body = json.dumps(payload, ensure_ascii=False)
    for leaked in ("require_after_hat", "motion_movesteps", "rules_snapshot"):
        assert leaked not in body

    starter = sclient.get(f"/api/scratch/lesson-blocks/{built['block_ids'][0]}/starter.sb3")
    assert starter.status_code == 200
    assert zipfile.ZipFile(BytesIO(starter.content)).read("project.json")


def test_lesson_detail_entry_card_tracks_submission_state(tmp_path: Path):
    """课时详情里的 scratch 入口卡片：关卡名 + 摘要 + 我上次交得怎么样。

    对应 `BlockScratch.vue` 消费的字段。**不含题面全文与判定清单**——那些要走
    /api/scratch/lesson-blocks/{id}，那条路径会重跑一次门控。
    """
    app = scratch_env(tmp_path)
    built = build_scratch_lesson(app)
    sclient = student_login(app)
    block_id = built["block_ids"][0]

    card = sclient.get(f"/api/lessons/{built['lesson_id']}").json()["blocks"][0]["scratch"]
    assert card["challenge_id"] == built["challenge"]["id"]
    assert card["challenge_title"] == "绿旗动一动"
    assert card["has_starter"] is True
    assert card["submission_status"] is None
    assert card["attempt_count"] == 0
    assert card["instructions_summary"].startswith("任务")

    project_id = open_block(sclient, block_id).json()["project"]["id"]
    save_project(sclient, project_id,
                 sb3_bytes([stage_target(), scripted_sprite(steps="5")]))
    submit(sclient, block_id)
    card = sclient.get(f"/api/lessons/{built['lesson_id']}").json()["blocks"][0]["scratch"]
    assert card["submission_status"] == "failed"
    assert card["attempt_count"] == 1
    assert card["feedback"]

    save_project(sclient, project_id, sb3_bytes())
    submit(sclient, block_id)
    card = sclient.get(f"/api/lessons/{built['lesson_id']}").json()["blocks"][0]["scratch"]
    assert card["submission_status"] == "passed"
    assert card["attempt_count"] == 2


def test_project_row_is_reused_across_reads(tmp_path: Path):
    """重复打开挑战不会建出第二份工作副本（一人一挑战唯一）。"""
    app = scratch_env(tmp_path)
    built = build_scratch_lesson(app)
    sclient = student_login(app)
    first = open_block(sclient, built["block_ids"][0]).json()["project"]["id"]
    second = open_block(sclient, built["block_ids"][0]).json()["project"]["id"]
    assert first == second
    db = app.state.session_factory()
    try:
        assert len(db.scalars(select(ScratchProject)).all()) == 1
    finally:
        db.close()


# ---------- 保存与版本 ----------


def test_save_creates_immutable_revisions(tmp_path: Path):
    """保存产生递增版本；内容没变时不新建版本（Studio 高频自动保存的去重）。"""
    app = scratch_env(tmp_path)
    built = build_scratch_lesson(app)
    sclient = student_login(app)
    project_id = open_block(sclient, built["block_ids"][0]).json()["project"]["id"]

    first = save_project(sclient, project_id, sb3_bytes(),
                         challenge_id=built["challenge"]["id"])
    assert first.status_code == 200, first.text
    assert first.json()["unchanged"] is False
    assert first.json()["revision"]["revision_no"] == 1
    assert first.json()["revision"]["sprite_count"] == 1

    again = save_project(sclient, project_id, sb3_bytes())
    assert again.json()["unchanged"] is True
    assert again.json()["revision"]["revision_no"] == 1

    changed = save_project(sclient, project_id,
                           sb3_bytes([stage_target(), scripted_sprite(steps="20")]))
    assert changed.json()["revision"]["revision_no"] == 2

    # 取回的永远是当前版本
    content = sclient.get(f"/api/scratch/projects/{project_id}/content.sb3")
    assert content.status_code == 200
    project = json.loads(zipfile.ZipFile(BytesIO(content.content)).read("project.json"))
    assert project["targets"][1]["blocks"]["b_move"]["inputs"]["STEPS"][1][1] == "20"


def test_challenge_mismatch_is_rejected(tmp_path: Path):
    """挑战不匹配（Studio 状态过期）→ 409，不把 A 关的作品写进 B 关的项目。"""
    app = scratch_env(tmp_path)
    built = build_scratch_lesson(app)
    sclient = student_login(app)
    project_id = open_block(sclient, built["block_ids"][0]).json()["project"]["id"]
    resp = save_project(sclient, project_id, sb3_bytes(),
                        challenge_id=built["challenge"]["id"] + 999)
    assert resp.status_code == 409


def test_cross_student_project_is_404(tmp_path: Path):
    """跨学生：拿到别人的 project_id，读和写都必须是 **404**（403 等于确认它存在）。"""
    app = scratch_env(tmp_path)
    built = build_scratch_lesson(app)
    owner = student_login(app, "owner")
    project_id = open_block(owner, built["block_ids"][0]).json()["project"]["id"]
    assert save_project(owner, project_id, sb3_bytes()).status_code == 200

    intruder = student_login(app, "intruder")
    assert save_project(intruder, project_id, sb3_bytes()).status_code == 404
    assert intruder.get(f"/api/scratch/projects/{project_id}/content.sb3").status_code == 404


def test_broken_uploads_are_rejected(tmp_path: Path):
    """结构检查：坏 ZIP / 缺 project.json / 超大文件分别 400 / 400 / 413。"""
    app = scratch_env(tmp_path, scratch_sb3_max_bytes=256 * 1024)
    built = build_scratch_lesson(app)
    sclient = student_login(app)
    project_id = open_block(sclient, built["block_ids"][0]).json()["project"]["id"]

    bad = save_project(sclient, project_id, b"this is not a zip at all")
    assert bad.status_code == 400 and "ZIP" in bad.json()["detail"]

    empty_zip = sb3_bytes(project_json=False, extra={"readme.txt": "hi"})
    missing = save_project(sclient, project_id, empty_zip)
    assert missing.status_code == 400 and "project.json" in missing.json()["detail"]

    oversize = save_project(sclient, project_id, b"x" * (256 * 1024 + 10))
    assert oversize.status_code == 413


def test_save_rate_limited(tmp_path: Path):
    """保存频率闸：超过配额 429（限流在读文件体之前，不浪费带宽）。"""
    app = scratch_env(tmp_path, scratch_save_rate_max=2, scratch_save_rate_seconds=60)
    built = build_scratch_lesson(app)
    sclient = student_login(app)
    project_id = open_block(sclient, built["block_ids"][0]).json()["project"]["id"]
    assert save_project(sclient, project_id, sb3_bytes()).status_code == 200
    assert save_project(sclient, project_id, sb3_bytes([stage_target()])).status_code == 200
    assert save_project(sclient, project_id, sb3_bytes()).status_code == 429


# ---------- 判定 ----------


def test_submit_requires_saved_work(tmp_path: Path):
    app = scratch_env(tmp_path)
    built = build_scratch_lesson(app)
    sclient = student_login(app)
    open_block(sclient, built["block_ids"][0])
    resp = submit(sclient, built["block_ids"][0])
    assert resp.status_code == 400 and "先保存" in resp.json()["detail"]


def test_failing_submission_gives_per_rule_feedback(tmp_path: Path):
    """未通过：逐条反馈 + 不完成 + 不解锁。"""
    app = scratch_env(tmp_path)
    built = build_scratch_lesson(app)
    sclient = student_login(app)
    block_id, next_id = built["block_ids"]
    project_id = open_block(sclient, block_id).json()["project"]["id"]
    # 没有绿旗帽子、步数是 5、说的话也不对：三条规则全不满足
    save_project(sclient, project_id,
                 sb3_bytes([stage_target(),
                            scripted_sprite(steps="5", message="哈喽", with_flag=False)]))
    resp = submit(sclient, block_id)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["submission_status"] == "failed"
    assert body["passed"] is False
    assert body["completed"] is False
    assert body["unlocked_block_ids"] == []
    assert body["score"] == 0
    assert [item["passed"] for item in body["feedback"]["items"]] == [False, False, False]
    assert all(item["message"] for item in body["feedback"]["items"])

    # 后继块仍然锁着
    detail = sclient.get(f"/api/lessons/{built['lesson_id']}").json()
    assert [b["lock_reason"] for b in detail["blocks"]] == [None, "sequential"]
    assert next_id == detail["blocks"][1]["id"]


def test_passing_submission_completes_and_unlocks(tmp_path: Path):
    """判定通过 → 服务端写完成记录 → progress / unlocked_block_ids 与 /complete 同形状。"""
    app = scratch_env(tmp_path)
    built = build_scratch_lesson(app)
    sclient = student_login(app)
    block_id, next_id = built["block_ids"]
    project_id = open_block(sclient, block_id).json()["project"]["id"]
    save_project(sclient, project_id, sb3_bytes())

    body = submit(sclient, block_id).json()
    assert body["submission_status"] == "passed"
    assert body["passed"] is True
    assert body["score"] == 100
    assert body["completed"] is True
    assert body["unlocked_block_ids"] == [next_id]
    assert body["progress"] == {"total": 2, "done": 1, "percent": 50}
    assert body["attempt_no"] == 1

    detail = sclient.get(f"/api/lessons/{built['lesson_id']}").json()
    assert [b["lock_reason"] for b in detail["blocks"]] == [None, None]
    assert detail["blocks"][0]["completed"] is True

    db = app.state.session_factory()
    try:
        row = db.scalar(select(LessonBlockCompletion).where(
            LessonBlockCompletion.block_id == block_id))
        assert row is not None and row.source == "scratch"
    finally:
        db.close()


def test_runtime_rules_go_to_manual_review(tmp_path: Path):
    """运行型规则本版判不了 → needs_review（**不自动通过**），不写完成记录。"""
    app = scratch_env(tmp_path)
    client, headers = admin_login(app)
    challenge = create_challenge(client, headers, rules=[
        {"type": "require_after_hat", "hat": "event_whenflagclicked",
         "opcode": "motion_movesteps", "label": "绿旗后移动"},
        {"type": "sprite_end_position", "sprite": "小猫", "x": 100, "y": 0,
         "label": "跑完停在舞台右边"},
    ])
    built = build_scratch_lesson(app, challenge=challenge)
    sclient = student_login(app)
    block_id = built["block_ids"][0]
    project_id = open_block(sclient, block_id).json()["project"]["id"]
    save_project(sclient, project_id, sb3_bytes())

    body = submit(sclient, block_id).json()
    assert body["submission_status"] == "needs_review"
    assert body["passed"] is False
    assert body["needs_review"] is True
    assert body["score"] is None
    assert body["completed"] is False
    assert body["unlocked_block_ids"] == []


def test_disallowed_extension_fails_submission(tmp_path: Path):
    """扩展白名单在提交时裁决：保存不拦（不丢学生的工作），提交判不过。"""
    app = scratch_env(tmp_path)
    client, headers = admin_login(app)
    challenge = create_challenge(client, headers, extensions=["pen"])
    built = build_scratch_lesson(app, challenge=challenge)
    sclient = student_login(app)
    block_id = built["block_ids"][0]
    project_id = open_block(sclient, block_id).json()["project"]["id"]
    saved = save_project(sclient, project_id,
                         sb3_bytes(extensions=["pen", "music"]))
    assert saved.status_code == 200  # 保存照常成功

    body = submit(sclient, block_id).json()
    assert body["submission_status"] == "failed"
    assert "music" in body["feedback"]["note"]
    assert body["feedback"]["items"][-1]["label"] == "只使用本关允许的扩展"


# ---------- 伪造、重复提交与版本冻结 ----------


def test_client_cannot_forge_completion(tmp_path: Path):
    """伪造通过：学生端 `/complete` 对 scratch 块**静默只读**，不写任何记录。"""
    app = scratch_env(tmp_path)
    built = build_scratch_lesson(app)
    sclient = student_login(app)
    block_id, next_id = built["block_ids"]

    resp = sclient.post(
        f"/api/lessons/{built['lesson_id']}/blocks/{block_id}/complete",
        headers=scsrf(sclient), json={"source": "manual", "progress_percent": 100},
    )
    assert resp.status_code == 200
    assert resp.json()["completed"] is False
    assert resp.json()["unlocked_block_ids"] == []

    db = app.state.session_factory()
    try:
        assert db.scalars(select(LessonBlockCompletion)).all() == []
    finally:
        db.close()
    # 后继块没被解锁
    detail = sclient.get(f"/api/lessons/{built['lesson_id']}").json()
    assert detail["blocks"][1]["id"] == next_id
    assert detail["blocks"][1]["lock_reason"] == "sequential"


def test_submit_ignores_client_supplied_verdict(tmp_path: Path):
    """提交请求里塞 passed/score/completed：服务端一概不看，仍按作品判定。"""
    app = scratch_env(tmp_path)
    built = build_scratch_lesson(app)
    sclient = student_login(app)
    block_id = built["block_ids"][0]
    project_id = open_block(sclient, block_id).json()["project"]["id"]
    save_project(sclient, project_id,
                 sb3_bytes([stage_target(), scripted_sprite(steps="5")]))

    body = submit(sclient, block_id, passed=True, score=100, completed=True,
                  submission_status="passed").json()
    assert body["passed"] is False
    assert body["submission_status"] == "failed"
    assert body["completed"] is False
    assert body["score"] == 67  # 三条规则过了两条


def test_repeated_submissions_are_recorded(tmp_path: Path):
    """重复提交：attempt_no 递增，历史最新在前，通过后仍可再交。"""
    app = scratch_env(tmp_path)
    built = build_scratch_lesson(app)
    sclient = student_login(app)
    block_id = built["block_ids"][0]
    project_id = open_block(sclient, block_id).json()["project"]["id"]

    save_project(sclient, project_id,
                 sb3_bytes([stage_target(), scripted_sprite(steps="5")]))
    assert submit(sclient, block_id).json()["attempt_no"] == 1
    save_project(sclient, project_id, sb3_bytes())
    second = submit(sclient, block_id).json()
    assert second["attempt_no"] == 2
    assert second["passed"] is True

    history = sclient.get(f"/api/scratch/lesson-blocks/{block_id}/submissions").json()
    assert history["completed"] is True
    assert [s["attempt_no"] for s in history["submissions"]] == [2, 1]
    assert [s["status"] for s in history["submissions"]] == ["passed", "failed"]
    assert [s["revision_no"] for s in history["submissions"]] == [2, 1]
    # 历史里同样不出规则参数
    assert "require_after_hat" not in json.dumps(history, ensure_ascii=False)


def test_submission_freezes_revision_and_rules(tmp_path: Path):
    """版本冻结：交完再改作品/再改规则，历史提交仍指向当时那一版、那套规则。"""
    app = scratch_env(tmp_path)
    built = build_scratch_lesson(app)
    sclient = student_login(app)
    block_id = built["block_ids"][0]
    project_id = open_block(sclient, block_id).json()["project"]["id"]
    save_project(sclient, project_id, sb3_bytes())
    submitted = submit(sclient, block_id).json()
    assert submitted["revision_no"] == 1

    # 交完继续改：项目往前走到 v2，提交仍然钉在 v1
    save_project(sclient, project_id,
                 sb3_bytes([stage_target(), scripted_sprite(steps="99")]))
    db = app.state.session_factory()
    try:
        project = db.get(ScratchProject, project_id)
        assert project.current_revision_no == 2
        submission = db.get(ScratchSubmission, submitted["submission_id"])
        frozen = db.get(ScratchProjectRevision, submission.project_revision_id)
        assert frozen.revision_no == 1
        assert submission.challenge_version == built["challenge"]["version"]
        assert json.loads(submission.rules_snapshot) == PASSING_RULES
        # 老师事后改规则：历史判定结论不被改写
        challenge = db.get(ScratchChallenge, built["challenge"]["id"])
        challenge.rules_json = json.dumps([{"type": "min_sprites", "count": 9}])
        db.commit()
        db.refresh(submission)
        assert json.loads(submission.rules_snapshot) == PASSING_RULES
        assert submission.passed is True
    finally:
        db.close()

    history = sclient.get(f"/api/scratch/lesson-blocks/{block_id}/submissions").json()
    assert history["submissions"][0]["revision_no"] == 1
    assert history["submissions"][0]["passed"] is True


# ---------- 管理端 ----------


def test_publish_blocks_draft_challenge(tmp_path: Path):
    """发布检查：绑了草稿挑战的课包上不了架（否则学生点进去必然 404）。"""
    app = scratch_env(tmp_path)
    client, headers = admin_login(app)
    challenge = create_challenge(client, headers, publish=False)
    built = build_scratch_lesson(app, challenge=challenge, publish_course=False, blocks=[
        {"block_type": "scratch", "title": "闯关",
         "detail": {"scratch": {"challenge_id": challenge["id"]}}},
    ])
    resp = built["client"].post(f"/api/admin/courses/{built['course_id']}/publish",
                                headers=built["headers"])
    assert resp.status_code == 422, resp.text
    codes = [p["code"] for p in resp.json()["problems"]]
    assert "scratch_challenge_not_published" in codes


def test_publish_rejects_missing_starter(tmp_path: Path):
    """初始项目是发布硬门槛，不能让学生误进空白工作台。"""
    app = scratch_env(tmp_path)
    client, headers = admin_login(app)
    challenge = create_challenge(client, headers, starter=False, publish=False)
    resp = client.post(f"/api/admin/scratch/challenges/{challenge['id']}/publish", headers=headers)
    assert resp.status_code == 400
    assert "初始项目" in resp.json()["detail"]


def test_analysis_video_is_optional_but_must_reference_a_real_video(tmp_path: Path):
    """解析视频不能让管理端写任意 id；不存在或尚未 ready 的素材一律拒绝绑定。"""
    app = scratch_env(tmp_path)
    client, headers = admin_login(app)
    resp = client.post("/api/admin/scratch/challenges", headers=headers, json={
        "title": "带解析的关卡", "instructions_md": "说明", "rules": PASSING_RULES,
        "analysis_video_id": 99999,
    })
    assert resp.status_code == 400
    assert "解析视频不存在" in resp.json()["detail"]


def test_analysis_video_requires_a_terminal_submission(tmp_path: Path):
    """即使题目配置了视频，未提交学生也不能借播放端点提前看到解法。"""
    app = scratch_env(tmp_path)
    built = build_scratch_lesson(app)
    sclient = student_login(app, "xiaoming")
    block_id = built["block_ids"][0]
    denied = sclient.post(f"/api/scratch/lesson-blocks/{block_id}/analysis-play", headers=scsrf(sclient))
    assert denied.status_code == 403
    assert "先提交作品" in denied.json()["detail"]


def test_published_challenge_duplicates_to_independent_draft(tmp_path: Path):
    """新版本复用安全的内容寻址项目，但不复制学生项目、提交或课程块。"""
    app = scratch_env(tmp_path)
    client, headers = admin_login(app)
    source = create_challenge(client, headers)
    copied = client.post(f"/api/admin/scratch/challenges/{source['id']}/duplicate", headers=headers)
    assert copied.status_code == 201, copied.text
    draft = copied.json()
    assert draft["id"] != source["id"]
    assert draft["status"] == "draft"
    assert draft["version"] == 1
    assert draft["has_starter"] is True
    assert draft["rules"] == source["rules"]
    assert draft["submission_count"] == 0
    blocked = client.put(f"/api/admin/scratch/challenges/{source['id']}", headers=headers, json={
        "title": "不应原地修改", "instructions_md": "x", "rules": [], "base_version": source["version"],
    })
    assert blocked.status_code == 409


def test_block_requires_existing_challenge(tmp_path: Path):
    """块必须绑一个存在的挑战；不给明细直接 400。"""
    app = scratch_env(tmp_path)
    client, headers = admin_login(app)
    cat = create_category(client, headers, name="分类X").json()
    course = create_course(client, headers, cat["id"], title="课包X").json()
    section = add_section(client, headers, course["id"]).json()
    lesson = client.post(f"/api/admin/sections/{section['id']}/lessons", headers=headers,
                         json={"title": "课时", "duration_minutes": 10}).json()
    no_detail = client.post(f"/api/admin/lessons/{lesson['id']}/blocks", headers=headers,
                            json={"block_type": "scratch", "title": "闯关"})
    assert no_detail.status_code == 400
    ghost = client.post(f"/api/admin/lessons/{lesson['id']}/blocks", headers=headers,
                        json={"block_type": "scratch", "title": "闯关",
                              "detail": {"scratch": {"challenge_id": 9999}}})
    assert ghost.status_code == 400


def test_admin_rejects_unknown_rule_type(tmp_path: Path):
    """规则类型写错在**写入时**就拒——留到判定时才发现，全班会静静地挂起等人工。"""
    app = scratch_env(tmp_path)
    client, headers = admin_login(app)
    resp = client.post("/api/admin/scratch/challenges", headers=headers, json={
        "title": "打错字的关卡", "instructions_md": "x",
        "rules": [{"type": "require_opcodes", "opcode": "motion_movesteps"}],
    })
    assert resp.status_code == 400 and "类型无效" in resp.json()["detail"]


def test_published_challenge_is_read_only(tmp_path: Path):
    """已发布挑战不能直接改；被在售课包引用时也不能撤回。"""
    app = scratch_env(tmp_path)
    built = build_scratch_lesson(app)
    client, headers = built["client"], built["headers"]
    cid = built["challenge"]["id"]
    edit = client.put(f"/api/admin/scratch/challenges/{cid}", headers=headers,
                      json={"title": "改个名", "instructions_md": "x", "rules": []})
    assert edit.status_code == 409
    back = client.post(f"/api/admin/scratch/challenges/{cid}/unpublish", headers=headers)
    assert back.status_code == 409

    # 课包下架后可以撤回，版本号 +1（下一次发布出去的是新的一版）
    assert client.post(f"/api/admin/courses/{built['course_id']}/off-shelf",
                       headers=headers).status_code == 200
    back = client.post(f"/api/admin/scratch/challenges/{cid}/unpublish", headers=headers)
    assert back.status_code == 200
    assert back.json()["status"] == "draft"
    assert back.json()["version"] == built["challenge"]["version"] + 1


def test_admin_submission_list_and_snapshot(tmp_path: Path):
    """教师侧只读列表：学生、挑战、状态、提交次数、快照摘要 + 下载**冻结那一版**。"""
    app = scratch_env(tmp_path)
    built = build_scratch_lesson(app)
    sclient = student_login(app, "xiaoming")
    block_id = built["block_ids"][0]
    project_id = open_block(sclient, block_id).json()["project"]["id"]
    save_project(sclient, project_id,
                 sb3_bytes([stage_target(), scripted_sprite(steps="5")]))
    submitted = submit(sclient, block_id).json()
    # 交完继续改：老师看到的必须还是提交时那一版
    save_project(sclient, project_id, sb3_bytes())

    client = built["client"]  # 只读列表不需要 CSRF 头
    listing = client.get(
        f"/api/admin/scratch/submissions?challenge_id={built['challenge']['id']}&page_size=10"
    )
    assert listing.status_code == 200, listing.text
    data = listing.json()
    assert data["total"] == 1
    row = data["items"][0]
    assert row["student_name"] == "xiaoming"
    assert row["challenge_title"] == "绿旗动一动"
    assert row["status"] == "failed"
    assert row["attempt_count"] == 1
    assert row["snapshot"]["revision_no"] == 1
    assert row["snapshot"]["content_hash"].startswith("sha256:")
    # 有绿旗、说了「你好」，只有步数不对 → 三条里差第二条
    assert row["evaluation"] == {"rules_total": 3, "rules_passed": 2,
                                 "missing": ["移动 10 步"], "unsupported": []}

    detail = client.get(f"/api/admin/scratch/submissions/{submitted['submission_id']}").json()
    assert detail["rules_snapshot"] == PASSING_RULES
    assert [r["passed"] for r in detail["rules"]] == [True, False, True]

    snapshot = client.get(
        f"/api/admin/scratch/submissions/{submitted['submission_id']}/project.sb3")
    assert snapshot.status_code == 200
    project = json.loads(zipfile.ZipFile(BytesIO(snapshot.content)).read("project.json"))
    assert project["targets"][1]["blocks"]["b_move"]["inputs"]["STEPS"][1][1] == "5"

    # 按状态筛选
    assert client.get("/api/admin/scratch/submissions?status=passed").json()["total"] == 0
    assert client.get("/api/admin/scratch/submissions?status=failed").json()["total"] == 1


def test_manual_review_closes_needs_review_loop(tmp_path: Path):
    """人工点评通过 → 走既有完成流程写完成记录，学生那边课时进度随之推进。"""
    app = scratch_env(tmp_path)
    client, headers = admin_login(app)
    challenge = create_challenge(client, headers, rules=[
        {"type": "sprite_end_position", "sprite": "小猫", "x": 100, "y": 0,
         "label": "跑完停在舞台右边"},
    ])
    built = build_scratch_lesson(app, challenge=challenge)
    sclient = student_login(app)
    block_id, next_id = built["block_ids"]
    project_id = open_block(sclient, block_id).json()["project"]["id"]
    save_project(sclient, project_id, sb3_bytes())
    submitted = submit(sclient, block_id).json()
    assert submitted["submission_status"] == "needs_review"
    assert submitted["completed"] is False

    review = built["client"].post(
        f"/api/admin/scratch/submissions/{submitted['submission_id']}/review",
        headers=built["headers"], json={"verdict": "passed", "comment": "思路对了，通过。"},
    )
    assert review.status_code == 200, review.text
    assert review.json()["completed"] is True
    assert review.json()["submission"]["status"] == "passed"
    assert review.json()["submission"]["reviewed"] is True

    # 学生侧：块已完成、后继块解锁、历史里能看到老师的评语
    detail = sclient.get(f"/api/lessons/{built['lesson_id']}").json()
    assert detail["blocks"][0]["completed"] is True
    assert [b["lock_reason"] for b in detail["blocks"]] == [None, None]
    assert detail["blocks"][1]["id"] == next_id
    history = sclient.get(f"/api/scratch/lesson-blocks/{block_id}/submissions").json()
    assert history["submissions"][0]["review_comment"] == "思路对了，通过。"


def test_manual_review_failed_does_not_revoke_progress(tmp_path: Path):
    """点评为未通过：写终态与评语，但**不撤销**已有完成记录（完成事实只增不减）。"""
    app = scratch_env(tmp_path)
    built = build_scratch_lesson(app)
    sclient = student_login(app)
    block_id = built["block_ids"][0]
    project_id = open_block(sclient, block_id).json()["project"]["id"]
    save_project(sclient, project_id, sb3_bytes())
    submitted = submit(sclient, block_id).json()
    assert submitted["passed"] is True  # 自动判定已通过并写了完成记录

    review = built["client"].post(
        f"/api/admin/scratch/submissions/{submitted['submission_id']}/review",
        headers=built["headers"], json={"verdict": "failed", "comment": "重做一次。"},
    )
    assert review.status_code == 200
    assert review.json()["submission"]["status"] == "failed"
    db = app.state.session_factory()
    try:
        assert db.scalar(select(LessonBlockCompletion).where(
            LessonBlockCompletion.block_id == block_id)) is not None
    finally:
        db.close()


def test_admin_client_contract_aliases(tmp_path: Path):
    """21c 管理端已按另一套命名写好：这些别名/别名字段必须都能用。"""
    app = scratch_env(tmp_path)
    client, headers = admin_login(app)
    # rules_json 作为键名 + base_version 乐观锁
    created = client.post("/api/admin/scratch/challenges", headers=headers, json={
        "title": "别名关卡", "instructions_md": "说明",
        "rules_json": [{"type": "min_sprites", "count": 1}],
    })
    assert created.status_code == 201, created.text
    cid = created.json()["id"]
    assert created.json()["rules"] == [{"type": "min_sprites", "count": 1}]

    stale = client.put(f"/api/admin/scratch/challenges/{cid}", headers=headers, json={
        "title": "改名", "instructions_md": "说明", "rules_json": [], "base_version": 99,
    })
    assert stale.status_code == 409

    ok = client.put(f"/api/admin/scratch/challenges/{cid}", headers=headers, json={
        "title": "改名", "instructions_md": "说明",
        "rules_json": [{"type": "min_sprites", "count": 1}], "base_version": 1,
    })
    assert ok.status_code == 200 and ok.json()["title"] == "改名"

    # starter-project / demo-project 别名
    for path in ("starter-project", "demo-project"):
        up = client.post(f"/api/admin/scratch/challenges/{cid}/{path}", headers=headers,
                         files={"file": ("p.sb3", sb3_bytes([stage_target()]), "application/zip")})
        assert up.status_code == 200, up.text
    assert client.get(f"/api/admin/scratch/challenges/{cid}").json()["has_starter"] is True

    # options 下拉（必须能按名字取到，不被 {challenge_id} 抢走路由）
    options = client.get("/api/admin/scratch/challenges/options")
    assert options.status_code == 200
    assert [o["id"] for o in options.json()["items"]] == [cid]

    # withdraw = unpublish
    assert client.post(f"/api/admin/scratch/challenges/{cid}/publish",
                       headers=headers).status_code == 200
    back = client.post(f"/api/admin/scratch/challenges/{cid}/withdraw", headers=headers)
    assert back.status_code == 200 and back.json()["status"] == "draft"


def test_block_with_submissions_cannot_be_deleted(tmp_path: Path):
    """已有学生提交的 scratch 块不能删（删了会静默带走学生的判定记录）。"""
    app = scratch_env(tmp_path)
    built = build_scratch_lesson(app)
    sclient = student_login(app)
    block_id = built["block_ids"][0]
    project_id = open_block(sclient, block_id).json()["project"]["id"]
    save_project(sclient, project_id, sb3_bytes())
    assert submit(sclient, block_id).json()["passed"] is True

    client, headers = built["client"], built["headers"]
    assert client.post(f"/api/admin/courses/{built['course_id']}/off-shelf",
                       headers=headers).status_code == 200
    resp = client.delete(f"/api/admin/lesson-blocks/{block_id}", headers=headers)
    assert resp.status_code == 409
    db = app.state.session_factory()
    try:
        assert db.get(CourseLessonBlock, block_id) is not None
        assert len(db.scalars(select(ScratchSubmission)).all()) == 1
    finally:
        db.close()


def test_challenge_project_round_trip(tmp_path: Path):
    """初始项目要能取回来再改回去——Studio 里编初始项目全靠这个闭环。

    在这三条 GET 之前，`.sb3` 只进不出：教研想在上一版基础上改只能指望本地底稿。
    """
    app = scratch_env(tmp_path)
    client, headers = admin_login(app)
    challenge = create_challenge(client, headers, starter=False, publish=False)
    cid = challenge["id"]

    # 还没传：两条下载都 404，且 _serialize 不给 URL（前端据此灰按钮）
    assert client.get(f"/api/admin/scratch/challenges/{cid}/starter.sb3").status_code == 404
    assert client.get(f"/api/admin/scratch/challenges/{cid}/demo.sb3").status_code == 404
    card = client.get(f"/api/admin/scratch/challenges/{cid}").json()
    assert card["starter_url"] is None and card["demo_url"] is None

    first = sb3_bytes([stage_target()])
    assert client.post(f"/api/admin/scratch/challenges/{cid}/starter", headers=headers,
                       files={"file": ("s.sb3", first, "application/zip")}).status_code == 200
    card = client.get(f"/api/admin/scratch/challenges/{cid}").json()
    assert card["starter_url"] == f"/api/admin/scratch/challenges/{cid}/starter.sb3"

    got = client.get(card["starter_url"])
    assert got.status_code == 200
    # 内容寻址存的是原字节，取回来必须一模一样（Studio 装载的就是这份）
    assert got.content == first
    assert zipfile.ZipFile(BytesIO(got.content)).read("project.json")

    # 改一版写回：sha256 变、下载跟着变，这就是"Studio 里另存为初始项目"的服务端半边
    second = sb3_bytes([stage_target(), scripted_sprite()])
    assert client.post(f"/api/admin/scratch/challenges/{cid}/starter-project", headers=headers,
                       files={"file": ("s.sb3", second, "application/zip")}).status_code == 200
    reread = client.get(f"/api/admin/scratch/challenges/{cid}").json()
    assert reread["starter_sha256"] != card["starter_sha256"]
    assert client.get(f"/api/admin/scratch/challenges/{cid}/starter.sb3").content == second

    # 示范项目同理，但走自己的路径（它是答案，不能从 starter 那条漏出去）
    demo = sb3_bytes([stage_target()], extra={"note.txt": b"answer"})
    assert client.post(f"/api/admin/scratch/challenges/{cid}/demo-project", headers=headers,
                       files={"file": ("d.sb3", demo, "application/zip")}).status_code == 200
    assert client.get(f"/api/admin/scratch/challenges/{cid}/demo.sb3").content == demo

    assert client.get("/api/admin/scratch/challenges/9999/starter.sb3").status_code == 404


def test_studio_context_serves_unbound_draft_and_locks_after_publish(tmp_path: Path):
    """教研预览的正是草稿，而草稿通常还没绑课时块——学生端那条路从设计上就走不通。"""
    app = scratch_env(tmp_path)
    client, headers = admin_login(app)
    challenge = create_challenge(client, headers, publish=False)
    cid = challenge["id"]

    resp = client.get(f"/api/admin/scratch/challenges/{cid}/studio-context")
    assert resp.status_code == 200, resp.text
    ctx = resp.json()
    assert ctx["mode"] == "admin_preview" and ctx["readonly"] is True
    # 键在值为空：Studio 照学生端 payload 写的渲染分支不该撞 undefined
    assert ctx["block"] is None and ctx["project"] is None and ctx["last_submission"] is None
    assert ctx["challenge"]["status"] == "draft"
    assert ctx["challenge"]["starter_url"] == f"/api/admin/scratch/challenges/{cid}/starter.sb3"
    # 规则参数不下发，只给中文清单（与学生端同一份）
    assert ctx["challenge"]["checklist"] and "rules" not in ctx["challenge"]
    assert ctx["limits"]["max_bytes"] > 0

    authoring = ctx["authoring"]
    assert authoring["can_write_starter"] is True
    assert authoring["starter_write_url"].endswith(f"/challenges/{cid}/starter-project")
    assert authoring["locked_reason"] is None

    # 发布后写回入口必须消失：把"已发布不能直接改"留在服务端，Studio 不复述状态机
    assert client.post(f"/api/admin/scratch/challenges/{cid}/publish",
                       headers=headers).status_code == 200
    locked = client.get(f"/api/admin/scratch/challenges/{cid}/studio-context").json()
    assert locked["challenge"]["status"] == "published"
    assert locked["authoring"]["can_write_starter"] is False
    assert locked["authoring"]["starter_write_url"] is None
    assert locked["authoring"]["demo_write_url"] is None
    assert "撤回" in locked["authoring"]["locked_reason"]
    # 上传端点自己也要拦住，不能只靠前端看 URL 有没有
    assert client.post(f"/api/admin/scratch/challenges/{cid}/starter-project", headers=headers,
                       files={"file": ("s.sb3", sb3_bytes(), "application/zip")}).status_code == 409

    # 下载仍开放（已发布的关卡教研也要能取回来做新版本），但未登录一律挡住
    assert client.get(f"/api/admin/scratch/challenges/{cid}/starter.sb3").status_code == 200
    from fastapi.testclient import TestClient
    guest = TestClient(app)
    assert guest.get(f"/api/admin/scratch/challenges/{cid}/starter.sb3").status_code == 401
    assert guest.get(f"/api/admin/scratch/challenges/{cid}/demo.sb3").status_code == 401
    assert guest.get(f"/api/admin/scratch/challenges/{cid}/studio-context").status_code == 401


# ---------- 示范项目（21g）----------
#
# 与解析视频同一道闸：课时门控之外，还要"最近一次提交已出结果"。区别只在于示范
# 项目是**文件**——它一旦下发就无法收回（学生本地解包就能看到全部答案），所以这
# 一组用例的重点全在"什么时候一个字节都不发"。


def test_demo_requires_a_terminal_submission(tmp_path: Path):
    """未提交 / 只保存 / 判定中都不给，出了结果（含未通过）才给。

    「只保存不算交」是这里最容易写错的一条：学生存了作品、拿到了 project 版本号，
    看起来"做过了"，但他一次都没被判过，此时放行等于直接送答案。
    """
    app = scratch_env(tmp_path)
    client, headers = admin_login(app)
    challenge = create_challenge(client, headers, demo=True)
    built = build_scratch_lesson(app, challenge=challenge)
    block_id = built["block_ids"][0]
    sclient = student_login(app, "xiaoming")

    # 从没交过
    denied = fetch_demo(sclient, block_id)
    assert denied.status_code == 403
    assert "先提交作品" in denied.json()["detail"]
    detail = open_block(sclient, block_id).json()
    assert detail["demo"] == {
        "has_demo": True, "available": False, "url": None,
        "notice": "提交作品并得到结果后可查看教师示范项目。",
    }

    # 只保存不算交：有版本号了，但一次都没被判过
    project_id = detail["project"]["id"]
    assert save_project(sclient, project_id, sb3_bytes()).status_code == 200
    assert fetch_demo(sclient, block_id).status_code == 403
    assert open_block(sclient, block_id).json()["demo"]["available"] is False

    # 交完拿到结果 → 开放。**未通过也算**：讲评要给的正是没做对的人。
    failed = work_and_submit(sclient, block_id,
                             sb3_bytes([stage_target(), scripted_sprite(steps="5")]))
    assert failed.json()["submission_status"] == "failed"
    demo = fetch_demo(sclient, block_id)
    assert demo.status_code == 200
    assert demo.content == DEMO_SB3
    assert demo.headers["cache-control"] == "private, no-store"
    assert demo.headers["content-type"].startswith("application/x.scratch.sb3")
    # 文件名用 block_id 而不是 challenge_id：这个名字会落到学生磁盘上
    assert f"demo-block-{block_id}.sb3" in demo.headers["content-disposition"]
    assert zipfile.ZipFile(BytesIO(demo.content)).read("project.json")

    opened = open_block(sclient, block_id).json()["demo"]
    assert opened["available"] is True
    assert opened["url"] == f"/api/scratch/lesson-blocks/{block_id}/demo.sb3"
    assert opened["notice"] is None


def test_demo_stays_open_after_passing(tmp_path: Path):
    """通过之后仍能看——示范项目是复盘材料，不是"没做出来才给"的补偿。"""
    app = scratch_env(tmp_path)
    client, headers = admin_login(app)
    challenge = create_challenge(client, headers, demo=True)
    built = build_scratch_lesson(app, challenge=challenge)
    block_id = built["block_ids"][0]
    sclient = student_login(app, "xiaohong")

    assert work_and_submit(sclient, block_id).json()["submission_status"] == "passed"
    assert fetch_demo(sclient, block_id).status_code == 200


def test_demo_opens_for_manual_review_too(tmp_path: Path):
    """`needs_review` 也是终态：等人工点评的这几天不该把学生挡在门外。"""
    app = scratch_env(tmp_path)
    client, headers = admin_login(app)
    challenge = create_challenge(
        client, headers, demo=True,
        rules=[{"type": "sprite_end_position", "params": {"x": 10, "y": 0}}])
    built = build_scratch_lesson(app, challenge=challenge)
    block_id = built["block_ids"][0]
    sclient = student_login(app, "xiaogang")

    assert work_and_submit(sclient, block_id).json()["submission_status"] == "needs_review"
    assert fetch_demo(sclient, block_id).status_code == 200


def test_demo_reruns_the_whole_lesson_gate(tmp_path: Path):
    """存储 key 不是权限凭证：未登录 / 未选课 / 未解锁 / 挑战下架逐一挡住。

    这些码全部来自 `_gated()`，本端点自己一条门控都不写——门控只有一份实现，
    复刻一份就意味着以后改课时规则时会漏掉这里。
    """
    app = scratch_env(tmp_path)
    client, headers = admin_login(app)

    # 未登录
    challenge = create_challenge(client, headers, demo=True)
    built = build_scratch_lesson(app, challenge=challenge)
    from fastapi.testclient import TestClient
    assert TestClient(app).get(
        f"/api/scratch/lesson-blocks/{built['block_ids'][0]}/demo.sb3").status_code == 401

    # 未选课
    closed_challenge = create_challenge(client, headers, demo=True, title="未选课的关")
    closed = build_scratch_lesson(app, challenge=closed_challenge, open_policy="closed")
    sclient = student_login(app, "keqing")
    denied = fetch_demo(sclient, closed["block_ids"][0])
    assert denied.status_code == 403
    assert "尚未对你开放" in denied.json()["detail"]

    # 顺序未解锁
    seq_challenge = create_challenge(client, headers, demo=True, title="顺序锁的关")
    seq = build_scratch_lesson(app, challenge=seq_challenge, blocks=[
        {"block_type": "markdown", "title": "先看这个",
         "detail": {"markdown": {"content_md": "# 前置"}}},
        {"block_type": "scratch", "title": "闯关", "unlock_rule": "sequential",
         "detail": {"scratch": {"challenge_id": seq_challenge["id"]}}},
    ])
    locked = fetch_demo(sclient, seq["block_ids"][1])
    assert locked.status_code == 403
    assert "前面" in locked.json()["detail"]

    # 挑战被改回草稿（课包在售期间被归档的脏状态）→ 404，即使这名学生已经交过
    student = student_login(app, "yifan")
    assert work_and_submit(student, built["block_ids"][0]).status_code == 200
    assert fetch_demo(student, built["block_ids"][0]).status_code == 200
    db = app.state.session_factory()
    try:
        db.get(ScratchChallenge, challenge["id"]).status = "draft"
        db.commit()
    finally:
        db.close()
    assert fetch_demo(student, built["block_ids"][0]).status_code == 404


def test_demo_cannot_be_reached_by_swapping_block_id(tmp_path: Path):
    """换一个自己没权限的 block_id 读不到别人的示范项目。

    这条是本功能唯一真正的越权面：`block_id` 是 URL 上唯一的输入，而它同时决定
    「查哪个挑战」和「查谁的提交」。两件事必须来自同一个已鉴权的块。
    """
    app = scratch_env(tmp_path)
    client, headers = admin_login(app)
    mine = create_challenge(client, headers, demo=True, title="我的关")
    theirs = create_challenge(client, headers, demo=True, title="别人的关")
    my_lesson = build_scratch_lesson(app, challenge=mine)
    their_lesson = build_scratch_lesson(app, challenge=theirs, open_policy="closed")

    sclient = student_login(app, "chuanyue")
    # 在自己的关里交到终态，拿到一次合法的开放资格
    assert work_and_submit(sclient, my_lesson["block_ids"][0]).status_code == 200
    assert fetch_demo(sclient, my_lesson["block_ids"][0]).status_code == 200

    # 换成没选课的那一关：开放资格不跟着人走，跟着「块」走
    stolen = fetch_demo(sclient, their_lesson["block_ids"][0])
    assert stolen.status_code == 403
    assert not stolen.content.startswith(b"PK")

    # 不存在的块、以及同课时里的 markdown 块，都不是 500
    assert fetch_demo(sclient, 999999).status_code == 404
    assert fetch_demo(sclient, my_lesson["block_ids"][1]).status_code == 404


def test_demo_absent_is_404_without_leaking_storage_key(tmp_path: Path):
    """没配示范项目 / 文件在存储里丢了：都 404，且错误文案不带对象存储 key。"""
    app = scratch_env(tmp_path)
    built = build_scratch_lesson(app)  # 默认不带示范项目
    block_id = built["block_ids"][0]
    sclient = student_login(app, "wuxi")
    assert work_and_submit(sclient, block_id).status_code == 200

    missing = fetch_demo(sclient, block_id)
    assert missing.status_code == 404
    assert missing.json()["detail"] == "该题暂未提供示范项目。"
    assert open_block(sclient, block_id).json()["demo"] == {
        "has_demo": False, "available": False, "url": None, "notice": None,
    }

    # 库里有 key、存储里没文件（迁移/清理事故）→ 仍是 404，不是 500，也不回显 key
    db = app.state.session_factory()
    try:
        challenge = db.get(ScratchChallenge, built["challenge"]["id"])
        challenge.demo_sb3_key = "sb3/de/adbeef-not-on-disk.sb3"
        db.commit()
    finally:
        db.close()
    broken = fetch_demo(sclient, block_id)
    assert broken.status_code == 404
    assert "adbeef" not in broken.text and "sb3/" not in broken.text


def test_detail_and_lesson_card_never_leak_the_demo_address(tmp_path: Path):
    """两个 JSON 接口都不该出现 `demo_sb3_key`；未开放时连 URL 都不给。

    整段序列化后做子串断言，而不是逐个字段查：将来有人往 payload 里加字段时，
    这条断言会替他挡住"顺手把 key 也发出去了"。
    """
    app = scratch_env(tmp_path)
    client, headers = admin_login(app)
    challenge = create_challenge(client, headers, demo=True)
    built = build_scratch_lesson(app, challenge=challenge)
    block_id = built["block_ids"][0]
    sclient = student_login(app, "milu")

    before = open_block(sclient, block_id)
    assert "demo_sb3_key" not in before.text
    assert "demo.sb3" not in before.text  # 未提交时连地址都不该出现

    card = sclient.get(f"/api/lessons/{built['lesson_id']}").json()["blocks"][0]["scratch"]
    assert card["has_demo"] is True
    assert card["demo_available"] is False
    # 课时详情一次性下发整节课所有块：这里漏一个字段就是几十个块一起漏
    assert "demo_url" not in card and "demo_sb3_key" not in card

    assert work_and_submit(sclient, block_id).status_code == 200
    after = open_block(sclient, block_id)
    assert "demo_sb3_key" not in after.text
    card = sclient.get(f"/api/lessons/{built['lesson_id']}").json()["blocks"][0]["scratch"]
    assert card["demo_available"] is True
    assert "demo_url" not in card


def test_lesson_card_demo_flag_flips_with_the_detail_endpoint(tmp_path: Path):
    """入口卡片的 demo_available 与详情接口必须同时翻转。

    一处算得早一处算得晚，就会出现"课时页按钮亮着、点进去 403"——只有学生本人
    能复现的那类 bug。
    """
    app = scratch_env(tmp_path)
    client, headers = admin_login(app)
    challenge = create_challenge(client, headers, demo=True)
    built = build_scratch_lesson(app, challenge=challenge)
    block_id = built["block_ids"][0]
    sclient = student_login(app, "tongbu")

    def card():
        return sclient.get(
            f"/api/lessons/{built['lesson_id']}").json()["blocks"][0]["scratch"]

    def detail():
        return open_block(sclient, block_id).json()["demo"]["available"]

    assert card()["demo_available"] is detail() is False
    save_project(sclient, open_block(sclient, block_id).json()["project"]["id"], sb3_bytes())
    assert card()["demo_available"] is detail() is False
    assert submit(sclient, block_id).status_code == 200
    assert card()["demo_available"] is detail() is True


def test_studio_context_exposes_a_separate_demo_write_entry(tmp_path: Path):
    """录制示范项目走自己的写回地址与自己的布尔值，不共用 starter 那一套。

    共用的话，"哪天两者规则分叉"就会变成一次静默的判错——比如将来允许已发布挑战
    补录示范项目，starter 的 false 会把它一起摁死。
    """
    app = scratch_env(tmp_path)
    client, headers = admin_login(app)
    challenge = create_challenge(client, headers, publish=False)
    cid = challenge["id"]

    authoring = client.get(
        f"/api/admin/scratch/challenges/{cid}/studio-context").json()["authoring"]
    assert authoring["can_write_starter"] is True
    assert authoring["can_write_demo"] is True
    assert authoring["demo_write_url"].endswith(f"/challenges/{cid}/demo-project")
    assert authoring["starter_write_url"] != authoring["demo_write_url"]
    # 还没录：地址为 null，Studio 的「重新载入」据此灰按钮
    assert authoring["has_demo"] is False and authoring["demo_url"] is None

    # 录一版：只有示范项目那一侧变化，初始项目原封不动
    before = client.get(f"/api/admin/scratch/challenges/{cid}").json()
    saved = client.post(f"/api/admin/scratch/challenges/{cid}/demo-project", headers=headers,
                        files={"file": ("demo.sb3", DEMO_SB3, "application/zip")})
    assert saved.status_code == 200, saved.text
    assert saved.json()["has_demo"] is True
    assert saved.json()["starter_sha256"] == before["starter_sha256"]

    authoring = client.get(
        f"/api/admin/scratch/challenges/{cid}/studio-context").json()["authoring"]
    assert authoring["has_demo"] is True
    assert authoring["demo_url"] == f"/api/admin/scratch/challenges/{cid}/demo.sb3"
    assert client.get(authoring["demo_url"]).content == DEMO_SB3

    # 发布后两条写回入口一起消失，上传端点自己也拦（不能只靠前端看 URL 有没有）
    assert client.post(f"/api/admin/scratch/challenges/{cid}/publish",
                       headers=headers).status_code == 200
    locked = client.get(
        f"/api/admin/scratch/challenges/{cid}/studio-context").json()["authoring"]
    assert locked["can_write_demo"] is False and locked["demo_write_url"] is None
    assert client.post(f"/api/admin/scratch/challenges/{cid}/demo-project", headers=headers,
                       files={"file": ("d.sb3", DEMO_SB3, "application/zip")}).status_code == 409
    # 下载仍开放：已发布的关卡教研也要能取回来做新版本
    assert client.get(f"/api/admin/scratch/challenges/{cid}/demo.sb3").status_code == 200


def test_demo_upload_is_validated_like_any_other_sb3(tmp_path: Path):
    """示范项目是老师传的，但结构校验一条都不能少——坏文件学生同样打不开。"""
    app = scratch_env(tmp_path)
    client, headers = admin_login(app)
    challenge = create_challenge(client, headers, publish=False)
    cid = challenge["id"]
    for name, blob in [("坏 ZIP", b"not a zip at all"),
                       ("缺 project.json", sb3_bytes(project_json=False))]:
        resp = client.post(f"/api/admin/scratch/challenges/{cid}/demo-project", headers=headers,
                           files={"file": ("d.sb3", blob, "application/zip")})
        assert resp.status_code == 400, f"{name} 应被拒: {resp.text}"
    assert client.get(f"/api/admin/scratch/challenges/{cid}").json()["has_demo"] is False


# ---------- 教师人工批改：量规 + 退回重做（文档 23） ----------

RUBRIC = {
    "max_score": 100,
    "criteria": [
        {"id": "c_logic", "label": "程序逻辑", "desc": "", "levels": [
            {"value": 3, "label": "完全达成", "points": 40, "desc": ""},
            {"value": 2, "label": "基本达成", "points": 25, "desc": ""},
            {"value": 1, "label": "部分达成", "points": 10, "desc": ""},
            {"value": 0, "label": "未达成", "points": 0, "desc": ""}]},
        {"id": "c_structure", "label": "代码结构", "desc": "", "levels": [
            {"value": 2, "label": "清晰", "points": 30, "desc": ""},
            {"value": 1, "label": "一般", "points": 15, "desc": ""},
            {"value": 0, "label": "混乱", "points": 0, "desc": ""}]},
        {"id": "c_creative", "label": "创意表达", "desc": "", "levels": [
            {"value": 2, "label": "有亮点", "points": 30, "desc": ""},
            {"value": 1, "label": "按部就班", "points": 15, "desc": ""},
            {"value": 0, "label": "未体现", "points": 0, "desc": ""}]},
    ],
}

RUBRIC_FULL = [
    {"criterion_id": "c_logic", "level": 3, "note": "移动和说话都做到了"},
    {"criterion_id": "c_structure", "level": 2, "note": ""},
    {"criterion_id": "c_creative", "level": 1, "note": ""},
]


def test_rubric_validation(tmp_path: Path):
    """量规写入校验：满分=各准则最高档之和；id 唯一且合法；至少两个档位。"""
    app = scratch_env(tmp_path)
    client, headers = admin_login(app)
    base = {"title": "带量规的关卡", "instructions_md": "# 任务", "rules": PASSING_RULES}

    ok = client.post("/api/admin/scratch/challenges", headers=headers,
                     json={**base, "rubric": RUBRIC})
    assert ok.status_code == 201, ok.text
    assert ok.json()["rubric"]["max_score"] == 100
    assert len(ok.json()["rubric"]["criteria"]) == 3

    bad_max = json.loads(json.dumps(RUBRIC)); bad_max["max_score"] = 99
    assert client.post("/api/admin/scratch/challenges", headers=headers,
                       json={**base, "rubric": bad_max}).status_code == 400

    dup = {"max_score": 30, "criteria": [
        {"id": "c_x", "label": "a", "levels": [
            {"value": 1, "label": "高", "points": 30}, {"value": 0, "label": "低", "points": 0}]},
        {"id": "c_x", "label": "b", "levels": [
            {"value": 1, "label": "高", "points": 0}, {"value": 0, "label": "低", "points": 0}]}]}
    assert client.post("/api/admin/scratch/challenges", headers=headers,
                       json={**base, "rubric": dup}).status_code == 400

    single = {"max_score": 10, "criteria": [
        {"id": "c_x", "label": "a", "levels": [{"value": 1, "label": "高", "points": 10}]}]}
    assert client.post("/api/admin/scratch/challenges", headers=headers,
                       json={**base, "rubric": single}).status_code == 400

    bad_id = {"max_score": 10, "criteria": [
        {"id": "BAD ID!", "label": "a", "levels": [
            {"value": 1, "label": "高", "points": 10}, {"value": 0, "label": "低", "points": 0}]}]}
    assert client.post("/api/admin/scratch/challenges", headers=headers,
                       json={**base, "rubric": bad_id}).status_code == 400


def test_rubric_bumps_edit_seq_on_update(tmp_path: Path):
    """草稿挑战改量规是实质性修改：edit_seq +1（乐观锁要感知），version 不动
    （发布版次只在撤回再发时 +1，草稿编辑不该污染它）。"""
    app = scratch_env(tmp_path)
    client, headers = admin_login(app)
    challenge = create_challenge(client, headers, publish=False)
    cid = challenge["id"]
    before_seq, before_version = challenge["edit_seq"], challenge["version"]
    updated = client.put(f"/api/admin/scratch/challenges/{cid}", headers=headers, json={
        "title": challenge["title"], "instructions_md": challenge["instructions_md"],
        "rules": PASSING_RULES, "rubric": RUBRIC})
    assert updated.status_code == 200, updated.text
    assert updated.json()["edit_seq"] == before_seq + 1
    assert updated.json()["version"] == before_version
    assert updated.json()["rubric"]["max_score"] == 100


def test_edit_seq_lock_and_publish_version_split(tmp_path: Path):
    """version / edit_seq 拆分后的完整生命周期：

    - 草稿反复保存：edit_seq 递增，version 恒为 1（第 1 版还没发出去过）；
    - base_version 乐观锁比对 edit_seq：拿旧 edit_seq 保存 → 409；
    - 首次发布 version 仍是 1，学生提交冻结 challenge_version=1；
    - 撤回再发 version → 2，edit_seq 继续在草稿编辑时递增。
    """
    app = scratch_env(tmp_path)
    client, headers = admin_login(app)
    challenge = create_challenge(client, headers, publish=False)
    cid = challenge["id"]

    first = client.put(f"/api/admin/scratch/challenges/{cid}", headers=headers, json={
        "title": "第一稿", "instructions_md": "说明", "rules": PASSING_RULES,
        "base_version": challenge["edit_seq"]})
    assert first.status_code == 200, first.text
    assert first.json()["edit_seq"] == challenge["edit_seq"] + 1
    assert first.json()["version"] == 1

    # 拿旧 edit_seq 再保存 → 冲突
    stale = client.put(f"/api/admin/scratch/challenges/{cid}", headers=headers, json={
        "title": "覆盖", "instructions_md": "说明", "rules": PASSING_RULES,
        "base_version": challenge["edit_seq"]})
    assert stale.status_code == 409

    # 再改几稿，version 仍然是 1
    for i in range(2):
        seq = client.get(f"/api/admin/scratch/challenges/{cid}").json()["edit_seq"]
        ok = client.put(f"/api/admin/scratch/challenges/{cid}", headers=headers, json={
            "title": f"第{i + 2}稿", "instructions_md": "说明", "rules": PASSING_RULES,
            "base_version": seq})
        assert ok.status_code == 200
        assert ok.json()["version"] == 1

    # 改够草稿后发布，再进入课程链路
    pub = client.post(f"/api/admin/scratch/challenges/{cid}/publish", headers=headers)
    assert pub.status_code == 200, pub.text
    built = build_scratch_lesson(app, challenge=client.get(
        f"/api/admin/scratch/challenges/{cid}").json())
    assert built["challenge"]["version"] == 1  # 首次发布

    sclient = student_login(app, "seq_student")
    block_id = built["block_ids"][0]
    project_id = open_block(sclient, block_id).json()["project"]["id"]
    save_project(sclient, project_id, sb3_bytes())
    submitted = submit(sclient, block_id).json()
    detail = client.get(f"/api/admin/scratch/submissions/{submitted['submission_id']}").json()
    assert detail["challenge_version"] == 1  # 冻结的是发布版次

    # 撤回 → 再发：version 2，编辑草稿继续走 edit_seq
    # （先下架课包：被已发布课包引用的挑战不许撤回）
    assert client.post(f"/api/admin/courses/{built['course_id']}/off-shelf",
                       headers=headers).status_code == 200
    assert client.post(f"/api/admin/scratch/challenges/{cid}/unpublish",
                       headers=headers).status_code == 200
    republished = client.post(f"/api/admin/scratch/challenges/{cid}/publish", headers=headers)
    assert republished.status_code == 200
    assert republished.json()["challenge"]["version"] == 2


def test_review_rubric_full_coverage_and_points(tmp_path: Path):
    """有量规：/review 缺项 400、漏准则 400；客户端 points 被丢弃，分由后端查表。"""
    app = scratch_env(tmp_path)
    client, headers = admin_login(app)
    challenge = create_challenge(client, headers, rubric=RUBRIC)
    built = build_scratch_lesson(app, challenge=challenge)
    sclient = student_login(app)
    block_id = built["block_ids"][0]
    project_id = open_block(sclient, block_id).json()["project"]["id"]
    save_project(sclient, project_id, sb3_bytes())
    sid = submit(sclient, block_id).json()["submission_id"]

    # 有量规却缺 rubric → 400
    assert built["client"].post(
        f"/api/admin/scratch/submissions/{sid}/review", headers=built["headers"],
        json={"verdict": "passed", "comment": ""}).status_code == 400
    # 只交一项准则 → 400
    assert built["client"].post(
        f"/api/admin/scratch/submissions/{sid}/review", headers=built["headers"],
        json={"verdict": "passed", "comment": "",
              "rubric": [{"criterion_id": "c_logic", "level": 3, "note": ""}]}).status_code == 400
    # 客户端塞 points 也被丢弃：c_logic=3→40、c_structure=2→30、c_creative=1→15 = 85
    forged = [dict(item, points=999) for item in RUBRIC_FULL]
    review = built["client"].post(
        f"/api/admin/scratch/submissions/{sid}/review", headers=built["headers"],
        json={"verdict": "passed", "comment": "不错", "rubric": forged})
    assert review.status_code == 200, review.text
    sub = review.json()["submission"]
    assert sub["review"]["manual_score"] == 85
    assert sub["review"]["manual_score_max"] == 100
    assert sub["review"]["items"][0]["points"] == 40  # 不是 999

    history = sclient.get(f"/api/scratch/lesson-blocks/{block_id}/submissions").json()
    teacher = history["submissions"][0]["teacher"]
    assert teacher["verdict"] == "passed"
    assert teacher["rubric"]["total"] == 85
    assert teacher["rubric"]["max"] == 100
    assert teacher["rubric"]["items"][0]["label"] == "程序逻辑"
    assert teacher["rubric"]["items"][0]["points"] == 40
    assert teacher["rubric"]["items"][0]["max"] == 40
    assert teacher["rubric"]["items"][0]["note"] == "移动和说话都做到了"


def test_review_without_rubric_rejects_rubric(tmp_path: Path):
    """无量规的挑战：/review 带 rubric → 400（不接受临时发明量规）。"""
    app = scratch_env(tmp_path)
    built = build_scratch_lesson(app)
    sclient = student_login(app)
    block_id = built["block_ids"][0]
    project_id = open_block(sclient, block_id).json()["project"]["id"]
    save_project(sclient, project_id, sb3_bytes())
    sid = submit(sclient, block_id).json()["submission_id"]
    resp = built["client"].post(
        f"/api/admin/scratch/submissions/{sid}/review", headers=built["headers"],
        json={"verdict": "passed", "comment": "",
              "rubric": [{"criterion_id": "c_x", "level": 1, "note": ""}]})
    assert resp.status_code == 400


def test_return_requires_comment(tmp_path: Path):
    app = scratch_env(tmp_path)
    built = build_scratch_lesson(app)
    sclient = student_login(app)
    block_id = built["block_ids"][0]
    project_id = open_block(sclient, block_id).json()["project"]["id"]
    save_project(sclient, project_id, sb3_bytes())
    sid = submit(sclient, block_id).json()["submission_id"]
    assert built["client"].post(
        f"/api/admin/scratch/submissions/{sid}/return", headers=built["headers"],
        json={"comment": ""}).status_code == 422
    assert built["client"].post(
        f"/api/admin/scratch/submissions/{sid}/return", headers=built["headers"],
        json={}).status_code == 422


def test_return_keeps_completion_and_resubmit(tmp_path: Path):
    """passed → returned：完成记录保留；学生重交产生新行 attempt_no+1，老行仍是 returned。"""
    app = scratch_env(tmp_path)
    built = build_scratch_lesson(app)
    sclient = student_login(app)
    block_id = built["block_ids"][0]
    project_id = open_block(sclient, block_id).json()["project"]["id"]
    save_project(sclient, project_id, sb3_bytes())
    submitted = submit(sclient, block_id).json()
    assert submitted["passed"] is True
    sid = submitted["submission_id"]

    ret = built["client"].post(
        f"/api/admin/scratch/submissions/{sid}/return", headers=built["headers"],
        json={"comment": "改一下初始位置再交一次。"})
    assert ret.status_code == 200, ret.text
    assert ret.json()["submission"]["status"] == "returned"
    assert ret.json()["submission"]["passed"] is False

    db = app.state.session_factory()
    try:
        # 完成记录仍在（进度不回退）
        assert db.scalar(select(LessonBlockCompletion).where(
            LessonBlockCompletion.block_id == block_id)) is not None
    finally:
        db.close()

    again = submit(sclient, block_id).json()
    assert again["attempt_no"] == submitted["attempt_no"] + 1
    history = sclient.get(f"/api/scratch/lesson-blocks/{block_id}/submissions").json()
    assert [s["status"] for s in history["submissions"]] == ["passed", "returned"]


def test_latest_only(tmp_path: Path):
    """批改队列口径：latest_only=true 每人每块只排最新一条，默认 false 看全历史。"""
    app = scratch_env(tmp_path)
    built = build_scratch_lesson(app)
    sclient = student_login(app)
    block_id = built["block_ids"][0]
    project_id = open_block(sclient, block_id).json()["project"]["id"]
    save_project(sclient, project_id, sb3_bytes())
    for _ in range(3):
        submit(sclient, block_id)

    admin = built["client"]
    all_rows = admin.get("/api/admin/scratch/submissions", headers=built["headers"]).json()
    assert all_rows["total"] == 3
    latest = admin.get("/api/admin/scratch/submissions?latest_only=true",
                       headers=built["headers"]).json()
    assert latest["total"] == 1
    assert latest["items"][0]["attempt_count"] == 3


def test_rubric_snapshot_freezes_version(tmp_path: Path):
    """批改后改量规：旧提交仍按冻结的当时量规解释，不按当前量规重算。"""
    app = scratch_env(tmp_path)
    client, headers = admin_login(app)
    challenge = create_challenge(client, headers, rubric=RUBRIC)
    built = build_scratch_lesson(app, challenge=challenge)
    sclient = student_login(app)
    block_id = built["block_ids"][0]
    project_id = open_block(sclient, block_id).json()["project"]["id"]
    save_project(sclient, project_id, sb3_bytes())
    sid = submit(sclient, block_id).json()["submission_id"]

    items = [
        {"criterion_id": "c_logic", "level": 2, "note": ""},      # 25
        {"criterion_id": "c_structure", "level": 1, "note": ""},  # 15
        {"criterion_id": "c_creative", "level": 1, "note": ""},   # 15
    ]
    review = built["client"].post(
        f"/api/admin/scratch/submissions/{sid}/review", headers=built["headers"],
        json={"verdict": "failed", "comment": "再改改", "rubric": items})
    assert review.status_code == 200, review.text
    assert review.json()["submission"]["review"]["manual_score"] == 55

    # 模拟改版：直接改库里的 rubric_json（把 c_logic 满分调到 80，总分 140）
    db = app.state.session_factory()
    try:
        ch = db.get(ScratchChallenge, challenge["id"])
        new_rubric = json.loads(json.dumps(RUBRIC))
        new_rubric["criteria"][0]["levels"][0]["points"] = 80
        new_rubric["max_score"] = 140
        ch.rubric_json = json.dumps(new_rubric, ensure_ascii=False)
        db.commit()
    finally:
        db.close()

    detail = built["client"].get(f"/api/admin/scratch/submissions/{sid}",
                                 headers=built["headers"]).json()
    assert detail["review"]["manual_score"] == 55
    assert detail["review"]["manual_score_max"] == 100  # 冻结的旧满分
    assert detail["rubric"]["max_score"] == 140          # 当前量规已更新

    student = sclient.get(f"/api/scratch/lesson-blocks/{block_id}/submissions").json()
    teacher = student["submissions"][0]["teacher"]
    assert teacher["rubric"]["max"] == 100               # 学生看到的仍是批改当时
    assert teacher["rubric"]["items"][0]["max"] == 40


def test_project_json_endpoint(tmp_path: Path):
    app = scratch_env(tmp_path)
    built = build_scratch_lesson(app)
    sclient = student_login(app)
    block_id = built["block_ids"][0]
    project_id = open_block(sclient, block_id).json()["project"]["id"]
    save_project(sclient, project_id, sb3_bytes())
    sid = submit(sclient, block_id).json()["submission_id"]

    resp = built["client"].get(f"/api/admin/scratch/submissions/{sid}/project.json",
                               headers=built["headers"])
    assert resp.status_code == 200, resp.text
    project = resp.json()
    assert "targets" in project
    assert any(t.get("blocks") for t in project["targets"])

    from fastapi.testclient import TestClient
    guest = TestClient(app)
    assert guest.get(f"/api/admin/scratch/submissions/{sid}/project.json").status_code == 401


def test_reviewer_cannot_review_or_return(tmp_path: Path):
    """reviewer（题库审核员）不是教师：/review 与 /return 一律 403。"""
    app = scratch_env(tmp_path)
    built = build_scratch_lesson(app)
    sclient = student_login(app)
    block_id = built["block_ids"][0]
    project_id = open_block(sclient, block_id).json()["project"]["id"]
    save_project(sclient, project_id, sb3_bytes())
    sid = submit(sclient, block_id).json()["submission_id"]

    rclient, rheaders = reviewer_login(app)
    assert rclient.post(f"/api/admin/scratch/submissions/{sid}/review", headers=rheaders,
                        json={"verdict": "passed", "comment": ""}).status_code == 403
    assert rclient.post(f"/api/admin/scratch/submissions/{sid}/return", headers=rheaders,
                        json={"comment": "改改"}).status_code == 403
