"""学员端作答闭环的端到端测试。

管理员建题组卷发链接、学员开考作答交卷，两个 TestClient 共用一个 app（各自的
cookie jar 就是两套会话）。判题一律走 FakeJudgeClient，不连真沙箱。

题面里埋了几个哨兵字符串（SECRETFILL / SECRETANALYSIS / SECRETIN / SECRETOUT /
SECRETREFCODE），作答期的响应里出现任何一个都算答案泄露，见 test_no_answer_leak_*。
"""

import json
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.config import DEV_FERNET_KEY, Settings
from app.database import build_database
from app.main import create_app
from app.models import AdminUser, AuditEvent, Base, PaperAttempt
from app.security import password_hash

ADMIN_PASSWORD = "Admin-pass-123!"
STUDENT_PASSWORD = "A-long-password-123!"


# ==================== 环境搭建 ====================


def build_app(tmp_path: Path, **overrides):
    tmp_path.mkdir(parents=True, exist_ok=True)  # 同一个用例里建第二套环境时目录还不存在
    settings = Settings(
        environment="test", database_url=f"sqlite:///{tmp_path / 'exam_test.db'}",
        outbox_encryption_key=DEV_FERNET_KEY, cookie_secure=False, smtp_host=None,
        smtp_username=None, smtp_password=None, smtp_from=None, captcha_enabled=False,
        mfa_enabled=False, pwned_check_enabled=False, slider_captcha_enabled=False,
        # 钉死 redis_url=None：本机 .env 配了 REDIS_URL 时，限流器会升格成
        # RedisRateLimiter，计数跨用例/跨轮累积，导致同一套测试随机失败
        # （失败数随轮次增加）。None 时回落 InMemoryRateLimiter，每 app 独立。
        redis_url=None,
        # .env 切到真实沙箱（JUDGE_BACKEND=go-judge）后必须在这里钉回 fake：
        # 本文件的断言全部按 FakeJudgeClient 的写死规则设计（空代码→compile_error、
        # __WA__→第 2 个测试点起 WA），真沙箱会给出不同结果，见文件头说明。
        judge_backend="fake",
        # 同理钉死资料/视频的「浏览器直连端点」：本机 .env 配了 MINIO_PUBLIC_ENDPOINT
        # 之后，Settings 会把它读进来，学生端 download/inline 就改走 302 到预签名 URL；
        # TestClient 默认跟随重定向，而它的 ASGI transport 会把**任何** host 都打回本 app，
        # 于是预签名地址落进 SPA 兜底路由，测试看到的是 404 {"detail":"Not Found"}——
        # 一个纯粹由本机 .env 决定的假失败。测试要覆盖的是应用代理分支（Range/ETag/
        # Content-Disposition 都在那条路径上），这里一律回落到代理模式。
        minio_public_endpoint="",
        testdata_upload_root=str(tmp_path / "testdata"), **overrides,
    )
    engine, _ = build_database(settings.database_url)
    Base.metadata.create_all(engine)
    engine.dispose()
    app = create_app(settings)
    db = app.state.session_factory()
    try:
        db.add(AdminUser(username="root", password_hash=password_hash.hash(ADMIN_PASSWORD),
                         display_name="root", role="super_admin"))
        db.commit()
    finally:
        db.close()
    return app


def admin_login(app) -> tuple[TestClient, dict]:
    client = TestClient(app)
    client.get("/api/admin/csrf")
    response = client.post("/api/admin/login", headers={"X-CSRF-Token": client.cookies.get("admin_csrf_token")},
                           json={"username": "root", "password": ADMIN_PASSWORD})
    assert response.status_code == 200, response.text
    return client, {"X-CSRF-Token": client.cookies.get("admin_csrf_token")}


def student_login(app, username: str = "learner") -> TestClient:
    client = TestClient(app)
    client.get("/api/auth/csrf")
    headers = {"X-CSRF-Token": client.cookies.get("csrf_token")}
    email = f"{username}@example.com"
    assert client.post("/api/auth/register", headers=headers,
                       json={"username": username, "email": email, "password": STUDENT_PASSWORD}).status_code == 202
    code = app.state.mailer.sent[-1]["code"]
    assert client.post("/api/auth/verify-email", headers=headers,
                       json={"email": email, "code": code}).status_code == 200
    assert client.post("/api/auth/login", headers=headers,
                       json={"identifier": username, "password": STUDENT_PASSWORD}).status_code == 200
    return client


def scsrf(client: TestClient) -> dict:
    """学员端 CSRF 头。登录后 cookie 会轮换，每次写操作前重新取。"""
    return {"X-CSRF-Token": client.cookies.get("csrf_token")}


def match(headers: dict, revision: int) -> dict:
    return {**headers, "If-Match": str(revision)}


# ---------- 题目载荷 ----------


def common(**overrides) -> dict:
    payload = {"difficulty": "入门", "source": "自命题", "structure": "单项知识点",
               "knowledge": [], "stage": [], "business": []}
    payload.update(overrides)
    return payload


def choice_payload() -> dict:
    # 选项内容避开 Markdown 语法字符：题库的提交校验会把 "#" 当标题、"--" 当分隔线
    # 剥成空字符串，然后判定"选项没填完整"。
    return {"type": "choice", "sub_type": None, "common": common(),
            "stem": "Python 中用于输出的内置函数是哪一个？", "analysis": "SECRETANALYSIS-choice",
            "options": [{"content": "input", "is_correct": False}, {"content": "print", "is_correct": True},
                        {"content": "len", "is_correct": False}, {"content": "type", "is_correct": False}],
            "blanks": [], "programming": None}


def multi_payload() -> dict:
    return {"type": "multi_choice", "sub_type": None, "common": common(),
            "stem": "以下哪些是 Python 内置类型？", "analysis": "SECRETANALYSIS-multi",
            "options": [{"content": "list", "is_correct": True}, {"content": "vector", "is_correct": False},
                        {"content": "dict", "is_correct": True}, {"content": "map", "is_correct": False}],
            "blanks": [], "programming": None}


def judge_payload() -> dict:
    return {"type": "judge", "sub_type": None, "common": common(),
            "stem": "Python 是解释型语言。", "analysis": "SECRETANALYSIS-judge",
            "options": [{"content": "对", "is_correct": True}, {"content": "错", "is_correct": False}],
            "blanks": [], "programming": None}


def fill_payload() -> dict:
    return {"type": "fill", "sub_type": None, "common": common(),
            "stem": "输出用 \\placeholder[b1]{} 函数。", "analysis": "SECRETANALYSIS-fill",
            "options": [], "blanks": [{"blank_index": 0, "blank_key": "b1", "answer": "SECRETFILL"}],
            "programming": None}


def programming_payload() -> dict:
    """Python 编程题：2 个样例 + 2 个隐藏测试点。隐藏点的内容埋了哨兵串。"""
    return {"type": "programming", "sub_type": "python", "common": common(difficulty="普及-", source="洛谷"),
            "stem": "输入两个整数，输出和。", "analysis": "SECRETANALYSIS-prog", "options": [], "blanks": [],
            "programming": {"title": "A+B", "pass_condition": "全测试点通过",
                            "input_format": "两个整数", "output_format": "一个整数", "hints": "无",
                            "samples": [{"input": "1 2", "output": "3"}, {"input": "3 4", "output": "7"}],
                            # 包一层 print 是为了让 FakeJudgeClient 判通过（它只看代码里有没有
                            # print/cout）——「全测试点通过」型的题现在必须先试跑通过才能提交审核。
                            # 哨兵串本身保留：作答期响应里出现它仍然算参考代码泄露。
                            "ref_code": {"cpp": "", "python": "print('SECRETREFCODE')"},
                            "manual_test_cases": [{"input": "SECRETIN-1", "output": "SECRETOUT-1"},
                                                  {"input": "SECRETIN-2", "output": "SECRETOUT-2"}]}}


def dry_run_until_done(client: TestClient, headers: dict, problem_id: int) -> None:
    """跑一次参考代码试跑并等到终态。

    「全测试点通过」型的题必须先有一次通过的完整试跑才能提交审核（见
    admin_questions._submission_error）——这一步不是测试的装饰，是真实流程的一环。
    """
    queued = client.post(f"/api/admin/problems/{problem_id}/dry-run", headers=headers,
                         json={"scope": "all"})
    assert queued.status_code == 201, queued.text
    deadline = time.time() + 15
    while time.time() < deadline:
        body = client.get(f"/api/admin/dry-runs/{queued.json()['id']}", headers=headers).json()
        if body.get("done"):
            assert body["status"] == "accepted", body
            return
        time.sleep(0.02)
    raise AssertionError("试跑超时未结束")


def approve(client: TestClient, headers: dict, payload: dict) -> str:
    created = client.post("/api/admin/problems", headers=headers, json=payload)
    assert created.status_code == 201, created.text
    problem = created.json()
    revision = problem["revision"]
    if (payload.get("programming") or {}).get("pass_condition") == "全测试点通过":
        dry_run_until_done(client, headers, problem["id"])
    assert client.post(f"/api/admin/problems/{problem['id']}/submit", headers=match(headers, revision)).status_code == 200
    assert client.post(f"/api/admin/problems/{problem['id']}/approve", headers=match(headers, revision + 1)).status_code == 200
    detail = client.get(f"/api/admin/problems/{problem['id']}", headers=headers).json()
    assert detail["problem_id_no"]
    return detail["problem_id_no"]


def link_payload(**overrides) -> dict:
    payload = {"name": "默认场次", "open_at": None, "close_at": None, "duration_minutes": 60,
               "late_start_policy": "truncate", "attempt_limit": 1, "score_policy": "best",
               "penalty_minutes": 0, "feedback_mode": "realtime", "show_analysis": "after_submit",
               "show_score": "immediate", "shuffle_questions": False, "shuffle_options": False,
               "notice": "", "notice_ack_required": False, "entry_open_minutes": 0,
               "remind_minutes": "", "warn_unanswered": True}
    payload.update(overrides)
    return payload


def build_exam(tmp_path: Path, *, link=None, paper=None, only=None, programming=None, fill=None):
    """建好一整套：五种题型各一道 → 一张卷 → 发布 → 一条链接 → 一个学员。"""
    app = build_app(tmp_path)
    admin, headers = admin_login(app)

    builders = {"choice": choice_payload, "multi_choice": multi_payload, "judge": judge_payload,
                "fill": fill_payload, "programming": programming_payload}
    if programming is not None:
        builders["programming"] = lambda: programming
    if fill is not None:
        builders["fill"] = lambda: fill
    wanted = only or list(builders)
    scores = {"choice": 10, "multi_choice": 10, "judge": 10, "fill": 10, "programming": 20}
    ids, questions = {}, []
    for order, key in enumerate(wanted):
        ids[key] = approve(admin, headers, builders[key]())
        questions.append({"problem_id_no": ids[key], "score": scores[key], "sort_order": order})

    paper_body = {"title": "闭环测试卷", "description": "", "paper_type": "测试卷", "subject": "python",
                  "ruleset": "IOI", "score_mode": "testcase", "partial_credit_multi": False,
                  "pass_score": None, "questions": questions}
    paper_body.update(paper or {})
    created = admin.post("/api/admin/papers", headers=headers, json=paper_body)
    assert created.status_code == 201, created.text
    paper_id = created.json()["id"]
    published = admin.post(f"/api/admin/papers/{paper_id}/publish", headers=match(headers, 1))
    assert published.status_code == 200, published.text

    made = admin.post(f"/api/admin/papers/{paper_id}/links", headers=headers, json=link_payload(**(link or {})))
    assert made.status_code == 201, made.text
    link_row = made.json()

    return SimpleNamespace(app=app, admin=admin, admin_headers=headers, student=student_login(app),
                           paper_id=paper_id, link_id=link_row["id"], token=_token_of(app, link_row["id"]),
                           ids=ids)


def _token_of(app, link_id: int) -> str:
    """链接列表出于安全只给掩码地址，测试直接从库里取完整 token。"""
    from app.models import ExamLink
    db = app.state.session_factory()
    try:
        return db.get(ExamLink, link_id).access_token
    finally:
        db.close()


def start(env) -> int:
    response = env.student.post(f"/api/exam/{env.token}/start", headers=scsrf(env.student))
    assert response.status_code == 201, response.text
    return response.json()["attempt_id"]


def save(env, attempt_id: int, problem_id_no: str, answer: dict):
    return env.student.put(f"/api/exam/attempts/{attempt_id}/answers", headers=scsrf(env.student),
                           json={"problem_id_no": problem_id_no, "answer": answer})


# ==================== 判题（异步）====================
#
# 判题是异步的：POST /code 只落一条 status="queued" 就返回，结果得轮询。
# 所以凡是"提交完直接断言 status/score"的地方，都要先等到终态；凡是"提交完就交卷"
# 的地方，也要先等——不等的话成绩还没写进去，总分会少算。


def post_code(env, attempt_id: int, **body):
    """裸提交，返回原始响应。要断言 4xx/429 的用例用这个。"""
    payload = {"problem_id_no": env.ids["programming"], "language": "python", "code": "print(1)"}
    payload.update(body)
    return env.student.post(f"/api/exam/attempts/{attempt_id}/code", headers=scsrf(env.student),
                            json=payload)


def wait_for_judge(env, attempt_id: int, submission_id: int, timeout: float = 15.0) -> dict:
    """轮询到判题终态，返回最终 payload。超时直接失败——卡住比慢更值得暴露。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        got = env.student.get(f"/api/exam/attempts/{attempt_id}/submissions/{submission_id}")
        assert got.status_code == 200, got.text
        body = got.json()
        if body.get("done"):
            return body
        time.sleep(0.02)
    raise AssertionError(f"判题超时未完成：submission={submission_id}")


def run_code(env, attempt_id: int, **body) -> dict:
    """提交并等到终态。同步时代那些断言可以照旧写，只是数据从这里拿。"""
    posted = post_code(env, attempt_id, **body)
    assert posted.status_code == 200, posted.text
    assert posted.json()["status"] == "queued", "提交应当立即返回排队态，而不是判完再返回"
    return wait_for_judge(env, attempt_id, posted.json()["id"])


def iso(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat()


# ==================== 入口与权限 ====================


def test_anonymous_visitor_is_401(tmp_path):
    env = build_exam(tmp_path)
    assert TestClient(env.app).get(f"/api/exam/{env.token}").status_code == 401


def test_unknown_disabled_and_unpublished_share_one_404_message(tmp_path):
    """三种失效原因必须给同一句话，区分开就是给爆破者送信息。"""
    env = build_exam(tmp_path)
    messages = {env.student.get("/api/exam/deadbeefdeadbeefdeadbeefdeadbeef").json()["detail"]}

    env.admin.post(f"/api/admin/links/{env.link_id}/disable", headers=match(env.admin_headers, 1))
    disabled = env.student.get(f"/api/exam/{env.token}")
    assert disabled.status_code == 404
    messages.add(disabled.json()["detail"])

    env.admin.post(f"/api/admin/links/{env.link_id}/enable", headers=match(env.admin_headers, 2))
    env.admin.post(f"/api/admin/papers/{env.paper_id}/archive", headers=match(env.admin_headers, 2))
    archived = env.student.get(f"/api/exam/{env.token}")
    assert archived.status_code == 404
    messages.add(archived.json()["detail"])

    assert len(messages) == 1


def test_entry_reports_paper_shape_without_questions(tmp_path):
    env = build_exam(tmp_path)
    body = env.student.get(f"/api/exam/{env.token}").json()
    assert body["paper"]["question_count"] == 5
    assert body["paper"]["total_score"] == 60
    assert body["paper"]["type_breakdown"]["programming"] == 1
    assert body["phase"] == "open" and body["can_start"] is True
    assert "questions" not in body  # 候考页不发题


def test_entry_blocked_before_open_and_after_close(tmp_path):
    later = datetime.now(UTC) + timedelta(hours=2)
    env = build_exam(tmp_path, link={"open_at": iso(later), "close_at": iso(later + timedelta(hours=1)),
                                     "duration_minutes": 30})
    body = env.student.get(f"/api/exam/{env.token}").json()
    assert body["phase"] == "waiting" and body["can_start"] is False
    assert "考试尚未开始" in body["blocked_reason"]
    denied = env.student.post(f"/api/exam/{env.token}/start", headers=scsrf(env.student))
    assert denied.status_code == 403
    db = env.app.state.session_factory()
    try:
        event = db.query(AuditEvent).filter_by(event_type="exam_entry_denied").one()
        assert (event.outcome, event.user_id) == ("failure", 1)
        assert (event.resource_type, event.resource_id) == ("exam_link", env.link_id)
        assert json.loads(event.summary_json) == {
            "source_type": "exam_link", "source_id": env.link_id,
            "reason": denied.json()["detail"],
        }
    finally:
        db.close()

    past = datetime.now(UTC) - timedelta(hours=2)
    closed = build_exam(tmp_path / "closed", link={"open_at": iso(past - timedelta(hours=1)),
                                                   "close_at": iso(past), "duration_minutes": 30})
    body = closed.student.get(f"/api/exam/{closed.token}").json()
    assert body["phase"] == "closed" and "考试已结束" in body["blocked_reason"]


def test_entry_open_window_before_start_time(tmp_path):
    soon = datetime.now(UTC) + timedelta(minutes=5)
    env = build_exam(tmp_path, link={"open_at": iso(soon), "close_at": iso(soon + timedelta(hours=2)),
                                     "duration_minutes": 30, "entry_open_minutes": 15})
    body = env.student.get(f"/api/exam/{env.token}").json()
    assert body["phase"] == "entry_open" and body["can_start"] is False


def test_attempt_limit_is_enforced_and_zero_means_unlimited(tmp_path):
    env = build_exam(tmp_path)
    attempt_id = start(env)
    env.student.post(f"/api/exam/attempts/{attempt_id}/submit", headers=scsrf(env.student))
    denied = env.student.post(f"/api/exam/{env.token}/start", headers=scsrf(env.student))
    assert denied.status_code == 403 and "已达最大作答次数" in denied.json()["detail"]

    unlimited = build_exam(tmp_path / "unlimited", link={"attempt_limit": 0})
    first = start(unlimited)
    unlimited.student.post(f"/api/exam/attempts/{first}/submit", headers=scsrf(unlimited.student))
    assert start(unlimited) != first


def test_ongoing_attempt_resumes_instead_of_consuming_a_new_one(tmp_path):
    """刷新页面不能吃掉一次作答机会——续做必须排在次数检查之前。"""
    env = build_exam(tmp_path)
    first = start(env)
    again = env.student.post(f"/api/exam/{env.token}/start", headers=scsrf(env.student))
    assert again.status_code == 201 and again.json()["attempt_id"] == first
    assert again.json()["resumed"] is True


def test_block_policy_refuses_late_start(tmp_path):
    close_at = datetime.now(UTC) + timedelta(minutes=10)
    env = build_exam(tmp_path, link={"open_at": iso(close_at - timedelta(hours=3)), "close_at": iso(close_at),
                                     "duration_minutes": 60, "late_start_policy": "block"})
    denied = env.student.post(f"/api/exam/{env.token}/start", headers=scsrf(env.student))
    assert denied.status_code == 403 and "剩余时间不足" in denied.json()["detail"]


def test_truncate_and_overrun_deadlines(tmp_path):
    close_at = datetime.now(UTC) + timedelta(minutes=10)
    window = {"open_at": iso(close_at - timedelta(hours=3)), "close_at": iso(close_at), "duration_minutes": 60}

    truncated = build_exam(tmp_path / "truncate", link={**window, "late_start_policy": "truncate"})
    deadline = truncated.student.post(f"/api/exam/{truncated.token}/start",
                                      headers=scsrf(truncated.student)).json()["deadline_at"]
    assert datetime.fromisoformat(deadline) <= close_at + timedelta(seconds=1)

    overrun = build_exam(tmp_path / "overrun", link={**window, "late_start_policy": "overrun"})
    deadline = overrun.student.post(f"/api/exam/{overrun.token}/start",
                                    headers=scsrf(overrun.student)).json()["deadline_at"]
    assert datetime.fromisoformat(deadline) > close_at


def test_other_students_attempt_is_404_not_403(tmp_path):
    env = build_exam(tmp_path)
    attempt_id = start(env)
    intruder = student_login(env.app, "intruder")
    assert intruder.get(f"/api/exam/attempts/{attempt_id}").status_code == 404


# ==================== 答案零泄露 ====================


SENTINELS = ("SECRETFILL", "SECRETANALYSIS", "SECRETIN", "SECRETOUT", "SECRETREFCODE")


def assert_clean(raw: str):
    for sentinel in SENTINELS:
        assert sentinel not in raw, f"作答期响应泄露了 {sentinel}"


def walk_keys(node, forbidden, path="$"):
    if isinstance(node, dict):
        for key, value in node.items():
            assert key not in forbidden, f"{path}.{key} 不该出现在作答期响应里"
            walk_keys(value, forbidden, f"{path}.{key}")
    elif isinstance(node, list):
        for index, item in enumerate(node):
            walk_keys(item, forbidden, f"{path}[{index}]")


def find_answer_keys(node, path="$"):
    """递归找出响应里所有「标准答案」字段，返回它们的路径。

    **不能用 walk_keys({"correct"}) 代替**：`correct` 这个键名在两种语义下都出现——
    判分明细里 `detail.correct` 是正确选项的 label 列表（是答案），而
    `detail.blanks[].correct` 是逐空对错的布尔值（是判定，结果页要用它标对错）。
    按键名一刀切会把后者一起判成泄露。所以这里按**值的形态**区分：
    列表值的 correct 才是答案表；`matched` 是填空命中的写法原文，一律算答案。

    这个函数存在的原因是一次真实的泄露：结果页的 `detail` 受 show_score 管、
    有意下发的 `correct` 受 show_analysis 管，两把闸门错位，于是配了
    show_analysis=never 的卷子照样从 detail 里把答案发了出去。当时的断言
    `all("correct" not in item ...)` 只查了顶层，嵌在 detail 里的那份查不到。
    """
    found = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "matched" or (key == "correct" and isinstance(value, list)):
                found.append(f"{path}.{key}")
            found += find_answer_keys(value, f"{path}.{key}")
    elif isinstance(node, list):
        for index, item in enumerate(node):
            found += find_answer_keys(item, f"{path}[{index}]")
    return found


def test_no_answer_leak_in_question_delivery(tmp_path):
    env = build_exam(tmp_path)
    attempt_id = start(env)
    response = env.student.get(f"/api/exam/attempts/{attempt_id}")
    assert response.status_code == 200
    assert_clean(response.text)
    # 递归查键名：只查顶层挡不住嵌在 options / programming 里的泄露。
    walk_keys(response.json(), {"is_correct", "ref_code", "analysis", "blanks"})


def test_hidden_test_cases_never_reach_the_student(tmp_path):
    env = build_exam(tmp_path)
    attempt_id = start(env)
    body = env.student.get(f"/api/exam/attempts/{attempt_id}").json()
    programming = next(item for item in body["questions"] if item["type"] == "programming")
    assert [sample["input"] for sample in programming["programming"]["samples"]] == ["1 2", "3 4"]

    ran = run_code(env, attempt_id, kind="submit")
    assert_clean(json.dumps(ran, ensure_ascii=False))  # 提交跑了隐藏点，但结果里不能带它们的内容


def test_fill_question_gives_keys_but_not_answers(tmp_path):
    env = build_exam(tmp_path)
    attempt_id = start(env)
    body = env.student.get(f"/api/exam/attempts/{attempt_id}").json()
    fill = next(item for item in body["questions"] if item["type"] == "fill")
    assert fill["blank_keys"] == ["b1"]
    assert "blanks" not in fill


def test_show_score_never_hides_the_key_entirely(tmp_path):
    """裁剪必须是「键不出现」——给 null 等于告诉前端这里本来有东西。"""
    env = build_exam(tmp_path, link={"show_score": "never"})
    attempt_id = start(env)
    env.student.post(f"/api/exam/attempts/{attempt_id}/submit", headers=scsrf(env.student))
    result = env.student.get(f"/api/exam/attempts/{attempt_id}/result").json()
    assert "total_score" not in result["attempt"]
    assert all("score" not in item for item in result["questions"])
    assert result["show_score"] is False
    assert result["leaderboard_enabled"] is True


def test_show_score_after_close_flips_at_the_boundary(tmp_path):
    close_at = datetime.now(UTC) + timedelta(hours=1)
    env = build_exam(tmp_path, link={"open_at": iso(close_at - timedelta(hours=2)), "close_at": iso(close_at),
                                     "duration_minutes": 30, "show_score": "after_close"})
    attempt_id = start(env)
    env.student.post(f"/api/exam/attempts/{attempt_id}/submit", headers=scsrf(env.student))
    assert "total_score" not in env.student.get(f"/api/exam/attempts/{attempt_id}/result").json()["attempt"]

    _shift_close(env, close_at - timedelta(hours=2))
    assert "total_score" in env.student.get(f"/api/exam/attempts/{attempt_id}/result").json()["attempt"]


def _shift_close(env, moment: datetime):
    """直接改库里的 close_at：绕过接口是有意的，接口不允许把时间改到过去。"""
    from app.models import ExamLink
    db = env.app.state.session_factory()
    try:
        link = db.get(ExamLink, env.link_id)
        link.close_at = moment
        db.commit()
    finally:
        db.close()


def test_show_analysis_never_withholds_analysis_and_answers(tmp_path):
    env = build_exam(tmp_path, link={"show_analysis": "never"})
    attempt_id = start(env)
    env.student.post(f"/api/exam/attempts/{attempt_id}/submit", headers=scsrf(env.student))
    result = env.student.get(f"/api/exam/attempts/{attempt_id}/result")
    assert_clean(result.text)
    assert all("correct" not in item for item in result.json()["questions"])
    # 顶层没有还不够：答案曾经从 questions[].detail.correct 整份漏出去（见 find_answer_keys）
    assert find_answer_keys(result.json()) == []


def test_result_detail_never_carries_answer_keys(tmp_path):
    """判分明细不得携带标准答案——哪怕成绩是公开的。

    这是一条**独立于 show_analysis** 的红线。detail 受 show_score 管，正确答案受
    show_analysis 管；只要 detail 里带着答案，show_score=immediate +
    show_analysis=never 的卷子就等于把答案公开了。配上不限次数（attempt_limit=0），
    学员交一次卷读出全部客观题答案，第二次直接满分。
    """
    env = build_exam(tmp_path, link={"show_score": "immediate", "show_analysis": "never",
                                     "attempt_limit": 0},
                     only=["choice", "multi_choice", "judge", "fill"])
    attempt_id = start(env)
    # 全部答错：答错时 detail 里除了"你选了什么"不该再有别的
    save(env, attempt_id, env.ids["choice"], {"type": "choice", "picked": "A"})
    save(env, attempt_id, env.ids["multi_choice"], {"type": "multi_choice", "picked": ["B"]})
    save(env, attempt_id, env.ids["judge"], {"type": "judge", "picked": "B"})
    env.student.post(f"/api/exam/attempts/{attempt_id}/submit", headers=scsrf(env.student))

    body = env.student.get(f"/api/exam/attempts/{attempt_id}/result").json()
    leaked = find_answer_keys(body)
    assert leaked == [], f"结果页泄露了标准答案：{leaked}"
    # 成绩本身照给（这条红线不该把 show_score 一起关掉）
    choice = next(item for item in body["questions"] if item.get("type") == "choice")
    assert choice["score"] == 0 and choice["is_correct"] is False
    assert choice["detail"]["picked"] == "A"


def test_result_keeps_per_blank_verdict_after_redaction(tmp_path):
    """裁掉答案不能连逐空对错一起裁掉——结果页靠 detail.blanks[].correct 标对错。"""
    env = build_exam(tmp_path, link={"show_score": "immediate", "show_analysis": "never"},
                     only=["fill"])
    attempt_id = start(env)
    save(env, attempt_id, env.ids["fill"],
         {"type": "fill", "blanks": {"b1": "SECRETFILL"}})  # 答对
    env.student.post(f"/api/exam/attempts/{attempt_id}/submit", headers=scsrf(env.student))

    body = env.student.get(f"/api/exam/attempts/{attempt_id}/result").json()
    fill = next(item for item in body["questions"] if item.get("type") == "fill")
    blanks = fill["detail"]["blanks"]
    assert [b["correct"] for b in blanks] == [True], "逐空对错被误删了"
    # 但答对时命中的那条标准答案原文（matched）必须裁掉。
    # 这里不能用 assert_clean：学员自己填对了，SECRETFILL 本来就会在 answer 里回显。
    assert find_answer_keys(body) == []


def test_show_analysis_after_submit_reveals_analysis_and_answers(tmp_path):
    env = build_exam(tmp_path, link={"show_analysis": "after_submit"})
    attempt_id = start(env)
    env.student.post(f"/api/exam/attempts/{attempt_id}/submit", headers=scsrf(env.student))
    result = env.student.get(f"/api/exam/attempts/{attempt_id}/result").json()
    choice = next(item for item in result["questions"] if item.get("type") == "choice")
    assert choice["analysis"] == "SECRETANALYSIS-choice"
    assert choice["correct"]["labels"] == ["B"]


# ==================== 作答与判分 ====================


def test_save_is_idempotent_and_keeps_one_row(tmp_path):
    env = build_exam(tmp_path)
    attempt_id = start(env)
    answer = {"type": "choice", "picked": "B"}
    assert save(env, attempt_id, env.ids["choice"], answer).status_code == 200
    assert save(env, attempt_id, env.ids["choice"], answer).status_code == 200

    from app.models import AttemptAnswer
    db = env.app.state.session_factory()
    try:
        rows = db.query(AttemptAnswer).filter_by(attempt_id=attempt_id).all()
        assert len([row for row in rows if row.problem_id_no == env.ids["choice"]]) == 1
    finally:
        db.close()


def test_save_rejects_answer_type_mismatch(tmp_path):
    env = build_exam(tmp_path)
    attempt_id = start(env)
    bad = save(env, attempt_id, env.ids["choice"], {"type": "fill", "blanks": {"b1": "x"}})
    assert bad.status_code == 422


def test_programming_draft_is_restored_without_a_judge_submission(tmp_path):
    env = build_exam(tmp_path, only=["programming"])
    attempt_id = start(env)
    draft = "#include <iostream>\nint main() { return 0; }"
    response = save(
        env,
        attempt_id,
        env.ids["programming"],
        {"type": "programming", "language": "cpp", "draft_code": draft},
    )
    assert response.status_code == 200, response.text

    payload = env.student.get(f"/api/exam/attempts/{attempt_id}").json()
    question = payload["questions"][0]
    assert question["answer"]["draft_code"] == draft
    assert question["last_code"] == draft


def test_save_rejects_question_outside_the_paper(tmp_path):
    env = build_exam(tmp_path)
    attempt_id = start(env)
    assert save(env, attempt_id, "Q999999", {"type": "choice", "picked": "A"}).status_code == 404


def test_full_marks_across_every_objective_type(tmp_path):
    env = build_exam(tmp_path)
    attempt_id = start(env)
    save(env, attempt_id, env.ids["choice"], {"type": "choice", "picked": "B"})
    save(env, attempt_id, env.ids["multi_choice"], {"type": "multi_choice", "picked": ["A", "C"]})
    save(env, attempt_id, env.ids["judge"], {"type": "judge", "picked": "A"})
    save(env, attempt_id, env.ids["fill"], {"type": "fill", "blanks": {"b1": "  secretfill "}})  # 规范化后仍算对
    run_code(env, attempt_id, kind="submit")  # 判完再交卷，否则成绩还没写进去
    env.student.post(f"/api/exam/attempts/{attempt_id}/submit", headers=scsrf(env.student))

    result = env.student.get(f"/api/exam/attempts/{attempt_id}/result").json()
    assert result["attempt"]["total_score"] == 60


def test_fill_accepts_alternative_spelling_end_to_end(tmp_path):
    """一个空多种写法：学员写次要写法照样满分，而「正确答案」仍只展示标准答案。"""
    payload = fill_payload()
    payload["blanks"] = [{"blank_index": 0, "blank_key": "b1", "answer": "SECRETFILL",
                          "alternatives": ["SECRETFILL-ALT", "另一种写法"]}]
    env = build_exam(tmp_path, only=["fill"], fill=payload)
    attempt_id = start(env)
    save(env, attempt_id, env.ids["fill"], {"type": "fill", "blanks": {"b1": " 另一种写法 "}})
    env.student.post(f"/api/exam/attempts/{attempt_id}/submit", headers=scsrf(env.student))

    result = env.student.get(f"/api/exam/attempts/{attempt_id}/result").json()
    assert result["attempt"]["total_score"] == 10
    question = result["questions"][0]
    assert question["score"] == 10 and question["is_correct"] is True
    # 展示给学员的正确答案永远是标准答案那一条，不是一串或关系
    assert question["correct"]["blanks"] == [{"blank_key": "b1", "answer": "SECRETFILL"}]


def test_fill_alternatives_round_trip_through_admin_api(tmp_path):
    """多写法能存能回填；与标准答案重复的那条会被丢掉，免得录题人以为自己多设了一种。"""
    env = build_exam(tmp_path, only=["choice"])  # 只借一个建好的 app
    payload = fill_payload()
    payload["blanks"] = [{"blank_index": 0, "blank_key": "b1", "answer": "  0.5  ",
                          "alternatives": ["1/2", "1/2", "0.5", " 二分之一 ", ""]}]
    created = env.admin.post("/api/admin/problems", headers=env.admin_headers, json=payload)
    assert created.status_code == 201, created.text
    blank = created.json()["blanks"][0]
    assert blank["answer"] == "0.5"
    # 去空、去重、去掉与标准答案相同的那条，顺序保持录入顺序
    assert blank["alternatives"] == ["1/2", "二分之一"]

    # 改题时清空多写法 → 回到只认标准答案
    payload["blanks"][0]["alternatives"] = []
    updated = env.admin.put(f"/api/admin/problems/{created.json()['id']}",
                            headers=match(env.admin_headers, 1), json=payload)
    assert updated.status_code == 200, updated.text
    assert updated.json()["blanks"][0]["alternatives"] == []


def test_fill_alternatives_reject_oversized_list(tmp_path):
    """一个空堆 20 条以上同义词说明题面问得太开放，该改题面而不是继续堆。"""
    env = build_exam(tmp_path, only=["choice"])
    payload = fill_payload()
    payload["blanks"] = [{"blank_index": 0, "blank_key": "b1", "answer": "x",
                          "alternatives": [f"w{index}" for index in range(21)]}]
    response = env.admin.post("/api/admin/problems", headers=env.admin_headers, json=payload)
    assert response.status_code == 422, response.text


def test_zero_marks_when_nothing_answered(tmp_path):
    env = build_exam(tmp_path)
    attempt_id = start(env)
    env.student.post(f"/api/exam/attempts/{attempt_id}/submit", headers=scsrf(env.student))
    assert env.student.get(f"/api/exam/attempts/{attempt_id}/result").json()["attempt"]["total_score"] == 0


def test_multi_choice_partial_credit_switch(tmp_path):
    strict = build_exam(tmp_path / "strict", only=["multi_choice"])
    attempt_id = start(strict)
    save(strict, attempt_id, strict.ids["multi_choice"], {"type": "multi_choice", "picked": ["A"]})
    strict.student.post(f"/api/exam/attempts/{attempt_id}/submit", headers=scsrf(strict.student))
    assert strict.student.get(f"/api/exam/attempts/{attempt_id}/result").json()["attempt"]["total_score"] == 0

    lenient = build_exam(tmp_path / "lenient", only=["multi_choice"], paper={"partial_credit_multi": True})
    attempt_id = start(lenient)
    save(lenient, attempt_id, lenient.ids["multi_choice"], {"type": "multi_choice", "picked": ["A"]})
    lenient.student.post(f"/api/exam/attempts/{attempt_id}/submit", headers=scsrf(lenient.student))
    assert lenient.student.get(f"/api/exam/attempts/{attempt_id}/result").json()["attempt"]["total_score"] == 5


def test_programming_partial_score_by_testcase_ratio(tmp_path):
    """4 个测试点过 1 个（FakeJudgeClient 的 __WA__ 规则），20 分的题拿 5 分。"""
    env = build_exam(tmp_path, only=["programming"])
    attempt_id = start(env)
    ran = run_code(env, attempt_id, code="print(1)  # __WA__", kind="submit")
    assert ran["score"] == 5
    env.student.post(f"/api/exam/attempts/{attempt_id}/submit", headers=scsrf(env.student))
    assert env.student.get(f"/api/exam/attempts/{attempt_id}/result").json()["attempt"]["total_score"] == 5


def test_all_or_nothing_mode_gives_zero_for_partial(tmp_path):
    env = build_exam(tmp_path, only=["programming"], paper={"score_mode": "all_or_nothing"})
    attempt_id = start(env)
    assert run_code(env, attempt_id, code="print(1)  # __WA__", kind="submit")["score"] == 0


def test_trial_run_only_uses_samples_and_scores_nothing(tmp_path):
    env = build_exam(tmp_path, only=["programming"])
    attempt_id = start(env)
    ran = run_code(env, attempt_id, kind="trial")
    assert len(ran["cases"]) == 2  # 只有两个样例
    assert "score" not in ran
    env.student.post(f"/api/exam/attempts/{attempt_id}/submit", headers=scsrf(env.student))
    assert env.student.get(f"/api/exam/attempts/{attempt_id}/result").json()["attempt"]["total_score"] == 0


def test_compile_only_feedback_hides_case_results(tmp_path):
    env = build_exam(tmp_path, only=["programming"], link={"feedback_mode": "compile_only"})
    attempt_id = start(env)
    assert "cases" not in run_code(env, attempt_id, kind="submit")


def test_empty_code_is_a_compile_error(tmp_path):
    env = build_exam(tmp_path, only=["programming"])
    attempt_id = start(env)
    ran = run_code(env, attempt_id, code="   ", kind="submit")
    assert ran["status"] == "compile_error" and ran["score"] == 0


def test_judge_failure_is_not_scored_as_zero(tmp_path):
    """判题服务故障不能算学员 0 分：该题 score 留 null 且不计入总分。"""
    env = build_exam(tmp_path, only=["choice", "programming"])
    attempt_id = start(env)
    save(env, attempt_id, env.ids["choice"], {"type": "choice", "picked": "B"})

    class BrokenJudge:
        def judge(self, **_kwargs):
            from app.judge import JudgeUnavailable
            raise JudgeUnavailable("sandbox down")

    env.app.state.judge = BrokenJudge()
    # 异步之后，沙箱故障不再表现为 POST 的 503——那一刻只是排上队而已。
    # 学员是在轮询里看到 judge_failed 的，前端必须认这个终态而不是等 HTTP 错误。
    broken = run_code(env, attempt_id, kind="submit")
    assert broken["status"] == "judge_failed"
    assert "score" not in broken or broken["score"] is None

    env.student.post(f"/api/exam/attempts/{attempt_id}/submit", headers=scsrf(env.student))
    result = env.student.get(f"/api/exam/attempts/{attempt_id}/result").json()
    assert result["attempt"]["total_score"] == 10  # 只有选择题的分，编程题没被算成 0
    programming = next(item for item in result["questions"] if item.get("type") == "programming")
    assert programming["judge_status"] == "failed" and programming["score"] is None


# ==================== 自测（trial + custom_input）====================


def test_custom_input_runs_once_and_scores_nothing(tmp_path):
    """自测：只跑学员给的那一条输入，不写成绩。"""
    env = build_exam(tmp_path, only=["programming"])
    attempt_id = start(env)
    body = run_code(env, attempt_id, kind="trial", custom_input="SELFTEST-STDIN")
    # 样例有两条，自测只该有一条——说明走的是 custom_input 而不是库里的样例
    assert len(body["cases"]) == 1
    case = body["cases"][0]
    assert case["input"] == "SELFTEST-STDIN"
    assert case["actual"] is not None  # 自测的意义就是看得到输出
    assert "score" not in body

    # 没作答过就交卷，编程题必须还是 0 分：自测不该被当成一次提交
    env.student.post(f"/api/exam/attempts/{attempt_id}/submit", headers=scsrf(env.student))
    assert env.student.get(f"/api/exam/attempts/{attempt_id}/result").json()["attempt"]["total_score"] == 0


def test_empty_custom_input_is_a_valid_run(tmp_path):
    """空串是「用空输入跑一次」，不是「没给自定义输入」，更不该 422。"""
    env = build_exam(tmp_path, only=["programming"])
    attempt_id = start(env)
    ran = run_code(env, attempt_id, kind="trial", custom_input="")
    assert len(ran["cases"]) == 1 and ran["cases"][0]["input"] == ""


def test_custom_input_does_not_disturb_a_later_submit(tmp_path):
    """先自测再正式提交，成绩按全部测试点算，不受自测那次影响。"""
    env = build_exam(tmp_path, only=["programming"])
    attempt_id = start(env)
    run_code(env, attempt_id, kind="trial", custom_input="noise")
    submitted = run_code(env, attempt_id, kind="submit")
    assert submitted["score"] == 20  # 满分，与没自测过时一致
    assert len(submitted["cases"]) == 4  # 2 样例 + 2 隐藏点，自测那条没混进来

    env.student.post(f"/api/exam/attempts/{attempt_id}/submit", headers=scsrf(env.student))
    assert env.student.get(f"/api/exam/attempts/{attempt_id}/result").json()["attempt"]["total_score"] == 20


def test_submit_ignores_custom_input(tmp_path):
    """提交判题携带 custom_input 时忽略它——前端切着页签提交是常事，不能 422。"""
    env = build_exam(tmp_path, only=["programming"])
    attempt_id = start(env)
    submitted = run_code(env, attempt_id, kind="submit", custom_input="should-be-ignored")
    assert len(submitted["cases"]) == 4 and submitted["score"] == 20
    assert_clean(json.dumps(submitted, ensure_ascii=False))


# ==================== 异步判题 ====================


def test_submit_returns_immediately_without_judging(tmp_path):
    """提交只落一条排队记录就返回——判题不能再占着请求和那条 DB 连接。"""
    env = build_exam(tmp_path, only=["programming"])
    attempt_id = start(env)
    posted = post_code(env, attempt_id, kind="submit")
    assert posted.status_code == 200
    body = posted.json()
    assert body["status"] == "queued"
    assert "cases" not in body and "score" not in body  # 还没判，当然什么都没有
    assert body["queue_position"] >= 0

    final = wait_for_judge(env, attempt_id, body["id"])
    assert final["status"] == "accepted" and final["score"] == 20


def test_poll_reports_done_only_at_a_terminal_status(tmp_path):
    """done 是前端停止轮询的唯一依据，不能在中间态就为真。"""
    env = build_exam(tmp_path, only=["programming"])
    attempt_id = start(env)
    sid = post_code(env, attempt_id, kind="submit").json()["id"]
    final = wait_for_judge(env, attempt_id, sid)
    assert final["done"] is True
    assert final["status"] in {"accepted", "wrong_answer", "compile_error",
                               "runtime_error", "time_limit", "memory_limit", "judge_failed"}


def test_polling_another_students_submission_is_404(tmp_path):
    env = build_exam(tmp_path, only=["programming"])
    attempt_id = start(env)
    sid = post_code(env, attempt_id, kind="submit").json()["id"]
    wait_for_judge(env, attempt_id, sid)
    intruder = student_login(env.app, username="peeper")
    assert intruder.get(f"/api/exam/attempts/{attempt_id}/submissions/{sid}").status_code == 404


def test_concurrent_submits_all_get_judged(tmp_path):
    """并发提交必须全部判完——线程池是并发闸，不是丢件箱。"""
    env = build_exam(tmp_path, only=["programming"])
    attempt_id = start(env)
    ids = [post_code(env, attempt_id, kind="trial").json()["id"] for _ in range(12)]
    finals = [wait_for_judge(env, attempt_id, sid, timeout=30.0) for sid in ids]
    assert all(item["status"] == "accepted" for item in finals)
    assert len({item["id"] for item in finals}) == 12  # 12 条互不相同，没有串号


def test_queue_full_is_429_not_a_hang(tmp_path):
    """排队满了要当场 429，不能让请求挂着——挂着只会把等待变成超时。"""
    env = build_app(tmp_path, judge_queue_max=1)
    # 直接对着 runner 灌，构造"队列已满"比真发 500 个请求便宜得多
    from app.judge.runner import JudgeQueueFull, JudgeTask
    runner = env.state.judge_runner
    runner.enqueue(JudgeTask(submission_id=-1))
    try:
        runner.enqueue(JudgeTask(submission_id=-2))
        raise AssertionError("队列满了却没拦住")
    except JudgeQueueFull:
        pass


def test_stale_judging_is_failed_not_zero(tmp_path):
    """进程重启会丢掉在途判题。收尾必须是 judge_failed，成绩留 null——
    系统的锅算成学员 0 分是验收手册四级明令禁止的。"""
    from datetime import timedelta as _td

    from app.models import CodeSubmission
    from app.routers.exam import sweep_stale_judgings

    env = build_exam(tmp_path, only=["choice", "programming"])
    attempt_id = start(env)
    save(env, attempt_id, env.ids["choice"], {"type": "choice", "picked": "B"})
    sid = post_code(env, attempt_id, kind="submit").json()["id"]
    wait_for_judge(env, attempt_id, sid)

    # 手工把它打回"卡在 judging 且很久以前创建"的样子
    db = env.app.state.session_factory()
    try:
        row = db.get(CodeSubmission, sid)
        row.status, row.score = "judging", None
        row.created_at = row.created_at - _td(hours=2)
        db.commit()
    finally:
        db.close()

    assert sweep_stale_judgings(env.app.state.session_factory, 600) == 1
    polled = env.student.get(f"/api/exam/attempts/{attempt_id}/submissions/{sid}").json()
    assert polled["status"] == "judge_failed" and polled["done"] is True

    env.student.post(f"/api/exam/attempts/{attempt_id}/submit", headers=scsrf(env.student))
    result = env.student.get(f"/api/exam/attempts/{attempt_id}/result").json()
    assert result["attempt"]["total_score"] == 10  # 只有选择题的分
    programming = next(item for item in result["questions"] if item.get("type") == "programming")
    assert programming["judge_status"] == "failed" and programming["score"] is None


def test_queue_full_marks_judge_failed_not_zero(tmp_path):
    """排队已满回 429，成绩要落 judge_failed（null）而不是留成未作答的 0 分。

    与 JudgeUnavailable / 僵尸清理同一口径：排不上队是系统的锅，不是学员答错。
    """
    from app.judge.runner import JudgeQueueFull

    env = build_exam(tmp_path, only=["choice", "programming"])
    attempt_id = start(env)
    save(env, attempt_id, env.ids["choice"], {"type": "choice", "picked": "B"})

    class FullRunner:
        def enqueue(self, task):
            raise JudgeQueueFull("满了")

        def position(self, submission_id):
            return None

    env.app.state.judge_runner = FullRunner()
    assert post_code(env, attempt_id, kind="submit").status_code == 429

    env.student.post(f"/api/exam/attempts/{attempt_id}/submit", headers=scsrf(env.student))
    result = env.student.get(f"/api/exam/attempts/{attempt_id}/result").json()
    programming = next(item for item in result["questions"] if item.get("type") == "programming")
    assert programming["judge_status"] == "failed" and programming["score"] is None
    assert result["attempt"]["total_score"] == 10  # 只有选择题的分，编程题不按 0 计


def test_judging_after_seal_keeps_the_record_but_not_the_score(tmp_path):
    """判完时学员已经交卷：提交记录照留（审计），但不许改已封存的成绩。"""
    env = build_exam(tmp_path, only=["programming"])
    attempt_id = start(env)
    # 先交卷封卷，再手工塞一条 queued 让 worker 去判
    env.student.post(f"/api/exam/attempts/{attempt_id}/submit", headers=scsrf(env.student))
    before = env.student.get(f"/api/exam/attempts/{attempt_id}/result").json()["attempt"]["total_score"]

    from app.judge.runner import JudgeTask
    from app.models import CodeSubmission
    from app.routers.exam import judge_submission

    db = env.app.state.session_factory()
    try:
        row = CodeSubmission(attempt_id=attempt_id, problem_id_no=env.ids["programming"],
                             language="python", code="print(1)", kind="submit", status="queued")
        db.add(row)
        db.commit()
        sid = row.id
    finally:
        db.close()
    judge_submission(env.app.state.session_factory, env.app.state.judge, JudgeTask(submission_id=sid),
                     env.app.state.settings)

    db = env.app.state.session_factory()
    try:
        assert db.get(CodeSubmission, sid).status == "accepted"  # 记录留下了
    finally:
        db.close()
    after = env.student.get(f"/api/exam/attempts/{attempt_id}/result").json()["attempt"]["total_score"]
    assert after == before == 0  # 封存的成绩没被改动


# ==================== 提交记录 ====================


def submissions(env, attempt_id: int, client=None):
    return (client or env.student).get(
        f"/api/exam/attempts/{attempt_id}/submissions",
        params={"problem_id_no": env.ids["programming"]},
    )


def test_submissions_list_only_counts_real_submits(tmp_path):
    """试跑与自测是草稿，不进提交记录——否则「成绩以最后一次提交为准」会被误读。"""
    env = build_exam(tmp_path, only=["programming"])
    attempt_id = start(env)
    run_code(env, attempt_id, kind="trial")
    run_code(env, attempt_id, kind="trial", custom_input="x")
    run_code(env, attempt_id, kind="submit", code="__WA__\nprint(1)")
    run_code(env, attempt_id, kind="submit")

    listed = submissions(env, attempt_id)
    assert listed.status_code == 200
    rows = listed.json()["submissions"]
    assert len(rows) == 2
    assert [row["kind"] for row in rows] == ["submit", "submit"]
    assert rows[0]["id"] < rows[1]["id"]  # 按时间正序，前端自己决定怎么排
    assert rows[1]["score"] == 20
    # 自己的代码可以下发，答案资产不行
    assert rows[1]["code"] == "print(1)"
    assert_clean(listed.text)


def test_submissions_respect_feedback_mode(tmp_path):
    """换个接口就能绕过裁剪等于没裁：compile_only 下这里同样不给逐点结果。"""
    env = build_exam(tmp_path, only=["programming"], link={"feedback_mode": "compile_only"})
    attempt_id = start(env)
    run_code(env, attempt_id, kind="submit")
    rows = submissions(env, attempt_id).json()["submissions"]
    assert len(rows) == 1 and "cases" not in rows[0]
    assert "compile_message" in rows[0]  # 编译信息照给


def test_submissions_of_another_student_is_404(tmp_path):
    env = build_exam(tmp_path, only=["programming"])
    attempt_id = start(env)
    run_code(env, attempt_id, kind="submit")
    intruder = student_login(env.app, username="stranger")
    assert submissions(env, attempt_id, client=intruder).status_code == 404


def test_pass_condition_is_delivered_to_the_student(tmp_path):
    """满分条件是计分规则不是判分资产，学员必须看得到。"""
    env = build_exam(tmp_path, only=["programming"])
    attempt_id = start(env)
    body = env.student.get(f"/api/exam/attempts/{attempt_id}").json()
    programming = next(item for item in body["questions"] if item["type"] == "programming")
    assert programming["programming"]["pass_condition"] == "全测试点通过"


# ==================== 洗牌 ====================


def test_shuffle_is_deterministic_across_requests(tmp_path):
    env = build_exam(tmp_path, link={"shuffle_questions": True, "shuffle_options": True})
    attempt_id = start(env)
    first = env.student.get(f"/api/exam/attempts/{attempt_id}").json()["questions"]
    second = env.student.get(f"/api/exam/attempts/{attempt_id}").json()["questions"]
    assert [item["problem_id_no"] for item in first] == [item["problem_id_no"] for item in second]

    def labels(body):
        return [option["label"] for item in body if item.get("options") for option in item["options"]]

    assert labels(first) == labels(second)


def test_judge_options_are_never_shuffled(tmp_path):
    """「正确/错误」换位置只会让人以为自己看错了。"""
    env = build_exam(tmp_path, link={"shuffle_options": True})
    attempt_id = start(env)
    body = env.student.get(f"/api/exam/attempts/{attempt_id}").json()
    judge = next(item for item in body["questions"] if item["type"] == "judge")
    assert [option["label"] for option in judge["options"]] == ["A", "B"]
    assert judge["options"][0]["content"] == "对"


def test_scoring_follows_labels_after_option_shuffle(tmp_path):
    """洗牌后学员回传的仍是原始 label——这条错了多选判分全盘皆错。"""
    env = build_exam(tmp_path, only=["choice"], link={"shuffle_options": True})
    attempt_id = start(env)
    # 洗牌种子是随机的，4 个选项有 1/24 的概率洗成原序。撞上就换个种子重来——
    # 这条断言要的是"确实洗过了"，不是"运气好"，靠概率过测试等于每 24 次红一次。
    for _ in range(20):
        body = env.student.get(f"/api/exam/attempts/{attempt_id}").json()
        options = body["questions"][0]["options"]
        if [option["label"] for option in options] != ["A", "B", "C", "D"]:
            break
        db = env.app.state.session_factory()
        try:
            attempt = db.get(PaperAttempt, attempt_id)
            attempt.shuffle_seed += 1
            db.commit()
        finally:
            db.close()
    else:
        raise AssertionError("换了 20 个种子都没洗动，洗牌多半没生效")
    right = next(option["label"] for option in options if option["content"] == "print")
    save(env, attempt_id, env.ids["choice"], {"type": "choice", "picked": right})
    env.student.post(f"/api/exam/attempts/{attempt_id}/submit", headers=scsrf(env.student))
    assert env.student.get(f"/api/exam/attempts/{attempt_id}/result").json()["attempt"]["total_score"] == 10


# ==================== 超时与交卷 ====================


def _expire(env, attempt_id: int):
    db = env.app.state.session_factory()
    try:
        attempt = db.get(PaperAttempt, attempt_id)
        attempt.deadline_at = datetime.now(UTC) - timedelta(minutes=1)
        db.commit()
    finally:
        db.close()


def test_expired_attempt_is_sealed_on_next_request(tmp_path):
    env = build_exam(tmp_path)
    attempt_id = start(env)
    save(env, attempt_id, env.ids["choice"], {"type": "choice", "picked": "B"})
    _expire(env, attempt_id)

    assert env.student.get(f"/api/exam/attempts/{attempt_id}").status_code == 409
    result = env.student.get(f"/api/exam/attempts/{attempt_id}/result").json()
    assert result["attempt"]["submit_kind"] == "auto_timeout"
    assert result["attempt"]["total_score"] == 10  # 超时前存下的答案照样判分


def test_saving_after_deadline_is_rejected(tmp_path):
    env = build_exam(tmp_path)
    attempt_id = start(env)
    _expire(env, attempt_id)
    assert save(env, attempt_id, env.ids["choice"], {"type": "choice", "picked": "B"}).status_code == 409


def test_resubmit_is_idempotent_and_keeps_the_score(tmp_path):
    env = build_exam(tmp_path)
    attempt_id = start(env)
    save(env, attempt_id, env.ids["choice"], {"type": "choice", "picked": "B"})
    assert env.student.post(f"/api/exam/attempts/{attempt_id}/submit", headers=scsrf(env.student)).status_code == 200
    again = env.student.post(f"/api/exam/attempts/{attempt_id}/submit", headers=scsrf(env.student))
    assert again.status_code == 409
    assert env.student.get(f"/api/exam/attempts/{attempt_id}/result").json()["attempt"]["total_score"] == 10


def test_result_before_submit_is_409(tmp_path):
    env = build_exam(tmp_path)
    attempt_id = start(env)
    assert env.student.get(f"/api/exam/attempts/{attempt_id}/result").status_code == 409


def test_duration_seconds_is_recorded(tmp_path):
    env = build_exam(tmp_path)
    attempt_id = start(env)
    env.student.post(f"/api/exam/attempts/{attempt_id}/submit", headers=scsrf(env.student))
    result = env.student.get(f"/api/exam/attempts/{attempt_id}/result").json()
    assert result["attempt"]["duration_seconds"] >= 0


# ==================== 与后台的联动 ====================


def test_sweeper_closes_abandoned_attempts(tmp_path):
    """学员关掉浏览器就再也不发请求了，惰性封卷收不了——这是兜底脚本存在的理由。"""
    from app.close_expired_attempts import seal_expired

    env = build_exam(tmp_path)
    attempt_id = start(env)
    save(env, attempt_id, env.ids["choice"], {"type": "choice", "picked": "B"})
    _expire(env, attempt_id)

    db = env.app.state.session_factory()
    try:
        assert seal_expired(db, dry_run=True, verbose=False) == 1
        assert db.get(PaperAttempt, attempt_id).status == "ongoing"  # dry-run 不写库
        assert seal_expired(db, verbose=False) == 1
        sealed = db.get(PaperAttempt, attempt_id)
        assert sealed.status == "submitted" and sealed.submit_kind == "auto_close"
        assert sealed.total_score == 10  # 收卷时照常判分
        assert seal_expired(db, verbose=False) == 0  # 幂等：再跑一次没有可收的了
    finally:
        db.close()


def test_paper_with_attempts_cannot_be_deleted(tmp_path):
    """回填 _paper_delete_blocker：删卷会打穿已有的作答记录。"""
    env = build_exam(tmp_path)
    start(env)
    # 发布已经把 revision 推到 2，归档后是 3。
    assert env.admin.post(f"/api/admin/papers/{env.paper_id}/archive",
                          headers=match(env.admin_headers, 2)).status_code == 200
    denied = env.admin.delete(f"/api/admin/papers/{env.paper_id}", headers=match(env.admin_headers, 3))
    assert denied.status_code == 409 and "作答" in denied.json()["detail"]


def test_link_with_attempts_cannot_be_deleted(tmp_path):
    """删链接是唯一能绕过删卷保护销毁成绩的路径（exam_link_id 是 CASCADE），必须同口径拦住。"""
    env = build_exam(tmp_path)
    start(env)
    link = env.admin.get(f"/api/admin/papers/{env.paper_id}", headers=env.admin_headers).json()["links"][0]
    denied = env.admin.delete(f"/api/admin/links/{env.link_id}",
                              headers=match(env.admin_headers, link["revision"]))
    assert denied.status_code == 409 and "作答" in denied.json()["detail"], denied.text
    # 成绩原封不动，链接也还在。
    assert env.student.get(f"/api/exam/{env.token}").status_code == 200


def _plant_queued_submission(env, attempt_id: int) -> int:
    """直接在库里塞一条 queued 的计分提交，模拟"判题还没跑完"的窗口期。"""
    from app.models import CodeSubmission
    db = env.app.state.session_factory()
    try:
        row = CodeSubmission(attempt_id=attempt_id, problem_id_no=env.ids["programming"],
                             language="python", code="print(1)", kind="submit", status="queued")
        db.add(row)
        db.commit()
        return row.id
    finally:
        db.close()


def test_submit_with_pending_judge_is_409_and_recoverable(tmp_path):
    """手动交卷撞上没有跑完的计分判题：409 + judge_pending，判题终态后放行。"""
    from app.models import CodeSubmission
    env = build_exam(tmp_path)
    attempt_id = start(env)
    submission_id = _plant_queued_submission(env, attempt_id)

    denied = env.student.post(f"/api/exam/attempts/{attempt_id}/submit", headers=scsrf(env.student))
    assert denied.status_code == 409
    detail = denied.json()["detail"]
    assert detail["code"] == "judge_pending" and detail["problems"] == [env.ids["programming"]]
    # 没封卷：attempt 仍在 ongoing，能继续作答。
    assert env.student.get(f"/api/exam/attempts/{attempt_id}").status_code == 200

    # 判题落地（终态）之后再交就放行；僵尸提交被 sweep 判死后同理。
    db = env.app.state.session_factory()
    try:
        db.get(CodeSubmission, submission_id).status = "accepted"
        db.commit()
    finally:
        db.close()
    sealed = env.student.post(f"/api/exam/attempts/{attempt_id}/submit", headers=scsrf(env.student))
    assert sealed.status_code == 200 and sealed.json()["sealed"] is False, sealed.text


def test_auto_seal_fails_pending_judge_instead_of_zero(tmp_path):
    """cron 收卷等不到判题跑完：按 judge_failed 收编（score 留 null 不计分），不能落 0 分。"""
    from app.close_expired_attempts import seal_expired
    from app.models import CodeSubmission
    env = build_exam(tmp_path, only=["choice", "programming"])
    attempt_id = start(env)
    save(env, attempt_id, env.ids["choice"], {"type": "choice", "picked": "B"})
    submission_id = _plant_queued_submission(env, attempt_id)
    _expire(env, attempt_id)

    db = env.app.state.session_factory()
    try:
        assert seal_expired(db, verbose=False) == 1
        sealed = db.get(PaperAttempt, attempt_id)
        assert sealed.status == "submitted" and sealed.total_score == 10  # 只有选择题的分
        submission = db.get(CodeSubmission, submission_id)
        assert submission.status == "judge_failed"
    finally:
        db.close()

    result = env.student.get(f"/api/exam/attempts/{attempt_id}/result").json()
    programming = next(item for item in result["questions"] if item.get("type") == "programming")
    assert programming["judge_status"] == "failed" and programming["score"] is None


def test_judge_writeback_after_seal_does_not_revive_failed_submission(tmp_path):
    """竞态守卫：判题跑到一半时收卷把提交收编成 judge_failed，
    判题线程跑完后不许把它改写回"已判分"，成绩也不许再落。"""
    from app.judge.runner import JudgeTask
    from app.models import CodeSubmission, Paper
    from app.routers.exam import _seal, judge_submission
    env = build_exam(tmp_path, only=["programming"])
    attempt_id = start(env)
    submission_id = _plant_queued_submission(env, attempt_id)

    class SealMidJudge:
        """包一层 fake 判题：判题这几秒里超时收卷发生，提交被收编成 judge_failed。"""

        def judge(self, **kwargs):
            db = env.app.state.session_factory()
            try:
                _seal(db, db.get(PaperAttempt, attempt_id), db.get(Paper, env.paper_id), "auto_timeout")
                db.commit()
            finally:
                db.close()
            return env.app.state.judge.judge(**kwargs)

    judge_submission(env.app.state.session_factory, SealMidJudge(), JudgeTask(submission_id=submission_id),
                     env.app.state.settings)

    db = env.app.state.session_factory()
    try:
        submission = db.get(CodeSubmission, submission_id)
        assert submission.status == "judge_failed"  # 没被改写回 accepted
        assert db.get(PaperAttempt, attempt_id).total_score == 0  # 未计分，但也不是"答错的 0 分"
    finally:
        db.close()
    result = env.student.get(f"/api/exam/attempts/{attempt_id}/result").json()
    programming = result["questions"][0]
    assert programming["judge_status"] == "failed" and programming["score"] is None


# ==================== 排行榜与结果页回看 ====================


def start_as(env, client: TestClient) -> int:
    response = client.post(f"/api/exam/{env.token}/start", headers=scsrf(client))
    assert response.status_code == 201, response.text
    return response.json()["attempt_id"]


def answer_choice_as(env, client: TestClient, attempt_id: int, picked: str):
    return client.put(f"/api/exam/attempts/{attempt_id}/answers", headers=scsrf(client),
                      json={"problem_id_no": env.ids["choice"],
                            "answer": {"type": "choice", "picked": picked}})


def submit_as(client: TestClient, attempt_id: int):
    return client.post(f"/api/exam/attempts/{attempt_id}/submit", headers=scsrf(client))


# ==================== 历史作答（摘要 + 分页） ====================


def _one_attempt(env, *, correct: bool) -> int:
    """跑完一次作答并交卷。correct=True 拿满分（10），否则交白卷（0）。"""
    attempt_id = start(env)
    if correct:
        answer_choice_as(env, env.student, attempt_id, "B")
    submit_as(env.student, attempt_id)
    return attempt_id


def test_history_preview_is_capped_and_keeps_the_counted_attempt(tmp_path):
    """一百次记录不能全量下发。默认只带最近 5 条，但"算数的那一次"必须在里面——
    它可能早被挤出最近 5 条，而学员最关心的恰恰是它。"""
    env = build_exam(tmp_path, only=["choice"], link={"attempt_limit": 0})
    first = _one_attempt(env, correct=True)  # 唯一满分的一次，之后全是 0 分
    for _ in range(6):
        _one_attempt(env, correct=False)

    attempts = env.student.get(f"/api/exam/{env.token}").json()["attempts"]
    summary = attempts["summary"]
    assert summary["count"] == 7 and summary["has_more"] is True
    assert summary["score_policy"] == "best"
    assert summary["counted_attempt_id"] == first
    assert summary["best"]["total_score"] == 10 and summary["last"]["total_score"] == 0

    history = attempts["history"]
    assert len(history) == 6  # 最近 5 条 + 被挤出去的计分那次
    assert [item["attempt_no"] for item in history] == [7, 6, 5, 4, 3, 1]
    counted = [item for item in history if item["counted"]]
    assert len(counted) == 1 and counted[0]["attempt_id"] == first


def test_history_marks_the_attempt_that_counts_per_score_policy(tmp_path):
    """score_policy 决定哪一次算数。这个字段此前从未被作答链路读过。"""
    for policy, expected_score in (("best", 10), ("last", 0), ("first", 10)):
        env = build_exam(tmp_path / policy, only=["choice"],
                         link={"attempt_limit": 0, "score_policy": policy})
        _one_attempt(env, correct=True)   # 第 1 次：10 分
        _one_attempt(env, correct=False)  # 第 2 次：0 分
        body = env.student.get(f"/api/exam/{env.token}").json()
        assert body["link"]["score_policy"] == policy
        counted_id = body["attempts"]["summary"]["counted_attempt_id"]
        counted = next(item for item in body["attempts"]["history"] if item["attempt_id"] == counted_id)
        assert counted["total_score"] == expected_score, policy


def test_history_hides_ranking_when_scores_are_not_public(tmp_path):
    """成绩不公开时不能靠"哪一次最好"把分数的相对关系漏出去。"""
    env = build_exam(tmp_path, only=["choice"], link={"attempt_limit": 0, "show_score": "never"})
    _one_attempt(env, correct=True)
    _one_attempt(env, correct=False)

    attempts = env.student.get(f"/api/exam/{env.token}").json()["attempts"]
    assert attempts["summary"]["best"] is None
    assert attempts["summary"]["counted_attempt_id"] is None  # policy=best，标出来就等于泄分
    assert all("total_score" not in item for item in attempts["history"])
    # last 是纯时间口径，与分数无关，照给
    assert attempts["summary"]["last"]["attempt_no"] == 2


def test_attempt_history_pagination(tmp_path):
    """「查看全部」走分页接口：倒序、总数正确、计分那次在整套里选而不是按页选。"""
    env = build_exam(tmp_path, only=["choice"], link={"attempt_limit": 0})
    first = _one_attempt(env, correct=True)
    for _ in range(6):
        _one_attempt(env, correct=False)

    page1 = env.student.get(f"/api/exam/{env.token}/attempts", params={"page": 1, "size": 3}).json()
    assert page1["total"] == 7 and page1["page"] == 1
    assert [item["attempt_no"] for item in page1["items"]] == [7, 6, 5]
    assert page1["counted_attempt_id"] == first  # 不在这一页里，但仍要报对

    page3 = env.student.get(f"/api/exam/{env.token}/attempts", params={"page": 3, "size": 3}).json()
    assert [item["attempt_no"] for item in page3["items"]] == [1]
    assert page3["items"][0]["counted"] is True

    empty = env.student.get(f"/api/exam/{env.token}/attempts", params={"page": 9, "size": 3}).json()
    assert empty["items"] == [] and empty["total"] == 7


def test_attempt_history_rejects_other_students(tmp_path):
    """历史只给自己的。别人的 token 拿不到别人的记录。"""
    env = build_exam(tmp_path, only=["choice"], link={"attempt_limit": 0})
    _one_attempt(env, correct=True)
    other = student_login(env.app, username="second")
    assert other.get(f"/api/exam/{env.token}/attempts").json()["total"] == 0
    assert TestClient(env.app).get(f"/api/exam/{env.token}/attempts").status_code == 401


def test_leaderboard_follows_score_policy(tmp_path):
    """排行榜的代表成绩与候考页同一个口径。这里曾经写死"取最高一次"，
    于是配了 score_policy=last 的链接，候考页说最后一次算数、榜上却按最好成绩排。"""
    env = build_exam(tmp_path, only=["choice"],
                     link={"attempt_limit": 0, "score_policy": "last"})
    _one_attempt(env, correct=True)            # 10 分
    last = _one_attempt(env, correct=False)    # 0 分，按 last 应当以它上榜

    body = env.student.get(f"/api/exam/attempts/{last}/leaderboard").json()
    assert body["me"]["total_score"] == 0
    assert [(e["username"], e["total_score"]) for e in body["entries"]] == [("learner", 0)]


def test_leaderboard_is_scoped_to_the_current_source(tmp_path):
    """同一张卷可以投放到两个正式场次；任何一个场次的榜都不能混入另一个场次的人。"""
    env = build_exam(tmp_path, only=["choice"])
    first_attempt = start(env)
    submit_as(env.student, first_attempt)

    made = env.admin.post(
        f"/api/admin/papers/{env.paper_id}/links",
        headers=env.admin_headers,
        json=link_payload(name="第二场"),
    )
    assert made.status_code == 201, made.text
    second_token = _token_of(env.app, made.json()["id"])
    second_student = student_login(env.app, username="second-session")
    second_start = second_student.post(f"/api/exam/{second_token}/start", headers=scsrf(second_student))
    assert second_start.status_code == 201, second_start.text
    second_attempt = second_start.json()["attempt_id"]
    assert submit_as(second_student, second_attempt).status_code == 200

    first_board = env.student.get(f"/api/exam/attempts/{first_attempt}/leaderboard").json()
    second_board = second_student.get(f"/api/exam/attempts/{second_attempt}/leaderboard").json()
    assert first_board["participant_count"] == 1
    assert [entry["username"] for entry in first_board["entries"]] == ["learner"]
    assert second_board["participant_count"] == 1
    assert [entry["username"] for entry in second_board["entries"]] == ["second-session"]


def test_leaderboard_ranks_each_student_by_their_best_attempt(tmp_path):
    """多次作答只取最高一次上榜：0 分那次不该把 10 分那次顶掉。"""
    env = build_exam(tmp_path, only=["choice"], link={"attempt_limit": 2})
    blank = start(env)  # 第一次交白卷：0 分
    submit_as(env.student, blank)
    scored = start(env)  # 第二次答对：10 分
    answer_choice_as(env, env.student, scored, "B")
    submit_as(env.student, scored)

    other = student_login(env.app, username="second")
    submit_as(other, start_as(env, other))  # 交白卷：0 分

    board = env.student.get(f"/api/exam/attempts/{scored}/leaderboard")
    assert board.status_code == 200, board.text
    body = board.json()
    assert body["participant_count"] == 2
    assert [(e["rank"], e["username"], e["total_score"]) for e in body["entries"]] == [
        (1, "learner", 10), (2, "second", 0)]
    assert body["me"]["rank"] == 1 and body["me"]["total_score"] == 10
    # 榜单只该有这几样，多一个字段都要问一句"这能给吗"
    assert set(body["entries"][0]) == {"rank", "username", "total_score", "duration_seconds"}


def test_leaderboard_ties_share_the_same_rank(tmp_path):
    """并列同名次（1、1、3）——跳名次会让学员以为榜单漏了人。"""
    env = build_exam(tmp_path, only=["choice"])
    first = start(env)
    answer_choice_as(env, env.student, first, "B")
    submit_as(env.student, first)

    second = student_login(env.app, username="second")
    second_attempt = start_as(env, second)
    answer_choice_as(env, second, second_attempt, "B")
    submit_as(second, second_attempt)

    third = student_login(env.app, username="third")
    submit_as(third, start_as(env, third))

    body = env.student.get(f"/api/exam/attempts/{first}/leaderboard").json()
    assert [e["rank"] for e in body["entries"]] == [1, 1, 3]
    assert {e["username"] for e in body["entries"] if e["rank"] == 1} == {"learner", "second"}


def test_leaderboard_is_403_when_scores_are_hidden(tmp_path):
    """成绩不公开的考试给排行榜 = 变相泄分，必须 403 而不是给空榜。"""
    env = build_exam(tmp_path, only=["choice"], link={"show_score": "never"})
    attempt_id = start(env)
    submit_as(env.student, attempt_id)
    denied = env.student.get(f"/api/exam/attempts/{attempt_id}/leaderboard")
    assert denied.status_code == 403


def test_leaderboard_of_another_students_attempt_is_404(tmp_path):
    """和 result 同一口径：别人的 attempt 是不存在，不是 forbidden。"""
    env = build_exam(tmp_path, only=["choice"])
    attempt_id = start(env)
    submit_as(env.student, attempt_id)
    intruder = student_login(env.app, username="stranger")
    assert intruder.get(f"/api/exam/attempts/{attempt_id}/leaderboard").status_code == 404


def test_result_page_returns_own_code_and_case_details(tmp_path):
    """交卷后的结果页要能回看自己交的代码和逐测试点结果（口径同提交记录接口）。"""
    env = build_exam(tmp_path, only=["programming"])
    attempt_id = start(env)
    run_code(env, attempt_id, kind="submit")
    submit_as(env.student, attempt_id)

    response = env.student.get(f"/api/exam/attempts/{attempt_id}/result")
    # 交卷后解析（SECRETANALYSIS）按配置本就公开，不能用作答期的 assert_clean；
    # 但隐藏测试点内容和参考代码是判分资产，任何阶段都不许出现。
    for sentinel in ("SECRETIN", "SECRETOUT", "SECRETREFCODE"):
        assert sentinel not in response.text
    programming = response.json()["questions"][0]
    submission = programming["last_submission"]
    assert submission["code"] == "print(1)"  # 自己的代码可以回看
    assert len(submission["cases"]) == 4  # realtime 模式：2 样例 + 2 隐藏点（内容仍裁掉）
    assert programming["programming"]["pass_condition"] == "全测试点通过"


def test_result_page_respects_compile_only_feedback(tmp_path):
    """feedback_mode 说不给就不给：结果页同样不能成为绕过裁剪的后门。"""
    env = build_exam(tmp_path, only=["programming"], link={"feedback_mode": "compile_only"})
    attempt_id = start(env)
    run_code(env, attempt_id, kind="submit")
    submit_as(env.student, attempt_id)

    programming = env.student.get(f"/api/exam/attempts/{attempt_id}/result").json()["questions"][0]
    assert "last_submission" not in programming
# ==================== 测试点独立时空限制 ====================


def _limits_assert_no_per_case(node, path="$"):
    """递归检查：学员端响应里不允许出现逐点限制明细（列表项里带限制字段的字典）。"""
    if isinstance(node, dict):
        for key, value in node.items():
            _limits_assert_no_per_case(value, f"{path}.{key}")
    elif isinstance(node, list):
        for index, item in enumerate(node):
            if isinstance(item, dict) and ("time_limit_ms" in item or "memory_limit_mb" in item):
                raise AssertionError(f"{path}[{index}] 是逐点限制明细，不应出现在学员端响应")
            _limits_assert_no_per_case(item, f"{path}[{index}]")


def test_per_case_limits_reach_the_judge(tmp_path):
    """第 2 个手工测试点设逐点限制，判题时确实按点传下去；没设的点是 None（继承）。"""
    payload = programming_payload()
    payload["programming"]["time_limit_ms"] = 1500
    payload["programming"]["memory_limit_mb"] = 128
    payload["programming"]["manual_test_cases"] = [
        {"input": "SECRETIN-1", "output": "SECRETOUT-1"},
        {"input": "SECRETIN-2", "output": "SECRETOUT-2", "time_limit_ms": 3000, "memory_limit_mb": 64},
    ]
    env = build_exam(tmp_path, only=["programming"], programming=payload)
    attempt_id = start(env)

    captured = {}
    class CapturingJudge:
        def judge(self, *, language, code, cases, time_limit_ms, memory_limit_mb):
            captured["cases"] = list(cases)
            captured["time_limit_ms"] = time_limit_ms
            captured["memory_limit_mb"] = memory_limit_mb
            from app.judge.fake import FakeJudgeClient
            return FakeJudgeClient().judge(language=language, code=code, cases=cases,
                                           time_limit_ms=time_limit_ms, memory_limit_mb=memory_limit_mb)
    env.app.state.judge = CapturingJudge()
    run_code(env, attempt_id, kind="submit")

    assert captured["time_limit_ms"] == 1500  # 题目级兜底值
    assert captured["memory_limit_mb"] == 128
    # 排序：2 个样例在前，2 个隐藏点在后
    assert captured["cases"][0].time_limit_ms is None and captured["cases"][0].memory_limit_mb is None
    assert captured["cases"][2].time_limit_ms is None and captured["cases"][2].memory_limit_mb is None
    assert captured["cases"][3].time_limit_ms == 3000 and captured["cases"][3].memory_limit_mb == 64


def test_per_case_limits_are_never_sent_to_students(tmp_path):
    """学员端只拿到题目级标量 + 聚合范围；逐点明细结构不出现在响应里。"""
    payload = programming_payload()
    payload["programming"]["manual_test_cases"] = [
        {"input": "SECRETIN-1", "output": "SECRETOUT-1", "time_limit_ms": 3000, "memory_limit_mb": 64},
        {"input": "SECRETIN-2", "output": "SECRETOUT-2", "time_limit_ms": 1500, "memory_limit_mb": 128},
    ]
    env = build_exam(tmp_path, only=["programming"], programming=payload)
    attempt_id = start(env)
    body = env.student.get(f"/api/exam/attempts/{attempt_id}").json()
    assert_clean(json.dumps(body, ensure_ascii=False))
    _limits_assert_no_per_case(body)

    programming = next(item for item in body["questions"] if item["type"] == "programming")["programming"]
    assert programming["time_limit_ms"] == 1000  # 题目级标量照旧
    # 范围按生效值算：两个样例继承 1000，两个隐藏点是 3000 / 1500
    assert programming["time_limit_range"] == [1000, 3000]
    assert programming["memory_limit_range"] == [64, 256]


def test_limit_range_counts_inherited_cases(tmp_path):
    """只有一个点单独设了限制时，范围也要把继承题目级的点算进去。

    只统计显式设过的点会算出 [200, 200]，min == max，前端回落成「限时 1000 ms」——
    学员照 1000 写解法，在那个 200ms 的点上无声 TLE。
    """
    payload = programming_payload()
    payload["programming"]["manual_test_cases"] = [
        {"input": "SECRETIN-1", "output": "SECRETOUT-1", "time_limit_ms": 200},
        {"input": "SECRETIN-2", "output": "SECRETOUT-2"},
    ]
    env = build_exam(tmp_path, only=["programming"], programming=payload)
    attempt_id = start(env)
    body = env.student.get(f"/api/exam/attempts/{attempt_id}").json()
    programming = next(item for item in body["questions"] if item["type"] == "programming")["programming"]
    assert programming["time_limit_range"] == [200, 1000]
    # 一个点都没设过内存的话仍然是 None，前端继续渲染题目级单值
    assert programming["memory_limit_range"] is None


def test_samples_reject_per_case_limits(tmp_path):
    """样例恒继承题目级：录入接口不再接受样例上的逐点限制字段。"""
    env = build_exam(tmp_path, only=["choice"])
    payload = programming_payload()
    payload["programming"]["samples"] = [{"input": "1 2", "output": "3", "time_limit_ms": 500}]
    response = env.admin.post("/api/admin/problems", headers=env.admin_headers, json=payload)
    assert response.status_code == 422, response.text


def test_problem_level_limits_round_trip_through_admin_api(tmp_path):
    """纯手工录入的 Python 题现在能设题目级限制（现状缺口），且逐点值能回填到编辑表单。"""
    env = build_exam(tmp_path, only=["choice"])  # 只用建好的 app，编程题另建（草稿可编辑）
    headers = env.admin_headers
    payload = {
        "type": "programming", "sub_type": "python",
        "common": {"difficulty": "普及-", "source": "洛谷", "structure": "综合应用",
                   "knowledge": [], "stage": [], "business": []},
        "stem": "输入两个整数，输出和。", "analysis": "SECRETANALYSIS-prog",
        "options": [], "blanks": [],
        "programming": {
            "title": "A+B", "pass_condition": "编译通过",
            "input_format": "两个整数", "output_format": "一个整数", "hints": "无",
            "time_limit_ms": 2000, "memory_limit_mb": 512,
            "samples": [{"input": "1 2", "output": "3"}],
            "ref_code": {"cpp": "", "python": "SECRETREFCODE"},
            "manual_test_cases": [
                {"input": "1 1", "output": "2", "time_limit_ms": 3000, "memory_limit_mb": 64},
            ],
        },
    }
    created = env.admin.post("/api/admin/problems", headers=headers, json=payload)
    assert created.status_code == 201, created.text
    problem_id = created.json()["id"]
    back = created.json()["programming"]
    assert back["time_limit_ms"] == 2000 and back["memory_limit_mb"] == 512
    assert back["manual_test_cases"][0]["time_limit_ms"] == 3000
    assert back["manual_test_cases"][0]["memory_limit_mb"] == 64
    assert back["samples"][0] == {"input": "1 2", "output": "3"}  # 样例不带逐点限制
    # 再改一次题（草稿）：题目级限制可以被修改并回显
    payload["programming"]["time_limit_ms"] = 3000
    payload["programming"]["manual_test_cases"][0]["time_limit_ms"] = None  # 回到继承
    updated = env.admin.put(f"/api/admin/problems/{problem_id}", headers=match(headers, 1), json=payload)
    assert updated.status_code == 200, updated.text
    back = updated.json()["programming"]
    assert back["time_limit_ms"] == 3000
    assert back["manual_test_cases"][0]["time_limit_ms"] is None
