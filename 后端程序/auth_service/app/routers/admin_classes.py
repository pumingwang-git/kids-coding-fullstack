"""班级主数据管理：创建、修改、归档和受保护的物理删除。"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import AdminUser, ClassGroup, ClassMember, ClassTeacher, Course, User
from ..permissions import (
    ACADEMIC_ADMIN_ROLE,
    ASSISTANT_ROLE,
    SUPER_ROLE,
    TEACHER_ROLE,
    log_scope_denial,
    visible_class_ids,
)
from ..security import as_utc, utcnow
from .admin_auth import audit, client_ip, current_admin, db_session, require_csrf

router = APIRouter(prefix="/api/admin/classes", tags=["admin-classes"])
MANAGER_ROLES = frozenset({ACADEMIC_ADMIN_ROLE, SUPER_ROLE})
READER_ROLES = MANAGER_ROLES | frozenset({TEACHER_ROLE, ASSISTANT_ROLE})
CLASS_STATUS_LABELS = {
    "draft": "草稿",
    "active": "进行中",
    "archived": "已归档",
}
CLASS_ROLE_LABELS = {
    "teacher": "主讲教师",
    "assistant": "助教",
}


class ClassPayload(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    course_id: int = Field(gt=0)
    start_at: datetime | None = None
    end_at: datetime | None = None

    @model_validator(mode="after")
    def validate_time_range(self):
        self.name = self.name.strip()
        if not self.name:
            raise ValueError("班级名称不能为空。")
        if self.start_at and self.end_at and self.end_at < self.start_at:
            raise ValueError("结束时间不能早于开始时间。")
        return self


class TeacherAssignmentPayload(BaseModel):
    admin_user_id: int = Field(gt=0)
    role_in_class: Literal["teacher", "assistant"]


class MemberPayload(BaseModel):
    student_id: int = Field(gt=0)


class TransferPayload(BaseModel):
    to_class_id: int = Field(gt=0)


def _require_manager(request: Request, db: Session):
    admin = current_admin(request, db)
    if admin.role not in MANAGER_ROLES:
        raise HTTPException(403, "仅教务管理员或超级管理员可管理班级。")
    return admin


def _require_class_reader(
    request: Request, db: Session, class_id: int | None = None
):
    admin = current_admin(request, db)
    if admin.role not in READER_ROLES:
        raise HTTPException(403, "没有查看班级关系的权限。")
    class_ids = visible_class_ids(admin, db)
    if class_id is not None and class_ids is not None and class_id not in class_ids:
        log_scope_denial(admin, "class_group", class_id)
        raise HTTPException(404, "班级不存在。")
    return admin, class_ids


def _course_or_404(db: Session, course_id: int) -> Course:
    course = db.get(Course, course_id)
    if course is None:
        raise HTTPException(404, "课包不存在。")
    return course


def _serialize_class(row: ClassGroup) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        "course_id": row.course_id,
        "start_at": row.start_at,
        "end_at": row.end_at,
        "status": row.status,
        "status_label": CLASS_STATUS_LABELS[row.status],
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _utc_iso(value: datetime) -> str:
    """Serialize audit timestamps in the UTC ``Z`` form required by §37."""
    return as_utc(value).isoformat().replace("+00:00", "Z")


def _serialize_teacher(row: ClassTeacher) -> dict:
    return {
        "id": row.id,
        "class_id": row.class_id,
        "admin_user_id": row.admin_user_id,
        "role_in_class": row.role_in_class,
        "role_in_class_label": CLASS_ROLE_LABELS[row.role_in_class],
        "assigned_at": row.assigned_at,
        "ended_at": row.ended_at,
    }


def _serialize_member(row: ClassMember) -> dict:
    return {
        "id": row.id,
        "class_id": row.class_id,
        "student_id": row.student_id,
        "joined_at": row.joined_at,
        "left_at": row.left_at,
        "status": row.status,
    }


def _audit_failure(
    db: Session,
    request: Request,
    event: str,
    actor_id: int,
    *,
    resource_type: str,
    resource_id: int | None = None,
    summary: dict | None = None,
) -> None:
    audit(
        db,
        request.app.state.settings,
        event,
        "failure",
        client_ip(request),
        actor_id,
        resource_type=resource_type,
        resource_id=resource_id,
        summary=summary or {"schema_version": 1, "reason_code": "forbidden"},
    )
    db.commit()


def _require_relation_manager(
    request: Request,
    db: Session,
    event: str,
    *,
    resource_type: str,
    resource_id: int | None = None,
    summary: dict | None = None,
):
    admin = current_admin(request, db)
    if admin.role not in MANAGER_ROLES:
        _audit_failure(
            db,
            request,
            event,
            admin.id,
            resource_type=resource_type,
            resource_id=resource_id,
            summary=summary,
        )
        raise HTTPException(403, "仅教务管理员或超级管理员可管理班级关系。")
    return admin


def _class_for_relation_change(
    db: Session, class_id: int, *, allow_archived: bool = False
) -> ClassGroup:
    row = db.get(ClassGroup, class_id)
    if row is None:
        raise HTTPException(404, "班级不存在。")
    if row.status == "archived" and not allow_archived:
        raise HTTPException(409, "已归档班级不可变更关系。")
    return row


def _audit_success(
    db: Session,
    request: Request,
    event: str,
    admin_id: int,
    *,
    resource_type: str,
    resource_id: int,
    summary: dict,
) -> None:
    audit(
        db,
        request.app.state.settings,
        event,
        "success",
        client_ip(request),
        admin_id,
        resource_type=resource_type,
        resource_id=resource_id,
        summary=summary,
    )


@router.get("")
def list_classes(request: Request, db: Session = Depends(db_session)):
    _, class_ids = _require_class_reader(request, db)
    statement = select(ClassGroup)
    if class_ids is not None:
        statement = statement.where(ClassGroup.id.in_(class_ids))
    rows = db.scalars(statement.order_by(ClassGroup.id)).all()
    return {"items": [_serialize_class(row) for row in rows]}


@router.post("", status_code=201)
def create_class(
    payload: ClassPayload, request: Request, db: Session = Depends(db_session)
):
    require_csrf(request)
    _require_manager(request, db)
    _course_or_404(db, payload.course_id)
    row = ClassGroup(
        name=payload.name,
        course_id=payload.course_id,
        start_at=payload.start_at,
        end_at=payload.end_at,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _serialize_class(row)


@router.get("/{class_id}")
def get_class(class_id: int, request: Request, db: Session = Depends(db_session)):
    _require_class_reader(request, db, class_id)
    row = db.get(ClassGroup, class_id)
    if row is None:
        raise HTTPException(404, "班级不存在。")
    return _serialize_class(row)


@router.put("/{class_id}")
def update_class(
    class_id: int,
    payload: ClassPayload,
    request: Request,
    db: Session = Depends(db_session),
):
    require_csrf(request)
    _require_manager(request, db)
    row = db.get(ClassGroup, class_id)
    if row is None:
        raise HTTPException(404, "班级不存在。")
    if row.status == "archived":
        raise HTTPException(409, "已归档班级不可修改。")
    _course_or_404(db, payload.course_id)
    row.name = payload.name
    row.course_id = payload.course_id
    row.start_at = payload.start_at
    row.end_at = payload.end_at
    row.updated_at = utcnow()
    db.commit()
    db.refresh(row)
    return _serialize_class(row)


@router.post("/{class_id}/archive")
def archive_class(class_id: int, request: Request, db: Session = Depends(db_session)):
    require_csrf(request)
    _require_manager(request, db)
    row = db.get(ClassGroup, class_id)
    if row is None:
        raise HTTPException(404, "班级不存在。")
    if row.status != "archived":
        row.status = "archived"
        row.updated_at = utcnow()
        db.commit()
        db.refresh(row)
    return _serialize_class(row)


@router.delete("/{class_id}")
def delete_class(class_id: int, request: Request, db: Session = Depends(db_session)):
    require_csrf(request)
    _require_manager(request, db)
    row = db.get(ClassGroup, class_id)
    if row is None:
        raise HTTPException(404, "班级不存在。")
    member_count = db.scalar(
        select(func.count()).select_from(ClassMember).where(ClassMember.class_id == class_id)
    )
    teacher_count = db.scalar(
        select(func.count()).select_from(ClassTeacher).where(ClassTeacher.class_id == class_id)
    )
    if member_count or teacher_count:
        raise HTTPException(409, "已有班级成员或带班关系，班级不可物理删除。")
    db.delete(row)
    db.commit()
    return {"ok": True}


@router.get("/{class_id}/teachers")
def list_class_teachers(class_id: int, request: Request, db: Session = Depends(db_session)):
    _require_class_reader(request, db, class_id)
    if db.get(ClassGroup, class_id) is None:
        raise HTTPException(404, "班级不存在。")
    rows = db.scalars(
        select(ClassTeacher)
        .where(ClassTeacher.class_id == class_id)
        .order_by(ClassTeacher.assigned_at, ClassTeacher.id)
    ).all()
    return {"items": [_serialize_teacher(row) for row in rows]}


@router.post("/{class_id}/teachers", status_code=201)
def assign_class_teacher(
    class_id: int,
    payload: TeacherAssignmentPayload,
    request: Request,
    db: Session = Depends(db_session),
):
    require_csrf(request)
    admin = _require_relation_manager(
        request,
        db,
        "class_teacher_assign",
        resource_type="class_teacher",
        summary={
            "schema_version": 1,
            "class_id": class_id,
            "teacher_admin_user_id": payload.admin_user_id,
            "role_in_class": payload.role_in_class,
            "reason_code": "forbidden",
        },
    )
    _class_for_relation_change(db, class_id)
    if db.get(AdminUser, payload.admin_user_id) is None:
        raise HTTPException(404, "后台账号不存在。")
    if db.scalar(
        select(ClassTeacher.id).where(
            ClassTeacher.class_id == class_id,
            ClassTeacher.admin_user_id == payload.admin_user_id,
            ClassTeacher.ended_at.is_(None),
        )
    ) is not None:
        raise HTTPException(409, "该账号已在此班级任职。")
    assigned_at = utcnow()
    row = ClassTeacher(
        class_id=class_id,
        admin_user_id=payload.admin_user_id,
        role_in_class=payload.role_in_class,
        assigned_at=assigned_at,
    )
    db.add(row)
    db.flush()
    _audit_success(
        db,
        request,
        "class_teacher_assign",
        admin.id,
        resource_type="class_teacher",
        resource_id=row.id,
        summary={
            "schema_version": 1,
            "class_id": class_id,
            "teacher_admin_user_id": payload.admin_user_id,
            "role_in_class": payload.role_in_class,
            "assigned_at": _utc_iso(assigned_at),
        },
    )
    db.commit()
    db.refresh(row)
    return _serialize_teacher(row)


def _unassign_class_teacher(
    class_id: int, assignment_id: int, request: Request, db: Session
):
    require_csrf(request)
    admin = _require_relation_manager(
        request,
        db,
        "class_teacher_unassign",
        resource_type="class_teacher",
        resource_id=assignment_id,
        summary={"schema_version": 1, "reason_code": "forbidden"},
    )
    _class_for_relation_change(db, class_id, allow_archived=True)
    row = db.scalar(
        select(ClassTeacher).where(
            ClassTeacher.id == assignment_id, ClassTeacher.class_id == class_id
        )
    )
    if row is None:
        raise HTTPException(404, "带班关系不存在。")
    if row.ended_at is not None:
        raise HTTPException(409, "带班关系已经结束。")
    ended_at = utcnow()
    row.ended_at = ended_at
    _audit_success(
        db,
        request,
        "class_teacher_unassign",
        admin.id,
        resource_type="class_teacher",
        resource_id=row.id,
        summary={
            "schema_version": 1,
            "class_id": row.class_id,
            "teacher_admin_user_id": row.admin_user_id,
            "role_in_class": row.role_in_class,
            "ended_at": _utc_iso(ended_at),
        },
    )
    db.commit()
    db.refresh(row)
    return _serialize_teacher(row)


@router.post("/{class_id}/teachers/{assignment_id}/unassign")
def unassign_class_teacher(
    class_id: int,
    assignment_id: int,
    request: Request,
    db: Session = Depends(db_session),
):
    return _unassign_class_teacher(class_id, assignment_id, request, db)


@router.delete("/{class_id}/teachers/{assignment_id}")
def delete_class_teacher(
    class_id: int,
    assignment_id: int,
    request: Request,
    db: Session = Depends(db_session),
):
    return _unassign_class_teacher(class_id, assignment_id, request, db)


@router.get("/{class_id}/members")
def list_class_members(class_id: int, request: Request, db: Session = Depends(db_session)):
    _require_class_reader(request, db, class_id)
    if db.get(ClassGroup, class_id) is None:
        raise HTTPException(404, "班级不存在。")
    rows = db.scalars(
        select(ClassMember)
        .where(ClassMember.class_id == class_id)
        .order_by(ClassMember.joined_at, ClassMember.id)
    ).all()
    return {"items": [_serialize_member(row) for row in rows]}


@router.post("/{class_id}/members", status_code=201)
def enroll_class_member(
    class_id: int,
    payload: MemberPayload,
    request: Request,
    db: Session = Depends(db_session),
):
    require_csrf(request)
    admin = _require_relation_manager(
        request,
        db,
        "class_member_enroll",
        resource_type="class_member",
        summary={"schema_version": 1, "reason_code": "forbidden"},
    )
    _class_for_relation_change(db, class_id)
    if db.get(User, payload.student_id) is None:
        raise HTTPException(404, "学员不存在。")
    if db.scalar(
        select(ClassMember.id).where(
            ClassMember.class_id == class_id,
            ClassMember.student_id == payload.student_id,
            ClassMember.status == "active",
        )
    ) is not None:
        raise HTTPException(409, "该学员已在此班级。")
    joined_at = utcnow()
    row = ClassMember(class_id=class_id, student_id=payload.student_id, joined_at=joined_at)
    db.add(row)
    db.flush()
    _audit_success(
        db,
        request,
        "class_member_enroll",
        admin.id,
        resource_type="class_member",
        resource_id=row.id,
        summary={
            "schema_version": 1,
            "student_user_id": row.student_id,
            "class_id": row.class_id,
            "joined_at": _utc_iso(joined_at),
        },
    )
    db.commit()
    db.refresh(row)
    return _serialize_member(row)


def _withdraw_class_member(
    class_id: int, member_id: int, request: Request, db: Session
):
    require_csrf(request)
    admin = _require_relation_manager(
        request,
        db,
        "class_member_withdraw",
        resource_type="class_member",
        resource_id=member_id,
        summary={"schema_version": 1, "reason_code": "forbidden"},
    )
    _class_for_relation_change(db, class_id, allow_archived=True)
    row = db.scalar(
        select(ClassMember).where(ClassMember.id == member_id, ClassMember.class_id == class_id)
    )
    if row is None:
        raise HTTPException(404, "班级成员关系不存在。")
    if row.status != "active":
        raise HTTPException(409, "该学员已经退班。")
    left_at = utcnow()
    row.status = "left"
    row.left_at = left_at
    _audit_success(
        db,
        request,
        "class_member_withdraw",
        admin.id,
        resource_type="class_member",
        resource_id=row.id,
        summary={
            "schema_version": 1,
            "student_user_id": row.student_id,
            "class_id": row.class_id,
            "left_at": _utc_iso(left_at),
        },
    )
    db.commit()
    db.refresh(row)
    return _serialize_member(row)


@router.post("/{class_id}/members/{member_id}/withdraw")
def withdraw_class_member(
    class_id: int,
    member_id: int,
    request: Request,
    db: Session = Depends(db_session),
):
    return _withdraw_class_member(class_id, member_id, request, db)


@router.delete("/{class_id}/members/{member_id}")
def delete_class_member(
    class_id: int,
    member_id: int,
    request: Request,
    db: Session = Depends(db_session),
):
    return _withdraw_class_member(class_id, member_id, request, db)


@router.post("/{class_id}/members/{member_id}/transfer", status_code=201)
def transfer_class_member(
    class_id: int,
    member_id: int,
    payload: TransferPayload,
    request: Request,
    db: Session = Depends(db_session),
):
    require_csrf(request)
    admin = _require_relation_manager(
        request,
        db,
        "class_member_transfer",
        resource_type="class_member",
        resource_id=member_id,
        summary={"schema_version": 1, "reason_code": "forbidden"},
    )
    if payload.to_class_id == class_id:
        raise HTTPException(409, "转入班级不能与原班级相同。")
    _class_for_relation_change(db, class_id, allow_archived=True)
    _class_for_relation_change(db, payload.to_class_id)
    row = db.scalar(
        select(ClassMember).where(ClassMember.id == member_id, ClassMember.class_id == class_id)
    )
    if row is None:
        raise HTTPException(404, "班级成员关系不存在。")
    if row.status != "active":
        raise HTTPException(409, "只有在读学员可以转班。")
    if db.scalar(
        select(ClassMember.id).where(
            ClassMember.class_id == payload.to_class_id,
            ClassMember.student_id == row.student_id,
            ClassMember.status == "active",
        )
    ) is not None:
        raise HTTPException(409, "该学员已在目标班级。")

    transferred_at = utcnow()
    row.status = "left"
    row.left_at = transferred_at
    new_row = ClassMember(
        class_id=payload.to_class_id,
        student_id=row.student_id,
        joined_at=transferred_at,
    )
    db.add(new_row)
    try:
        db.flush()
        _audit_success(
            db,
            request,
            "class_member_transfer",
            admin.id,
            resource_type="class_member",
            resource_id=new_row.id,
            summary={
                "schema_version": 1,
                "student_user_id": row.student_id,
                "from_class_id": class_id,
                "to_class_id": payload.to_class_id,
                "from_membership_id": row.id,
                "to_membership_id": new_row.id,
                "transferred_at": _utc_iso(transferred_at),
            },
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(new_row)
    return _serialize_member(new_row)
