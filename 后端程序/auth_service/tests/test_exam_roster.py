from datetime import UTC, datetime

import pytest
import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.exam_roster import assigned_student_ids
from app.models import (
    Base,
    ClassGroup,
    ClassMember,
    Course,
    ExamAssignment,
    ExamLink,
    LearningArea,
    Paper,
    User,
)
from app.student_tasks import collect_exam_candidates


@pytest.fixture
def db(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'exam-roster.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def _seed(db: Session):
    student = User(username="roster-student", email="roster@example.com", hashed_password="hash")
    paper = Paper(title="名单卷", status="published")
    db.add_all([student, paper, LearningArea(key="roster", name="名单", status="active")])
    db.flush()
    course = Course(title="名单课", area_key="roster")
    db.add(course)
    db.flush()
    group = ClassGroup(name="名单班", course_id=course.id, status="active")
    db.add(group)
    db.flush()
    db.add(ClassMember(class_id=group.id, student_id=student.id))
    link = ExamLink(
        paper_id=paper.id,
        name="名单考试",
        access_token="exam-roster-token",
        status="active",
    )
    db.add(link)
    db.commit()
    return student, group, link


@pytest.mark.parametrize(
    ("class_assigned", "student_assigned"),
    [(True, False), (False, True), (True, True), (False, False)],
    ids=["class-only", "student-only", "both", "neither"],
)
def test_assigned_students_and_student_candidates_agree(
    db, class_assigned: bool, student_assigned: bool
):
    student, group, link = _seed(db)
    if class_assigned:
        db.add(ExamAssignment(exam_link_id=link.id, target_type="class", target_id=group.id))
    if student_assigned:
        db.add(ExamAssignment(exam_link_id=link.id, target_type="student", target_id=student.id))
    db.commit()

    forward_ids = {source.source_id for source, _paper, _token in collect_exam_candidates(db, student)}
    assert (link.id in forward_ids) == (student.id in assigned_student_ids(db, link.id))


def test_leaving_class_removes_class_assignment_but_keeps_direct_assignment(db):
    student, group, link = _seed(db)
    class_assignment = ExamAssignment(exam_link_id=link.id, target_type="class", target_id=group.id)
    db.add(class_assignment)
    db.commit()
    assert assigned_student_ids(db, link.id) == {student.id}

    member = db.scalar(select(ClassMember).where(ClassMember.student_id == student.id))
    member.status = "left"
    member.left_at = datetime.now(UTC)
    db.commit()
    assert assigned_student_ids(db, link.id) == set()

    direct_assignment = ExamAssignment(exam_link_id=link.id, target_type="student", target_id=student.id)
    db.add(direct_assignment)
    db.commit()
    assert assigned_student_ids(db, link.id) == {student.id}

    direct_assignment.status = "ended"
    direct_assignment.ended_at = datetime.now(UTC)
    db.commit()
    assert assigned_student_ids(db, link.id) == set()
    assert db.scalar(select(sa.func.count()).select_from(ExamAssignment)) == 2


def test_unassigned_link_has_empty_roster(db):
    _student, _group, link = _seed(db)
    assert assigned_student_ids(db, link.id) == set()
