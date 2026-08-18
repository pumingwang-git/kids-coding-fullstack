"""Course enrollment history driven by class membership changes."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import ClassGroup, ClassMember, Enrollment
from .security import as_utc, utcnow
from .routers.admin_auth import audit, client_ip

CLASS_BATCH_SOURCE = "class_batch"


def _utc_iso(value: datetime | None) -> str | None:
    return as_utc(value).isoformat().replace("+00:00", "Z") if value else None


def _window(class_group: ClassGroup) -> tuple[datetime, datetime | None]:
    now = utcnow()
    start_at = as_utc(class_group.start_at) if class_group.start_at else now
    return max(now, start_at), as_utc(class_group.end_at) if class_group.end_at else None


def _grant_summary(row: Enrollment) -> dict:
    return {
        "schema_version": 1,
        "student_user_id": row.student_id,
        "course_id": row.course_id,
        "source": row.source,
        "class_id": row.class_id,
        "opened_at": _utc_iso(row.opened_at),
        "expires_at": _utc_iso(row.expires_at),
    }


def grant_for_membership(
    db: Session, *, class_group: ClassGroup, student_id: int, admin_id: int, request
) -> Enrollment:
    opened_at, expires_at = _window(class_group)
    row = Enrollment(
        student_id=student_id,
        course_id=class_group.course_id,
        class_id=class_group.id,
        source=CLASS_BATCH_SOURCE,
        status="active",
        opened_at=opened_at,
        expires_at=expires_at,
    )
    db.add(row)
    db.flush()
    audit(
        db, request.app.state.settings, "enrollment_grant", "success", client_ip(request), admin_id,
        resource_type="enrollment", resource_id=row.id, summary=_grant_summary(row),
    )
    return row


def revoke_for_membership(
    db: Session, *, class_group: ClassGroup, student_id: int, admin_id: int, request
) -> int:
    rows = db.scalars(
        select(Enrollment).where(
            Enrollment.student_id == student_id,
            Enrollment.source == CLASS_BATCH_SOURCE,
            Enrollment.class_id == class_group.id,
            Enrollment.status == "active",
        )
    ).all()
    for row in rows:
        row.status = "disabled"
        audit(
            db, request.app.state.settings, "enrollment_status_change", "success", client_ip(request), admin_id,
            resource_type="enrollment", resource_id=row.id,
            summary={**_grant_summary(row), "old_status": "active", "new_status": "disabled"},
        )
    return len(rows)


def sync_class_window(db: Session, *, class_group: ClassGroup, admin_id: int, request) -> int:
    student_ids = db.scalars(
        select(ClassMember.student_id).where(
            ClassMember.class_id == class_group.id, ClassMember.status == "active"
        )
    ).all()
    for student_id in student_ids:
        revoke_for_membership(
            db, class_group=class_group, student_id=student_id, admin_id=admin_id, request=request
        )
        grant_for_membership(
            db, class_group=class_group, student_id=student_id, admin_id=admin_id, request=request
        )
    return len(student_ids)


def has_effective_class_enrollment(db: Session, *, class_group: ClassGroup, student_id: int) -> bool:
    now = utcnow()
    rows = db.scalars(
        select(Enrollment).where(
            Enrollment.student_id == student_id,
            Enrollment.source == CLASS_BATCH_SOURCE,
            Enrollment.class_id == class_group.id,
            Enrollment.status == "active",
        )
    ).all()
    return any(
        as_utc(row.opened_at) <= now
        and (row.expires_at is None or as_utc(row.expires_at) >= now)
        for row in rows
    )
