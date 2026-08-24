from __future__ import annotations

import hashlib

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..class_groups import active_teacher_assignments_for_class
from ..course_access import lesson_access, Access
from ..notification_links import help_request_link
from ..models import (
    ClassGroup, ClassMember, Course, CourseLesson, CourseLessonBlock, HelpMessage, HelpRequest,
    LessonProblemAttempt, LessonProblemBlock, Problem, User,
)
from ..notification_service import create_notification, request_hash
from ..permissions import ACADEMIC_ADMIN_ROLE, SUPER_ROLE, visible_class_ids
from ..security import utcnow
from .admin_auth import current_admin, db_session
from .auth_secure import current_user, limit, require_csrf

student_router = APIRouter(prefix="/api/student/help-requests", tags=["help-requests"])
admin_router = APIRouter(prefix="/api/admin/help-requests", tags=["help-requests"])


class HelpRequestPayload(BaseModel):
    class_id: int
    body: str = Field(min_length=1, max_length=10_000)
    context_type: str = Field(default="general", max_length=64)
    context_id: int | None = None


class HelpMessagePayload(BaseModel):
    body: str = Field(min_length=1, max_length=10_000)


def _context_is_accessible(db: Session, user: User, class_id: int,
                           context_type: str, context_id: int | None) -> bool:
    """Resolve a context through its owning course and the student's access gate.

    The ticket schema intentionally keeps one typed id; this resolver prevents a
    client from attaching an arbitrary course/lesson/problem id to a class ticket.
    """
    if context_type == "general":
        return context_id is None
    if context_id is None or context_type not in {"course", "lesson", "block", "problem", "attempt"}:
        return False
    class_course_id = db.scalar(select(ClassGroup.course_id).where(ClassGroup.id == class_id))
    if class_course_id is None:
        return False
    lesson = None
    if context_type == "course":
        course = db.get(Course, context_id)
        return course is not None and course.id == class_course_id and course.status == "published"
    if context_type == "lesson":
        lesson = db.get(CourseLesson, context_id)
    elif context_type == "block":
        block = db.get(CourseLessonBlock, context_id)
        lesson = db.get(CourseLesson, block.lesson_id) if block else None
    elif context_type == "problem":
        problem = db.get(Problem, context_id)
        if problem is None:
            return False
        lesson = db.scalar(select(CourseLesson).join(CourseLessonBlock,
            CourseLessonBlock.lesson_id == CourseLesson.id)
            .join(LessonProblemBlock, LessonProblemBlock.block_id == CourseLessonBlock.id)
            .where(LessonProblemBlock.problem_id_no == str(problem.id),
                   CourseLesson.course_id == class_course_id))
    else:
        attempt = db.get(LessonProblemAttempt, context_id)
        if attempt is None or attempt.user_id != user.id:
            return False
        lesson = db.get(CourseLesson, attempt.lesson_id)
    return lesson is not None and lesson.course_id == class_course_id \
        and lesson_access(db, user, lesson) is Access.GRANTED


def _hash(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def _serialize(db: Session, row: HelpRequest) -> dict:
    messages = db.scalars(select(HelpMessage).where(HelpMessage.help_request_id == row.id)
                          .order_by(HelpMessage.created_at, HelpMessage.id)).all()
    return {
        "id": row.id, "class_id": row.class_id, "student_id": row.student_id,
        "assigned_admin_user_id": row.assigned_admin_user_id, "body": row.body,
        "context_type": row.context_type, "context_id": row.context_id,
        "status": row.status, "created_at": row.created_at, "closed_at": row.closed_at,
        "messages": [{"id": item.id, "body": item.body, "created_at": item.created_at,
                      "sender_type": "student" if item.sender_user_id else "admin"}
                     for item in messages],
    }


def _student_row_or_404(db: Session, user_id: int, request_id: int) -> HelpRequest:
    row = db.scalar(select(HelpRequest).where(HelpRequest.id == request_id,
                    HelpRequest.student_id == user_id))
    if row is None:
        raise HTTPException(404, "联系记录不存在。")
    return row


def _admin_row_or_404(db: Session, admin, request_id: int) -> HelpRequest:
    row = db.get(HelpRequest, request_id)
    class_ids = visible_class_ids(admin, db)
    can_govern = admin.role in {ACADEMIC_ADMIN_ROLE, SUPER_ROLE}
    if (row is None
            or (class_ids is not None and row.class_id not in class_ids)
            or (not can_govern and row.assigned_admin_user_id != admin.id)):
        raise HTTPException(404, "联系记录不存在。")
    return row


@student_router.post("", status_code=201)
def create_help_request(payload: HelpRequestPayload, request: Request,
                        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
                        user: User = Depends(current_user), db: Session = Depends(db_session)):
    require_csrf(request)
    if not idempotency_key:
        raise HTTPException(422, "缺少 Idempotency-Key。")
    if not _context_is_accessible(db, user, payload.class_id, payload.context_type, payload.context_id):
        raise HTTPException(422, "联系上下文无效或当前不可访问。")
    membership = db.scalar(select(ClassMember).where(ClassMember.class_id == payload.class_id,
                           ClassMember.student_id == user.id, ClassMember.status == "active",
                           ClassMember.left_at.is_(None)))
    if membership is None:
        raise HTTPException(404, "班级不存在。")
    limit(request, "help-request-create", f"{user.id}:{payload.class_id}", 10, 60)
    key_hash = _hash(idempotency_key)
    input_hash = request_hash(payload.model_dump())
    existing = db.scalar(select(HelpRequest).where(HelpRequest.student_id == user.id,
                         HelpRequest.request_key_hash == key_hash))
    if existing:
        if existing.request_hash != input_hash:
            raise HTTPException(409, "Idempotency-Key 已用于不同请求。")
        return _serialize(db, existing)
    assignees = active_teacher_assignments_for_class(db, payload.class_id)
    if not assignees:
        raise HTTPException(409, "当前班级暂无承办教师。")
    row = HelpRequest(class_id=payload.class_id, student_id=user.id,
                      assigned_admin_user_id=assignees[0].admin_user_id,
                      body=payload.body.strip(), context_type=payload.context_type,
                      context_id=payload.context_id, request_key_hash=key_hash,
                      request_hash=input_hash)
    db.add(row)
    db.flush()
    create_notification(db, kind="help_request_created", title="新的学生联系",
                        body="有学生发起了一条联系请求。", target_type="help_request", target_id=row.id,
                        source_type="help_request", source_id=row.id, link_url=help_request_link(row.id),
                        idempotency_key=f"help-request-created:{row.id}:{row.assigned_admin_user_id}",
                        recipients=[{"user_id": None, "admin_user_id": row.assigned_admin_user_id}])
    db.commit()
    return _serialize(db, row)


@student_router.get("")
def student_list(request: Request, user: User = Depends(current_user), db: Session = Depends(db_session)):
    rows = db.scalars(select(HelpRequest).where(HelpRequest.student_id == user.id)
                      .order_by(HelpRequest.created_at.desc(), HelpRequest.id.desc())).all()
    return {"items": [_serialize(db, row) for row in rows]}


@student_router.get("/{request_id}")
def student_detail(request_id: int, request: Request, user: User = Depends(current_user), db: Session = Depends(db_session)):
    return _serialize(db, _student_row_or_404(db, user.id, request_id))


@student_router.post("/{request_id}/close")
def student_close(request_id: int, request: Request, user: User = Depends(current_user), db: Session = Depends(db_session)):
    require_csrf(request)
    row = _student_row_or_404(db, user.id, request_id)
    if row.status == "open":
        row.status, row.closed_at = "closed", utcnow()
        db.commit()
    return _serialize(db, row)


@admin_router.get("")
def admin_list(request: Request, status: str | None = Query(default=None, pattern="^(open|closed)$"),
               admin=Depends(current_admin), db: Session = Depends(db_session)):
    stmt = select(HelpRequest)
    class_ids = visible_class_ids(admin, db)
    if class_ids is not None:
        stmt = stmt.where(HelpRequest.class_id.in_(class_ids))
    if admin.role not in {ACADEMIC_ADMIN_ROLE, SUPER_ROLE}:
        stmt = stmt.where(HelpRequest.assigned_admin_user_id == admin.id)
    if status:
        stmt = stmt.where(HelpRequest.status == status)
    rows = db.scalars(stmt.order_by(HelpRequest.created_at.desc(), HelpRequest.id.desc())).all()
    return {"items": [_serialize(db, row) for row in rows]}


@admin_router.get("/{request_id}")
def admin_detail(request_id: int, request: Request, admin=Depends(current_admin), db: Session = Depends(db_session)):
    return _serialize(db, _admin_row_or_404(db, admin, request_id))


@admin_router.post("/{request_id}/messages", status_code=201)
def reply(request_id: int, payload: HelpMessagePayload, request: Request,
          idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
          admin=Depends(current_admin), db: Session = Depends(db_session)):
    require_csrf(request)
    if not idempotency_key:
        raise HTTPException(422, "缺少 Idempotency-Key。")
    row = _admin_row_or_404(db, admin, request_id)
    limit(request, "help-request-reply", f"{admin.id}:{row.id}", 20, 60)
    if row.status != "open":
        raise HTTPException(409, "联系记录已关闭。")
    key_hash = _hash(idempotency_key)
    input_hash = request_hash({"help_request_id": row.id, **payload.model_dump()})
    existing = db.scalar(select(HelpMessage).where(HelpMessage.help_request_id == row.id,
                         HelpMessage.sender_admin_user_id == admin.id,
                         HelpMessage.request_key_hash == key_hash))
    if existing:
        if existing.request_hash != input_hash:
            raise HTTPException(409, "Idempotency-Key 已用于不同请求。")
        return {"id": existing.id, "created_at": existing.created_at}
    message = HelpMessage(help_request_id=row.id, sender_admin_user_id=admin.id,
                          body=payload.body.strip(), request_key_hash=key_hash)
    message.request_hash = input_hash
    db.add(message)
    db.flush()
    create_notification(db, kind="teacher_reply", title="教师回复了你的联系",
                        body="你的教师联系收到了新回复。", target_type="help_request", target_id=row.id,
                        source_type="help_request", source_id=row.id, link_url=help_request_link(row.id),
                        idempotency_key=f"teacher-reply:{message.id}:{row.student_id}",
                        recipients=[{"user_id": row.student_id, "admin_user_id": None}])
    db.commit()
    return {"id": message.id, "created_at": message.created_at}


@admin_router.post("/{request_id}/close")
def admin_close(request_id: int, request: Request, admin=Depends(current_admin), db: Session = Depends(db_session)):
    require_csrf(request)
    row = _admin_row_or_404(db, admin, request_id)
    if row.status == "open":
        row.status, row.closed_at = "closed", utcnow()
        db.commit()
    return _serialize(db, row)
