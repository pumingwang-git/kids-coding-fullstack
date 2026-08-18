"""管理端学员目录：范围过滤、分页排序与单项范围闸。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..models import User
from ..permissions import can_read_students, log_scope_denial, visible_student_ids
from .admin_auth import current_admin, db_session

router = APIRouter(prefix="/api/admin/students", tags=["admin-students"])

# User.status 由注册与邮箱验证流程维护；管理端只消费服务端下发的标签。
STUDENT_STATUS_LABELS = {
    "pending_verification": "待验证",
    "active": "正常",
}

_SORTABLE_COLUMNS = {
    "id": User.id,
    "username": User.username,
    "email": User.email,
    "status": User.status,
    "created_at": User.created_at,
    "updated_at": User.updated_at,
}


def _serialize_student(row: User) -> dict:
    return {
        "id": row.id,
        "username": row.username,
        "email": row.email,
        "status": row.status,
        "status_label": STUDENT_STATUS_LABELS[row.status],
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _student_statement(admin, db: Session, keyword: str):
    student_ids = visible_student_ids(admin, db)
    statement = select(User)
    count_statement = select(func.count()).select_from(User)
    filters = []
    if student_ids is not None:
        filters.append(User.id.in_(student_ids))
    term = keyword.strip()
    if term:
        matches = [User.username.ilike(f"%{term}%"), User.email.ilike(f"%{term}%")]
        if term.isdigit():
            matches.append(User.id == int(term))
        filters.append(or_(*matches))
    if filters:
        statement = statement.where(*filters)
        count_statement = count_statement.where(*filters)
    return statement, count_statement


def _require_student_reader(request: Request, db: Session):
    admin = current_admin(request, db)
    if not can_read_students(admin):
        raise HTTPException(403, "没有查看学员的权限。")
    return admin


@router.get("")
def list_students(
    request: Request,
    keyword: str = Query("", max_length=100),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    sort: str = Query("id", max_length=32),
    db: Session = Depends(db_session),
):
    """返回当前管理员可见学员的稳定分页列表。"""
    admin = _require_student_reader(request, db)
    statement, count_statement = _student_statement(admin, db, keyword)

    descending = sort.startswith("-")
    field = sort[1:] if descending else sort
    column = _SORTABLE_COLUMNS.get(field)
    if column is None:
        raise HTTPException(422, "不支持的排序字段。")
    order = column.desc() if descending else column.asc()
    id_order = User.id.desc() if descending else User.id.asc()
    rows = db.scalars(
        statement.order_by(order, id_order).offset((page - 1) * page_size).limit(page_size)
    ).all()
    total = db.scalar(count_statement) or 0
    return {
        "items": [_serialize_student(row) for row in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/{student_id}")
def get_student(student_id: int, request: Request, db: Session = Depends(db_session)):
    """按 ID 读取学员；越界与不存在共用一条 404，避免泄露存在性。"""
    admin = _require_student_reader(request, db)
    student = db.get(User, student_id)
    student_ids = visible_student_ids(admin, db)
    out_of_scope = student is not None and student_ids is not None and student_id not in student_ids
    if out_of_scope:
        log_scope_denial(admin, "student", student_id)
    if student is None or out_of_scope:
        raise HTTPException(404, "学员不存在。")
    return _serialize_student(student)
