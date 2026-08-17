"""课时内编程题试跑（形态 B · 只运行不计分）回归。

对应《15、课时作答与资料展示-开发交接》§4 与 §8.1 S4。

最重要的一条：**隐藏测试点在任何路径下都不下发**。样例是题面的一部分（本来就公开），
隐藏点是判分资产——这条链路只跑样例，题面接口也只给样例。
"""
import json
from pathlib import Path

from test_exam import admin_login, build_app, scsrf, student_login, walk_keys
from test_lesson_block_unlock import build_lesson_with_blocks

# TestCase 起别名：pytest 会把名字以 Test 开头的类当测试类收集，
# 直接 import 会刷一条 PytestCollectionWarning。
from app.models import LessonCodeRun, Problem, ProgrammingDetail
from app.models import TestCase as OjTestCase

SECRET_INPUT = "999888777"
SECRET_OUTPUT = "隐藏点的期望输出"


def seed_programming_problem(app, *, problem_id_no="Q300001"):
    """一道编程题：1 个样例 + 1 个隐藏点。隐藏点的内容故意写成好 grep 的串。"""
    db = app.state.session_factory()
    try:
        p = Problem(type="programming", sub_type="cpp", title="A+B",
                    stem="读入两个整数，输出它们的和。", status="approved",
                    analysis="送分题", problem_id_no=problem_id_no, version_no=1, revision=1)
        db.add(p)
        db.flush()
        p.root_problem_id = p.id
        db.add(ProgrammingDetail(problem_id=p.id, input_format="两个整数",
                                 output_format="一个整数", hints="注意换行",
                                 time_limit_ms=1000, memory_limit_mb=256))
        db.add(OjTestCase(problem_id=p.id, input="1 2\n", output="3\n",
                        is_sample=True, sort_order=0, case_no=1))
        db.add(OjTestCase(problem_id=p.id, input=SECRET_INPUT, output=SECRET_OUTPUT,
                        is_sample=False, sort_order=1, case_no=2))
        db.commit()
        return {"problem_id_no": p.problem_id_no}
    finally:
        db.close()


def build_coding_lesson(app, *, problem_id_no):
    return build_lesson_with_blocks(app, [{
        "block_type": "practice", "title": "编程练习",
        "problem_id_no": problem_id_no, "score": 20, "display_no": "1",
    }])


def get_problem(sclient, lid, bid):
    return sclient.get(f"/api/lessons/{lid}/blocks/{bid}/problem")


def start_run(sclient, lid, bid, **body):
    payload = {"language": "cpp", "code": "int main(){}", "scope": "samples", **body}
    return sclient.post(f"/api/lessons/{lid}/blocks/{bid}/run",
                        headers=scsrf(sclient), json=payload)


# ---------- 题面：只给样例 ----------


def test_programming_payload_hides_secret_cases(tmp_path: Path):
    """编程题题面只下发样例；隐藏测试点的输入与期望输出一个字都不能出现。"""
    app = build_app(tmp_path)
    no = seed_programming_problem(app)["problem_id_no"]
    built = build_coding_lesson(app, problem_id_no=no)
    sclient = student_login(app)
    bid = built["block_ids"][-1]

    resp = get_problem(sclient, built["lesson_id"], bid)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    prog = body["question"]["programming"]

    assert len(prog["samples"]) == 1
    assert prog["samples"][0]["input"] == "1 2\n"
    assert prog["time_limit_ms"] == 1000 and prog["memory_limit_mb"] == 256
    # 隐藏点绝不出现在整个响应里
    assert SECRET_INPUT not in resp.text
    assert SECRET_OUTPUT not in resp.text
    walk_keys(body, {"problem_id_no", "analysis", "is_correct"})


# ---------- 试跑 ----------


def test_run_only_uses_sample_cases(tmp_path: Path):
    """试跑只跑样例：结果里只有 1 个点，且不含隐藏点内容。"""
    app = build_app(tmp_path)
    no = seed_programming_problem(app)["problem_id_no"]
    built = build_coding_lesson(app, problem_id_no=no)
    sclient = student_login(app)
    lid, bid = built["lesson_id"], built["block_ids"][-1]

    started = start_run(sclient, lid, bid, code="print(1)")
    assert started.status_code == 201, started.text
    run_id = started.json()["run_id"]

    polled = sclient.get(f"/api/lessons/{lid}/blocks/{bid}/runs/{run_id}")
    assert polled.status_code == 200
    body = polled.json()
    assert body["done"] is True, f"fake 判题应同步跑完：{body}"
    assert len(body["cases"]) == 1, "只应跑 1 个样例，隐藏点不参与试跑"
    assert SECRET_INPUT not in polled.text
    assert SECRET_OUTPUT not in polled.text

    db = app.state.session_factory()
    try:
        run = db.query(LessonCodeRun).one()
        assert run.scope == "samples" and run.user_id and run.block_id == bid
        # 隐藏点内容也不该被写进 detail_json
        assert SECRET_OUTPUT not in (run.detail_json or "")
    finally:
        db.close()


def test_run_custom_input(tmp_path: Path):
    """自定义输入：只跑一个点，没有期望输出。"""
    app = build_app(tmp_path)
    no = seed_programming_problem(app)["problem_id_no"]
    built = build_coding_lesson(app, problem_id_no=no)
    sclient = student_login(app)
    lid, bid = built["lesson_id"], built["block_ids"][-1]

    started = start_run(sclient, lid, bid, scope="custom", custom_input="5 6\n")
    assert started.status_code == 201
    body = sclient.get(
        f"/api/lessons/{lid}/blocks/{bid}/runs/{started.json()['run_id']}"
    ).json()
    assert len(body["cases"]) == 1
    assert body["cases"][0]["expected"] == ""


def test_run_rejects_empty_code(tmp_path: Path):
    app = build_app(tmp_path)
    no = seed_programming_problem(app)["problem_id_no"]
    built = build_coding_lesson(app, problem_id_no=no)
    sclient = student_login(app)
    r = start_run(sclient, built["lesson_id"], built["block_ids"][-1], code="   ")
    assert r.status_code == 400


def test_run_result_is_owner_scoped(tmp_path: Path):
    """别人的 run_id 查不到：光认 run_id 就能读到他人的代码与结果。"""
    app = build_app(tmp_path)
    no = seed_programming_problem(app)["problem_id_no"]
    built = build_coding_lesson(app, problem_id_no=no)
    sclient = student_login(app)
    lid, bid = built["lesson_id"], built["block_ids"][-1]
    run_id = start_run(sclient, lid, bid, code="print(1)").json()["run_id"]

    # 换一个学生
    other = student_login(app, username="learner2")
    assert other.get(f"/api/lessons/{lid}/blocks/{bid}/runs/{run_id}").status_code == 404


def test_answer_endpoint_rejects_programming(tmp_path: Path):
    """编程题不能走客观题的作答接口（否则会被判 0 分）。"""
    app = build_app(tmp_path)
    no = seed_programming_problem(app)["problem_id_no"]
    built = build_coding_lesson(app, problem_id_no=no)
    sclient = student_login(app)
    r = sclient.post(
        f"/api/lessons/{built['lesson_id']}/blocks/{built['block_ids'][-1]}/answer",
        headers=scsrf(sclient), json={"answer": {"picked": "A"}},
    )
    assert r.status_code == 400


def test_run_blocked_when_block_locked(tmp_path: Path):
    """顺序锁的编程块：试跑也要 403，且不留运行记录。"""
    app = build_app(tmp_path)
    no = seed_programming_problem(app)["problem_id_no"]
    built = build_lesson_with_blocks(app, [
        {"title": "前置图文"},
        {"block_type": "practice", "title": "编程练习", "unlock_rule": "sequential",
         "problem_id_no": no, "score": 20, "display_no": "1"},
    ])
    sclient = student_login(app)
    r = start_run(sclient, built["lesson_id"], built["block_ids"][1], code="print(1)")
    assert r.status_code == 403

    db = app.state.session_factory()
    try:
        assert db.query(LessonCodeRun).count() == 0
    finally:
        db.close()
