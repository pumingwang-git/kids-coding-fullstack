import csv
import io
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import event
from test_admin_classes import login_as_role, seed_course, seed_student
from test_exam import admin_login, build_app
from test_homework_roster import _seed_roster
from test_weak_items import _seed_class

from app.lesson_homework_kinds import PAPER_KIND
from app.models import (
    ClassMember, ClassTeacher, CourseLessonBlock, ExamAssignment, ExamLink,
    LessonProblemAttempt, LessonProblemBlock, Paper, PaperAttempt, Problem,
    ScratchSubmission,
)


def test_teaching_classes_enforces_reader_roles_and_empty_teacher_scope(tmp_path: Path):
    app = build_app(tmp_path)
    manager, manager_headers = admin_login(app)
    course_id = seed_course(app)
    class_id = manager.post(
        "/api/admin/classes", headers=manager_headers,
        json={"name": "教师工作台班", "course_id": course_id},
    ).json()["id"]

    for role in ("editor", "reviewer"):
        client, headers = login_as_role(app, role, admin_id=10 if role == "editor" else 11)
        assert client.get("/api/admin/teaching/classes", headers=headers).status_code == 403

    teacher, teacher_headers = login_as_role(app, "teacher", admin_id=12)
    assert teacher.get("/api/admin/teaching/classes", headers=teacher_headers).json() == {
        "items": []
    }

    db = app.state.session_factory()
    try:
        db.add(ClassTeacher(class_id=class_id, admin_user_id=12, role_in_class="teacher"))
        db.commit()
    finally:
        db.close()
    response = teacher.get("/api/admin/teaching/classes", headers=teacher_headers)
    assert response.status_code == 200
    assert [row["id"] for row in response.json()["items"]] == [class_id]


def test_teaching_classes_match_admin_classes_scope(tmp_path: Path):
    app = build_app(tmp_path)
    manager, manager_headers = admin_login(app)
    course_id = seed_course(app)
    class_ids = [
        manager.post(
            "/api/admin/classes", headers=manager_headers,
            json={"name": name, "course_id": course_id},
        ).json()["id"]
        for name in ("工作台一班", "工作台二班")
    ]
    unassigned_class_id = manager.post(
        "/api/admin/classes", headers=manager_headers,
        json={"name": "教师不带的班", "course_id": course_id},
    ).json()["id"]
    teacher, teacher_headers = login_as_role(app, "teacher", admin_id=13)
    db = app.state.session_factory()
    try:
        db.add(ClassTeacher(class_id=class_ids[0], admin_user_id=13, role_in_class="teacher"))
        db.add(
            ClassTeacher(
                class_id=class_ids[1], admin_user_id=13, role_in_class="assistant",
            )
        )
        db.commit()
    finally:
        db.close()

    teaching = teacher.get("/api/admin/teaching/classes", headers=teacher_headers)
    classes = teacher.get("/api/admin/classes", headers=teacher_headers)
    assert teaching.status_code == classes.status_code == 200
    assert {row["id"] for row in teaching.json()["items"]} == {
        row["id"] for row in classes.json()["items"]
    }
    assert unassigned_class_id not in {row["id"] for row in teaching.json()["items"]}


def test_teaching_overview_scope_denial_matches_missing_class(tmp_path: Path):
    app = build_app(tmp_path)
    manager, manager_headers = admin_login(app)
    course_id = seed_course(app)
    foreign_class_id = manager.post(
        "/api/admin/classes", headers=manager_headers,
        json={"name": "他人班级", "course_id": course_id},
    ).json()["id"]
    teacher, teacher_headers = login_as_role(app, "teacher", admin_id=14)

    foreign = teacher.get(
        f"/api/admin/teaching/classes/{foreign_class_id}/overview",
        headers=teacher_headers,
    )
    missing = teacher.get(
        "/api/admin/teaching/classes/99999/overview", headers=teacher_headers
    )
    assert foreign.status_code == missing.status_code == 404
    assert foreign.json() == missing.json() == {"detail": "班级不存在。"}


def test_teaching_router_does_not_query_teacher_relationships_directly():
    source = Path(__file__).parents[1] / "app" / "routers" / "admin_teaching.py"
    text = source.read_text(encoding="utf-8")
    assert "ClassTeacher" not in text
    assert "class_teachers" not in text


def test_teaching_class_insight_counts_only_active_members_and_keeps_empty_class_zero(
    tmp_path: Path,
):
    app = build_app(tmp_path)
    manager, manager_headers = admin_login(app)
    course_id = seed_course(app)
    enrolled_class_id = manager.post(
        "/api/admin/classes", headers=manager_headers,
        json={"name": "在读统计班", "course_id": course_id},
    ).json()["id"]
    empty_class_id = manager.post(
        "/api/admin/classes", headers=manager_headers,
        json={"name": "空班", "course_id": course_id},
    ).json()["id"]
    for student_id in (1, 2, 3):
        seed_student(app, student_id)

    db = app.state.session_factory()
    try:
        member_at = datetime.now(UTC)
        active_members = [
            ClassMember(
                class_id=enrolled_class_id,
                student_id=student_id,
                joined_at=member_at,
            )
            for student_id in (1, 2)
        ]
        withdrawn_member = ClassMember(
            class_id=enrolled_class_id,
            student_id=3,
            joined_at=member_at,
            left_at=member_at,
            status="left",
        )
        db.add_all([*active_members, withdrawn_member])
        db.commit()
    finally:
        db.close()

    response = manager.get("/api/admin/teaching/classes", headers=manager_headers)
    assert response.status_code == 200
    insights = {row["id"]: row["insight"] for row in response.json()["items"]}
    assert insights[enrolled_class_id]["enrolled_people"] == 2
    assert insights[empty_class_id]["enrolled_people"] == 0


def _teaching_class_query_count(tmp_path: Path, class_count: int) -> int:
    app = build_app(tmp_path)
    manager, manager_headers = admin_login(app)
    course_id = seed_course(app)
    for index in range(class_count):
        manager.post(
            "/api/admin/classes", headers=manager_headers,
            json={"name": f"批量统计班 {index}", "course_id": course_id},
        )

    statements = []
    engine = app.state.session_factory().get_bind()

    def count(_conn, _cursor, statement, _parameters, _context, _executemany):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", count)
    try:
        response = manager.get("/api/admin/teaching/classes", headers=manager_headers)
    finally:
        event.remove(engine, "before_cursor_execute", count)
    assert response.status_code == 200
    return len(statements)


def test_teaching_class_list_query_count_is_independent_of_class_count(tmp_path: Path):
    assert _teaching_class_query_count(tmp_path / "one", 1) == _teaching_class_query_count(
        tmp_path / "twenty", 20
    )


def _teaching_class(app, client, headers, name="端点接线班"):
    course_id = seed_course(app)
    return client.post(
        "/api/admin/classes", headers=headers,
        json={"name": name, "course_id": course_id},
    ).json()["id"]


def test_new_teaching_endpoints_enforce_capability_and_class_scope(tmp_path: Path):
    app = build_app(tmp_path)
    manager, manager_headers = admin_login(app)
    class_id = _teaching_class(app, manager, manager_headers)
    teacher, teacher_headers = login_as_role(app, "teacher", admin_id=31)
    editor, editor_headers = login_as_role(app, "editor", admin_id=32)

    class_paths = (
        f"/api/admin/teaching/classes/{class_id}/students",
        f"/api/admin/teaching/classes/{class_id}/homework",
        f"/api/admin/teaching/classes/{class_id}/exams",
        f"/api/admin/teaching/classes/{class_id}/weak-items",
    )
    for path in (*class_paths, "/api/admin/teaching/review-queue"):
        assert editor.get(path, headers=editor_headers).status_code == 403

    for path in class_paths:
        foreign = teacher.get(path, headers=teacher_headers)
        missing = teacher.get(path.replace(str(class_id), "99999"), headers=teacher_headers)
        assert foreign.status_code == missing.status_code == 404
        assert foreign.json() == missing.json() == {"detail": "班级不存在。"}

    # A teacher with no class has an empty list endpoint, not a fabricated 404.
    assert teacher.get("/api/admin/teaching/review-queue", headers=teacher_headers).json() == {
        "items": [], "total": 0,
    }


def test_teaching_students_paginates_keeps_never_active_and_rejoining_member(tmp_path: Path):
    app = build_app(tmp_path)
    manager, manager_headers = admin_login(app)
    class_id = _teaching_class(app, manager, manager_headers, "学习活动班")
    teacher, teacher_headers = login_as_role(app, "teacher", admin_id=33)
    db = app.state.session_factory()
    try:
        db.add(ClassTeacher(class_id=class_id, admin_user_id=33, role_in_class="teacher"))
        for student_id in range(100, 125):
            seed_student(app, student_id)
            db.add(ClassMember(class_id=class_id, student_id=student_id))
        outsider_id = 125
        seed_student(app, outsider_id)
        withdrawn = ClassMember(
            class_id=class_id, student_id=outsider_id, status="left",
            joined_at=datetime.now(UTC), left_at=datetime.now(UTC),
        )
        db.add(withdrawn)
        db.commit()
    finally:
        db.close()

    first = teacher.get(
        f"/api/admin/teaching/classes/{class_id}/students?page=1&page_size=20",
        headers=teacher_headers,
    )
    second = teacher.get(
        f"/api/admin/teaching/classes/{class_id}/students?page=2&page_size=20",
        headers=teacher_headers,
    )
    assert first.status_code == second.status_code == 200
    assert first.json()["total"] == 25
    first_ids = {row["student"]["id"] for row in first.json()["items"]}
    second_ids = {row["student"]["id"] for row in second.json()["items"]}
    assert len(first_ids) == 20
    assert len(second_ids) == 5
    assert first_ids.isdisjoint(second_ids)
    assert all(row["never_active"] is True and row["inactive_days"] is None for row in first.json()["items"])
    assert outsider_id not in first_ids | second_ids
    assert teacher.get(
        f"/api/admin/teaching/classes/{class_id}/students?sort=unknown", headers=teacher_headers
    ).status_code == 422

    db = app.state.session_factory()
    try:
        old = db.query(ClassMember).filter_by(class_id=class_id, student_id=outsider_id).one()
        old.status, old.left_at = "left", datetime.now(UTC)
        db.add(ClassMember(class_id=class_id, student_id=outsider_id))
        db.commit()
    finally:
        db.close()
    rejoined = teacher.get(
        f"/api/admin/teaching/classes/{class_id}/students?page_size=100", headers=teacher_headers
    )
    assert outsider_id in {row["student"]["id"] for row in rejoined.json()["items"]}


def test_teaching_class_export_is_scoped_utf8_csv_and_ignores_unknown_filters(tmp_path: Path):
    app = build_app(tmp_path)
    manager, manager_headers = admin_login(app)
    class_id = _teaching_class(app, manager, manager_headers, "学情导出班")
    teacher, teacher_headers = login_as_role(app, "teacher", admin_id=35)
    db = app.state.session_factory()
    try:
        db.add(ClassTeacher(class_id=class_id, admin_user_id=35, role_in_class="teacher"))
        for student_id in (301, 302):
            seed_student(app, student_id)
            db.add(ClassMember(class_id=class_id, student_id=student_id))
        seed_student(app, 303)
        db.add(ClassMember(class_id=class_id, student_id=303, status="left", left_at=datetime.now(UTC)))
        db.commit()
    finally:
        db.close()

    response = teacher.get(
        f"/api/admin/teaching/classes/{class_id}/export?unexpected=value",
        headers=teacher_headers,
    )
    listing = teacher.get(
        f"/api/admin/teaching/classes/{class_id}/students?page_size=100",
        headers=teacher_headers,
    )
    assert response.status_code == 200
    assert response.content.startswith(b"\xef\xbb\xbf")
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]
    rows = list(csv.DictReader(io.StringIO(response.content.decode("utf-8-sig"))))
    assert len(rows) == listing.json()["total"] == 2
    assert {int(row["学员ID"]) for row in rows} == {301, 302}
    assert "用户名" in rows[0]
    assert not any("answer" in key.lower() or "problem_id_no" in key.lower() for key in rows[0])


def test_review_queue_endpoint_filters_to_teacher_students_and_is_stable(tmp_path: Path):
    app = build_app(tmp_path)
    manager, manager_headers = admin_login(app)
    class_id = _teaching_class(app, manager, manager_headers, "批改队列班")
    teacher, teacher_headers = login_as_role(app, "teacher", admin_id=34)
    db = app.state.session_factory()
    try:
        # The queue query only reads submission metadata; fixture IDs below avoid
        # constructing an unrelated Scratch project graph.
        db.connection().exec_driver_sql("PRAGMA foreign_keys = OFF")
        db.add(ClassTeacher(class_id=class_id, admin_user_id=34, role_in_class="teacher"))
        seed_student(app, 201)
        seed_student(app, 202)
        db.add(ClassMember(class_id=class_id, student_id=201))
        submitted_at = datetime.now(UTC) - timedelta(days=1)
        db.add_all([
            ScratchSubmission(id=801, user_id=201, lesson_block_id=1, lesson_id=1,
                              project_id=1, project_revision_id=1, challenge_id=1,
                              status="needs_review", submitted_at=submitted_at),
            ScratchSubmission(id=802, user_id=201, lesson_block_id=1, lesson_id=1,
                              project_id=1, project_revision_id=1, challenge_id=1,
                              attempt_no=2, status="needs_review", submitted_at=submitted_at),
            ScratchSubmission(id=803, user_id=202, lesson_block_id=1, lesson_id=1,
                              project_id=1, project_revision_id=1, challenge_id=1,
                              status="needs_review", submitted_at=submitted_at),
            ScratchSubmission(id=804, user_id=201, lesson_block_id=1, lesson_id=1,
                              project_id=1, project_revision_id=1, challenge_id=1,
                              attempt_no=3, status="returned", submitted_at=submitted_at),
        ])
        db.commit()
    finally:
        db.close()

    response = teacher.get("/api/admin/teaching/review-queue", headers=teacher_headers)
    assert response.status_code == 200
    assert [row["submission_id"] for row in response.json()["items"]] == [801, 802]
    assert response.json()["total"] == 2
    assert response.json()["items"][0]["review_endpoint"] == "scratch-review.html?submission_id=801"


def test_teaching_homework_route_uses_existing_roster_dto(tmp_path: Path):
    app = build_app(tmp_path)
    teacher, headers = login_as_role(app, "teacher", admin_id=35)
    db = app.state.session_factory()
    try:
        db.connection().exec_driver_sql("PRAGMA foreign_keys = OFF")
        group, block, blocked, submitted = _seed_roster(db, PAPER_KIND)
        db.add(ClassTeacher(class_id=group.id, admin_user_id=35, role_in_class="teacher"))
        db.commit()
    finally:
        db.close()

    response = teacher.get(f"/api/admin/teaching/classes/{group.id}/homework", headers=headers)
    assert response.status_code == 200
    item = response.json()["items"][0]
    assert {key: item[key] for key in (
        "source_type", "source_id", "title", "roster_people", "submitted_people",
        "not_submitted_people", "submitted_attempts",
    )} == {
        "source_type": "lesson_homework", "source_id": block.id, "title": block.title,
        "roster_people": 2, "submitted_people": 1, "not_submitted_people": 1,
        "submitted_attempts": 1,
    }
    assert [row["student"]["id"] for row in item["not_submitted"]] == [blocked.id]
    assert submitted.id not in {
        row["student"]["id"] for row in item["not_submitted"]
    }


def test_teaching_exams_route_exposes_unknown_roster_without_question_fields(tmp_path: Path):
    app = build_app(tmp_path)
    manager, manager_headers = admin_login(app)
    class_id = _teaching_class(app, manager, manager_headers, "当前考试班")
    known_class_id = _teaching_class(app, manager, manager_headers, "同教师考试班")
    foreign_class_id = _teaching_class(app, manager, manager_headers, "他人考试班")
    teacher, headers = login_as_role(app, "teacher", admin_id=36)
    db = app.state.session_factory()
    try:
        paper = Paper(title="名单未知卷", status="published")
        foreign_paper = Paper(title="他人班卷", status="published")
        db.add_all([
            paper, foreign_paper,
            ClassTeacher(class_id=class_id, admin_user_id=36, role_in_class="teacher"),
            ClassTeacher(class_id=known_class_id, admin_user_id=36, role_in_class="teacher"),
        ])
        db.flush()
        known_link = ExamLink(paper_id=paper.id, name="同教师另一班考试", access_token="known-roster-link")
        foreign_link = ExamLink(paper_id=foreign_paper.id, name="他人班考试", access_token="foreign-roster-link")
        db.add_all([known_link, foreign_link])
        db.flush()
        db.add_all([
            ExamAssignment(exam_link_id=known_link.id, target_type="class", target_id=known_class_id),
            ExamAssignment(exam_link_id=foreign_link.id, target_type="class", target_id=foreign_class_id),
        ])
        db.commit()
    finally:
        db.close()

    response = teacher.get(f"/api/admin/teaching/classes/{class_id}/exams", headers=headers)
    assert response.status_code == 200
    assert [item["exam_link_id"] for item in response.json()["items"]] == [known_link.id]
    assert response.json()["items"][0]["roster_people"] is None
    assert response.json()["items"][0]["not_submitted_people"] is None

    def walk(node):
        if isinstance(node, dict):
            assert {"problem_id_no", "questions", "test_case", "answer"}.isdisjoint(node)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(response.json())


def test_teaching_exams_route_keeps_assigned_participation_and_all_phases(tmp_path: Path):
    app = build_app(tmp_path)
    manager, manager_headers = admin_login(app)
    class_id = _teaching_class(app, manager, manager_headers, "考试相位班")
    teacher, headers = login_as_role(app, "teacher", admin_id=38)
    db = app.state.session_factory()
    try:
        seed_student(app, 401)
        db.add_all([
            ClassTeacher(class_id=class_id, admin_user_id=38, role_in_class="teacher"),
            ClassMember(class_id=class_id, student_id=401),
        ])
        now = datetime.now(UTC)
        papers = [Paper(title=f"相位卷{index}", status="published") for index in range(3)]
        db.add_all(papers)
        db.flush()
        links = [
            ExamLink(paper_id=papers[0].id, name="未开始", access_token="phase-upcoming",
                     open_at=now + timedelta(days=1), close_at=now + timedelta(days=2)),
            ExamLink(paper_id=papers[1].id, name="进行中", access_token="phase-running",
                     open_at=now - timedelta(days=1), close_at=now + timedelta(days=1)),
            ExamLink(paper_id=papers[2].id, name="已结束", access_token="phase-ended",
                     open_at=now - timedelta(days=2), close_at=now - timedelta(days=1)),
        ]
        db.add_all(links)
        db.flush()
        db.add_all([
            *(ExamAssignment(exam_link_id=link.id, target_type="class", target_id=class_id) for link in links),
            PaperAttempt(source_type="exam_link", source_id=links[1].id,
                         exam_link_id=links[1].id, paper_id=papers[1].id, user_id=401,
                         attempt_no=1, status="submitted"),
        ])
        db.commit()
    finally:
        db.close()

    response = teacher.get(f"/api/admin/teaching/classes/{class_id}/exams", headers=headers)
    assert response.status_code == 200
    by_name = {item["name"]: item for item in response.json()["items"]}
    assert {name: by_name[name]["phase"] for name in ("未开始", "进行中", "已结束")} == {
        "未开始": "upcoming", "进行中": "running", "已结束": "ended",
    }
    assert by_name["进行中"]["roster_people"] == 1
    assert by_name["进行中"]["submitted_people"] == 1
    assert by_name["进行中"]["not_submitted_people"] == 0


def test_teaching_weak_items_route_projects_practice_correct_rate(tmp_path: Path):
    app = build_app(tmp_path)
    teacher, headers = login_as_role(app, "teacher", admin_id=37)
    db = app.state.session_factory()
    try:
        group, lesson, students = _seed_class(db, users=1)
        problem = Problem(type="choice", title="端点练习题", stem="题干", status="approved",
                          problem_id_no="ROUTE-PR-1", version_no=1, revision=1)
        block = CourseLessonBlock(lesson_id=lesson.id, block_type="practice", title="端点练习", sort_order=0)
        db.add_all([problem, block, ClassTeacher(class_id=group.id, admin_user_id=37, role_in_class="teacher")])
        db.flush()
        problem.root_problem_id = problem.id
        db.add_all([
            LessonProblemBlock(block_id=block.id, problem_id_no=problem.problem_id_no,
                               problem_type=problem.type, display_no="1", score=10),
            LessonProblemAttempt(user_id=students[0].id, block_id=block.id, lesson_id=lesson.id,
                                 tries=1, last_correct=True),
        ])
        db.commit()
    finally:
        db.close()

    response = teacher.get(f"/api/admin/teaching/classes/{group.id}/weak-items", headers=headers)
    assert response.status_code == 200
    row = response.json()["items"][0]
    assert row["practice_correct_rate"] == 1.0
    assert "score_rate" not in row
    assert "paper_score_rate" not in row


def test_student_profile_reuses_class_workbench_data_without_sensitive_fields(tmp_path: Path):
    app = build_app(tmp_path)
    teacher, headers = login_as_role(app, "teacher", admin_id=39)
    db = app.state.session_factory()
    try:
        db.connection().exec_driver_sql("PRAGMA foreign_keys = OFF")
        group, homework_block, _blocked, student = _seed_roster(db, PAPER_KIND)
        db.add(ClassTeacher(class_id=group.id, admin_user_id=39, role_in_class="teacher"))

        problem = Problem(type="choice", title="档案练习题", stem="题干", status="approved",
                          problem_id_no="PROFILE-PR-1", version_no=1, revision=1)
        practice_block = CourseLessonBlock(
            lesson_id=homework_block.lesson_id, block_type="practice", title="档案练习", sort_order=1,
        )
        exam_paper = Paper(title="档案考试卷", status="published")
        db.add_all([problem, practice_block, exam_paper])
        db.flush()
        problem.root_problem_id = problem.id
        link = ExamLink(paper_id=exam_paper.id, name="档案考试", access_token="profile-exam-link")
        db.add_all([
            LessonProblemBlock(block_id=practice_block.id, problem_id_no=problem.problem_id_no,
                               problem_type=problem.type, display_no="1", score=10),
            LessonProblemAttempt(user_id=student.id, block_id=practice_block.id,
                                 lesson_id=homework_block.lesson_id, tries=1, last_correct=True),
            link,
        ])
        db.flush()
        db.add_all([
            ExamAssignment(exam_link_id=link.id, target_type="class", target_id=group.id),
            PaperAttempt(source_type="exam_link", source_id=link.id, exam_link_id=link.id,
                         paper_id=exam_paper.id, user_id=student.id, attempt_no=1,
                         status="submitted"),
        ])
        db.commit()
    finally:
        db.close()

    profile = teacher.get(
        f"/api/admin/teaching/students/{student.id}/profile", headers=headers
    )
    homework = teacher.get(
        f"/api/admin/teaching/classes/{group.id}/homework", headers=headers
    )
    students = teacher.get(
        f"/api/admin/teaching/classes/{group.id}/students", headers=headers
    )
    exams = teacher.get(
        f"/api/admin/teaching/classes/{group.id}/exams", headers=headers
    )
    weak_items = teacher.get(
        f"/api/admin/teaching/classes/{group.id}/weak-items", headers=headers
    )
    assert all(response.status_code == 200 for response in (
        profile, homework, students, exams, weak_items,
    ))

    body = profile.json()
    homework_item = next(item for item in homework.json()["items"]
                         if item["source_id"] == homework_block.id)
    homework_row = next(row for row in homework_item["roster"]
                        if row["student"]["id"] == student.id)
    assert body["homework"] == [{
        "class_id": group.id,
        "source_type": homework_item["source_type"],
        "source_id": homework_item["source_id"],
        "title": homework_item["title"],
        **homework_row,
    }]

    student_activity = next(row for row in students.json()["items"]
                            if row["student"]["id"] == student.id)
    assert body["learning"] == {
        key: value for key, value in student_activity.items() if key != "student"
    }
    exam_item = next(item for item in exams.json()["items"] if item["exam_link_id"] == link.id)
    exam_row = next(row for row in exam_item["roster"] if row["student"]["id"] == student.id)
    assert body["exams"] == [{
        "class_id": group.id,
        "exam_link_id": link.id,
        "name": exam_item["name"],
        "phase": exam_item["phase"],
        "phase_label": exam_item["phase_label"],
        **exam_row,
    }]
    weak_item = next(item for item in weak_items.json()["items"]
                     if item["source_id"] == practice_block.id)
    assert body["practice"] == [{
        "class_id": group.id,
        "source_type": "lesson_practice",
        "source_id": practice_block.id,
        "source_title": "档案练习",
        "practice_correct_rate": weak_item["practice_correct_rate"],
    }]

    forbidden = {"answer", "questions", "test_case", "problem_id_no", "code", "script"}

    def walk_keys(node):
        if isinstance(node, dict):
            assert forbidden.isdisjoint(node)
            for value in node.values():
                walk_keys(value)
        elif isinstance(node, list):
            for value in node:
                walk_keys(value)

    walk_keys(body)


def test_student_profile_scope_denial_matches_missing_and_empty_teacher_scope(tmp_path: Path):
    app = build_app(tmp_path)
    manager, manager_headers = admin_login(app)
    class_id = _teaching_class(app, manager, manager_headers, "档案范围班")
    seed_student(app, 501)
    teacher, headers = login_as_role(app, "teacher", admin_id=40)

    foreign = teacher.get(f"/api/admin/teaching/students/501/profile", headers=headers)
    missing = teacher.get("/api/admin/teaching/students/99999/profile", headers=headers)
    assert foreign.status_code == missing.status_code == 404
    assert foreign.json() == missing.json() == {"detail": "学员不存在。"}

    db = app.state.session_factory()
    try:
        db.add_all([
            ClassTeacher(class_id=class_id, admin_user_id=40, role_in_class="teacher"),
            ClassMember(class_id=class_id, student_id=501),
        ])
        db.commit()
    finally:
        db.close()
    assert teacher.get(
        "/api/admin/teaching/students/501/profile", headers=headers
    ).status_code == 200


def test_student_profile_practice_rate_is_per_student_and_omits_unanswered(tmp_path: Path):
    app = build_app(tmp_path)
    teacher, headers = login_as_role(app, "teacher", admin_id=41)
    db = app.state.session_factory()
    try:
        group, lesson, students = _seed_class(db, users=3)
        problem = Problem(
            type="choice", title="个人练习题", stem="题干", status="approved",
            problem_id_no="PROFILE-PERSONAL-1", version_no=1, revision=1,
        )
        block = CourseLessonBlock(
            lesson_id=lesson.id, block_type="practice", title="个人练习块", sort_order=0,
        )
        db.add_all([problem, block, ClassTeacher(
            class_id=group.id, admin_user_id=41, role_in_class="teacher"
        )])
        db.flush()
        problem.root_problem_id = problem.id
        db.add_all([
            LessonProblemBlock(
                block_id=block.id, problem_id_no=problem.problem_id_no,
                problem_type=problem.type, display_no="1", score=10,
            ),
            LessonProblemAttempt(
                user_id=students[0].id, block_id=block.id, lesson_id=lesson.id,
                tries=1, last_correct=True,
            ),
            LessonProblemAttempt(
                user_id=students[1].id, block_id=block.id, lesson_id=lesson.id,
                tries=1, last_correct=False,
            ),
        ])
        db.commit()
    finally:
        db.close()

    profiles = {
        student.id: teacher.get(
            f"/api/admin/teaching/students/{student.id}/profile", headers=headers
        ).json()
        for student in students
    }
    assert profiles[students[0].id]["practice"] == [{
        "class_id": group.id,
        "source_type": "lesson_practice",
        "source_id": block.id,
        "source_title": "个人练习块",
        "practice_correct_rate": 1.0,
    }]
    assert profiles[students[1].id]["practice"] == [{
        "class_id": group.id,
        "source_type": "lesson_practice",
        "source_id": block.id,
        "source_title": "个人练习块",
        "practice_correct_rate": 0.0,
    }]
    assert profiles[students[2].id]["practice"] == []
