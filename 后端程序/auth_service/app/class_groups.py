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
    if not class_ids:
        return set()
    return set(
        db.scalars(
            select(ClassMember.student_id).where(
                ClassMember.class_id.in_(class_ids),
                ClassMember.status == "active",
                ClassMember.left_at.is_(None),
            )
        ).all()
    )


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
