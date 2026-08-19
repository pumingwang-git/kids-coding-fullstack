"""G8 学生考试列表：名单可见性、状态和零泄题契约。"""

from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import select

from app.models import ClassGroup, ClassMember, Course, ExamAssignment, ExamLink, LearningArea, Paper, User
from test_exam import build_app, student_login


def _student(app, username: str):
    client = student_login(app, username)
    db = app.state.session_factory()
    try:
        user = db.scalar(select(User).where(User.username == username))
        return user, client
    finally:
        db.close()


def _link(app, name: str, *, open_at=None, close_at=None, status="active"):
    db = app.state.session_factory()
    try:
        paper = Paper(title=f"{name} 卷", status="published")
        db.add(paper)
        db.flush()
        link = ExamLink(
            paper_id=paper.id,
            name=name,
            access_token=f"token-{name}",
            open_at=open_at,
            close_at=close_at,
            status=status,
        )
        db.add(link)
        db.commit()
        db.refresh(link)
        return link
    finally:
        db.close()


def _assign(app, link_id: int, target_type: str, target_id: int):
    db = app.state.session_factory()
    try:
        row = ExamAssignment(
            exam_link_id=link_id,
            target_type=target_type,
            target_id=target_id,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row
    finally:
        db.close()


def _walk_keys(value):
    if isinstance(value, dict):
        for key, child in value.items():
            yield key
            yield from _walk_keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_keys(child)


def _class_for(app, student_id: int):
    db = app.state.session_factory()
    try:
        db.add(LearningArea(key="exam-area", name="考试专区", status="active"))
        db.flush()
        course = Course(title="考试课包", area_key="exam-area")
        db.add(course)
        db.flush()
        group = ClassGroup(name="考试班", course_id=course.id, status="active")
        db.add(group)
        db.flush()
        member = ClassMember(class_id=group.id, student_id=student_id)
        db.add(member)
        db.commit()
        db.refresh(group)
        db.refresh(member)
        return group.id, member.id
    finally:
        db.close()


def test_exam_list_has_three_phases_and_never_returns_paper_content(tmp_path: Path):
    app = build_app(tmp_path)
    user, client = _student(app, "phase-student")
    now = datetime.now(UTC)
    links = [
        _link(app, "upcoming", open_at=now + timedelta(hours=2), close_at=now + timedelta(hours=3)),
        _link(app, "running", open_at=now - timedelta(hours=1), close_at=now + timedelta(hours=1)),
        _link(app, "ended", open_at=now - timedelta(hours=3), close_at=now - timedelta(hours=1)),
    ]
    for link in links:
        _assign(app, link.id, "student", user.id)

    response = client.get("/api/student/exams")
    assert response.status_code == 200, response.text
    body = response.json()
    assert {item["phase"] for item in body["items"]} == {"upcoming", "running", "ended"}
    assert all(item["open_at"].endswith("Z") for item in body["items"] if item["open_at"])
    assert not {"problem_id_no", "questions", "test_case", "answer", "paper_id"}.intersection(_walk_keys(body))


def test_exam_list_union_deduplicates_direct_and_class_assignments(tmp_path: Path):
    app = build_app(tmp_path)
    class_only, class_client = _student(app, "class-only")
    direct_only, direct_client = _student(app, "direct-only")
    both, both_client = _student(app, "both")
    class_id, _ = _class_for(app, class_only.id)
    db = app.state.session_factory()
    try:
        db.add(ClassMember(class_id=class_id, student_id=both.id))
        db.commit()
    finally:
        db.close()
    link = _link(app, "union-exam")
    _assign(app, link.id, "class", class_id)
    _assign(app, link.id, "student", direct_only.id)
    _assign(app, link.id, "student", both.id)
    assert len(class_client.get("/api/student/exams").json()["items"]) == 1
    assert len(direct_client.get("/api/student/exams").json()["items"]) == 1
    assert len(both_client.get("/api/student/exams").json()["items"]) == 1


def test_exam_list_leave_removes_class_assignment_but_keeps_direct_assignment(tmp_path: Path):
    app = build_app(tmp_path)
    user, client = _student(app, "leave-student")
    class_id, member_id = _class_for(app, user.id)
    class_link = _link(app, "class-exam")
    direct_link = _link(app, "direct-exam")
    _assign(app, class_link.id, "class", class_id)
    _assign(app, direct_link.id, "student", user.id)
    assert {item["scope"]["title"] for item in client.get("/api/student/exams").json()["items"]} == {"class-exam", "direct-exam"}
    db = app.state.session_factory()
    try:
        db.execute(
            ClassMember.__table__.update().where(ClassMember.id == member_id).values(
                status="left", left_at=datetime.now(UTC)
            )
        )
        db.commit()
    finally:
        db.close()
    assert [item["scope"]["title"] for item in client.get("/api/student/exams").json()["items"]] == ["direct-exam"]


def test_exam_list_cancelled_assignment_disappears_but_token_still_opens(tmp_path: Path):
    app = build_app(tmp_path)
    user, client = _student(app, "cancel-student")
    link = _link(app, "cancel-exam")
    row = _assign(app, link.id, "student", user.id)
    assert len(client.get("/api/student/exams").json()["items"]) == 1
    db = app.state.session_factory()
    try:
        db.execute(
            ExamAssignment.__table__.update().where(ExamAssignment.id == row.id).values(
                status="ended", ended_at=datetime.now(UTC)
            )
        )
        db.commit()
    finally:
        db.close()
    assert client.get("/api/student/exams").json()["items"] == []
    assert client.get(f"/api/exam/{link.access_token}").status_code == 200


def test_exam_list_filters_status_paginates_and_ignores_disabled_links(tmp_path: Path):
    app = build_app(tmp_path)
    user, client = _student(app, "filter-student")
    now = datetime.now(UTC)
    links = [_link(app, f"exam-{index}", open_at=now + timedelta(hours=index + 1)) for index in range(3)]
    for link in links:
        _assign(app, link.id, "student", user.id)
    disabled = _link(app, "disabled-exam", open_at=now + timedelta(hours=5), status="disabled")
    _assign(app, disabled.id, "student", user.id)
    upcoming = client.get("/api/student/exams?status=upcoming&page_size=2").json()
    assert upcoming["total"] == 3 and len(upcoming["items"]) == 2
    assert "disabled-exam" not in {item["scope"]["title"] for item in upcoming["items"]}
    assert client.get("/api/student/exams?status=invalid").status_code == 422
    assert client.get("/api/student/exams?page_size=101").status_code == 422


def test_exam_list_empty_scope_returns_empty_success(tmp_path: Path):
    app = build_app(tmp_path)
    _user, client = _student(app, "empty-student")
    assert client.get("/api/student/exams").json() == {
        "items": [], "total": 0, "page": 1, "page_size": 20,
    }
