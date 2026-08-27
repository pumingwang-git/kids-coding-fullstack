"""全局审计查询。读取接口受功能权限控制，审计表不提供写入口。"""

from __future__ import annotations

import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import AdminUser, AuditEvent, User
from ..permissions import has_capability
from .admin_auth import audit, client_ip, current_admin, db_session

router = APIRouter(prefix="/api/admin/audit", tags=["admin-audit"])


def _payload(row: AuditEvent, db: Session) -> dict:
    admin_user = db.get(AdminUser, row.admin_user_id) if row.admin_user_id else None
    user = db.get(User, row.user_id) if row.user_id else None
    return {
        "id": row.id,
        "event": row.event_type,
        "event_type": row.event_type,
        "outcome": row.outcome,
        "admin_user_id": row.admin_user_id,
        "admin_user": {
            "id": admin_user.id,
            "username": admin_user.username,
            "display_name": admin_user.display_name,
        } if admin_user else None,
        "user_id": row.user_id,
        "user": {
            "id": user.id,
            "username": user.username,
            "display_name": getattr(user, "display_name", None),
        } if user else None,
        "resource_type": row.resource_type,
        "resource_id": row.resource_id,
        "summary": json.loads(row.summary_json) if row.summary_json else {},
        "created_at": row.created_at,
    }


@router.get("/events")
def list_audit_events(
    request: Request,
    event_type: str | None = None,
    outcome: str | None = None,
    admin_user_id: int | None = None,
    user_id: int | None = None,
    resource_type: str | None = None,
    resource_id: int | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    ip_hmac: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1),
    db: Session = Depends(db_session),
):
    admin = current_admin(request, db)
    if not has_capability(admin, "audit_events_read"):
        audit(
            db, request.app.state.settings, "audit_events_read", "failure", client_ip(request), admin.id,
            resource_type="audit_event", summary={"schema_version": 1, "reason_code": "forbidden"},
        )
        db.commit()
        raise HTTPException(403, "仅超级管理员可查看全局审计记录。")

    page_size = min(max(1, page_size), 100)
    stmt = select(AuditEvent)
    filters = (
        (AuditEvent.event_type, event_type), (AuditEvent.outcome, outcome),
        (AuditEvent.admin_user_id, admin_user_id), (AuditEvent.user_id, user_id),
        (AuditEvent.resource_type, resource_type), (AuditEvent.resource_id, resource_id),
        (AuditEvent.ip_hmac, ip_hmac),
    )
    for column, value in filters:
        if value is not None:
            stmt = stmt.where(column == value)
    if created_from is not None:
        stmt = stmt.where(AuditEvent.created_at >= created_from)
    if created_to is not None:
        stmt = stmt.where(AuditEvent.created_at <= created_to)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(AuditEvent.id.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    return {"total": total, "page": page, "page_size": page_size, "items": [_payload(row, db) for row in rows]}
