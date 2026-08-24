"""Transactional in-app notification primitives for E6.

Routers should use this module instead of constructing notification rows directly.
It keeps idempotency and recipient invariants in one place; callers own the
surrounding business transaction and commit once after the event is accepted.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .models import Notification, NotificationReceipt
from .notification_domain import (
    validate_notification_kind,
    validate_recipient,
    validate_source_pair,
)
from .security import utcnow


def request_hash(value: object) -> str:
    """Return a stable digest for the normalized business input."""

    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def create_notification(
    db: Session,
    *,
    kind: str,
    title: str,
    body: str,
    target_type: str,
    target_id: int,
    idempotency_key: str,
    recipients: Iterable[dict[str, int | None]],
    source_type: str | None = None,
    source_id: int | None = None,
    link_url: str | None = None,
    created_by: int | None = None,
    request_input: object | None = None,
    max_recipients: int = 5000,
) -> Notification:
    """Create one notification and its receipts, or return an identical retry.

    The function intentionally does not commit.  A conflicting idempotency key
    is a client error and fan-out limits are checked before any row is added.
    """

    validate_notification_kind(kind)
    validate_source_pair(source_type, source_id)
    if not idempotency_key or len(idempotency_key) > 255:
        raise HTTPException(422, "Idempotency-Key 无效。")

    recipient_rows = list(recipients)
    if len(recipient_rows) > max_recipients:
        raise HTTPException(413, "通知收件人数量超过上限。")
    digest = request_hash(request_input if request_input is not None else {
        "kind": kind, "title": title, "body": body,
        "target_type": target_type, "target_id": target_id,
        "source_type": source_type, "source_id": source_id,
        "link_url": link_url,
        "recipients": recipient_rows,
    })

    existing = db.scalar(select(Notification).where(Notification.idempotency_key == idempotency_key))
    if existing is not None:
        if existing.request_hash and existing.request_hash != digest:
            raise HTTPException(409, "Idempotency-Key 已用于不同请求。")
        return existing

    seen: set[tuple[int | None, int | None]] = set()
    try:
        # A savepoint preserves the caller's business changes if another worker
        # wins the notification idempotency race.
        with db.begin_nested():
            notification = Notification(
                kind=kind, title=title, body=body, target_type=target_type,
                target_id=target_id, source_type=source_type, source_id=source_id,
                link_url=link_url, idempotency_key=idempotency_key,
                request_hash=digest, created_by=created_by,
            )
            db.add(notification)
            db.flush()
            for row in recipient_rows:
                user_id = row.get("user_id")
                admin_user_id = row.get("admin_user_id")
                validate_recipient(user_id=user_id, admin_user_id=admin_user_id)
                pair = (user_id, admin_user_id)
                if pair in seen:
                    continue
                seen.add(pair)
                db.add(NotificationReceipt(
                    notification_id=notification.id,
                    user_id=user_id,
                    admin_user_id=admin_user_id,
                ))
            db.flush()
    except IntegrityError:
        concurrent = db.scalar(select(Notification).where(Notification.idempotency_key == idempotency_key))
        if concurrent is not None and concurrent.request_hash == digest:
            return concurrent
        raise HTTPException(409, "通知幂等键冲突。")
    return notification


def ensure_notification_recipients(
    db: Session,
    notification: Notification,
    recipients: Iterable[dict[str, int | None]],
) -> int:
    """Add missing receipts to an existing broadcast notification.

    Used when an entitlement becomes valid after the broadcast was published.
    The database's partial unique indexes remain the concurrent-process guard;
    each recipient gets an independent savepoint so one concurrent insert does
    not discard the rest of the batch.
    """

    added = 0
    seen: set[tuple[int | None, int | None]] = set()
    for row in recipients:
        user_id = row.get("user_id")
        admin_user_id = row.get("admin_user_id")
        validate_recipient(user_id=user_id, admin_user_id=admin_user_id)
        pair = (user_id, admin_user_id)
        if pair in seen:
            continue
        seen.add(pair)
        exists = db.scalar(select(NotificationReceipt.id).where(
            NotificationReceipt.notification_id == notification.id,
            NotificationReceipt.user_id == user_id,
            NotificationReceipt.admin_user_id == admin_user_id,
        ))
        if exists is not None:
            continue
        try:
            with db.begin_nested():
                db.add(NotificationReceipt(
                    notification_id=notification.id,
                    user_id=user_id,
                    admin_user_id=admin_user_id,
                ))
                db.flush()
            added += 1
        except IntegrityError:
            # Another cron process inserted this exact receipt first.
            continue
    return added


def mark_read(db: Session, receipt: NotificationReceipt) -> None:
    if receipt.read_at is None:
        receipt.read_at = utcnow()
        db.flush()


def revoke_notification(db: Session, notification: Notification, admin_user_id: int) -> None:
    if notification.revoked_at is None:
        notification.revoked_at = utcnow()
        notification.revoked_by = admin_user_id
        db.flush()
