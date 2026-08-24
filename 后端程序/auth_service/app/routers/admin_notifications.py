from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from ..class_groups import active_students_for_class
from ..models import Notification, NotificationReceipt
from ..notification_domain import notification_kind_label
from ..notification_service import create_notification, revoke_notification
from ..permissions import (
    ACADEMIC_ADMIN_ROLE,
    ASSISTANT_ROLE,
    SUPER_ROLE,
    TEACHER_ROLE,
    visible_class_ids,
)
from ..security import utcnow
from . import admin_classes
from .admin_auth import audit, client_ip, current_admin, db_session, require_csrf
from .auth_secure import limit

router = APIRouter(prefix="/api/admin/notifications", tags=["admin-notifications"])
teaching_router = APIRouter(prefix="/api/admin/teaching", tags=["admin-notifications"])


class AnnouncementPayload(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=10_000)
    link_url: str | None = Field(default=None, max_length=500)

    @field_validator("link_url")
    @classmethod
    def _internal_link_only(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return None
        if not value.startswith("/") or value.startswith("//"):
            raise ValueError("通知跳转地址必须是站内路径。")
        return value


def _item(notification: Notification, receipt: NotificationReceipt | None, *, sent: bool = False) -> dict:
    return {
        "id": notification.id, "kind": notification.kind,
        "kind_label": notification_kind_label(notification.kind), "title": notification.title,
        "body": notification.body, "target_type": notification.target_type,
        "target_id": notification.target_id, "source_type": notification.source_type,
        "source_id": notification.source_id, "link_url": notification.link_url,
        "created_at": notification.created_at,
        "read_at": receipt.read_at if receipt else None,
        "revoked_at": notification.revoked_at,
        "actions": ([{"type": "revoke", "label": "撤回"}] if sent and not notification.revoked_at else []),
    }


def _admin_notification_or_404(db: Session, admin, notification_id: int) -> tuple[Notification, NotificationReceipt | None, bool]:
    notification = db.get(Notification, notification_id)
    if notification is None:
        raise HTTPException(404, "通知不存在。")
    receipt = db.scalar(select(NotificationReceipt).where(
        NotificationReceipt.notification_id == notification_id,
        NotificationReceipt.admin_user_id == admin.id,
    ))
    class_ids = visible_class_ids(admin, db)
    in_visible_class = (
        notification.target_type == "class"
        and notification.target_id is not None
        and (class_ids is None or notification.target_id in class_ids)
    )
    sent = notification.kind == "class_announcement" and in_visible_class and (
        notification.created_by == admin.id or admin.role in {SUPER_ROLE, ACADEMIC_ADMIN_ROLE}
    )
    if receipt is None and not sent:
        raise HTTPException(404, "通知不存在。")
    return notification, receipt, sent


@router.get("")
def list_notifications(request: Request, box: str = Query("inbox", pattern="^(inbox|sent)$"),
                       tab: str = Query("all", pattern="^(all|unread)$"),
                       page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
                       admin=Depends(current_admin), db: Session = Depends(db_session)):
    if box == "sent" and tab == "unread":
        raise HTTPException(422, "已发送通知不支持未读筛选。")
    if box == "inbox":
        stmt = select(Notification, NotificationReceipt).join(NotificationReceipt).where(
            NotificationReceipt.admin_user_id == admin.id)
        if tab == "unread":
            stmt = stmt.where(NotificationReceipt.read_at.is_(None))
        total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows = db.execute(stmt.order_by(Notification.created_at.desc(), Notification.id.desc())
                          .offset((page - 1) * page_size).limit(page_size)).all()
        items = [_item(notification, receipt) for notification, receipt in rows]
    else:
        class_ids = visible_class_ids(admin, db)
        stmt = select(Notification).where(
            Notification.created_by == admin.id,
            Notification.kind == "class_announcement",
            Notification.target_type == "class",
        )
        if class_ids is not None:
            if not class_ids:
                return {"items": [], "page": page, "page_size": page_size, "total": 0, "has_more": False}
            stmt = stmt.where(Notification.target_id.in_(class_ids))
        total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows = db.scalars(stmt.order_by(Notification.created_at.desc(), Notification.id.desc())
                          .offset((page - 1) * page_size).limit(page_size)).all()
        items = [_item(notification, None, sent=True) for notification in rows]
    return {"items": items, "page": page, "page_size": page_size, "total": total,
            "has_more": page * page_size < total}


@router.get("/unread-count")
def unread_count(request: Request, admin=Depends(current_admin), db: Session = Depends(db_session)):
    count = db.scalar(select(func.count()).select_from(NotificationReceipt).where(
        NotificationReceipt.admin_user_id == admin.id, NotificationReceipt.read_at.is_(None))) or 0
    return {"count": count}


@router.get("/{notification_id}")
def detail(notification_id: int, request: Request, admin=Depends(current_admin), db: Session = Depends(db_session)):
    notification, receipt, sent = _admin_notification_or_404(db, admin, notification_id)
    return _item(notification, receipt, sent=sent)


@router.post("/{notification_id}/read")
def mark_read(notification_id: int, request: Request, admin=Depends(current_admin), db: Session = Depends(db_session)):
    require_csrf(request)
    _, receipt, _ = _admin_notification_or_404(db, admin, notification_id)
    if receipt is None:
        raise HTTPException(404, "通知不存在。")
    if receipt.read_at is None:
        receipt.read_at = utcnow()
        db.commit()
    return {"ok": True, "read_at": receipt.read_at}


@router.post("/read-all")
def mark_all_read(request: Request, admin=Depends(current_admin), db: Session = Depends(db_session)):
    require_csrf(request)
    now = utcnow()
    db.execute(update(NotificationReceipt).where(NotificationReceipt.admin_user_id == admin.id,
               NotificationReceipt.read_at.is_(None)).values(read_at=now))
    db.commit()
    return {"ok": True, "read_at": now}


@router.post("/{notification_id}/revoke")
def revoke(notification_id: int, request: Request, admin=Depends(current_admin), db: Session = Depends(db_session)):
    require_csrf(request)
    notification, _, sent = _admin_notification_or_404(db, admin, notification_id)
    if not sent:
        raise HTTPException(404, "通知不存在。")
    revoke_notification(db, notification, admin.id)
    audit(db, request.app.state.settings, "notification_revoke", "success", client_ip(request), admin.id,
          resource_type="notification", resource_id=notification.id,
          summary={"kind": notification.kind})
    db.commit()
    return {"ok": True, "revoked_at": notification.revoked_at}


@teaching_router.post("/classes/{class_id}/announcements", status_code=201)
def announce(class_id: int, payload: AnnouncementPayload, request: Request,
             idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
             admin=Depends(current_admin), db: Session = Depends(db_session)):
    require_csrf(request)
    if admin.role not in {SUPER_ROLE, ACADEMIC_ADMIN_ROLE, TEACHER_ROLE, ASSISTANT_ROLE}:
        raise HTTPException(403, "没有发布班级公告的权限。")
    admin_classes._require_class_reader(request, db, class_id)
    limit(request, "class-announcement", f"{admin.id}:{class_id}", 5, 60)
    students = active_students_for_class(db, class_id)
    if not students:
        raise HTTPException(409, "当前班级没有在读学员，无法发送公告。")
    notification = create_notification(
        db, kind="class_announcement", title=payload.title.strip(), body=payload.body.strip(),
        target_type="class", target_id=class_id, source_type="class", source_id=class_id,
        link_url=payload.link_url, created_by=admin.id,
        idempotency_key=idempotency_key or "",
        recipients=[{"user_id": student.id, "admin_user_id": None} for student in students],
        request_input={"class_id": class_id, **payload.model_dump()},
    )
    audit(db, request.app.state.settings, "class_announcement_create", "success", client_ip(request), admin.id,
          resource_type="notification", resource_id=notification.id,
          summary={"class_id": class_id, "recipient_count": len(students)})
    db.commit()
    return _item(notification, None, sent=True)
