"""班级关系的只读查询。

写入、授权和审计留给后续班级接口；本模块只集中定义关系表的读取口径。
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import ClassMember, ClassTeacher, User


def active_students_for_class(db: Session, class_id: int) -> list[User]:
    """返回某班当前在读学生，按学生 ID 稳定排序。"""
    student_ids = active_student_ids_for_classes(db, {class_id})
    return list(
        db.scalars(
            select(User)
            .where(User.id.in_(student_ids))
            .order_by(User.id)
        ).all()
    )


def active_student_ids_for_classes(db: Session, class_ids: set[int]) -> set[int]:
    """返回多个班级当前在读学生 ID，复用统一的关系有效性口径。"""
    return set().union(*active_student_ids_by_class_for_classes(db, class_ids).values())


def active_student_ids_by_class_for_classes(
    db: Session, class_ids: set[int]
) -> dict[int, set[int]]:
    """返回多个班级各自当前在读学生 ID，保留班级归属。"""
    student_ids_by_class = {class_id: set() for class_id in class_ids}
    if not class_ids:
        return student_ids_by_class
    for class_id, student_id in db.execute(
        select(ClassMember.class_id, ClassMember.student_id).where(
            ClassMember.class_id.in_(class_ids),
            ClassMember.status == "active",
            ClassMember.left_at.is_(None),
        )
    ):
        student_ids_by_class[class_id].add(student_id)
    return student_ids_by_class


def active_class_teacher_assignments(db: Session, admin_user_id: int) -> list[ClassTeacher]:
    """返回某管理员当前在任的全部班级关系，按班级 ID 稳定排序。"""
    return list(
        db.scalars(
            select(ClassTeacher)
            .where(
                ClassTeacher.admin_user_id == admin_user_id,
                ClassTeacher.ended_at.is_(None),
            )
            .order_by(ClassTeacher.class_id, ClassTeacher.id)
        ).all()
    )


def active_teacher_assignments_for_class(db: Session, class_id: int) -> list[ClassTeacher]:
    """Return current teachers before assistants, then stable assignment order."""

    return list(
        db.scalars(
            select(ClassTeacher)
            .where(ClassTeacher.class_id == class_id, ClassTeacher.ended_at.is_(None))
            .order_by(
                # SQL boolean ordering is portable enough for our supported DBs.
                ClassTeacher.role_in_class != "teacher",
                ClassTeacher.assigned_at,
                ClassTeacher.id,
            )
        ).all()
    )
