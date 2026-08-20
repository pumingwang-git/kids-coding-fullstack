"""班级学情的只读派生计算。

本模块只读取数据库并返回计算结果，不注册路由，也不产生写入副作用。
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import ClassGroup, ClassMember


def _active_student_ids(db: Session, class_id: int) -> set[int]:
    return set(db.scalars(select(ClassMember.student_id).where(
        ClassMember.class_id == class_id,
        ClassMember.status == "active",
        ClassMember.left_at.is_(None),
    )))


def build_class_insight(db: Session, class_id: int) -> dict:
    """Return the T5 class metric owned by this composition point."""
    class_group = db.get(ClassGroup, class_id)
    if class_group is None:
        raise LookupError("班级不存在。")

    student_ids = _active_student_ids(db, class_id)
    return {"enrolled_people": len(student_ids)}
