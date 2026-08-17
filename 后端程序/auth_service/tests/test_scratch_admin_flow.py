"""老师上传 Scratch 作业全流程**实测**（逐步打真实 API，不是读代码推断）。

步骤顺序与教研真实操作一致：建草稿 → 传 starter（含安检）→ 配 15 种规则 →
配量规 → submit/approve/publish → 学生提交拿判定。每一步断言实际响应，
顺带记录"非法参数在写入期 vs 判定期的真实行为"（写入期只拦未知 type，
参数问题按设计留给判定/发布检查，见 test_step_rules_bad_params）。
"""
import json
from pathlib import Path

from test_exam import admin_login, student_login
from test_scratch import (
    PASSING_RULES,
    build_scratch_lesson,
    open_block,
    save_project,
    sb3_bytes,
    scratch_env,
    scripted_sprite,
    stage_target,
    submit,
)

# 15 种合法规则（type 与后端 _EVALUATORS 一一对应；新 4 种含真实格式字段名）
ALL_VALID_RULES = [
    {"type": "require_opcode", "opcode": "motion_movesteps"},
    {"type": "forbid_opcode", "opcode": "motion_glidesecstoxy"},
    {"type": "require_after_hat", "hat": "event_whenflagclicked", "opcode": "motion_movesteps"},
    {"type": "require_input_value", "opcode": "motion_movesteps", "input": "STEPS", "equals": "10"},
    {"type": "require_say_text", "text": "你好"},
    {"type": "min_sprites", "count": 1},
    {"type": "min_variables", "count": 0},
    {"type": "require_variable", "name": "分数"},
    {"type": "require_broadcast", "name": "开始"},
    {"type": "sprite_start_position", "sprite": "小猫", "x": 0, "y": 0, "tolerance": 5},
    {"type": "require_extension", "name": "pen"},
    {"type": "no_dead_code", "max_allowed": 0},
    {"type": "broadcast_pairing", "direction": "both"},
    {"type": "require_initialization", "attributes": ["position", "variable:分数"]},
    {"type": "require_structure",
     "pattern": {"opcode": "control_repeat", "contains": [{"opcode": "control_if"}]}},
]

RUBRIC_OK = {
    "max_score": 30,
    "criteria": [
        {"id": "c_logic", "label": "程序逻辑", "levels": [
            {"value": 1, "label": "达成", "points": 20},
            {"value": 0, "label": "未达成", "points": 0}]},
        {"id": "c_structure", "label": "代码结构", "levels": [
            {"value": 1, "label": "清晰", "points": 10},
            {"value": 0, "label": "混乱", "points": 0}]},
    ],
}


def _create(client, headers, **extra):
    resp = client.post("/api/admin/scratch/challenges", headers=headers, json={
        "title": "实测关卡", "instructions_md": "让小猫动起来",
        "rules": PASSING_RULES, **extra})
    assert resp.status_code == 201, resp.text
    return resp.json()


def _upload_starter(client, headers, cid, data=b""):
    return client.post(f"/api/admin/scratch/challenges/{cid}/starter", headers=headers,
                       files={"file": ("s.sb3", data, "application/zip")})


# ---------- 步骤 1：创建草稿 ----------


def test_step1_create_draft(tmp_path: Path):
    app = scratch_env(tmp_path)
    client, headers = admin_login(app)
    challenge = _create(client, headers)
    assert challenge["status"] == "draft"
    assert challenge["version"] == 1       # 第 1 版（还没发布过）
    assert challenge["edit_seq"] == 1      # 编辑序号与发布版次分开计数
    assert challenge["has_starter"] is False


# ---------- 步骤 2：starter 上传与安检 ----------


def test_step2_starter_security(tmp_path: Path):
    app = scratch_env(tmp_path, scratch_sb3_max_bytes=262_144)
    client, headers = admin_login(app)
    cid = _create(client, headers)["id"]

    # 伪 sb3（不是 zip）→ 400 中文
    fake = _upload_starter(client, headers, cid, b"this is not a zip")
    assert fake.status_code == 400
    assert "zip" in fake.json()["detail"].lower() or "项目文件" in fake.json()["detail"]

    # 超大 → 413（限额取下限 256KB；用随机字节，避免 zip 压缩把负载压回限内）
    import os
    big = _upload_starter(client, headers, cid, sb3_bytes(extra={"pad.bin": os.urandom(300_000)}))
    assert big.status_code == 413

    # 路径穿越条目 → 400
    evil = _upload_starter(client, headers, cid, sb3_bytes(extra={"../evil.txt": b"x"}))
    assert evil.status_code == 400
    assert "结构异常" in evil.json()["detail"]

    # 缺 project.json → 400
    nojson = _upload_starter(client, headers, cid, sb3_bytes(project_json=False))
    assert nojson.status_code == 400

    # 合法 → 200，带 sha256 与 sprite_count
    ok = _upload_starter(client, headers, cid, sb3_bytes())
    assert ok.status_code == 200, ok.text
    body = ok.json()
    assert body["has_starter"] is True and body["starter_sha256"]


# ---------- 步骤 3：配规则 ----------


def test_step3_rules_15_valid_accepted(tmp_path: Path):
    app = scratch_env(tmp_path)
    client, headers = admin_login(app)
    challenge = _create(client, headers)
    resp = client.put(f"/api/admin/scratch/challenges/{challenge['id']}", headers=headers, json={
        "title": challenge["title"], "instructions_md": challenge["instructions_md"],
        "rules": ALL_VALID_RULES, "base_version": challenge["edit_seq"]})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert [r["type"] for r in body["rules"]] == [r["type"] for r in ALL_VALID_RULES]
    assert body["edit_seq"] == challenge["edit_seq"] + 1
    assert body["version"] == 1  # 草稿编辑不动发布版次


def test_step3_unknown_rule_type_400(tmp_path: Path):
    app = scratch_env(tmp_path)
    client, headers = admin_login(app)
    challenge = _create(client, headers)
    resp = client.put(f"/api/admin/scratch/challenges/{challenge['id']}", headers=headers, json={
        "title": challenge["title"], "instructions_md": challenge["instructions_md"],
        "rules": [{"type": "require_opcodes", "opcode": "motion_movesteps"}]})
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert "类型无效" in detail and "require_opcode" in detail  # 中文报错且列出可用类型


def test_step3_bad_params_deferred_to_judgement(tmp_path: Path):
    """非法参数的真实行为（设计如此，不是漏校验）：

    写入期只拦未知 type——参数写错（如 count 填 "abc"、新规则缺 attributes）会被存下；
    判定期老规则参数异常 → needs_review 转人工，新 4 种规则参数错误 → failed + 中文
    "规则参数错误"。两条路都不 500、都不误判学生。
    """
    app = scratch_env(tmp_path)
    built = build_scratch_lesson(app)
    client, headers = built["client"], built["headers"]
    cid = built["challenge"]["id"]

    # 撤回发布才能改（改为参数坏掉的规则）
    client.post(f"/api/admin/courses/{built['course_id']}/off-shelf", headers=headers)
    client.post(f"/api/admin/scratch/challenges/{cid}/unpublish", headers=headers)
    bad_rules = [
        {"type": "min_sprites", "count": "abc"},          # 老规则参数类型错 → 判定期转人工
        {"type": "require_initialization"},                # 新规则缺 attributes → failed 中文
        {"type": "require_structure", "pattern": None},    # 新规则 pattern 非法 → failed 中文
    ]
    saved = client.put(f"/api/admin/scratch/challenges/{cid}", headers=headers, json={
        "title": built["challenge"]["title"], "instructions_md": "说明", "rules": bad_rules})
    assert saved.status_code == 200  # 写入期不拦参数（与后端注释口径一致）

    client.post(f"/api/admin/scratch/challenges/{cid}/publish", headers=headers)
    client.post(f"/api/admin/courses/{built['course_id']}/publish", headers=headers)
    sclient = student_login(app, "badparams")
    block_id = built["block_ids"][0]
    project_id = open_block(sclient, block_id).json()["project"]["id"]
    save_project(sclient, project_id, sb3_bytes())
    result = submit(sclient, block_id).json()
    assert result["submission_status"] == "needs_review"  # 老规则参数坏 → 挂起人工
    msgs = [r["message"] for r in result.get("feedback", {}).get("items", [])]
    assert any("参数错误" in m for m in msgs)  # 新规则给出可读的中文参数错误


# ---------- 步骤 4：量规强一致 ----------


def test_step4_rubric_max_score_enforced(tmp_path: Path):
    app = scratch_env(tmp_path)
    client, headers = admin_login(app)
    challenge = _create(client, headers)

    bad = json.loads(json.dumps(RUBRIC_OK))
    bad["max_score"] = 100  # 与最高档之和 30 不一致
    resp = client.put(f"/api/admin/scratch/challenges/{challenge['id']}", headers=headers, json={
        "title": challenge["title"], "instructions_md": challenge["instructions_md"],
        "rules": PASSING_RULES, "rubric": bad})
    assert resp.status_code == 400
    assert "max_score" in resp.json()["detail"] and "30" in resp.json()["detail"]

    ok = client.put(f"/api/admin/scratch/challenges/{challenge['id']}", headers=headers, json={
        "title": challenge["title"], "instructions_md": challenge["instructions_md"],
        "rules": PASSING_RULES, "rubric": RUBRIC_OK})
    assert ok.status_code == 200, ok.text
    assert ok.json()["rubric"]["max_score"] == 30


# ---------- 步骤 5：发布门槛与状态机 ----------


def test_step5_publish_gate_and_lifecycle(tmp_path: Path):
    app = scratch_env(tmp_path)
    client, headers = admin_login(app)

    # 空题面：创建时 title 必填由 pydantic 拦（422）
    no_title = client.post("/api/admin/scratch/challenges", headers=headers,
                           json={"title": "", "rules": PASSING_RULES})
    assert no_title.status_code == 422

    challenge = _create(client, headers)
    cid = challenge["id"]

    # 缺 starter → submit 被拦
    no_starter = client.post(f"/api/admin/scratch/challenges/{cid}/submit", headers=headers)
    assert no_starter.status_code == 400 and "初始项目" in no_starter.json()["detail"]

    _upload_starter(client, headers, cid, sb3_bytes())

    # 清空规则 → submit 被拦
    client.put(f"/api/admin/scratch/challenges/{cid}", headers=headers, json={
        "title": challenge["title"], "instructions_md": "说明", "rules": []})
    no_rules = client.post(f"/api/admin/scratch/challenges/{cid}/submit", headers=headers)
    assert no_rules.status_code == 400 and "规则" in no_rules.json()["detail"]

    # 清空说明 → submit 被拦
    client.put(f"/api/admin/scratch/challenges/{cid}", headers=headers, json={
        "title": challenge["title"], "instructions_md": "", "rules": PASSING_RULES})
    no_doc = client.post(f"/api/admin/scratch/challenges/{cid}/submit", headers=headers)
    assert no_doc.status_code == 400 and "说明" in no_doc.json()["detail"]

    # 补齐 → submit → pending；approve → published
    client.put(f"/api/admin/scratch/challenges/{cid}", headers=headers, json={
        "title": challenge["title"], "instructions_md": "让小猫动起来", "rules": PASSING_RULES})
    submitted = client.post(f"/api/admin/scratch/challenges/{cid}/submit", headers=headers)
    assert submitted.status_code == 200 and submitted.json()["status"] == "pending"

    # pending 状态下不能再编辑（只有草稿可以）
    blocked = client.put(f"/api/admin/scratch/challenges/{cid}", headers=headers, json={
        "title": "x", "instructions_md": "x", "rules": PASSING_RULES})
    assert blocked.status_code == 409

    approved = client.post(f"/api/admin/scratch/challenges/{cid}/approve", headers=headers)
    assert approved.status_code == 200
    assert approved.json()["challenge"]["status"] == "published"
    assert approved.json()["challenge"]["version"] == 1  # 首次发布保持 v1

    # 发布后撤回 → 再发 v2
    client.post(f"/api/admin/scratch/challenges/{cid}/unpublish", headers=headers)
    republished = client.post(f"/api/admin/scratch/challenges/{cid}/publish", headers=headers)
    assert republished.json()["challenge"]["version"] == 2


# ---------- 步骤 6：学生提交与判定反馈 ----------


def test_step6_student_submit_evaluates(tmp_path: Path):
    app = scratch_env(tmp_path)
    built = build_scratch_lesson(app)  # PASSING_RULES：绿旗后移动 + 移动10步 + 说你好
    sclient = student_login(app, "step6")
    block_id = built["block_ids"][0]
    project_id = open_block(sclient, block_id).json()["project"]["id"]

    # 合格作品 → passed，分数 100，逐条反馈全过
    save_project(sclient, project_id, sb3_bytes())
    good = submit(sclient, block_id).json()
    assert good["submission_status"] == "passed"
    assert good["score"] == 100
    items = good["feedback"]["items"]
    assert len(items) == 3 and all(i["passed"] for i in items)

    # 有死代码且没说话的作品 → failed，反馈里能定位到哪条没过
    messy = scripted_sprite(with_flag=True)
    messy["blocks"]["junk"] = {
        "opcode": "looks_say", "next": None, "parent": None,
        "inputs": {"MESSAGE": [1, [10, "说错了"]]}, "fields": {},
        "shadow": False, "topLevel": True, "x": 300, "y": 100,
    }
    # 老师端给挑战加上 no_dead_code 规则（撤回→改→再发）
    client, headers = built["client"], built["headers"]
    cid = built["challenge"]["id"]
    client.post(f"/api/admin/courses/{built['course_id']}/off-shelf", headers=headers)
    client.post(f"/api/admin/scratch/challenges/{cid}/unpublish", headers=headers)
    client.put(f"/api/admin/scratch/challenges/{cid}", headers=headers, json={
        "title": built["challenge"]["title"], "instructions_md": "让小猫动起来",
        "rules": PASSING_RULES + [{"type": "no_dead_code"}]})
    client.post(f"/api/admin/scratch/challenges/{cid}/publish", headers=headers)
    client.post(f"/api/admin/courses/{built['course_id']}/publish", headers=headers)

    sclient2 = student_login(app, "step6b")
    project_id2 = open_block(sclient2, block_id).json()["project"]["id"]
    save_project(sclient2, project_id2, sb3_bytes([stage_target(), messy]))
    bad = submit(sclient2, block_id).json()
    assert bad["submission_status"] == "failed"
    dead = [i for i in bad["feedback"]["items"] if not i["passed"]]
    assert any("死代码" in (i["message"] or "") for i in dead)
    # attempt_no 递增（同一学生第一次交是 1）
    assert bad["attempt_no"] == 1
