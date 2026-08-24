"""班级主数据管理：创建、修改、归档和受保护的物理删除。"""
from __future__ import annotations

import csv
import io
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..class_enrollment import (
    CLASS_BATCH_SOURCE,
    grant_for_membership,
    has_effective_class_enrollment,
    revoke_for_class,
    revoke_for_membership,
    sync_class_window,
)
from ..models import AdminUser, ClassGroup, ClassMember, ClassTeacher, Course, Enrollment, User, HelpRequest
from ..notification_links import admin_help_request_link
from ..notification_service import create_notification
from .admin_enrollments import ENROLLMENT_STATUS_LABELS
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
# 班内角色与后台账号角色是两个维度；取值恰好同名也不共享常量，避免一边改值污染另一边。
CLASS_ROLE_LABELS = {
    "teacher": "主讲教师",
    "assistant": "助教",
}
MEMBER_STATUS_LABELS = {
    "active": "在读",
    "left": "已退班",
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


class BulkMemberPayload(BaseModel):
    student_ids: list[int]


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


def _serialize_teacher(row: ClassTeacher, admin_user: AdminUser | None = None) -> dict:
    return {
        "id": row.id,
        "class_id": row.class_id,
        "admin_user_id": row.admin_user_id,
        "teacher_name": admin_user.display_name if admin_user else None,
        "role_in_class": row.role_in_class,
        "role_in_class_label": CLASS_ROLE_LABELS[row.role_in_class],
        "assigned_at": row.assigned_at,
        "ended_at": row.ended_at,
    }


def _serialize_member(
    row: ClassMember, student: User | None = None, enrollment: Enrollment | None = None
) -> dict:
    return {
        "id": row.id,
        "class_id": row.class_id,
        "student_id": row.student_id,
        "student_name": student.username if student else None,
        "joined_at": row.joined_at,
        "left_at": row.left_at,
        "status": row.status,
        "status_label": MEMBER_STATUS_LABELS[row.status],
        "enrollment_status": enrollment.status if enrollment else None,
        "enrollment_status_label": ENROLLMENT_STATUS_LABELS[enrollment.status] if enrollment else None,
    }


def _csv_cell(value: object | None) -> object:
    """Keep exported user-controlled text from becoming an Excel formula."""
    if value is None:
        return ""
    if isinstance(value, datetime):
        return _utc_iso(value)
    if isinstance(value, str) and value.startswith(("=", "+", "-", "@")):
        return f"'{value}"
    return value


def _class_export_base(row: ClassGroup) -> list[object]:
    return [
        row.id,
        row.name,
        row.course_id,
        row.status,
        row.start_at,
        row.end_at,
    ]


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
    return {
        "items": [_serialize_class(row) for row in rows],
        "role_options": [
            {"value": value, "label": label}
            for value, label in CLASS_ROLE_LABELS.items()
        ],
    }


@router.get("/export")
def export_class_relationships(
    request: Request, db: Session = Depends(db_session)
):
    """Export all visible member and teacher relationship history as CSV."""
    _, class_ids = _require_class_reader(request, db)
    class_filter = [] if class_ids is None else [ClassGroup.id.in_(class_ids)]
    members = db.execute(
        select(ClassGroup, ClassMember, User)
        .join(ClassMember, ClassMember.class_id == ClassGroup.id)
        .join(User, User.id == ClassMember.student_id)
        .where(*class_filter)
        .order_by(ClassGroup.id, ClassMember.joined_at, ClassMember.id)
    ).all()
    teachers = db.execute(
        select(ClassGroup, ClassTeacher, AdminUser)
        .join(ClassTeacher, ClassTeacher.class_id == ClassGroup.id)
        .join(AdminUser, AdminUser.id == ClassTeacher.admin_user_id)
        .where(*class_filter)
        .order_by(ClassGroup.id, ClassTeacher.assigned_at, ClassTeacher.id)
    ).all()

    output = io.StringIO(newline="")
    writer = csv.writer(output)

    def write_row(row: list[object]) -> None:
        writer.writerow([_csv_cell(value) for value in row])

    write_row(
        [
            "关系类型",
            "班级ID",
            "班级名称",
            "课包ID",
            "班级状态",
            "班级开始时间",
            "班级结束时间",
            "成员关系ID",
            "学员ID",
            "学员账号",
            "入班时间",
            "退班时间",
            "成员状态",
            "带班关系ID",
            "后台账号ID",
            "后台账号",
            "班内角色",
            "指派时间",
            "结束带班时间",
        ]
    )
    for class_group, member, student in members:
        write_row(
            [
                "成员",
                *_class_export_base(class_group),
                member.id,
                student.id,
                student.username,
                member.joined_at,
                member.left_at,
                member.status,
                "",
                "",
                "",
                "",
                "",
                "",
            ]
        )
    for class_group, teacher, admin_user in teachers:
        write_row(
            [
                "带班",
                *_class_export_base(class_group),
                "",
                "",
                "",
                "",
                "",
                "",
                teacher.id,
                admin_user.id,
                admin_user.username,
                teacher.role_in_class,
                teacher.assigned_at,
                teacher.ended_at,
            ]
        )

    return Response(
        content=("\ufeff" + output.getvalue()).encode("utf-8"),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="class-relationships.csv"'},
    )


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
    admin = _require_manager(request, db)
    row = db.get(ClassGroup, class_id)
    if row is None:
        raise HTTPException(404, "班级不存在。")
    if row.status == "archived":
        raise HTTPException(409, "已归档班级不可修改。")
    _course_or_404(db, payload.course_id)
    old_end_at = as_utc(row.end_at) if row.end_at else None
    new_end_at = as_utc(payload.end_at) if payload.end_at else None
    window_changed = old_end_at != new_end_at
    row.name = payload.name
    row.course_id = payload.course_id
    row.start_at = payload.start_at
    row.end_at = payload.end_at
    row.updated_at = utcnow()
    if window_changed:
        sync_class_window(db, class_group=row, admin_id=admin.id, request=request)
    db.commit()
    db.refresh(row)
    return _serialize_class(row)


@router.post("/{class_id}/archive")
def archive_class(class_id: int, request: Request, db: Session = Depends(db_session)):
    require_csrf(request)
    admin = _require_manager(request, db)
    row = db.get(ClassGroup, class_id)
    if row is None:
        raise HTTPException(404, "班级不存在。")
    if row.status != "archived":
        row.status = "archived"
        row.updated_at = utcnow()
    # Re-archiving also repairs active records left by older code paths.
    revoke_for_class(db, class_group=row, admin_id=admin.id, request=request)
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
    rows = db.execute(
        select(ClassTeacher, AdminUser)
        .outerjoin(AdminUser, AdminUser.id == ClassTeacher.admin_user_id)
        .where(ClassTeacher.class_id == class_id)
        .order_by(ClassTeacher.assigned_at, ClassTeacher.id)
    ).all()
    return {
        "items": [_serialize_teacher(row, admin_user) for row, admin_user in rows],
    }


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
    return _serialize_teacher(row, db.get(AdminUser, row.admin_user_id))


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
    successor = db.scalar(
        select(ClassTeacher).where(
            ClassTeacher.class_id == row.class_id,
            ClassTeacher.ended_at.is_(None),
            ClassTeacher.id != row.id,
        ).order_by(ClassTeacher.role_in_class != "teacher", ClassTeacher.assigned_at, ClassTeacher.id)
    )
    requests = db.scalars(select(HelpRequest).where(
        HelpRequest.class_id == row.class_id,
        HelpRequest.assigned_admin_user_id == row.admin_user_id,
        HelpRequest.status.in_(["open", "answered"]),
    )).all()
    for ticket in requests:
        ticket.assigned_admin_user_id = successor.admin_user_id if successor else None
        ticket.assignment_revision += 1
        create_notification(
            db, kind="help_request_assigned", title="工单已重新分配",
            body="你的联系请求已转交新的承办教师。" if successor else "你的联系请求已进入未分派队列。",
            target_type="help_request", target_id=ticket.id,
            source_type="help_request", source_id=ticket.id,
            link_url=help_request_link(ticket.id),
            idempotency_key=f"help-request-assigned:{ticket.id}:{ticket.assignment_revision}",
            recipients=([{"user_id": None, "admin_user_id": successor.admin_user_id}]
                        if successor else [{"user_id": ticket.student_id, "admin_user_id": None}]),
        )
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
    return _serialize_teacher(row, db.get(AdminUser, row.admin_user_id))


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
    rows = db.execute(
        select(ClassMember, User)
        .outerjoin(User, User.id == ClassMember.student_id)
        .where(ClassMember.class_id == class_id)
        .order_by(ClassMember.joined_at, ClassMember.id)
    ).all()
    result = []
    for row, student in rows:
        enrollment = db.scalar(
            select(Enrollment).where(
                Enrollment.student_id == row.student_id,
                Enrollment.source == CLASS_BATCH_SOURCE,
                Enrollment.class_id == class_id,
            ).order_by(Enrollment.id.desc())
        )
        if (
            enrollment is not None
            and enrollment.status == "active"
            and enrollment.expires_at is not None
            and as_utc(enrollment.expires_at) < utcnow()
        ):
            enrollment.status = "expired"
        result.append(_serialize_member(row, student, enrollment))
    return {"items": result}


def _enroll_class_member(
    class_id: int, student_id: int, request: Request, db: Session, admin: AdminUser
):
    """Create one membership through the shared validation and audit path."""
    class_group = _class_for_relation_change(db, class_id)
    if db.get(User, student_id) is None:
        raise HTTPException(404, "学员不存在。")
    if db.scalar(
        select(ClassMember.id).where(
            ClassMember.class_id == class_id,
            ClassMember.student_id == student_id,
            ClassMember.status == "active",
        )
    ) is not None:
        raise HTTPException(409, "该学员已在此班级。")
    joined_at = utcnow()
    row = ClassMember(class_id=class_id, student_id=student_id, joined_at=joined_at)
    db.add(row)
    db.flush()
    grant_for_membership(
        db, class_group=class_group, student_id=student_id, admin_id=admin.id, request=request
    )
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
    return _serialize_member(row, db.get(User, row.student_id))


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
    return _enroll_class_member(class_id, payload.student_id, request, db, admin)


@router.post("/{class_id}/members/bulk")
def bulk_enroll_class_members(
    class_id: int,
    payload: BulkMemberPayload,
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
    if not payload.student_ids:
        raise HTTPException(400, "请至少选择一名学员。")
    if len(payload.student_ids) > 500:
        raise HTTPException(400, "单次最多导入 500 名学员。")

    # Reject archived classes before the row loop: no partial batch may be created.
    _class_for_relation_change(db, class_id)
    succeeded = []
    failed = []
    for student_id in payload.student_ids:
        try:
            succeeded.append(
                _enroll_class_member(class_id, student_id, request, db, admin)
            )
        except HTTPException as error:
            # Each successful row committed inside the shared path. Failed rows must not
            # affect the rows before or after them.
            db.rollback()
            if error.status_code == 404:
                reason_code = "not_found"
            elif error.status_code == 409:
                reason_code = "conflict"
            else:
                raise
            failed.append({"student_id": student_id, "reason_code": reason_code})
    return {"succeeded": succeeded, "failed": failed}


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
    class_group = _class_for_relation_change(db, class_id, allow_archived=True)
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
    revoke_for_membership(
        db, class_group=class_group, student_id=row.student_id, admin_id=admin.id, request=request
    )
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
    return _serialize_member(row, db.get(User, row.student_id))


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
    source_class = _class_for_relation_change(db, class_id, allow_archived=True)
    target_class = _class_for_relation_change(db, payload.to_class_id)
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
        revoke_for_membership(
            db, class_group=source_class, student_id=row.student_id, admin_id=admin.id, request=request
        )
        grant_for_membership(
            db, class_group=target_class, student_id=row.student_id, admin_id=admin.id, request=request
        )
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
    return _serialize_member(new_row, db.get(User, new_row.student_id))


@router.post("/{class_id}/enrollments/sync")
def sync_class_enrollments(class_id: int, request: Request, db: Session = Depends(db_session)):
    require_csrf(request)
    admin = _require_manager(request, db)
    class_group = _class_for_relation_change(db, class_id, allow_archived=True)
    student_ids = db.scalars(
        select(ClassMember.student_id).where(
            ClassMember.class_id == class_id, ClassMember.status == "active"
        )
    ).all()
    granted = 0
    skipped = 0
    for student_id in student_ids:
        if has_effective_class_enrollment(db, class_group=class_group, student_id=student_id):
            skipped += 1
            continue
        grant_for_membership(
            db, class_group=class_group, student_id=student_id, admin_id=admin.id, request=request
        )
        granted += 1
    db.commit()
    return {"granted": granted, "skipped": skipped}
