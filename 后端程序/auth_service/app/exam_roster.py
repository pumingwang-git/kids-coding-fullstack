"""考试指派名单的反向解析。"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .class_groups import active_student_ids_for_classes
from .models import ExamAssignment


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
