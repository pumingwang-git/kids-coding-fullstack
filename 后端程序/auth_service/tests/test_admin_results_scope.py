from fastapi.testclient import TestClient
from test_admin_results import _lesson_homework, _second_student, _start_homework
from test_exam import ADMIN_PASSWORD, build_exam, scsrf, start
from test_scratch import (
    build_scratch_lesson,
    open_block,
    save_project,
    sb3_bytes,
    scratch_env,
    student_login,
    submit,
)

import app.routers.admin_results as admin_results
from app.models import AdminUser, User
from app.security import password_hash


def _role_login(app, role: str) -> tuple[TestClient, dict]:
    db = app.state.session_factory()
    try:
        db.add(AdminUser(username=f"scope-{role}", password_hash=password_hash.hash(ADMIN_PASSWORD),
                         display_name=role, role=role))
        db.commit()
    finally:
        db.close()
    client = TestClient(app)
    client.get("/api/admin/csrf")
    headers = {"X-CSRF-Token": client.cookies.get("admin_csrf_token")}
    logged = client.post("/api/admin/login", headers=headers,
                         json={"username": f"scope-{role}", "password": ADMIN_PASSWORD})
    assert logged.status_code == 200, logged.text
    return client, headers


def test_teacher_empty_scope_covers_all_nine_results_endpoints(tmp_path):
    env = build_exam(tmp_path, only=["choice"])
    exam_attempt_id = start(env)
    homework = _lesson_homework(env)
    _start_homework(env.student, homework)
    db = env.app.state.session_factory()
    try:
        user_id = db.query(User).filter_by(username="learner").one().id
    finally:
        db.close()
    teacher, headers = _role_login(env.app, "teacher")

    exam_overview = teacher.get("/api/admin/exam-results", headers=headers)
    assert exam_overview.status_code == 200
    assert exam_overview.json()["items"] == []

    homework_overview = teacher.get("/api/admin/lesson-homework-results", headers=headers)
    assert homework_overview.status_code == 200
    assert homework_overview.json()["items"] == []

    block_id = homework["block"]["id"]
    # 范围为空的整体早退：拒绝理由与任何具体学生记录无关，保持 403（《39》§3.3）。
    denied_paths = [
        f"/api/admin/lesson-homework/{block_id}/results",
        f"/api/admin/lesson-homework/{block_id}/students/{user_id}/attempts",
        f"/api/admin/lesson-homework/{block_id}/records/1",
        f"/api/admin/lesson-homework/{block_id}/item-analysis",
        f"/api/admin/links/{env.link_id}/results",
        f"/api/admin/links/{env.link_id}/item-analysis",
    ]
    for path in denied_paths:
        response = teacher.get(path, headers=headers)
        assert response.status_code == 403, f"{path}: {response.status_code} {response.text}"

    # 资源寻址型的学生记录：越界必须与「不存在」不可区分（《39》§3.2）。
    review = teacher.get(f"/api/admin/attempts/{exam_attempt_id}/review", headers=headers)
    assert review.status_code == 404, review.text


def test_nonempty_scope_filters_aggregates_and_blocks_attempt_id_passthrough(tmp_path,
                                                                            monkeypatch):
    env = build_exam(tmp_path, only=["choice"])
    learner_attempt = start(env)
    other = _second_student(env)
    other_started = other.post(f"/api/exam/{env.token}/start", headers=scsrf(other))
    assert other_started.status_code == 201, other_started.text
    other_attempt = other_started.json()["attempt_id"]
    homework = _lesson_homework(env)
    _start_homework(env.student, homework)
    _start_homework(other, homework)

    db = env.app.state.session_factory()
    try:
        learner_id = db.query(User).filter_by(username="learner").one().id
    finally:
        db.close()
    monkeypatch.setattr(admin_results, "visible_student_ids",
                        lambda _admin, _db: {learner_id})

    overview = env.admin.get("/api/admin/exam-results", headers=env.admin_headers).json()
    assert overview["items"][0]["participants"] == 1
    assert overview["items"][0]["attempts"] == 1

    detail = env.admin.get(f"/api/admin/links/{env.link_id}/results",
                           headers=env.admin_headers).json()
    assert [row["user"]["id"] for row in detail["students"]] == [learner_id]

    homework_overview = env.admin.get("/api/admin/lesson-homework-results",
                                      headers=env.admin_headers).json()
    assert homework_overview["items"][0]["participants"] == 1
    homework_detail = env.admin.get(
        f"/api/admin/lesson-homework/{homework['block']['id']}/results",
        headers=env.admin_headers,
    ).json()
    assert [row["user"]["id"] for row in homework_detail["students"]] == [learner_id]

    assert env.admin.get(f"/api/admin/attempts/{learner_attempt}/review",
                         headers=env.admin_headers).status_code == 200
    # 越界的答卷与压根不存在的答卷必须逐字同响应，否则遍历 ID 就能枚举出
    # 系统里有哪些作答记录（《39》§3.2、E1 验收标准第 6 条）。
    denied = env.admin.get(f"/api/admin/attempts/{other_attempt}/review",
                           headers=env.admin_headers)
    missing = env.admin.get("/api/admin/attempts/99999/review",
                            headers=env.admin_headers)
    assert denied.status_code == missing.status_code == 404
    assert denied.json() == missing.json()


def test_nonempty_scope_reaches_scratch_homework_detail_history_and_record(tmp_path,
                                                                           monkeypatch):
    app = scratch_env(tmp_path)
    built = build_scratch_lesson(app)
    block_id = built["block_ids"][0]
    submissions = {}
    for username in ("visiblekid", "hiddenkid"):
        student = student_login(app, username)
        project_id = open_block(student, block_id).json()["project"]["id"]
        save_project(student, project_id, sb3_bytes())
        submissions[username] = submit(student, block_id).json()["submission_id"]

    db = app.state.session_factory()
    try:
        users = {user.username: user.id for user in db.query(User).all()}
    finally:
        db.close()
    monkeypatch.setattr(admin_results, "visible_student_ids",
                        lambda _admin, _db: {users["visiblekid"]})

    overview = built["client"].get("/api/admin/lesson-homework-results",
                                   headers=built["headers"]).json()
    scratch_row = next(row for row in overview["items"] if row["kind"] == "scratch")
    assert scratch_row["participants"] == 1

    detail = built["client"].get(
        f"/api/admin/lesson-homework/{block_id}/results", headers=built["headers"])
    assert detail.status_code == 200, detail.text
    assert [row["user"]["id"] for row in detail.json()["students"]] == [users["visiblekid"]]

    # 范围外的学员与「查无此记录」必须逐字同响应（《39》§3.2）：否则拿 user_id
    # 遍历就能问出某个学员到底有没有交过这份作业。
    hidden_history = built["client"].get(
        f"/api/admin/lesson-homework/{block_id}/students/{users['hiddenkid']}/attempts",
        headers=built["headers"],
    )
    missing_history = built["client"].get(
        f"/api/admin/lesson-homework/{block_id}/students/99999/attempts",
        headers=built["headers"],
    )
    assert hidden_history.status_code == missing_history.status_code == 404
    assert hidden_history.json() == missing_history.json()

    hidden_record = built["client"].get(
        f"/api/admin/lesson-homework/{block_id}/records/{submissions['hiddenkid']}",
        headers=built["headers"],
    )
    missing_record = built["client"].get(
        f"/api/admin/lesson-homework/{block_id}/records/99999",
        headers=built["headers"],
    )
    assert hidden_record.status_code == missing_record.status_code == 404
    assert hidden_record.json() == missing_record.json()
