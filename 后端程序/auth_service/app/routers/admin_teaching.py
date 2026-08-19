"""Teacher workbench route skeleton."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import ClassGroup
from . import admin_classes
from .admin_auth import db_session

router = APIRouter(prefix="/api/admin/teaching", tags=["admin-teaching"])


@router.get("/classes")
def list_teaching_classes(
    request: Request, db: Session = Depends(db_session)
):
    _, class_ids = admin_classes._require_class_reader(request, db)
    statement = select(ClassGroup)
    if class_ids is not None:
        statement = statement.where(ClassGroup.id.in_(class_ids))
    rows = db.scalars(statement.order_by(ClassGroup.id)).all()
    return {"items": [admin_classes._serialize_class(row) for row in rows]}


@router.get("/classes/{class_id}/overview")
def class_overview_placeholder(
    class_id: int, request: Request, db: Session = Depends(db_session)
):
    admin_classes._require_class_reader(request, db, class_id)
    if db.get(ClassGroup, class_id) is None:
        raise HTTPException(404, "班级不存在。")
    return {"class_id": class_id}
