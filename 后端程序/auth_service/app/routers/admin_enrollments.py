"""E3a 个人课程开通：单人、单课程、管理员来源。"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from ..models import Course, Enrollment, User
from ..audit_summary import diff_summary
from ..course_access import enrollment_predicates
from ..permissions import has_capability
from ..security import as_utc, utcnow
from .admin_auth import audit, client_ip, current_admin, db_session, require_csrf

router = APIRouter(prefix="/api/admin/enrollments", tags=["admin-enrollments"])

ENROLLMENT_SOURCE_ADMIN = "admin"
ENROLLMENT_STATUS_LABELS = {
    "active": "已开通",
    "not_started": "未开始",
    "disabled": "已停用",
    "expired": "已过期",
}
ENROLLMENT_PHASE_ACTIONS = {
    "active": ["disable"],
    "not_started": [],
    "expired": [],
    "disabled": ["restore"],
}


class EnrollmentPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    student_id: int = Field(gt=0)
    course_id: int = Field(gt=0)
    opened_at: datetime | None = None
    expires_at: datetime | None = None

    @model_validator(mode="after")
    def validate_time_range(self):
        if self.opened_at is not None:
            self.opened_at = as_utc(self.opened_at)
        if self.expires_at is not None:
            self.expires_at = as_utc(self.expires_at)
        if (
            self.opened_at is not None
            and self.expires_at is not None
            and self.expires_at < self.opened_at
        ):
            raise ValueError("到期时间不能早于开通时间。")
        return self


class EnrollmentStatusPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["active", "disabled"]


def _require_enrollment_manager(
    request: Request,
    db: Session,
    *,
    event: str,
    summary: dict,
    resource_id: int | None = None,
):
    admin = current_admin(request, db)
    if not has_capability(admin, "manage_enrollments"):
        audit(
            db,
            request.app.state.settings,
            event,
            "failure",
            client_ip(request),
            admin.id,
            resource_type="enrollment",
            resource_id=resource_id,
            summary={**summary, "reason_code": "forbidden"},
        )
        db.commit()
        raise HTTPException(403, "没有管理课程开通的权限。")
    return admin


def _utc_iso(value: datetime | None) -> str | None:
    return as_utc(value).isoformat().replace("+00:00", "Z") if value else None


def _enrollment_phase(row: Enrollment, now: datetime | None = None) -> str:
    """Return the one runtime phase shared by display, filtering and actions."""
    now = now or utcnow()
    opened_at = as_utc(row.opened_at)
    expires_at = as_utc(row.expires_at) if row.expires_at else None
    if row.status == "active" and opened_at > now:
        return "not_started"
    if expires_at is not None and expires_at < now:
        return "expired"
    if row.status == "disabled":
        return "disabled"
    return "active"


def _phase_filters(phase: str, now: datetime) -> list:
    """Build SQL predicates equivalent to ``_enrollment_phase``."""
    if phase == "active":
        return list(enrollment_predicates(now))
    if phase == "not_started":
        return [Enrollment.status == "active", Enrollment.opened_at > now]
    if phase == "expired":
        return [
            and_(
                Enrollment.status.in_(["active", "disabled"]),
                Enrollment.expires_at.is_not(None),
                Enrollment.expires_at < now,
            )
        ]
    if phase == "disabled":
        return [
            Enrollment.status == "disabled",
            or_(Enrollment.expires_at.is_(None), Enrollment.expires_at >= now),
        ]
    raise ValueError(f"unknown enrollment phase: {phase}")


def _serialize_enrollment(
    row: Enrollment, student: User | None = None, course: Course | None = None
) -> dict:
    display_status = _enrollment_phase(row)
    return {
        "id": row.id,
        "student_id": row.student_id,
        "course_id": row.course_id,
        "source": row.source,
        "status": display_status,
        "status_label": ENROLLMENT_STATUS_LABELS[display_status],
        "allowed_actions": ENROLLMENT_PHASE_ACTIONS[display_status],
        "student_username": student.username if student else None,
        "course_title": course.title if course else None,
        "opened_at": row.opened_at,
        "expires_at": row.expires_at,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _grant_summary(payload: EnrollmentPayload, *, opened_at: datetime, expires_at: datetime | None) -> dict:
    return diff_summary({}, {"course_id": payload.course_id, "status": "active",
        "opened_at": opened_at, "expires_at": expires_at},
        ("course_id", "status", "opened_at", "expires_at")) | {"student_user_id": payload.student_id}


def _status_summary(row: Enrollment, *, old_status: str, new_status: str) -> dict:
    return diff_summary({"course_id": row.course_id, "status": old_status},
        {"course_id": row.course_id, "status": new_status}, ("course_id", "status")) | {
            "student_user_id": row.student_id, "source": row.source,
            # Keep the established flat aliases while ``changed`` is the canonical shape.
            "old_status": old_status, "new_status": new_status}


@router.get("")
def list_enrollments(
    request: Request,
    student_id: int | None = Query(None, ge=1),
    course_id: int | None = Query(None, ge=1),
    status: Literal["active", "not_started", "expired", "disabled"] | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(db_session),
):
    _require_enrollment_manager(
        request,
        db,
        event="enrollment_grant",
        summary={"schema_version": 1},
    )
    filters = []
    if student_id is not None:
        filters.append(Enrollment.student_id == student_id)
    if course_id is not None:
        filters.append(Enrollment.course_id == course_id)
    if status is not None:
        filters.extend(_phase_filters(status, utcnow()))
    total = db.scalar(select(func.count()).select_from(Enrollment).where(*filters)) or 0
    rows = db.execute(
        select(Enrollment, User, Course)
        .join(User, User.id == Enrollment.student_id)
        .join(Course, Course.id == Enrollment.course_id)
        .where(*filters)
        .order_by(Enrollment.created_at.desc(), Enrollment.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return {
        "items": [_serialize_enrollment(row, student, course) for row, student, course in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.post("")
def grant_individual_enrollment(
    payload: EnrollmentPayload,
    request: Request,
    response: Response,
    db: Session = Depends(db_session),
):
    """创建一条管理员个人开通记录；重复开通也保留为独立历史行。"""
    require_csrf(request)
    opened_at = payload.opened_at or utcnow()
    expires_at = payload.expires_at
    grant_summary = _grant_summary(
        payload, opened_at=opened_at, expires_at=expires_at
    )
    admin = _require_enrollment_manager(
        request,
        db,
        event="enrollment_grant",
        summary=grant_summary,
    )
    if db.get(User, payload.student_id) is None:
        audit(
            db, request.app.state.settings, "enrollment_grant", "failure", client_ip(request), admin.id,
            resource_type="enrollment", summary={**grant_summary, "reason_code": "not_found"},
        )
        db.commit()
        raise HTTPException(404, "学员不存在。")
    if db.get(Course, payload.course_id) is None:
        audit(
            db, request.app.state.settings, "enrollment_grant", "failure", client_ip(request), admin.id,
            resource_type="enrollment", summary={**grant_summary, "reason_code": "not_found"},
        )
        db.commit()
        raise HTTPException(404, "课包不存在。")

    row = Enrollment(
        student_id=payload.student_id,
        course_id=payload.course_id,
        source=ENROLLMENT_SOURCE_ADMIN,
        status="active",
        opened_at=opened_at,
        expires_at=expires_at,
    )
    db.add(row)
    db.flush()
    audit(
        db,
        request.app.state.settings,
        "enrollment_grant",
        "success",
        client_ip(request),
        admin.id,
        resource_type="enrollment",
        resource_id=row.id,
        user_id=row.student_id,
        summary=grant_summary,
    )
    db.commit()
    db.refresh(row)
    response.status_code = 201
    return _serialize_enrollment(row, db.get(User, row.student_id), db.get(Course, row.course_id))


@router.put("/{enrollment_id}/status")
def update_enrollment_status(
    enrollment_id: int,
    payload: EnrollmentStatusPayload,
    request: Request,
    db: Session = Depends(db_session),
):
    require_csrf(request)
    admin = _require_enrollment_manager(
        request,
        db,
        event="enrollment_status_change",
        resource_id=enrollment_id,
        summary={"schema_version": 1},
    )
    row = db.get(Enrollment, enrollment_id)
    if row is None:
        audit(
            db, request.app.state.settings, "enrollment_status_change", "failure", client_ip(request), admin.id,
            resource_type="enrollment", resource_id=enrollment_id,
            summary={"schema_version": 1, "reason_code": "not_found"},
        )
        db.commit()
        raise HTTPException(404, "课程开通记录不存在。")
    now = utcnow()
    phase = _enrollment_phase(row, now)
    if payload.status == "active" and phase == "expired":
        audit(
            db, request.app.state.settings, "enrollment_status_change", "failure", client_ip(request), admin.id,
            resource_type="enrollment", resource_id=row.id,
            summary=_status_summary(row, old_status=row.status, new_status=payload.status) | {"reason_code": "conflict"},
        )
        db.commit()
        raise HTTPException(409, "已过期记录不能恢复，请重新开通课程。")
    if row.status == payload.status:
        audit(
            db, request.app.state.settings, "enrollment_status_change", "failure", client_ip(request), admin.id,
            resource_type="enrollment", resource_id=row.id,
            summary=_status_summary(row, old_status=row.status, new_status=payload.status) | {"reason_code": "conflict"},
        )
        db.commit()
        raise HTTPException(409, "课程开通记录已经是该状态。")
    old_status = row.status
    row.status = payload.status
    audit(
        db, request.app.state.settings, "enrollment_status_change", "success", client_ip(request), admin.id,
        resource_type="enrollment", resource_id=row.id,
        user_id=row.student_id,
        summary=_status_summary(row, old_status=old_status, new_status=payload.status),
    )
    db.commit()
    db.refresh(row)
    return _serialize_enrollment(row, db.get(User, row.student_id), db.get(Course, row.course_id))
