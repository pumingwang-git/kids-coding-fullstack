from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from ..models import Notification, NotificationReceipt, User
from ..notification_domain import notification_kind_label
from ..security import utcnow
from .auth_secure import current_user, db_session, require_csrf

router = APIRouter(prefix="/api/student/notifications", tags=["student-notifications"])


def _item(notification: Notification, receipt: NotificationReceipt) -> dict:
    return {
        "id": notification.id,
        "kind": notification.kind,
        "kind_label": notification_kind_label(notification.kind),
        "title": notification.title,
        "body": notification.body,
        "target_type": notification.target_type,
        "target_id": notification.target_id,
        "source_type": notification.source_type,
        "source_id": notification.source_id,
        "link_url": notification.link_url,
        "created_at": notification.created_at,
        "read_at": receipt.read_at,
        "dismissed_at": None,
        "revoked_at": notification.revoked_at,
        "actions": [] if notification.revoked_at else [{"type": "open", "label": "打开"}],
    }


def _receipt(db: Session, user_id: int, notification_id: int) -> NotificationReceipt:
    receipt = db.scalar(select(NotificationReceipt).where(
        NotificationReceipt.notification_id == notification_id,
        NotificationReceipt.user_id == user_id,
    ))
    if receipt is None:
        raise HTTPException(404, "通知不存在。")
    return receipt


@router.get("")
def list_notifications(
    request: Request,
    tab: str = Query("all", pattern="^(all|unread)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
):
    stmt = select(Notification, NotificationReceipt).join(
        NotificationReceipt, NotificationReceipt.notification_id == Notification.id
    ).where(NotificationReceipt.user_id == user.id)
    if tab == "unread":
        stmt = stmt.where(NotificationReceipt.read_at.is_(None))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.execute(stmt.order_by(Notification.created_at.desc(), Notification.id.desc())
                      .offset((page - 1) * page_size).limit(page_size)).all()
    return {"items": [_item(notification, receipt) for notification, receipt in rows],
            "page": page, "page_size": page_size, "total": total,
            "has_more": page * page_size < total}


@router.get("/unread-count")
def unread_count(request: Request, user: User = Depends(current_user), db: Session = Depends(db_session)):
    count = db.scalar(select(func.count()).select_from(NotificationReceipt).join(
        Notification, NotificationReceipt.notification_id == Notification.id
    ).where(
        NotificationReceipt.user_id == user.id,
        NotificationReceipt.read_at.is_(None),
        Notification.revoked_at.is_(None),
    )) or 0
    return {"count": count}


@router.get("/{notification_id}")
def notification_detail(notification_id: int, request: Request,
                         user: User = Depends(current_user), db: Session = Depends(db_session)):
    receipt = _receipt(db, user.id, notification_id)
    notification = db.get(Notification, notification_id)
    if notification is None:
        raise HTTPException(404, "通知不存在。")
    return _item(notification, receipt)


@router.post("/{notification_id}/read")
def mark_notification_read(notification_id: int, request: Request,
                           user: User = Depends(current_user), db: Session = Depends(db_session)):
    require_csrf(request)
    receipt = _receipt(db, user.id, notification_id)
    if receipt.read_at is None:
        receipt.read_at = utcnow()
        db.commit()
    return {"ok": True, "read_at": receipt.read_at}


@router.post("/read-all")
def mark_all_notifications_read(request: Request, user: User = Depends(current_user), db: Session = Depends(db_session)):
    require_csrf(request)
    now = utcnow()
    db.execute(update(NotificationReceipt).where(
        NotificationReceipt.user_id == user.id,
        NotificationReceipt.read_at.is_(None),
    ).values(read_at=now))
    db.commit()
    return {"ok": True, "read_at": now}
