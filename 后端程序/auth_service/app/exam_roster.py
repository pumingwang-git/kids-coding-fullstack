"""考试指派名单与班级参与情况的反向取数。"""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .attempt_source import attempt_scope, from_exam_link
from .class_groups import active_student_ids_for_classes
from .models import ExamAssignment, ExamLink, PaperAttempt, User
from .student_tasks import EXAM_PHASE_LABELS, exam_phase


def assigned_student_ids(db: Session, link_id: int) -> set[int]:
    """返回当前被指派到考试链接的学生，班级成员只包括当前在读者。"""
    assignments = db.scalars(
        select(ExamAssignment).where(
            ExamAssignment.exam_link_id == link_id,
            ExamAssignment.status == "active",
        )
    ).all()
    student_ids = {
        assignment.target_id
        for assignment in assignments
        if assignment.target_type == "student"
    }
    class_ids = {
        assignment.target_id
        for assignment in assignments
        if assignment.target_type == "class"
    }
    return student_ids | active_student_ids_for_classes(db, class_ids)


def exam_participation(
    db: Session,
    link_id: int,
    class_id: int,
    now: datetime | None = None,
) -> dict:
    """返回一条考试链接在一个班级内的应考与参与情况。

    班级指派是否存在必须单独判断：``assigned_student_ids`` 的空集合同时表示
    空名单和未指派，不能承担 D4 的 ``null`` 语义。
    """
    link = db.get(ExamLink, link_id)
    if link is None:
        raise LookupError("考试链接不存在。")

    roster_exists = db.scalar(select(ExamAssignment.id).where(
        ExamAssignment.exam_link_id == link_id,
        ExamAssignment.target_type == "class",
        ExamAssignment.target_id == class_id,
        ExamAssignment.status == "active",
    )) is not None
    class_student_ids = active_student_ids_for_classes(db, {class_id})
    roster_ids = assigned_student_ids(db, link_id) & class_student_ids

    attempts = db.scalars(select(PaperAttempt).where(
        *attempt_scope(from_exam_link(link)),
        PaperAttempt.user_id.in_(roster_ids or [0]),
    )).all()
    attempts_by_student: dict[int, list[PaperAttempt]] = {}
    for attempt in attempts:
        attempts_by_student.setdefault(attempt.user_id, []).append(attempt)

    students = {
        student.id: student
        for student in db.scalars(select(User).where(User.id.in_(roster_ids or [0]))).all()
    }

    def row(student_id: int) -> dict:
        return {"student": {"id": student_id, "username": students[student_id].username},
                "attempts": len(attempts_by_student.get(student_id, []))}

    participated_ids = roster_ids & attempts_by_student.keys()
    not_participated_ids = roster_ids - participated_ids
    ordered = sorted(roster_ids)
    submitted = [row(student_id) for student_id in ordered if student_id in participated_ids]
    not_submitted = [row(student_id) for student_id in ordered
                     if student_id in not_participated_ids]
    phase = exam_phase(from_exam_link(link), now or datetime.now(UTC))
    roster_people = len(roster_ids) if roster_exists else None
    return {
        "exam_link_id": link.id,
        "name": link.name,
        "phase": phase,
        "phase_label": EXAM_PHASE_LABELS[phase],
        "roster": [row(student_id) for student_id in ordered] if roster_exists else [],
        "submitted": submitted,
        "not_submitted": not_submitted,
        "roster_people": roster_people,
        "submitted_people": len(participated_ids),
        "submitted_attempts": sum(len(items) for items in attempts_by_student.values()),
        "not_submitted_people": len(not_participated_ids) if roster_exists else None,
    }
