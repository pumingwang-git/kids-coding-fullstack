"""参考代码试跑。

在这之前没有任何一步会去编译参考代码：一份粘贴时丢了半行的 C++ 可以一路通过审核、
进卷、发给学员。用例盯住三件事：

1. **隐藏测试点的内容对管理员全量下发**——这是全系统唯一这么做的地方，也正是试跑
   的价值所在（学员端那边被 build_case_result() 按 is_sample 裁掉了）；
2. **权限**：审核员对 pending 的题必须能跑，否则审核只能靠眼睛编译；approved 不能跑；
3. **提交审核的前置校验绑 revision**，不是绑时间戳——时间戳证明不了跑的是哪一版。

判题走 FakeJudgeClient：含 print/cout 全过，含 __WA__ 第 2 个点起错，空代码编译错误。
"""

import time

from test_exam import admin_login, build_app, common, match

from app.models import AdminUser, ExamLink, Paper, PaperAttempt, User
from app.security import password_hash

PASSWORD = "Admin-pass-123!"


def python_payload(*, ref_code="print(1)", condition="全测试点通过", hidden=None) -> dict:
    """Python 操作题：ZIP 那条路要传文件，试跑本身与语言无关，用 Python 省事。"""
    return {
        "type": "programming", "sub_type": "python",
        "common": common(difficulty="普及-", source="洛谷"),
        "stem": "输入两个整数，输出和。", "analysis": "", "options": [], "blanks": [],
        "programming": {
            "title": "A+B", "pass_condition": condition,
            "input_format": "两个整数", "output_format": "一个整数", "hints": "无",
            "samples": [{"input": "1 2", "output": "3"}],
            "ref_code": {"cpp": "", "python": ref_code},
            "manual_test_cases": hidden if hidden is not None else [
                {"input": "10 20", "output": "30"},
                {"input": "5 5", "output": "10"},
            ],
        },
    }


def create_problem(client, headers, payload=None):
    response = client.post("/api/admin/problems", headers=headers, json=payload or python_payload())
    assert response.status_code == 201, response.text
    return response.json()


def dry_run(client, headers, problem_id, *, scope="all", expect=201, **body):
    response = client.post(f"/api/admin/problems/{problem_id}/dry-run", headers=headers,
                           json={"scope": scope, **body})
    assert response.status_code == expect, response.text
    return response.json()


def wait_done(client, headers, dry_run_id, timeout=15.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        response = client.get(f"/api/admin/dry-runs/{dry_run_id}", headers=headers)
        assert response.status_code == 200, response.text
        body = response.json()
        if body.get("done"):
            return body
        time.sleep(0.05)
    raise AssertionError(f"试跑 {dry_run_id} 超时未结束")


def test_passing_reference_code_reports_every_case(tmp_path):
    app = build_app(tmp_path)
    client, headers = admin_login(app)
    problem = create_problem(client, headers)

    queued = dry_run(client, headers, problem["id"])
    result = wait_done(client, headers, queued["id"])

    assert result["status"] == "accepted"
    # 1 个样例 + 2 个隐藏点
    assert len(result["cases"]) == 3
    assert all(case["passed"] for case in result["cases"])
    # 隐藏点的输入输出对管理员全量下发——这正是学员端会裁掉的那部分
    hidden = [case for case in result["cases"] if not case["is_sample"]]
    assert len(hidden) == 2
    assert "10 20" in hidden[0]["input"]
    assert "30" in hidden[0]["expected"]


def test_failing_case_reports_diff_line(tmp_path):
    """把参考代码换成会错的：录题人要能一眼看出是第几个点、差在哪一行。"""
    app = build_app(tmp_path)
    client, headers = admin_login(app)
    problem = create_problem(client, headers, python_payload(ref_code="__WA__ print(1)"))

    result = wait_done(client, headers, dry_run(client, headers, problem["id"])["id"])

    assert result["status"] == "wrong_answer"
    failed = [case for case in result["cases"] if not case["passed"]]
    assert failed, result["cases"]
    assert failed[0]["diff_line"] == 1
    assert "__fake_wrong_output__" in failed[0]["actual"]


def test_compile_error_surfaces_the_message(tmp_path):
    """最常见也最尴尬的一种：参考代码根本没编译过。"""
    app = build_app(tmp_path)
    client, headers = admin_login(app)
    # 参考代码非空才建得出题，建完再清空，模拟"粘贴时丢了半行"
    problem = create_problem(client, headers)
    payload = python_payload(ref_code="   ")
    client.put(f"/api/admin/problems/{problem['id']}", headers=match(headers, 1), json=payload)

    queued = dry_run(client, headers, problem["id"], expect=422)
    assert "参考代码" in queued["detail"]


def test_samples_scope_runs_only_samples(tmp_path):
    app = build_app(tmp_path)
    client, headers = admin_login(app)
    problem = create_problem(client, headers)

    result = wait_done(client, headers, dry_run(client, headers, problem["id"], scope="samples")["id"])
    assert len(result["cases"]) == 1
    assert result["cases"][0]["is_sample"] is True


def test_custom_input_scope(tmp_path):
    app = build_app(tmp_path)
    client, headers = admin_login(app)
    problem = create_problem(client, headers)

    queued = dry_run(client, headers, problem["id"], scope="custom", custom_input="9 9")
    result = wait_done(client, headers, queued["id"])
    assert len(result["cases"]) == 1
    assert "9 9" in result["cases"][0]["input"]


def test_approved_problem_cannot_dry_run(tmp_path):
    """approved 是冻结态：连内容都不让改，没道理让它去占判题机。"""
    app = build_app(tmp_path)
    client, headers = admin_login(app)
    problem = create_problem(client, headers)
    wait_done(client, headers, dry_run(client, headers, problem["id"])["id"])
    assert client.post(f"/api/admin/problems/{problem['id']}/submit",
                       headers=match(headers, 1)).status_code == 200
    assert client.post(f"/api/admin/problems/{problem['id']}/approve",
                       headers=match(headers, 2)).status_code == 200

    dry_run(client, headers, problem["id"], expect=403)


def test_reviewer_can_dry_run_pending_problem(tmp_path):
    """审核环节的核心用途。不放行的话，审核员只能读代码用眼睛编译。"""
    app = build_app(tmp_path)
    client, headers = admin_login(app)
    problem = create_problem(client, headers)
    wait_done(client, headers, dry_run(client, headers, problem["id"])["id"])
    assert client.post(f"/api/admin/problems/{problem['id']}/submit",
                       headers=match(headers, 1)).status_code == 200

    db = app.state.session_factory()
    try:
        db.add(AdminUser(username="checker", password_hash=password_hash.hash(PASSWORD),
                         display_name="审核员", role="reviewer"))
        db.commit()
    finally:
        db.close()

    from fastapi.testclient import TestClient
    reviewer = TestClient(app)
    reviewer.get("/api/admin/csrf")
    assert reviewer.post("/api/admin/login",
                         headers={"X-CSRF-Token": reviewer.cookies.get("admin_csrf_token")},
                         json={"username": "checker", "password": PASSWORD}).status_code == 200
    reviewer_headers = {"X-CSRF-Token": reviewer.cookies.get("admin_csrf_token")}
    dry_run(reviewer, reviewer_headers, problem["id"], expect=201)


def test_submit_requires_a_passing_dry_run(tmp_path):
    app = build_app(tmp_path)
    client, headers = admin_login(app)
    problem = create_problem(client, headers)

    blocked = client.post(f"/api/admin/problems/{problem['id']}/submit", headers=match(headers, 1))
    assert blocked.status_code == 422
    assert "试跑" in blocked.json()["detail"]


def test_editing_after_dry_run_invalidates_it(tmp_path):
    """绑 revision 的意义：改完题不重跑就提交，等于拿旧结果给新内容背书。"""
    app = build_app(tmp_path)
    client, headers = admin_login(app)
    problem = create_problem(client, headers)
    wait_done(client, headers, dry_run(client, headers, problem["id"])["id"])

    payload = python_payload()
    payload["stem"] = "输入两个整数，输出它们的和。"
    updated = client.put(f"/api/admin/problems/{problem['id']}", headers=match(headers, 1), json=payload)
    assert updated.status_code == 200, updated.text

    blocked = client.post(f"/api/admin/problems/{problem['id']}/submit",
                          headers=match(headers, updated.json()["revision"]))
    assert blocked.status_code == 422
    assert "又改过" in blocked.json()["detail"]


def test_dry_run_refused_while_an_exam_is_running(tmp_path):
    """试跑与学员判题共用同一个 go-judge。考试进行中批量试跑就是跟考生抢沙箱。"""
    app = build_app(tmp_path)
    client, headers = admin_login(app)
    problem = create_problem(client, headers)

    db = app.state.session_factory()
    try:
        user = User(username="learner", email="learner@example.com",
                    hashed_password=password_hash.hash(PASSWORD), status="active")
        paper = Paper(title="占位卷", status="published")
        db.add_all([user, paper])
        db.flush()
        # 外键是真的会校验的（build_database 对 SQLite 打开了 PRAGMA foreign_keys），
        # 链接必须真建一条，不能拿一个不存在的 id 凑数。
        link = ExamLink(paper_id=paper.id, name="占位场次", access_token="t" * 32)
        db.add(link)
        db.flush()
        db.add(PaperAttempt(exam_link_id=link.id, paper_id=paper.id, user_id=user.id,
                            attempt_no=1, status="ongoing"))
        db.commit()
    finally:
        db.close()

    refused = dry_run(client, headers, problem["id"], expect=409)
    assert "考试" in refused["detail"]
