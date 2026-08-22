"""班级学情的只读派生计算。

本模块只读取数据库并返回计算结果，不注册路由，也不产生写入副作用。
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from .class_groups import active_student_ids_by_class_for_classes


def build_class_insight(db: Session, class_ids: set[int]) -> dict[int, dict]:
    """Return T5 class metrics in one batch for the supplied class IDs."""
    student_ids_by_class = active_student_ids_by_class_for_classes(db, class_ids)
    return {
        class_id: {"enrolled_people": len(student_ids)}
        for class_id, student_ids in student_ids_by_class.items()
    }
