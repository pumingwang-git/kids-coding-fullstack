"""后台成绩查看（admin_results.py）的测试。

环境搭建复用 test_exam 的 build_exam 系列（管理员建题组卷发链接、学员开考交卷），
这是本仓库第一个跨测试文件复用——成绩查看的输入就是一场真实考过的试，
自己再造一套环境只会跟着 test_exam 的夹具漂移。
"""

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.models import AdminUser, LessonPaperBlock
from app.security import password_hash
from test_admin_courses import add_section, create_category, create_course
from test_exam import (
    ADMIN_PASSWORD, _expire, _plant_queued_submission, build_exam, run_code,
    save, scsrf, start, student_login,
)


def _submit(env, attempt_id: int):
    response = env.student.post(f"/api/exam/attempts/{attempt_id}/submit", headers=scsrf(env.student))
    assert response.status_code == 200, response.text


def _second_student(env, username: str = "learner2") -> TestClient:
    return student_login(env.app, username)


def _lesson_homework(env) -> dict:
    """把 build_exam 已发布的试卷绑定为真实课时作业，供成绩接口回归复用。"""
    category = create_category(env.admin, env.admin_headers).json()
    course = create_course(env.admin, env.admin_headers, category["id"]).json()
    section = add_section(env.admin, env.admin_headers, course["id"]).json()
    lesson = env.admin.post(
        f"/api/admin/sections/{section['id']}/lessons", headers=env.admin_headers,
        json={"title": "作业课时", "content_md": "# 作业", "is_trial": True},
    ).json()
    block = env.admin.post(
        f"/api/admin/lessons/{lesson['id']}/blocks", headers=env.admin_headers,
        json={"block_type": "homework", "title": "课后作业", "detail": {"paper": {
            "paper_id": env.paper_id, "mode": "homework", "attempt_limit": 2,
            "shuffle_questions": False, "shuffle_options": False,
            "show_score": True, "show_analysis": True, "due_at": None,
        }}},
    ).json()
    published = env.admin.post(f"/api/admin/courses/{course['id']}/publish", headers=env.admin_headers)
    assert published.status_code == 200, published.text
    return {"course": course, "section": section, "lesson": lesson, "block": block}


def _start_homework(client: TestClient, built: dict) -> int:
    base = f"/api/exam/lesson-homework/{built['lesson']['id']}/blocks/{built['block']['id']}"
    response = client.post(f"{base}/start", headers=scsrf(client))
    assert response.status_code == 201, response.text
    return response.json()["attempt_id"]


# ==================== 总览 ====================


def test_overview_lists_links_with_stats(tmp_path):
    """两个学员一及格一挂科：总览行要给出开考/已交/平均/区间/及格率。"""
    env = build_exam(tmp_path, only=["choice"], paper={"pass_score": 10})
    attempt_id = start(env)
    save(env, attempt_id, env.ids["choice"], {"type": "choice", "picked": "B"})  # 对，10 分
    _submit(env, attempt_id)

    other = _second_student(env)
    started = other.post(f"/api/exam/{env.token}/start", headers=scsrf(other))
    assert started.status_code == 201, started.text
    other_id = started.json()["attempt_id"]
    other.put(f"/api/exam/attempts/{other_id}/answers", headers=scsrf(other),
              json={"problem_id_no": env.ids["choice"], "answer": {"type": "choice", "picked": "A"}})
    other.post(f"/api/exam/attempts/{other_id}/submit", headers=scsrf(other))

    payload = env.admin.get("/api/admin/exam-results", headers=env.admin_headers).json()
    assert payload["total"] == 1
    row = payload["items"][0]
    assert row["source"] == "exam_link"
    assert row["link"]["id"] == env.link_id and row["link"]["phase"] == "running"
    assert row["paper"]["paper_type"] == "测试卷" and row["paper"]["subject"] == "python"
    assert row["full_score"] == 10 and row["pass_score"] == 10
    # 人数与人次分开报：这里是 2 个人各考 1 次，两个数字恰好相等
    assert row["participants"] == 2 and row["submitted_participants"] == 2
    assert row["attempts"] == 2 and row["submitted"] == 2 and row["ongoing"] == 0
    assert row["score"] == {"avg": 5, "min": 0, "max": 10, "pass_rate": 50}


def test_overview_filters_and_unknown_source(tmp_path):
    env = build_exam(tmp_path, only=["choice"])
    start(env)
    assert env.admin.get("/api/admin/exam-results?keyword=闭环", headers=env.admin_headers).json()["total"] == 1
    assert env.admin.get("/api/admin/exam-results?keyword=不存在", headers=env.admin_headers).json()["total"] == 0
    assert env.admin.get("/api/admin/exam-results?paper_type=作业卷", headers=env.admin_headers).json()["total"] == 0
    assert env.admin.get("/api/admin/exam-results?subject=cpp", headers=env.admin_headers).json()["total"] == 0
    assert env.admin.get("/api/admin/exam-results?subject=python", headers=env.admin_headers).json()["total"] == 1
    unknown = env.admin.get("/api/admin/exam-results?source=practice", headers=env.admin_headers)
    assert unknown.status_code == 422  # 预留来源还没实现时是 422，不是静默空列表


def test_overview_visibility_follows_paper_read_permission(tmp_path):
    """editor 只看自己卷的场次；超管全看；未登录 401。"""
    env = build_exam(tmp_path, only=["choice"])
    start(env)
    db = env.app.state.session_factory()
    try:
        db.add(AdminUser(username="writer", password_hash=password_hash.hash(ADMIN_PASSWORD),
                         display_name="writer", role="editor"))
        db.commit()
    finally:
        db.close()

    writer = TestClient(env.app)
    writer.get("/api/admin/csrf")
    logged = writer.post("/api/admin/login",
                         headers={"X-CSRF-Token": writer.cookies.get("admin_csrf_token")},
                         json={"username": "writer", "password": ADMIN_PASSWORD})
    assert logged.status_code == 200, logged.text
    wheaders = {"X-CSRF-Token": writer.cookies.get("admin_csrf_token")}

    assert writer.get("/api/admin/exam-results", headers=wheaders).json()["total"] == 0
    assert env.admin.get("/api/admin/exam-results", headers=env.admin_headers).json()["total"] == 1
    assert TestClient(env.app).get("/api/admin/exam-results").status_code == 401


# ==================== 课时作业成绩 ====================


def test_lesson_homework_results_follow_course_path_and_best_score(tmp_path):
    env = build_exam(tmp_path, only=["choice"], paper={"pass_score": 10})
    built = _lesson_homework(env)

    first = _start_homework(env.student, built)
    save(env, first, env.ids["choice"], {"type": "choice", "picked": "B"})
    _submit(env, first)
    # 同一人第二次答错：作答人次增加，但 score_policy=best 的代表成绩仍是第一次 10 分。
    second = _start_homework(env.student, built)
    save(env, second, env.ids["choice"], {"type": "choice", "picked": "A"})
    _submit(env, second)
    other = _second_student(env)
    other_attempt = _start_homework(other, built)
    other.put(f"/api/exam/attempts/{other_attempt}/answers", headers=scsrf(other),
              json={"problem_id_no": env.ids["choice"], "answer": {"type": "choice", "picked": "A"}})
    assert other.post(f"/api/exam/attempts/{other_attempt}/submit", headers=scsrf(other)).status_code == 200

    overview = env.admin.get(
        f"/api/admin/lesson-homework-results?course_id={built['course']['id']}",
        headers=env.admin_headers,
    )
    assert overview.status_code == 200, overview.text
    payload = overview.json()
    assert payload["total"] == 1
    row = payload["items"][0]
    assert row["source"] == "lesson_homework" and row["source_id"] == built["block"]["id"]
    assert row["course"]["id"] == built["course"]["id"]
    assert row["section"]["id"] == built["section"]["id"]
    assert row["lesson"]["id"] == built["lesson"]["id"]
    assert row["homework"]["title"] == "课后作业"
    assert row["participants"] == 2 and row["submitted_participants"] == 2
    assert row["attempts"] == 3 and row["submitted"] == 3
    assert row["score"] == {"avg": 5, "min": 0, "max": 10, "pass_rate": 50}
    assert env.admin.get(
        f"/api/admin/lesson-homework-results?section_id={built['section']['id']}",
        headers=env.admin_headers,
    ).json()["total"] == 1
    assert env.admin.get(
        "/api/admin/lesson-homework-results?lesson_id=99999", headers=env.admin_headers,
    ).json()["total"] == 0

    detail = env.admin.get(
        f"/api/admin/lesson-homework/{built['block']['id']}/results", headers=env.admin_headers,
    )
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert body["homework"]["score_policy"] == "best"
    assert body["summary"]["participants"] == 2 and body["summary"]["attempts"] == 3
    learner = next(row for row in body["students"] if row["user"]["username"] == "learner")
    assert learner["attempt_count"] == 2 and learner["counted"]["total_score"] == 10
    assert "attempts" not in learner
    history = env.admin.get(
        f"/api/admin/lesson-homework/{built['block']['id']}/students/{learner['user']['id']}/attempts",
        headers=env.admin_headers,
    )
    assert history.status_code == 200, history.text
    assert [attempt["attempt_no"] for attempt in history.json()["student"]["attempts"]] == [1, 2]
    assert sum(bucket["count"] for bucket in body["distribution"]) == 2
    review = env.admin.get(f"/api/admin/attempts/{first}/review", headers=env.admin_headers)
    assert review.status_code == 200, review.text
    assert review.json()["questions"][0]["type"] == "choice"

    analysis = env.admin.get(
        f"/api/admin/lesson-homework/{built['block']['id']}/item-analysis", headers=env.admin_headers,
    )
    assert analysis.status_code == 200, analysis.text
    assert analysis.json()["grouping"]["participants"] == 2


def test_lesson_homework_results_require_course_and_paper_read_scope(tmp_path):
    env = build_exam(tmp_path, only=["choice"])
    built = _lesson_homework(env)
    db = env.app.state.session_factory()
    try:
        db.add(AdminUser(username="writer", password_hash=password_hash.hash(ADMIN_PASSWORD),
                         display_name="writer", role="editor"))
        db.commit()
    finally:
        db.close()
    writer = TestClient(env.app)
    writer.get("/api/admin/csrf")
    assert writer.post("/api/admin/login", headers={"X-CSRF-Token": writer.cookies.get("admin_csrf_token")},
                       json={"username": "writer", "password": ADMIN_PASSWORD}).status_code == 200
    headers = {"X-CSRF-Token": writer.cookies.get("admin_csrf_token")}
    assert writer.get("/api/admin/lesson-homework-results", headers=headers).json()["total"] == 0
    assert writer.get(f"/api/admin/lesson-homework/{built['block']['id']}/results", headers=headers).status_code == 403
    assert env.admin.get("/api/admin/lesson-homework/99999/results", headers=env.admin_headers).status_code == 404


def test_lesson_homework_results_status_comes_from_server(tmp_path):
    env = build_exam(tmp_path, only=["choice"])
    built = _lesson_homework(env)
    overview = env.admin.get("/api/admin/lesson-homework-results", headers=env.admin_headers).json()
    assert overview["items"][0]["homework"]["status"] == "open"
    assert overview["server_now"]

    db = env.app.state.session_factory()
    try:
        detail = db.get(LessonPaperBlock, built["block"]["id"])
        detail.due_at = datetime.now(UTC) - timedelta(minutes=1)
        db.commit()
    finally:
        db.close()
    closed = env.admin.get("/api/admin/lesson-homework-results", headers=env.admin_headers).json()
    assert closed["items"][0]["homework"]["status"] == "closed"


# ==================== 单场明细 ====================


def test_link_results_with_judge_failed_flag(tmp_path):
    """明细按作答记录列；判题异常的作答打 has_judge_failed 标，与"答错 0 分"区分。"""
    from app.close_expired_attempts import seal_expired
    env = build_exam(tmp_path, only=["choice", "programming"], paper={"pass_score": 15})

    normal = start(env)
    save(env, normal, env.ids["choice"], {"type": "choice", "picked": "B"})
    _submit(env, normal)

    other = _second_student(env)
    started = other.post(f"/api/exam/{env.token}/start", headers=scsrf(other)).json()
    abnormal_id = started["attempt_id"]
    other.put(f"/api/exam/attempts/{abnormal_id}/answers", headers=scsrf(other),
              json={"problem_id_no": env.ids["choice"], "answer": {"type": "choice", "picked": "B"}})
    _plant_queued_submission(env, abnormal_id)
    _expire(env, abnormal_id)
    db = env.app.state.session_factory()
    try:
        assert seal_expired(db, verbose=False) == 1
    finally:
        db.close()

    payload = env.admin.get(f"/api/admin/links/{env.link_id}/results",
                            headers=env.admin_headers).json()
    assert payload["summary"]["participants"] == 2
    assert payload["summary"]["submitted_participants"] == 2
    assert payload["summary"]["attempts"] == 2
    assert payload["full_score"] == 30 and payload["pass_score"] == 15
    # 两个人选择题都拿了 10 分；判题异常那位的编程题不计分
    assert payload["summary"]["avg"] == 10 and payload["summary"]["pass_rate"] == 0
    assert sum(bucket["count"] for bucket in payload["distribution"]) == 2

    rows = {row["user"]["username"]: row for row in payload["students"]}
    assert rows["learner"]["counted"]["total_score"] == 10
    assert rows["learner"]["has_judge_failed"] is False
    assert rows["learner2"]["counted"]["total_score"] == 10
    assert rows["learner2"]["has_judge_failed"] is True
    assert rows["learner2"]["counted"]["submit_kind"] == "auto_close"


def test_link_results_permission(tmp_path):
    env = build_exam(tmp_path, only=["choice"])
    assert env.admin.get("/api/admin/links/9999/results", headers=env.admin_headers).status_code == 404
    db = env.app.state.session_factory()
    try:
        db.add(AdminUser(username="writer", password_hash=password_hash.hash(ADMIN_PASSWORD),
                         display_name="writer", role="editor"))
        db.commit()
    finally:
        db.close()
    writer = TestClient(env.app)
    writer.get("/api/admin/csrf")
    writer.post("/api/admin/login", headers={"X-CSRF-Token": writer.cookies.get("admin_csrf_token")},
                json={"username": "writer", "password": ADMIN_PASSWORD})
    denied = writer.get(f"/api/admin/links/{env.link_id}/results",
                        headers={"X-CSRF-Token": writer.cookies.get("admin_csrf_token")})
    assert denied.status_code == 403


# ==================== 单份答卷回看 ====================


def test_attempt_review_payload(tmp_path):
    """逐题：学员答案、得分、判题状态；选择题给选项与对错，编程题给提交与代码。"""
    env = build_exam(tmp_path, only=["choice", "programming"])
    attempt_id = start(env)
    save(env, attempt_id, env.ids["choice"], {"type": "choice", "picked": "B"})
    run_code(env, attempt_id, kind="submit")
    _submit(env, attempt_id)

    payload = env.admin.get(f"/api/admin/attempts/{attempt_id}/review",
                            headers=env.admin_headers).json()
    assert payload["user"]["username"] == "learner"
    assert payload["attempt"]["total_score"] == 30  # 选择 10 + 编程 20（fake 判题全过）
    assert payload["full_score"] == 30

    choice, programming = payload["questions"]
    assert choice["type"] == "choice" and choice["score"] == 10 and choice["is_correct"] is True
    assert choice["answer"]["picked"] == "B"
    assert any(o["is_correct"] and o["option_label"] == "B" for o in choice["options"])
    assert programming["type"] == "programming" and programming["score"] == 20
    assert programming["judge_status"] == "judged"
    submission = programming["submissions"][0]
    assert submission["status"] == "accepted" and submission["code"] == "print(1)"
    assert submission["score"] == 20


def test_attempt_review_permission(tmp_path):
    env = build_exam(tmp_path, only=["choice"])
    attempt_id = start(env)
    assert env.admin.get("/api/admin/attempts/9999/review", headers=env.admin_headers).status_code == 404
    denied = TestClient(env.app).get(f"/api/admin/attempts/{attempt_id}/review")
    assert denied.status_code == 401


# ==================== 反复作答的聚合口径 ====================


def _answer_and_submit(env, picked: str) -> int:
    """开一次考、答一题、交卷，返回 attempt_id。"""
    attempt_id = start(env)
    save(env, attempt_id, env.ids["choice"], {"type": "choice", "picked": picked})
    _submit(env, attempt_id)
    return attempt_id


def test_repeated_attempts_count_as_one_participant(tmp_path):
    """一个人练 5 次，是「参考 1 人 / 作答 5 次」，不是「开考 5 人次」。

    这条盯的就是运营反馈的那个现象：练习卷允许反复作答，同一个学员刷 100 次，
    列表显示"开考 100"，看的人会以为来了 100 个学员。
    """
    env = build_exam(tmp_path, only=["choice"],
                     link={"attempt_limit": 0, "score_policy": "best"},   # 0 = 不限次
                     paper={"pass_score": 10})
    for picked in ("A", "B", "A", "A", "A"):   # 只有 B 是对的 → 最好成绩 10 分
        _answer_and_submit(env, picked)

    row = env.admin.get("/api/admin/exam-results", headers=env.admin_headers).json()["items"][0]
    assert row["participants"] == 1, "5 次作答来自同一个人，参考人数必须是 1"
    assert row["attempts"] == 5
    # 平均分按"每人一个代表成绩"算：1 个人、最好成绩 10 分 → 平均 10，不是 5 次的均值 2
    assert row["score"]["avg"] == 10

    payload = env.admin.get(f"/api/admin/links/{env.link_id}/results",
                            headers=env.admin_headers).json()
    assert payload["summary"]["participants"] == 1
    assert payload["summary"]["attempts"] == 5
    assert len(payload["students"]) == 1, "同一学员不能占 5 行"

    student = payload["students"][0]
    assert student["attempt_count"] == 5 and student["submitted_count"] == 5
    assert student["counted"]["total_score"] == 10
    # 历史正序，5 条都在，每条都能点进 review
    attempts = student["attempts"]
    assert len(attempts) == 5
    assert [a["attempt_no"] for a in attempts] == [1, 2, 3, 4, 5]
    assert student["counted"]["started_at"] and student["counted"]["submitted_at"]

    # 每条历史都能取到逐题详情（第三层）
    for attempt in attempts:
        review = env.admin.get(f"/api/admin/attempts/{attempt['attempt_id']}/review",
                               headers=env.admin_headers)
        assert review.status_code == 200, review.text
        assert review.json()["questions"][0]["type"] == "choice"


def test_counted_attempt_follows_link_score_policy(tmp_path):
    """代表成绩跟着链接的 score_policy 走，不是写死取最高。

    写死"最好"的话，配了 last 的场次会出现：后台显示 10 分、学员端候考页和
    排行榜按最后一次的 0 分算——老师和学员对着两个数字说话。
    """
    env = build_exam(tmp_path, only=["choice"],
                     link={"attempt_limit": 0, "score_policy": "last"})
    _answer_and_submit(env, "B")   # 对，10 分
    _answer_and_submit(env, "A")   # 错，0 分（这是最后一次）

    payload = env.admin.get(f"/api/admin/links/{env.link_id}/results",
                            headers=env.admin_headers).json()
    assert payload["link"]["score_policy"] == "last"
    student = payload["students"][0]
    assert student["counted"]["total_score"] == 0, "score_policy=last 时代表成绩是最后一次"
    assert student["counted"]["attempt_no"] == 2
    assert payload["summary"]["avg"] == 0


# ==================== 逐题分析（视图「逐题得分率」/「题目诊断」） ====================


def _take_exam(env, username: str, answers: dict) -> int:
    """新学员开考 → 按 answers（题号 → answer 载荷）作答 → 交卷，返回 attempt_id。"""
    client = student_login(env.app, username)
    started = client.post(f"/api/exam/{env.token}/start", headers=scsrf(client))
    assert started.status_code == 201, started.text
    attempt_id = started.json()["attempt_id"]
    for problem_id_no, answer in answers.items():
        client.put(f"/api/exam/attempts/{attempt_id}/answers", headers=scsrf(client),
                   json={"problem_id_no": problem_id_no, "answer": answer})
    assert client.post(f"/api/exam/attempts/{attempt_id}/submit",
                       headers=scsrf(client)).status_code == 200
    return attempt_id


def _analysis(env) -> dict:
    response = env.admin.get(f"/api/admin/links/{env.link_id}/item-analysis",
                             headers=env.admin_headers)
    assert response.status_code == 200, response.text
    return response.json()


def test_item_analysis_reports_score_rate_per_question(tmp_path):
    """一题一行，得分率按得分算而不是按对错——多选/编程拿部分分是常态。"""
    # partial_credit_multi：多选少选给半分。默认是少选给 0，那样这条用例的
    # "按得分算" 和 "按对错算" 会算出同一个数，证明不了任何东西。
    env = build_exam(tmp_path, only=["choice", "multi_choice"],
                     paper={"partial_credit_multi": True})
    # env 自带的 learner：单选对、多选只选一半（部分分）
    attempt_id = start(env)
    save(env, attempt_id, env.ids["choice"], {"type": "choice", "picked": "B"})
    save(env, attempt_id, env.ids["multi_choice"], {"type": "multi_choice", "picked": ["A"]})
    _submit(env, attempt_id)
    _take_exam(env, "learner2", {env.ids["choice"]: {"type": "choice", "picked": "A"},
                                 env.ids["multi_choice"]: {"type": "multi_choice", "picked": ["A", "C"]}})

    payload = _analysis(env)
    items = {i["problem_id_no"]: i for i in payload["items"]}
    assert [i["sort_order"] for i in payload["items"]] == [1, 2]  # 按卷内顺序，不按得分率排
    assert items[env.ids["choice"]]["answered"] == 2
    assert items[env.ids["choice"]]["score_rate"] == 0.5      # 一对一错
    # 多选：一人满分、一人半分 → 按得分算是 0.75，按对错算会是 0.5
    assert items[env.ids["multi_choice"]]["score_rate"] == 0.75
    assert all(i["judge_failed"] == 0 for i in payload["items"])


def test_item_analysis_counts_one_row_per_student(tmp_path):
    """练习卷反复作答只算代表作答——与分数分布同一口径，不许一个人刷出一张图。"""
    env = build_exam(tmp_path, only=["choice"], link={"attempt_limit": 0, "score_policy": "best"})
    for picked in ("A", "A", "B"):          # 同一个学员考三次，最后一次才对
        attempt_id = start(env)
        save(env, attempt_id, env.ids["choice"], {"type": "choice", "picked": picked})
        _submit(env, attempt_id)

    item = _analysis(env)["items"][0]
    # 按人次算会是 1/3；按代表作答（best）算就是 1 个人、1 次、满分
    assert item["answered"] == 1 and item["score_rate"] == 1.0


def test_item_analysis_skips_grouping_when_too_few_people(tmp_path):
    """人太少时 27% 分组就是「1 个人 vs 1 个人」，区分度是噪声，必须留空让前端走空态。"""
    env = build_exam(tmp_path, only=["choice"])
    attempt_id = start(env)
    save(env, attempt_id, env.ids["choice"], {"type": "choice", "picked": "B"})
    _submit(env, attempt_id)

    payload = _analysis(env)
    assert payload["grouping"]["enabled"] is False
    assert payload["grouping"]["participants"] == 1
    # 20 人 = 每组 5 人。再少一档（每组 2 人）时单个学员能把区分度拉动 0.5，那是噪声不是统计量
    assert payload["grouping"]["min_participants"] == 20
    item = payload["items"][0]
    # 得分率照常给（只是个比例，不涉及分组），分组字段一律 None
    assert item["score_rate"] == 1.0
    assert item["high_rate"] is None and item["low_rate"] is None
    assert item["discrimination"] is None


def _seed_submitted(env, username: str, per_question: dict[str, int]):
    """直接在库里塞一份已交卷的答卷。

    走 HTTP 是塞不进去的：注册接口有限流，第 9 个学员就开始 429。而这条用例要验的是
    **20 人规模下的聚合口径**，不是报名到交卷的流程（那条链路 test_exam 已经盯着）。
    形状照 _score_attempt 交卷后的样子来：每道题都有行，未作答的记 0 而不是没有行。
    """
    from app.models import AttemptAnswer, PaperAttempt, User
    db = env.app.state.session_factory()
    try:
        user = User(username=username, email=f"{username}@example.com",
                    hashed_password="x", status="active")
        db.add(user); db.flush()
        attempt = PaperAttempt(exam_link_id=env.link_id, paper_id=env.paper_id, user_id=user.id,
                               attempt_no=1, status="submitted", submit_kind="manual",
                               total_score=sum(per_question.values()), duration_seconds=600)
        db.add(attempt); db.flush()
        for problem_id_no, score in per_question.items():
            db.add(AttemptAnswer(attempt_id=attempt.id, problem_id_no=problem_id_no,
                                 answer_json="", score=score, is_correct=score > 0,
                                 judge_status="judged"))
        db.commit()
    finally:
        db.close()


def test_item_analysis_flags_negative_discrimination(tmp_path):
    """低分组比高分组答得还好、且低分组过半做对 = 答案多半配反了。

    人数卡在 20：前 / 后 27% 分组时每组 5 人，是"只够看方向"的下限。
    """
    env = build_exam(tmp_path, only=["choice", "multi_choice", "judge"])
    choice, multi, judge = env.ids["choice"], env.ids["multi_choice"], env.ids["judge"]
    # 高分组前两题满分、判断题 0 分（20 分）；低分组只有判断题拿分（10 分）
    for i in range(10):
        _seed_submitted(env, f"high{i}", {choice: 10, multi: 10, judge: 0})
    for i in range(10):
        _seed_submitted(env, f"low{i}", {choice: 0, multi: 0, judge: 10})

    payload = _analysis(env)
    grouping = payload["grouping"]
    assert grouping["enabled"] is True and grouping["participants"] == 20
    assert grouping["group_size"] == 5              # int(20 * 0.27)
    # 20 人够画图，但每组不足 10 人：必须标成参考值，否则老师会拿它当准数用
    assert grouping["stable"] is False
    assert grouping["stable_participants"] == 37

    items = {i["problem_id_no"]: i for i in payload["items"]}
    row = items[judge]
    assert row["high_rate"] == 0.0 and row["low_rate"] == 1.0
    assert row["discrimination"] == -1.0
    assert row["suspect"] == "negative_discrimination"
    # 正常题不该被打标
    assert items[choice]["discrimination"] == 1.0
    assert items[choice]["suspect"] is None


def test_item_analysis_marks_grouping_stable_at_37(tmp_path):
    """37 人 = 每组 10 人，区分度才开始可信；到这个规模就不该再标"参考值"了。"""
    env = build_exam(tmp_path, only=["choice"])
    choice = env.ids["choice"]
    for i in range(37):
        _seed_submitted(env, f"s{i}", {choice: 10 if i % 2 else 0})

    grouping = _analysis(env)["grouping"]
    assert grouping["participants"] == 37
    assert grouping["enabled"] is True and grouping["stable"] is True
    assert grouping["group_size"] == 9           # int(37 * 0.27)


def test_item_analysis_excludes_judge_failed_from_denominator(tmp_path):
    """判题异常的答题从得分率分母剔除，另计 judge_failed——
    混进去算等于把系统故障说成学生不会。"""
    env = build_exam(tmp_path, only=["choice"])
    attempt_id = start(env)
    save(env, attempt_id, env.ids["choice"], {"type": "choice", "picked": "B"})
    _submit(env, attempt_id)
    other_id = _take_exam(env, "learner2", {env.ids["choice"]: {"type": "choice", "picked": "B"}})

    db = env.app.state.session_factory()
    try:
        from app.models import AttemptAnswer
        row = db.query(AttemptAnswer).filter(AttemptAnswer.attempt_id == other_id).one()
        row.judge_status, row.score = "failed", None
        db.commit()
    finally:
        db.close()

    item = _analysis(env)["items"][0]
    assert item["answered"] == 1 and item["judge_failed"] == 1
    assert item["score_rate"] == 1.0        # 混进去算会掉到 0.5


def test_item_analysis_requires_paper_read_permission(tmp_path):
    """看不到这张卷的人也看不到它的逐题分析——与 /results 同一把尺子。"""
    env = build_exam(tmp_path, only=["choice"])
    db = env.app.state.session_factory()
    try:
        db.add(AdminUser(username="outsider", password_hash=password_hash.hash(ADMIN_PASSWORD),
                         display_name="outsider", role="editor", status="active"))
        db.commit()
    finally:
        db.close()

    outsider = TestClient(env.app)
    outsider.get("/api/admin/csrf")
    logged = outsider.post("/api/admin/login",
                           headers={"X-CSRF-Token": outsider.cookies.get("admin_csrf_token")},
                           json={"username": "outsider", "password": ADMIN_PASSWORD})
    assert logged.status_code == 200, logged.text
    response = outsider.get(f"/api/admin/links/{env.link_id}/item-analysis",
                            headers={"X-CSRF-Token": outsider.cookies.get("admin_csrf_token")})
    assert response.status_code == 403


# ---- 阈值本身的用例。这几个数是仿真推出来的，看起来却最像可以顺手清理的魔数 ----


def test_suspect_flag_does_not_cry_wolf_on_plain_negative_discrimination():
    """D<0 曾经就是触发条件，那是错的。

    十万次仿真：一道真实区分度为 0 的题（谁都不会、纯靠猜），观测 D 落在负半边
    本来就有约 40% 的概率，而且加人救不了——k 从 5 到 15 误报率反而从 38% 升到 43%。
    按 D<0 上线，一份 20 道题的卷子每次都会冒出好几个假警报。
    """
    from app.results_common import suspect_flag as _suspect_flag

    # 轻微为负 + 低分组本来就没做对多少 → 这是"这题没区分度"，不是"答案配错"
    assert _suspect_flag(0.45, 0.42, 0.48, -0.06) is None
    # 够负，但低分组也只有三成做对 → 仍然不是配错答案的样子
    assert _suspect_flag(0.30, 0.05, 0.35, -0.30) is None
    # 低分组过半做对、偏偏高分组栽了 → 这才像答案配反
    assert _suspect_flag(0.40, 0.20, 0.75, -0.55) == "negative_discrimination"


def test_suspect_flag_separates_all_low_from_hard_but_discriminating():
    from app.results_common import suspect_flag as _suspect_flag

    # 得分率极低且高分组也不会 → 先查题
    assert _suspect_flag(0.12, 0.25, 0.05, 0.20) == "all_low"
    # 同样难，但高分组做出来了 → 正常的压轴题，别提示老师去查题
    assert _suspect_flag(0.18, 0.55, 0.02, 0.53) is None
    # 分组数据缺失（人太少）时只看总体得分率
    assert _suspect_flag(0.10, None, None, None) == "all_low"
    assert _suspect_flag(None, None, None, None) is None


def test_distribution_bins_follow_sample_size():
    """固定 10 个桶要 ~100 个样本（平方根 / Rice / Sturges 三条规则一致），
    而一个班 30–50 人永远到不了：30 个人摊进 10 个桶画出来是一把梳子。"""
    from app.results_common import distribution_bins as _distribution_bins

    assert _distribution_bins(0) == 4        # 下界，别退化成 1 个桶
    assert _distribution_bins(12) == 4
    assert _distribution_bins(30) == 5
    assert _distribution_bins(50) == 7
    assert _distribution_bins(100) == 10
    assert _distribution_bins(400) == 10     # 上界，再多的桶对老师没有额外信息


def test_distribution_buckets_match_bin_rule(tmp_path):
    """接口返回的桶数要跟着人数走，不是写死 10 个。"""
    env = build_exam(tmp_path, only=["choice"])
    attempt_id = start(env)
    save(env, attempt_id, env.ids["choice"], {"type": "choice", "picked": "B"})
    _submit(env, attempt_id)

    payload = env.admin.get(f"/api/admin/links/{env.link_id}/results",
                            headers=env.admin_headers).json()
    assert len(payload["distribution"]) == 4          # 1 个人 → 下界 4 桶
    assert sum(b["count"] for b in payload["distribution"]) == 1
    # 桶的区间要覆盖满分，不能因为改了桶数就漏掉尾巴
    assert payload["distribution"][-1]["range"].endswith(str(payload["full_score"]))
