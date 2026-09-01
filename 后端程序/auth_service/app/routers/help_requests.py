from __future__ import annotations

import hashlib
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import (
    APIRouter,
    Depends,
    File,
    Header,
    HTTPException,
    Query,
    Request,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import case, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..attempt_source import lesson_homework_block_for_attempt, resolve_for_attempt
from ..audit_summary import diff_summary
from ..class_groups import active_teacher_assignments_for_class
from ..course_access import Access, lesson_access
from ..help_authorization import can_respond_to_help
from ..help_context import NormalizedHelpContext, normalize_help_context
from ..help_realtime import HelpRealtimeUnavailable, help_realtime_hub
from ..learning_activity import activity_status, last_activity_at
from ..models import (
    AdminUser,
    ClassGroup,
    ClassMember,
    ClassTeacher,
    Course,
    CourseLesson,
    CourseLessonBlock,
    ExamAssignment,
    HelpChatLine,
    HelpChatLineRead,
    HelpChatLineStudentRead,
    HelpMessage,
    HelpMessageAttachment,
    HelpRequest,
    LessonBlockCompletion,
    LessonProblemAttempt,
    LessonProblemBlock,
    LessonVideoWatch,
    Paper,
    PaperAttempt,
    PaperQuestion,
    Problem,
    User,
)
from ..notification_links import admin_help_request_link
from ..notification_service import create_notification, request_hash
from ..permissions import (
    admin_ids_visible_for_class,
    has_capability,
    log_scope_denial,
    visible_class_ids,
)
from ..security import utcnow
from ..scratch_cover import CoverInvalid, normalize_cover
from ..student_tasks import collect_homework_candidates, homework_phase
from ..text_sanitize import plain_text
from .admin_auth import audit, client_ip, current_admin, db_session
from .admin_auth import require_csrf as require_admin_csrf
from .auth_secure import audit as student_audit
from .auth_secure import current_user, limit
from .auth_secure import require_csrf as require_student_csrf

student_router = APIRouter(prefix="/api/student/help-requests", tags=["help-requests"])
admin_router = APIRouter(prefix="/api/admin/help-requests", tags=["help-requests"])
student_message_router = APIRouter(prefix="/api/student/help-messages", tags=["help-requests"])
admin_message_router = APIRouter(prefix="/api/admin/help-messages", tags=["help-requests"])
admin_attachment_router = APIRouter(prefix="/api/admin/help-attachments", tags=["help-requests"])
attachment_router = APIRouter(prefix="/api/help-attachments", tags=["help-requests"])
student_chat_router = APIRouter(prefix="/api/student/help-chat-lines", tags=["help-chat-lines"])
admin_chat_router = APIRouter(prefix="/api/admin/help-chat-lines", tags=["help-chat-lines"])

_SHANGHAI = ZoneInfo("Asia/Shanghai")


class HelpRequestPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    class_id: int
    body: str = Field(min_length=1, max_length=10_000)
    context_type: str = Field(default="general", max_length=64)
    context_id: int | None = None
    context_source: str | None = Field(default=None, max_length=32)
    problem_id_no: str | None = Field(default=None, max_length=64)


class HelpMessagePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    body: str = Field(default="", max_length=10_000)
    attachment_ids: list[int] = Field(default_factory=list, max_length=4)


class AssignmentPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_admin_user_id: int = Field(gt=0)


def _require_help_respond(admin, db: Session) -> None:
    if not can_respond_to_help(admin, db):
        raise HTTPException(403, "当前账号没有答疑回复权限。")


def _accessible_context(
    db: Session,
    user: User,
    class_id: int,
    context_type: str,
    context_id: int | None,
    context_source: str | None,
    requested_problem_number: str | None,
) -> NormalizedHelpContext | None:
    """Authorize a context, then derive its grouping key from server-owned rows."""
    if context_type == "general":
        try:
            return normalize_help_context(
                context_type,
                context_id=context_id,
                context_source=context_source,
                problem_id_no=requested_problem_number,
            )
        except ValueError:
            return None
    if context_id is None or context_type not in {
        "course",
        "lesson",
        "block",
        "problem",
        "attempt",
    }:
        return None
    class_course_id = db.scalar(select(ClassGroup.course_id).where(ClassGroup.id == class_id))
    if class_course_id is None:
        return None
    if context_type == "course":
        course = db.get(Course, context_id)
        if course is None or course.id != class_course_id or course.status != "published":
            return None
        return normalize_help_context(context_type, context_id=context_id)

    lesson = None
    problem_number = None
    if context_type == "lesson":
        lesson = db.get(CourseLesson, context_id)
    elif context_type == "block":
        block = db.get(CourseLessonBlock, context_id)
        lesson = db.get(CourseLesson, block.lesson_id) if block else None
    elif context_type == "problem":
        problem = db.get(Problem, context_id)
        if problem is None or problem.problem_id_no is None:
            return None
        problem_number = problem.problem_id_no
        lesson = db.scalar(
            select(CourseLesson)
            .join(CourseLessonBlock, CourseLessonBlock.lesson_id == CourseLesson.id)
            .join(LessonProblemBlock, LessonProblemBlock.block_id == CourseLessonBlock.id)
            .where(
                LessonProblemBlock.problem_id_no == problem_number,
                CourseLesson.course_id == class_course_id,
            )
        )
    elif context_source == "lesson_attempt":
        attempt = db.get(LessonProblemAttempt, context_id)
        if attempt is None or attempt.user_id != user.id:
            return None
        lesson = db.get(CourseLesson, attempt.lesson_id)
        problem_numbers = db.scalars(
            select(LessonProblemBlock.problem_id_no).where(
                LessonProblemBlock.block_id == attempt.block_id
            )
        ).all()
        if len(problem_numbers) != 1:
            return None
        problem_number = problem_numbers[0]
    elif context_source == "paper_attempt":
        attempt = db.get(PaperAttempt, context_id)
        problem_number = (requested_problem_number or "").strip()
        if attempt is None or attempt.user_id != user.id or not problem_number:
            return None
        try:
            _, paper = resolve_for_attempt(db, attempt)
        except HTTPException:
            return None
        if (
            db.scalar(
                select(PaperQuestion.id).where(
                    PaperQuestion.paper_id == paper.id,
                    PaperQuestion.problem_id_no == problem_number,
                )
            )
            is None
        ):
            return None
        homework_block = lesson_homework_block_for_attempt(db, attempt)
        if homework_block is not None:
            lesson = db.get(CourseLesson, homework_block.lesson_id)
        else:
            assigned_to_class = db.scalar(
                select(ExamAssignment.id).where(
                    ExamAssignment.exam_link_id == attempt.exam_link_id,
                    ExamAssignment.target_type == "class",
                    ExamAssignment.target_id == class_id,
                    ExamAssignment.status == "active",
                    ExamAssignment.ended_at.is_(None),
                )
            )
            if assigned_to_class is None:
                return None
            return normalize_help_context(
                context_type,
                context_id=context_id,
                context_source=context_source,
                problem_id_no=problem_number,
            )
    else:
        return None

    if (
        lesson is None
        or lesson.course_id != class_course_id
        or lesson_access(db, user, lesson) is not Access.GRANTED
    ):
        return None
    try:
        return normalize_help_context(
            context_type,
            context_id=context_id,
            context_source=context_source,
            problem_id_no=problem_number,
        )
    except ValueError:
        return None


def _hash(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def _serialize(
    db: Session,
    row: HelpRequest,
    *,
    messages: list[HelpMessage] | None = None,
) -> dict:
    if messages is None:
        messages = db.scalars(
            select(HelpMessage)
            .where(HelpMessage.help_request_id == row.id)
            .order_by(HelpMessage.created_at, HelpMessage.id)
        ).all()
    return {
        "id": row.id,
        "help_request_id": row.id,
        "chat_line_id": row.chat_line_id,
        "class_id": row.class_id,
        "student_id": row.student_id,
        "assigned_admin_user_id": row.assigned_admin_user_id,
        "body": row.body,
        "context_type": row.context_type,
        "context_id": row.context_id,
        "context_source": row.context_source,
        "context_key": row.context_key,
        "context_label": _context_label(db, row),
        "status": row.status,
        "answered_at": row.answered_at,
        "assignment_revision": row.assignment_revision,
        "created_at": row.created_at,
        "closed_at": row.closed_at,
        "last_message_at": row.last_message_at,
        "messages": [_message_payload(db, item) for item in messages],
    }


def _message_payload(
    db: Session,
    item: HelpMessage,
    *,
    read_by_student: bool | None = None,
    read_by_assigned_teacher: bool | None = None,
    viewer_student_id: int | None = None,
    viewer_admin_id: int | None = None,
) -> dict:
    # This is deliberately viewer-independent so student/admin REST and WS share
    # one frozen message shape.  The client combines it with sender_type only for
    # display; the recall endpoint rechecks the actual actor identity.
    can_recall = (
        item.recalled_at is None
        and item.created_at is not None
        and utcnow() - _utc(item.created_at) <= timedelta(minutes=2)
    )
    payload = {
        "id": item.id,
        "help_request_id": item.help_request_id,
        "body": "" if item.recalled_at else item.body,
        "created_at": item.created_at,
        "sender_type": "student" if item.sender_user_id else "admin",
        "recalled": item.recalled_at is not None,
        "recalled_at": item.recalled_at,
        "can_recall": can_recall,
        "attachments": [
            {
                "id": attachment.id,
                "kind": attachment.kind,
                "mime": attachment.mime,
                "original_name": attachment.original_name,
                "purged_at": attachment.purged_at,
                "url": None if attachment.purged_at else f"/api/help-attachments/{attachment.id}",
            }
            for attachment in db.scalars(
                select(HelpMessageAttachment)
                .where(HelpMessageAttachment.help_message_id == item.id)
                .order_by(HelpMessageAttachment.id)
            )
        ],
    }
    if read_by_student is not None:
        payload["read_by_student"] = read_by_student
    if read_by_assigned_teacher is not None:
        payload["read_by_assigned_teacher"] = read_by_assigned_teacher
    return payload


def _paged(items: list, total: int, page: int, page_size: int) -> dict:
    return {"items": items, "total": total, "page": page, "page_size": page_size}


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _context_label(db: Session, row: HelpRequest) -> str:
    labels = {
        "general": "通用问题",
        "course": "课程",
        "lesson": "课时",
        "lesson_block": "课时内容",
        "lesson_problem": "题目",
        "attempt": "作答",
    }
    label = labels.get(row.context_type, "学习上下文")
    if row.context_type == "general":
        return label
    if row.context_type == "attempt" and row.context_source == "paper_attempt":
        attempt = db.get(PaperAttempt, row.context_id)
        paper = db.get(Paper, attempt.paper_id) if attempt else None
        return f"{paper.title} · 作答题目" if paper else "作答题目"
    if row.context_type == "attempt" and row.context_source == "lesson_attempt":
        attempt = db.get(LessonProblemAttempt, row.context_id)
        lesson = db.get(CourseLesson, attempt.lesson_id) if attempt else None
        return f"{lesson.title} · 练习" if lesson else "课时练习"
    if row.context_type == "block":
        block = db.get(CourseLessonBlock, row.context_id)
        lesson = db.get(CourseLesson, block.lesson_id) if block else None
        return f"{lesson.title} · 课时内容" if lesson else "课时内容"
    return label


def _student_profile_payload(
    db: Session,
    line: HelpChatLine,
    requests: list[HelpRequest],
    now: datetime,
) -> dict:
    """Build the compact, class-scoped learner summary shown beside a chat line."""
    class_group = db.get(ClassGroup, line.class_id)
    student = db.get(User, line.student_id)
    course_id = class_group.course_id if class_group is not None else None
    lessons = list(db.scalars(
        select(CourseLesson)
        .where(CourseLesson.course_id == course_id)
        .order_by(CourseLesson.sort_order, CourseLesson.id)
    )) if course_id is not None else []
    lesson_ids = [lesson.id for lesson in lessons]
    blocks_by_lesson: dict[int, list[CourseLessonBlock]] = {lesson_id: [] for lesson_id in lesson_ids}
    if lesson_ids:
        for block in db.scalars(
            select(CourseLessonBlock)
            .where(CourseLessonBlock.lesson_id.in_(lesson_ids))
            .order_by(CourseLessonBlock.lesson_id, CourseLessonBlock.sort_order, CourseLessonBlock.id)
        ):
            blocks_by_lesson[block.lesson_id].append(block)

    completed_by_lesson: dict[int, set[int]] = {}
    if lesson_ids:
        for lesson_id, block_id in db.execute(
            select(LessonBlockCompletion.lesson_id, LessonBlockCompletion.block_id).where(
                LessonBlockCompletion.user_id == line.student_id,
                LessonBlockCompletion.lesson_id.in_(lesson_ids),
            )
        ):
            completed_by_lesson.setdefault(lesson_id, set()).add(block_id)

    resumed_lessons = set()
    if lesson_ids:
        resumed_lessons = set(db.scalars(
            select(LessonVideoWatch.lesson_id).where(
                LessonVideoWatch.user_id == line.student_id,
                LessonVideoWatch.lesson_id.in_(lesson_ids),
                LessonVideoWatch.max_position_seconds > 0,
            )
        ))

    completed_lessons = 0
    for lesson in lessons:
        required = [block for block in blocks_by_lesson[lesson.id] if block.required]
        completed_blocks = completed_by_lesson.get(lesson.id, set())
        if required:
            done = all(block.id in completed_blocks for block in required)
        else:
            done = bool(completed_blocks) or lesson.id not in resumed_lessons
        completed_lessons += int(done)
    total_lessons = len(lessons)

    local_now = now.astimezone(_SHANGHAI)
    week_start = (local_now - timedelta(days=local_now.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    ).astimezone(UTC)
    weekly_practice_completed = 0
    if lesson_ids:
        weekly_practice_completed = int(db.scalar(
            select(func.count(func.distinct(LessonBlockCompletion.block_id)))
            .join(CourseLessonBlock, CourseLessonBlock.id == LessonBlockCompletion.block_id)
            .where(
                LessonBlockCompletion.user_id == line.student_id,
                LessonBlockCompletion.lesson_id.in_(lesson_ids),
                LessonBlockCompletion.completed_at >= week_start,
                CourseLessonBlock.block_type == "practice",
            )
        ) or 0)

    pending_homework_count = 0
    if student is not None and course_id is not None:
        pending_homework_count = sum(
            1
            for item in collect_homework_candidates(db, student)
            if item["course_id"] == course_id and homework_phase(item["facts"], now) == "todo"
        )

    activity = activity_status(
        last_activity_at(db, {line.student_id}, course_id).get(line.student_id), now
    )
    history_requests = requests[:10]
    first_message_ids: dict[int, int] = {}
    history_ids = [item.id for item in history_requests]
    if history_ids:
        for request_id, message_id in db.execute(
            select(HelpMessage.help_request_id, HelpMessage.id)
            .where(HelpMessage.help_request_id.in_(history_ids))
            .order_by(HelpMessage.help_request_id, HelpMessage.created_at, HelpMessage.id)
        ):
            first_message_ids.setdefault(request_id, message_id)

    return {
        "course_progress": {
            "completed_lessons": completed_lessons,
            "total_lessons": total_lessons,
            "percent": round(completed_lessons / total_lessons * 100) if total_lessons else 0,
        },
        "learning_activity": activity,
        "weekly_practice_completed": weekly_practice_completed,
        "pending_homework_count": pending_homework_count,
        "help_request_count": len(requests),
        "context_history": [
            {
                "help_request_id": item.id,
                "context_label": _context_label(db, item),
                "status": item.status,
                "last_message_at": item.last_message_at,
                "first_message_id": first_message_ids.get(item.id),
            }
            for item in history_requests
        ],
    }


def _line_payload(
    db: Session,
    line: HelpChatLine,
    *,
    include_requests: bool = False,
    viewer_admin_id: int | None = None,
    viewer_student_id: int | None = None,
    before_id: int | None = None,
    message_limit: int = 20,
) -> dict:
    requests = db.scalars(
        select(HelpRequest)
        .where(HelpRequest.chat_line_id == line.id)
        .order_by(HelpRequest.last_message_at.desc(), HelpRequest.id.desc())
    ).all()
    active = next((item for item in requests if item.status == "open"), None)
    current = active or (requests[0] if requests else None)
    student = db.get(User, line.student_id)
    class_group = db.get(ClassGroup, line.class_id)
    latest_student_message = None
    if current is not None:
        latest_student_message = db.scalar(
            select(HelpMessage)
            .where(
                HelpMessage.help_request_id == current.id,
                HelpMessage.sender_user_id == line.student_id,
            )
            .order_by(HelpMessage.created_at.desc(), HelpMessage.id.desc())
        )
    waiting_seconds = 0
    if active is not None:
        waiting_seconds = max(
            0, int((_utc(utcnow()) - _utc(active.last_message_at)).total_seconds())
        )
    if active is None:
        waiting_status = {"label": "暂无待回复", "tone": "neutral"}
        waiting_level = "none"
    elif waiting_seconds >= 600:
        waiting_status = {"label": "等待超过 10 分钟", "tone": "danger"}
        waiting_level = "red"
    else:
        waiting_status = {"label": "等待回复", "tone": "warning"}
        waiting_level = "waiting"
    payload = {
        "id": line.id,
        "class_id": line.class_id,
        "student_id": line.student_id,
        "assigned_admin_user_id": active.assigned_admin_user_id if active is not None else None,
        "student_name": student.username if student is not None else "",
        "class_name": class_group.name if class_group is not None else "",
        "last_message_at": line.last_message_at,
        "created_at": line.created_at,
        "ended_at": line.ended_at,
        "waiting_seconds": waiting_seconds,
        "waiting_status": waiting_status,
        "waiting_status_label": waiting_status["label"],
        "waiting_status_tone": waiting_status["tone"],
        "waiting_label": waiting_status["label"],
        "waiting_level": waiting_level,
        "has_student_unanswered": active is not None,
        "active_help_request": (
            _serialize(db, active, messages=[] if include_requests else None)
            if active is not None
            else None
        ),
        "last_student_message_body": (
            latest_student_message.body
            if latest_student_message is not None
            else current.body
            if current is not None
            else ""
        ),
        "context_label": _context_label(db, current) if current is not None else "",
        "has_attachments": _line_has_attachments(db, line),
    }
    if viewer_admin_id is not None:
        payload["unread_count"] = _line_unread_count(db, line, viewer_admin_id)
    if viewer_student_id is not None:
        payload["unread_count"] = _line_student_unread_count(db, line, viewer_student_id)
    if include_requests:
        message_query = (
            select(HelpMessage)
            .join(HelpRequest, HelpRequest.id == HelpMessage.help_request_id)
            .where(HelpRequest.chat_line_id == line.id)
        )
        if before_id is not None:
            cursor = db.scalar(
                message_query.where(HelpMessage.id == before_id)
            )
            if cursor is None:
                message_query = message_query.where(HelpMessage.id < 0)
            else:
                message_query = message_query.where(
                    (HelpMessage.created_at < cursor.created_at)
                    | (
                        (HelpMessage.created_at == cursor.created_at)
                        & (HelpMessage.id < cursor.id)
                    )
                )
        newest_first = db.scalars(
            message_query
            .order_by(HelpMessage.created_at.desc(), HelpMessage.id.desc())
            .limit(message_limit + 1)
        ).all()
        has_more = len(newest_first) > message_limit
        line_messages = list(reversed(newest_first[:message_limit]))
        messages_by_request: dict[int, list[HelpMessage]] = {}
        for item in line_messages:
            messages_by_request.setdefault(item.help_request_id, []).append(item)
        payload["requests"] = [
            _serialize(db, item, messages=messages_by_request.get(item.id, []))
            for item in requests
        ]
        if active is not None:
            payload["active_help_request"] = _serialize(
                db, active, messages=messages_by_request.get(active.id, [])
            )
        student_cursor = db.scalar(
            select(HelpChatLineStudentRead.last_read_message_id).where(
                HelpChatLineStudentRead.chat_line_id == line.id,
                HelpChatLineStudentRead.student_id == line.student_id,
            )
        ) or 0
        assignee_cursor = 0
        if current is not None and current.assigned_admin_user_id is not None:
            assignee_cursor = db.scalar(
                select(HelpChatLineRead.last_read_message_id).where(
                    HelpChatLineRead.chat_line_id == line.id,
                    HelpChatLineRead.admin_user_id == current.assigned_admin_user_id,
                )
            ) or 0
        messages = [
            _message_payload(
                db,
                item,
                read_by_student=bool(item.sender_admin_user_id and item.id <= student_cursor),
                read_by_assigned_teacher=bool(item.sender_user_id and item.id <= assignee_cursor),
                viewer_student_id=viewer_student_id,
                viewer_admin_id=viewer_admin_id,
            )
            for item in line_messages
        ]
        # S0 freezes the cursor envelope while retaining `messages` for existing clients.
        payload["messages"] = messages
        payload["items"] = messages
        payload["next_cursor"] = line_messages[0].id if has_more else None
        payload["has_more"] = has_more
        payload["student_profile"] = _student_profile_payload(db, line, requests, utcnow())
    return payload


def _line_has_attachments(db: Session, line: HelpChatLine) -> bool:
    return db.scalar(
        select(HelpMessageAttachment.id)
        .join(HelpMessage, HelpMessage.id == HelpMessageAttachment.help_message_id)
        .join(HelpRequest, HelpRequest.id == HelpMessage.help_request_id)
        .where(HelpRequest.chat_line_id == line.id, HelpMessageAttachment.purged_at.is_(None))
        .limit(1)
    ) is not None


def _line_unread_count(db: Session, line: HelpChatLine, viewer_admin_id: int) -> int:
    cursor = db.scalar(
        select(HelpChatLineRead.last_read_message_id).where(
            HelpChatLineRead.chat_line_id == line.id,
            HelpChatLineRead.admin_user_id == viewer_admin_id,
        )
    )
    if cursor is None:
        cursor = 0
    return int(db.scalar(
        select(func.count(HelpMessage.id))
        .join(HelpRequest, HelpRequest.id == HelpMessage.help_request_id)
        .where(
            HelpRequest.chat_line_id == line.id,
            HelpMessage.sender_user_id == line.student_id,
            HelpMessage.id > cursor,
        )
    ) or 0)


def _line_student_unread_count(db: Session, line: HelpChatLine, student_id: int) -> int:
    cursor = db.scalar(
        select(HelpChatLineStudentRead.last_read_message_id).where(
            HelpChatLineStudentRead.chat_line_id == line.id,
            HelpChatLineStudentRead.student_id == student_id,
        )
    ) or 0
    return int(db.scalar(
        select(func.count(HelpMessage.id))
        .join(HelpRequest, HelpRequest.id == HelpMessage.help_request_id)
        .where(
            HelpRequest.chat_line_id == line.id,
            HelpMessage.sender_admin_user_id.is_not(None),
            HelpMessage.id > cursor,
        )
    ) or 0)


def _mark_student_line_read(db: Session, line: HelpChatLine) -> bool:
    latest_id = db.scalar(
        select(func.max(HelpMessage.id))
        .join(HelpRequest, HelpRequest.id == HelpMessage.help_request_id)
        .where(HelpRequest.chat_line_id == line.id)
    )
    if latest_id is None:
        return False
    cursor = db.get(HelpChatLineStudentRead, (line.student_id, line.id))
    if cursor is None:
        db.add(HelpChatLineStudentRead(
            student_id=line.student_id, chat_line_id=line.id, last_read_message_id=latest_id
        ))
    elif cursor.last_read_message_id < latest_id:
        cursor.last_read_message_id = latest_id
    else:
        return False
    db.commit()
    return True


def _active_chat_line(
    db: Session,
    membership: ClassMember,
    user_id: int,
) -> HelpChatLine:
    line = db.scalar(
        select(HelpChatLine).where(
            HelpChatLine.class_id == membership.class_id,
            HelpChatLine.student_id == user_id,
            HelpChatLine.ended_at.is_(None),
        )
    )
    if line is not None:
        previous_left_at = db.scalar(
            select(ClassMember.left_at)
            .where(
                ClassMember.class_id == membership.class_id,
                ClassMember.student_id == user_id,
                ClassMember.status == "left",
                ClassMember.left_at.is_not(None),
                ClassMember.id < membership.id,
            )
            .order_by(ClassMember.id.desc())
            .limit(1)
        )
        crossed_membership_boundary = previous_left_at is not None and _utc(
            line.created_at
        ) <= _utc(previous_left_at)
        if crossed_membership_boundary:
            line.ended_at = membership.joined_at
            db.flush()
            line = None
    if line is None:
        now = utcnow()
        candidate = HelpChatLine(
            class_id=membership.class_id,
            student_id=user_id,
            created_at=now,
            last_message_at=now,
        )
        try:
            with db.begin_nested():
                db.add(candidate)
                db.flush()
            line = candidate
        except IntegrityError:
            line = db.scalar(
                select(HelpChatLine).where(
                    HelpChatLine.class_id == membership.class_id,
                    HelpChatLine.student_id == user_id,
                    HelpChatLine.ended_at.is_(None),
                )
            )
            if line is None:
                raise
    return line


def _student_row_or_404(db: Session, user_id: int, request_id: int) -> HelpRequest:
    row = db.scalar(
        select(HelpRequest).where(HelpRequest.id == request_id, HelpRequest.student_id == user_id)
    )
    if row is None:
        raise HTTPException(404, "联系记录不存在。")
    return row


def _admin_row_or_404(db: Session, admin, request_id: int) -> HelpRequest:
    row = db.get(HelpRequest, request_id)
    if row is None or not _can_act_on_request(db, admin, row):
        if row is not None:
            log_scope_denial(admin, "help_request", request_id)
        raise HTTPException(404, "联系记录不存在。")
    return row


def _can_act_on_request(db: Session, admin, row: HelpRequest | None) -> bool:
    if row is None:
        return False
    class_ids = visible_class_ids(admin, db)
    can_govern = has_capability(admin, "manage_classes")
    return (class_ids is None or row.class_id in class_ids) and (
        can_govern or row.assigned_admin_user_id == admin.id
    )


def _typing_allowed(websocket: WebSocket, key: str) -> bool:
    """输入中提示的软限流。

    每一帧 typing 都会触发一次收件人解析 + 一次 Redis 广播 + 向 N 个 socket 扇出，
    没有限流就是一条放大器：任何登录用户按住键盘就能让服务端反复做这套动作。

    **返回 bool 而不是抛 429**：这是 WebSocket 接收循环，抛出去会被循环外的 except
    接住并把整条连接关掉，等于把限流做成了掉线（就是 L3 那个坑）。限流器不可用时
    返回 False——输入中提示丢一帧没有任何代价，不值得为它冒放大风险。
    """
    try:
        return bool(websocket.app.state.rate_limiter.allow("help-typing", key, 12, 10))
    except Exception:
        return False


def _event_admin_ids(db: Session, line: HelpChatLine) -> set[int]:
    """把事件发给当前有权查看该聊天线的后台账号。

    这里**不能**遍历全部 active 管理员：本函数挂在每条消息、每次输入中提示、每次已读
    回执上，逐个调 `has_capability()` + `visible_class_ids()` 会退化成「扫全表 + 每人
    两次查询」，管理员一多就是每次敲键盘上百条 SQL。
    `admin_ids_visible_for_class()` 用「本班带班人 ∪ 全局范围账号」这个超集收窄候选，
    最终判定仍然逐字走 `visible_class_ids()`，结论不变而查询数与管理员总数无关。
    """
    return admin_ids_visible_for_class(db, line.class_id, capability="help_respond")


def _publish_line_change(
    db: Session,
    line: HelpChatLine,
    event: str,
    row: HelpRequest | None = None,
) -> None:
    help_realtime_hub.publish(
        line_id=line.id,
        student_id=line.student_id,
        admin_ids=_event_admin_ids(db, line),
        event=event,
        # Message frames reuse the REST contract.  Do not introduce a third shape.
        serialized_payload=_serialize(db, row) if row is not None else None,
    )


def _websocket_ticket(websocket: WebSocket) -> str | None:
    for protocol in websocket.headers.get("sec-websocket-protocol", "").split(","):
        protocol = protocol.strip()
        if protocol.startswith("help-ticket."):
            return protocol.removeprefix("help-ticket.")
    return None


def _admin_line_or_404(db: Session, admin, line_id: int) -> HelpChatLine:
    row = db.get(HelpChatLine, line_id)
    class_ids = visible_class_ids(admin, db)
    if row is None or (class_ids is not None and row.class_id not in class_ids):
        if row is not None:
            log_scope_denial(admin, "help_chat_line", line_id)
        raise HTTPException(404, "聊天线不存在。")
    return row


async def _help_attachment_upload(
    *, request: Request, db: Session, row: HelpRequest, upload: UploadFile,
    principal_id: int, principal_kind: str, idempotency_key: str,
    message_id: int | None = None,
):
    """Store one staged image attachment after the request scope is authorized."""
    settings = request.app.state.settings
    limit(request, "help-attachment-upload", f"{principal_kind}:{principal_id}", 30, 60)
    key_hash = _hash(idempotency_key)
    storage_root = Path(settings.help_attachment_upload_root).resolve()
    storage_root.mkdir(parents=True, exist_ok=True)
    storage_key = f"{principal_kind}/{principal_id}/request-{row.id}/{key_hash}.bin"
    existing = db.scalar(select(HelpMessageAttachment).where(HelpMessageAttachment.storage_key == storage_key))
    if existing:
        return existing
    raw = await upload.read(settings.help_attachment_max_bytes + 1)
    if len(raw) > settings.help_attachment_max_bytes:
        raise HTTPException(413, f"附件不能超过 {settings.help_attachment_max_bytes // (1024 * 1024)} MB。")
    if not raw:
        raise HTTPException(422, "附件不能为空。")
    try:
        # normalize_cover only accepts raster PNG/JPEG/WebP, caps dimensions,
        # and rewrites bytes; SVG and spoofed Content-Type values cannot pass.
        raw = normalize_cover(raw)
    except CoverInvalid as exc:
        raise HTTPException(415, "附件必须是有效图片。") from exc
    digest = hashlib.sha256(raw).hexdigest()
    target = storage_root / storage_key
    part = target.with_suffix(".part")
    target.parent.mkdir(parents=True, exist_ok=True)
    part.write_bytes(raw)
    os.replace(part, target)
    attachment = HelpMessageAttachment(
        help_message_id=message_id, kind="image", sha256=digest,
        byte_size=len(raw), mime="image/webp",
        original_name=(upload.filename or "image")[:255], storage_key=storage_key,
        uploaded_by_user_id=principal_id if principal_kind == "student" else None,
        uploaded_by_admin_user_id=principal_id if principal_kind == "admin" else None,
    )
    db.add(attachment)
    db.commit()
    db.refresh(attachment)
    return attachment


def _bind_staged_attachments(
    db: Session, *, attachment_ids: list[int], row: HelpRequest, message: HelpMessage,
    principal_id: int, principal_kind: str,
) -> None:
    if not attachment_ids:
        return
    if len(set(attachment_ids)) != len(attachment_ids):
        raise HTTPException(422, "附件不能重复。")
    attachments = db.scalars(
        select(HelpMessageAttachment).where(HelpMessageAttachment.id.in_(attachment_ids))
    ).all()
    if len(attachments) != len(attachment_ids):
        raise HTTPException(404, "附件不存在。")
    for attachment in attachments:
        owner_id = attachment.uploaded_by_user_id if principal_kind == "student" else attachment.uploaded_by_admin_user_id
        if attachment.help_message_id is not None or owner_id != principal_id:
            raise HTTPException(404, "附件不存在。")
        attachment.help_message_id = message.id


def _attachment_path(settings, attachment: HelpMessageAttachment) -> Path:
    root = Path(settings.help_attachment_upload_root).resolve()
    target = (root / attachment.storage_key).resolve()
    if root not in target.parents:
        raise HTTPException(404, "附件不存在。")
    return target


def _recall_message(
    *, request: Request, db: Session, message: HelpMessage, actor_id: int, actor_kind: str,
) -> dict:
    sender_id = message.sender_user_id if actor_kind == "student" else message.sender_admin_user_id
    if sender_id != actor_id:
        raise HTTPException(404, "消息不存在。")
    if message.recalled_at is not None:
        return _message_payload(db, message, **{f"viewer_{actor_kind}_id": actor_id})
    if message.created_at is None or utcnow() - _utc(message.created_at) > timedelta(minutes=2):
        raise HTTPException(409, "消息发送超过 2 分钟，不能撤回。")
    message.recalled_at = utcnow()
    message.body = ""
    for attachment in db.scalars(
        select(HelpMessageAttachment).where(HelpMessageAttachment.help_message_id == message.id)
    ):
        _attachment_path(request.app.state.settings, attachment).unlink(missing_ok=True)
        attachment.purged_at = message.recalled_at
    db.commit()
    row = db.get(HelpRequest, message.help_request_id)
    _publish_line_change(db, db.get(HelpChatLine, row.chat_line_id), "message_recalled", row)
    return _message_payload(db, message, **{f"viewer_{actor_kind}_id": actor_id})


def _assignment_candidates(db: Session, class_id: int) -> list[dict]:
    rows = db.scalars(
        select(AdminUser)
        .join(ClassTeacher, ClassTeacher.admin_user_id == AdminUser.id)
        .where(
            ClassTeacher.class_id == class_id,
            ClassTeacher.ended_at.is_(None),
            ClassTeacher.role_in_class.in_(("teacher", "assistant")),
            AdminUser.status == "active",
        )
        .order_by(AdminUser.display_name, AdminUser.id)
    ).all()
    return [
        {"id": candidate.id, "display_name": candidate.display_name}
        for candidate in rows
        if can_respond_to_help(candidate, db)
    ]


def _eligible_assignees(db: Session, class_id: int):
    eligible = []
    for assignment in active_teacher_assignments_for_class(db, class_id):
        candidate = db.get(AdminUser, assignment.admin_user_id)
        if (
            candidate is not None
            and candidate.status == "active"
            and can_respond_to_help(candidate, db)
        ):
            eligible.append(assignment)
    return eligible


@student_router.post("", status_code=201)
def create_help_request(
    payload: HelpRequestPayload,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
):
    require_student_csrf(request)
    if not idempotency_key:
        raise HTTPException(422, "缺少 Idempotency-Key。")
    membership = db.scalar(
        select(ClassMember).where(
            ClassMember.class_id == payload.class_id,
            ClassMember.student_id == user.id,
            ClassMember.status == "active",
            ClassMember.left_at.is_(None),
        )
    )
    if membership is None:
        raise HTTPException(404, "班级不存在。")
    normalized = _accessible_context(
        db,
        user,
        payload.class_id,
        payload.context_type,
        payload.context_id,
        payload.context_source,
        payload.problem_id_no,
    )
    if normalized is None:
        combination_is_invalid = (
            payload.context_type
            not in {"general", "course", "lesson", "block", "problem", "attempt"}
            or (payload.context_type == "general" and payload.context_id is not None)
            or (payload.context_type != "general" and payload.context_id is None)
            or (
                payload.context_type == "attempt"
                and payload.context_source
                not in {
                    "lesson_attempt",
                    "paper_attempt",
                }
            )
            or (payload.context_type != "attempt" and payload.context_source is not None)
        )
        if combination_is_invalid:
            raise HTTPException(422, "联系上下文无效或当前不可访问。")
        raise HTTPException(404, "联系上下文不存在。")
    limit(request, "help-request-create", f"{user.id}:{payload.class_id}", 10, 60)
    key_hash = _hash(idempotency_key)
    input_hash = request_hash(payload.model_dump())
    existing_message = db.scalar(
        select(HelpMessage).where(
            HelpMessage.sender_user_id == user.id,
            HelpMessage.request_key_hash == key_hash,
        )
    )
    if existing_message:
        if existing_message.request_hash != input_hash:
            raise HTTPException(409, "Idempotency-Key 已用于不同请求。")
        return _serialize(db, db.get(HelpRequest, existing_message.help_request_id))
    assignees = _eligible_assignees(db, payload.class_id)
    if not assignees:
        raise HTTPException(409, "当前班级暂无承办教师。")
    line = _active_chat_line(db, membership, user.id)
    row = db.scalar(
        select(HelpRequest).where(
            HelpRequest.chat_line_id == line.id,
            HelpRequest.context_key == normalized.context_key,
        )
    )
    created_request = row is None
    now = utcnow()
    if row is None:
        candidate = HelpRequest(
            class_id=payload.class_id,
            student_id=user.id,
            assigned_admin_user_id=assignees[0].admin_user_id,
            chat_line_id=line.id,
            body=plain_text(payload.body),
            context_type=normalized.context_type,
            context_id=payload.context_id,
            context_source=normalized.context_source,
            context_key=normalized.context_key,
            request_key_hash=key_hash,
            request_hash=input_hash,
            last_message_at=now,
        )
        try:
            with db.begin_nested():
                db.add(candidate)
                db.flush()
            row = candidate
        except IntegrityError:
            row = db.scalar(
                select(HelpRequest).where(
                    HelpRequest.chat_line_id == line.id,
                    HelpRequest.context_key == normalized.context_key,
                )
            )
            if row is None:
                raise
            created_request = False
    else:
        row.status = "open"
        row.answered_at = None
        row.closed_at = None
        row.last_message_at = now
    db.flush()
    message = HelpMessage(
        help_request_id=row.id,
        sender_user_id=user.id,
        body=plain_text(payload.body),
        request_key_hash=key_hash,
        request_hash=input_hash,
    )
    db.add(message)
    line.last_message_at = row.last_message_at = now
    db.flush()
    create_notification(
        db,
        kind="help_request_created",
        title="新的学生联系",
        body="有学生发起了一条联系请求。",
        target_type="help_request",
        target_id=row.id,
        source_type="help_request",
        source_id=row.id,
        link_url=admin_help_request_link(row.id, row.chat_line_id),
        idempotency_key=f"help-request-created:{message.id}:{row.assigned_admin_user_id}",
        recipients=[{"user_id": None, "admin_user_id": row.assigned_admin_user_id}],
    )
    audit(
        db,
        request.app.state.settings,
        "help_request_create",
        "success",
        client_ip(request),
        resource_type="help_request",
        resource_id=row.id,
        user_id=user.id,
        summary={
            "schema_version": 1,
            "changed": {
                "help_request_id": {"old": None, "new": row.id},
                "class_id": {"old": None, "new": row.class_id},
                "chat_line_id": {"old": None, "new": row.chat_line_id},
                "created_request": {"old": None, "new": created_request},
                "assigned_admin_user_id": {"old": None, "new": row.assigned_admin_user_id},
            },
        },
    )
    db.commit()
    _publish_line_change(db, line, "student_message", row)
    return _serialize(db, row)


@student_router.get("")
def student_list(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    sort: str = Query(default="-last_message_at,-id"),
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
):
    if sort not in {"-last_message_at,-id", "last_message_at,id"}:
        raise HTTPException(422, "不支持的排序字段。")
    descending = sort.startswith("-")
    ordering = (
        (HelpRequest.last_message_at.desc(), HelpRequest.id.desc())
        if descending
        else (HelpRequest.last_message_at, HelpRequest.id)
    )
    base = select(HelpRequest).where(HelpRequest.student_id == user.id)
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = db.scalars(
        base.order_by(*ordering).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return _paged([_serialize(db, row) for row in rows], total, page, page_size)


@student_router.post("/{request_id}/attachments", status_code=201)
async def student_upload_help_attachment(
    request_id: int,
    request: Request,
    file: UploadFile = File(...),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
):
    require_student_csrf(request)
    if not idempotency_key:
        raise HTTPException(422, "缺少 Idempotency-Key。")
    row = _student_row_or_404(db, user.id, request_id)
    attachment = await _help_attachment_upload(
        request=request, db=db, row=row, upload=file, principal_id=user.id,
        principal_kind="student", idempotency_key=idempotency_key,
    )
    # 学生端先创建文字消息、再上传文件；只允许绑定到该请求最新的本人消息。
    message = db.scalar(
        select(HelpMessage)
        .where(HelpMessage.help_request_id == row.id, HelpMessage.sender_user_id == user.id)
        .order_by(HelpMessage.id.desc())
        .limit(1)
    )
    if message is None:
        raise HTTPException(409, "请先发送消息再上传附件。")
    attachment.help_message_id = message.id
    db.commit()
    db.refresh(attachment)
    return {"id": attachment.id, "kind": attachment.kind, "mime": attachment.mime,
            "byte_size": attachment.byte_size, "original_name": attachment.original_name,
            "url": f"/api/help-attachments/{attachment.id}"}


@student_message_router.post("/{message_id}/recall")
def student_recall_help_message(
    message_id: int,
    request: Request,
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
):
    require_student_csrf(request)
    limit(request, "help-message-recall", f"student:{user.id}", 20, 60)
    message = db.get(HelpMessage, message_id)
    if message is None:
        raise HTTPException(404, "消息不存在。")
    _student_row_or_404(db, user.id, message.help_request_id)
    student_audit(
        db, request.app.state.settings, "help_message_recall", "success", client_ip(request), user.id,
        resource_type="help_message", resource_id=message.id, summary={"schema_version": 1},
    )
    result = _recall_message(request=request, db=db, message=message, actor_id=user.id, actor_kind="student")
    return result


@student_chat_router.get("")
def student_chat_lines(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    sort: str = Query(default="-last_message_at,-id"),
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
):
    if sort not in {"-last_message_at,-id", "last_message_at,id"}:
        raise HTTPException(422, "不支持的排序字段。")
    descending = sort.startswith("-")
    ordering = (
        (HelpChatLine.last_message_at.desc(), HelpChatLine.id.desc())
        if descending
        else (HelpChatLine.last_message_at, HelpChatLine.id)
    )
    base = select(HelpChatLine).where(HelpChatLine.student_id == user.id)
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = db.scalars(
        base.order_by(*ordering).offset((page - 1) * page_size).limit(page_size)
    ).all()
    result = _paged(
        [_line_payload(db, row, viewer_student_id=user.id) for row in rows],
        total,
        page,
        page_size,
    )
    available = db.execute(
        select(ClassGroup.id, ClassGroup.name, ClassGroup.course_id, Course.title)
        .join(ClassMember, ClassMember.class_id == ClassGroup.id)
        .join(Course, Course.id == ClassGroup.course_id)
        .where(
            ClassMember.student_id == user.id,
            ClassMember.status == "active",
            ClassMember.left_at.is_(None),
            ClassGroup.status == "active",
        )
        .order_by(ClassGroup.name, ClassGroup.id)
    ).all()
    result["available_classes"] = [
        {
            "class_id": class_id,
            "class_name": class_name,
            "course_id": course_id,
            "course_title": course_title,
        }
        for class_id, class_name, course_id, course_title in available
    ]
    return result


@student_chat_router.websocket("/events")
async def student_chat_events(websocket: WebSocket):
    user_id = None
    try:
        # WebSocket can be idle for hours.  Authenticate with a short session,
        # then create another short session only while handling an event.
        db = websocket.app.state.session_factory()
        try:
            user_id = current_user(websocket, db).id
        finally:
            db.rollback()
            db.close()
        if not help_realtime_hub.consume_ticket(_websocket_ticket(websocket), "student", user_id):
            raise HTTPException(403)
        await help_realtime_hub.connect_student(user_id, websocket)
        while True:
            event = await websocket.receive_json()
            if not isinstance(event, dict) or event.get("type") != "typing":
                continue
            line_id = event.get("chat_line_id")
            if not isinstance(line_id, int) or not isinstance(event.get("is_typing"), bool):
                continue
            if not _typing_allowed(websocket, f"student:{user_id}"):
                continue
            db = websocket.app.state.session_factory()
            try:
                line = db.scalar(select(HelpChatLine).where(
                    HelpChatLine.id == line_id, HelpChatLine.student_id == user_id
                ))
                if line is not None:
                    _publish_line_change(
                        db,
                        line,
                        "student_typing" if event["is_typing"] else "student_stopped_typing",
                    )
            finally:
                db.rollback()
                db.close()
    except (HTTPException, WebSocketDisconnect):
        if websocket.client_state.name != "DISCONNECTED":
            await websocket.close(code=1008)
    finally:
        if user_id is not None:
            help_realtime_hub.disconnect_student(user_id, websocket)


@student_chat_router.post("/events/ticket")
def student_chat_events_ticket(
    request: Request,
    user: User = Depends(current_user),
):
    require_student_csrf(request)
    try:
        return {"ticket": help_realtime_hub.issue_ticket("student", user.id)}
    except HelpRealtimeUnavailable as exc:
        raise HTTPException(503, "实时答疑暂不可用。") from exc


@student_chat_router.get("/{line_id}")
def student_chat_line_detail(
    line_id: int,
    before_id: int | None = Query(default=None, gt=0),
    limit: int = Query(default=20, ge=1, le=100),
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
):
    row = db.scalar(
        select(HelpChatLine).where(
            HelpChatLine.id == line_id,
            HelpChatLine.student_id == user.id,
        )
    )
    if row is None:
        raise HTTPException(404, "聊天线不存在。")
    read_changed = _mark_student_line_read(db, row)
    payload = _line_payload(
        db,
        row,
        include_requests=True,
        viewer_student_id=user.id,
        before_id=before_id,
        message_limit=limit,
    )
    if read_changed:
        _publish_line_change(db, row, "student_read")
    return payload


@student_router.get("/{request_id}")
def student_detail(
    request_id: int,
    request: Request,
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
):
    return _serialize(db, _student_row_or_404(db, user.id, request_id))


@student_router.post("/{request_id}/close")
def student_close(
    request_id: int,
    request: Request,
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
):
    require_student_csrf(request)
    row = _student_row_or_404(db, user.id, request_id)
    if row.status in {"open", "answered"}:
        old_status = row.status
        row.status, row.closed_at = "closed", utcnow()
        audit(
            db,
            request.app.state.settings,
            "help_request_close",
            "success",
            client_ip(request),
            resource_type="help_request",
            resource_id=row.id,
            user_id=user.id,
            summary=diff_summary({"status": old_status}, {"status": row.status}, ("status",)),
        )
        db.commit()
    return _serialize(db, row)


@admin_router.get("")
def admin_list(
    request: Request,
    status: str | None = Query(default=None, pattern="^(open|answered|closed)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    sort: str = Query(default="-last_message_at,-id"),
    admin=Depends(current_admin),
    db: Session = Depends(db_session),
):
    # 功能闸必须在范围闸之前：只靠 visible_class_ids() + 承办人判断，等于让
    # 「有没有这项能力」由「是不是承办人」代答——一个有 manage_classes、没有
    # help_respond 的角色就能读到范围内全部答疑正文（本端点下发 body 与 messages）。
    # 同文件另外六处管理端端点都有这道闸，只有这里漏了。
    _require_help_respond(admin, db)
    if sort not in {"-last_message_at,-id", "last_message_at,id"}:
        raise HTTPException(422, "不支持的排序字段。")
    stmt = select(HelpRequest)
    class_ids = visible_class_ids(admin, db)
    if class_ids is not None:
        stmt = stmt.where(HelpRequest.class_id.in_(class_ids))
    if not has_capability(admin, "manage_classes"):
        stmt = stmt.where(HelpRequest.assigned_admin_user_id == admin.id)
    if status:
        stmt = stmt.where(HelpRequest.status == status)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    ordering = (
        (HelpRequest.last_message_at.desc(), HelpRequest.id.desc())
        if sort.startswith("-")
        else (HelpRequest.last_message_at, HelpRequest.id)
    )
    rows = db.scalars(
        stmt.order_by(*ordering).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return _paged([_serialize(db, row) for row in rows], total, page, page_size)


@admin_chat_router.get("")
def admin_chat_lines(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    sort: str = Query(default="-waiting_seconds,-last_message_at,-id"),
    filter: str = Query(default="all", pattern="^(waiting|mine|all|closed)$"),
    admin=Depends(current_admin),
    db: Session = Depends(db_session),
):
    _require_help_respond(admin, db)
    if sort != "-waiting_seconds,-last_message_at,-id":
        raise HTTPException(422, "不支持的排序字段。")
    # A chat line may contain historical closed requests.  The queue is driven
    # by the newest open request, exactly as `_line_payload()` derives `active`.
    active_request_id = (
        select(HelpRequest.id)
        .where(
            HelpRequest.chat_line_id == HelpChatLine.id,
            HelpRequest.status == "open",
        )
        .order_by(HelpRequest.last_message_at.desc(), HelpRequest.id.desc())
        .limit(1)
        .correlate(HelpChatLine)
        .scalar_subquery()
    )
    active_assignee_id = (
        select(HelpRequest.assigned_admin_user_id)
        .where(HelpRequest.id == active_request_id)
        .correlate(HelpChatLine)
        .scalar_subquery()
    )
    active_last_message_at = (
        select(HelpRequest.last_message_at)
        .where(HelpRequest.id == active_request_id)
        .correlate(HelpChatLine)
        .scalar_subquery()
    )
    stmt = select(HelpChatLine)
    class_ids = visible_class_ids(admin, db)
    if class_ids is not None:
        stmt = stmt.where(HelpChatLine.class_id.in_(class_ids))
    if filter == "closed":
        stmt = stmt.where(HelpChatLine.ended_at.is_not(None))
    elif filter == "mine":
        stmt = stmt.where(active_assignee_id == admin.id)
    elif filter == "waiting":
        stmt = stmt.where(
            active_request_id.is_not(None), active_assignee_id == admin.id
        )
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    # For an open request, waiting_seconds is now - last_message_at; descending
    # waiting time is therefore ascending SQL timestamp.  The CASE keeps lines
    # without an open request at zero, and the final id remains the unique tie-breaker.
    waiting_order = case((active_request_id.is_not(None), 1), else_=0).desc()
    rows = db.scalars(
        stmt.order_by(
            waiting_order,
            active_last_message_at.asc(),
            HelpChatLine.last_message_at.desc(),
            HelpChatLine.id.desc(),
        ).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return _paged(
        [_line_payload(db, row, viewer_admin_id=admin.id) for row in rows],
        total,
        page,
        page_size,
    )


@admin_chat_router.websocket("/events")
async def admin_chat_events(websocket: WebSocket):
    admin_id = None
    try:
        db = websocket.app.state.session_factory()
        try:
            admin = current_admin(websocket, db)
            _require_help_respond(admin, db)
            admin_id = admin.id
        finally:
            db.rollback()
            db.close()
        if not help_realtime_hub.consume_ticket(_websocket_ticket(websocket), "admin", admin_id):
            raise HTTPException(403)
        await help_realtime_hub.connect_admin(admin_id, websocket)
        while True:
            event = await websocket.receive_json()
            if not isinstance(event, dict) or event.get("type") != "typing":
                continue
            line_id = event.get("chat_line_id")
            if not isinstance(line_id, int) or not isinstance(event.get("is_typing"), bool):
                continue
            if not _typing_allowed(websocket, f"admin:{admin_id}"):
                continue
            # 查不到就跳过这一帧，不要抛——循环外的 except 会把整条连接以 1008
            # 关掉，等于一个过期的 chat_line_id 就能让教师掉线。学生侧同一位置
            # 用的就是「查不到则跳过」，两侧行为必须一致。
            db = websocket.app.state.session_factory()
            try:
                try:
                    admin = db.get(AdminUser, admin_id)
                    if admin is None:
                        continue
                    line = _admin_line_or_404(db, admin, line_id)
                except HTTPException:
                    continue
                _publish_line_change(
                    db,
                    line,
                    "admin_typing" if event["is_typing"] else "admin_stopped_typing",
                )
            finally:
                db.rollback()
                db.close()
    except HTTPException:
        await websocket.close(code=1008)
    except WebSocketDisconnect:
        pass
    finally:
        if admin_id is not None:
            help_realtime_hub.disconnect_admin(admin_id, websocket)


@admin_chat_router.post("/events/ticket")
def admin_chat_events_ticket(
    request: Request,
    admin=Depends(current_admin),
    db: Session = Depends(db_session),
):
    require_admin_csrf(request)
    _require_help_respond(admin, db)
    try:
        return {"ticket": help_realtime_hub.issue_ticket("admin", admin.id)}
    except HelpRealtimeUnavailable as exc:
        raise HTTPException(503, "实时答疑暂不可用。") from exc


@admin_chat_router.get("/{line_id}")
def admin_chat_line_detail(
    line_id: int,
    before_id: int | None = Query(default=None, gt=0),
    limit: int = Query(default=20, ge=1, le=100),
    admin=Depends(current_admin),
    db: Session = Depends(db_session),
):
    _require_help_respond(admin, db)
    line = _admin_line_or_404(db, admin, line_id)
    payload = _line_payload(
        db,
        line,
        include_requests=True,
        viewer_admin_id=admin.id,
        before_id=before_id,
        message_limit=limit,
    )
    latest_id = db.scalar(
        select(func.max(HelpMessage.id)).join(HelpRequest, HelpRequest.id == HelpMessage.help_request_id)
        .where(HelpRequest.chat_line_id == line.id)
    )
    if latest_id is not None:
        cursor = db.get(HelpChatLineRead, (admin.id, line.id))
        if cursor is None:
            cursor = HelpChatLineRead(admin_user_id=admin.id, chat_line_id=line.id, last_read_message_id=latest_id)
            db.add(cursor)
        else:
            cursor.last_read_message_id = latest_id
        db.commit()
        payload["unread_count"] = 0
    payload["assignment_candidates"] = _assignment_candidates(db, line.class_id)
    active = next(
        (
            row
            for row in db.scalars(
                select(HelpRequest)
                .where(
                    HelpRequest.chat_line_id == line.id,
                    HelpRequest.status == "open",
                )
                .order_by(HelpRequest.last_message_at.desc(), HelpRequest.id.desc())
            ).all()
        ),
        None,
    )
    current = next(
        (
            row
            for row in db.scalars(
                select(HelpRequest)
                .where(
                    HelpRequest.chat_line_id == line.id,
                    HelpRequest.status.in_(("open", "answered")),
                )
                .order_by(HelpRequest.last_message_at.desc(), HelpRequest.id.desc())
            ).all()
        ),
        None,
    )
    payload["can_reply"] = _can_act_on_request(db, admin, current)
    payload["can_reassign"] = _can_act_on_request(db, admin, active)
    return payload


@admin_router.get("/{request_id}")
def admin_detail(
    request_id: int,
    request: Request,
    admin=Depends(current_admin),
    db: Session = Depends(db_session),
):
    _require_help_respond(admin, db)
    row = _admin_row_or_404(db, admin, request_id)
    payload = _serialize(db, row)
    payload["assignment_candidates"] = _assignment_candidates(db, row.class_id)
    payload["can_reply"] = _can_act_on_request(db, admin, row)
    payload["can_reassign"] = _can_act_on_request(db, admin, row)
    return payload


@admin_router.patch("/{request_id}/assignment")
def reassign(
    request_id: int,
    payload: AssignmentPayload,
    request: Request,
    if_match: str | None = Header(default=None, alias="If-Match"),
    admin=Depends(current_admin),
    db: Session = Depends(db_session),
):
    require_admin_csrf(request)
    _require_help_respond(admin, db)
    row = _admin_row_or_404(db, admin, request_id)
    if if_match is None:
        raise HTTPException(428, "请携带 If-Match 承办版本号。")
    try:
        expected_revision = int(if_match.strip().strip('"'))
    except ValueError as exc:
        raise HTTPException(400, "If-Match 必须是非负整数版本号。") from exc
    if expected_revision < 0:
        raise HTTPException(400, "If-Match 必须是非负整数版本号。")
    if expected_revision != row.assignment_revision:
        raise HTTPException(409, "承办版本已变化，请刷新后重试。")
    target_assignment = db.scalar(
        select(ClassTeacher).where(
            ClassTeacher.class_id == row.class_id,
            ClassTeacher.admin_user_id == payload.target_admin_user_id,
            ClassTeacher.ended_at.is_(None),
            ClassTeacher.role_in_class.in_(("teacher", "assistant")),
        )
    )
    target_admin = db.get(AdminUser, payload.target_admin_user_id)
    if (
        target_assignment is None
        or target_admin is None
        or target_admin.status != "active"
        or not can_respond_to_help(target_admin, db)
    ):
        if target_admin is not None:
            log_scope_denial(admin, "help_assignment_target", payload.target_admin_user_id)
        raise HTTPException(404, "带班人员不存在。")
    previous = row.assigned_admin_user_id
    row.assigned_admin_user_id = payload.target_admin_user_id
    row.assignment_revision += 1
    create_notification(
        db,
        kind="help_request_assigned",
        title="工单已重新分配",
        body="一条学生联系已转交给你。",
        target_type="help_request",
        target_id=row.id,
        source_type="help_request",
        source_id=row.id,
        link_url=admin_help_request_link(row.id, row.chat_line_id),
        idempotency_key=f"help-request-assigned:{row.id}:{row.assignment_revision}",
        recipients=[{"user_id": None, "admin_user_id": row.assigned_admin_user_id}],
    )
    audit(
        db,
        request.app.state.settings,
        "help_request_reassign",
        "success",
        client_ip(request),
        admin.id,
        resource_type="help_request",
        resource_id=row.id,
        user_id=row.student_id,
        summary={
            "schema_version": 1,
            "changed": {
                "assigned_admin_user_id": {"old": previous, "new": row.assigned_admin_user_id},
                "assignment_revision": {
                    "old": row.assignment_revision - 1,
                    "new": row.assignment_revision,
                },
            },
        },
    )
    db.commit()
    _publish_line_change(db, db.get(HelpChatLine, row.chat_line_id), "assignment_changed")
    return _serialize(db, row)


@admin_router.post("/{request_id}/messages", status_code=201)
def reply(
    request_id: int,
    payload: HelpMessagePayload,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    admin=Depends(current_admin),
    db: Session = Depends(db_session),
):
    require_admin_csrf(request)
    _require_help_respond(admin, db)
    if not idempotency_key:
        raise HTTPException(422, "缺少 Idempotency-Key。")
    row = _admin_row_or_404(db, admin, request_id)
    limit(request, "help-request-reply", f"{admin.id}:{row.id}", 20, 60)
    key_hash = _hash(idempotency_key)
    input_hash = request_hash({"help_request_id": row.id, **payload.model_dump()})
    existing = db.scalar(
        select(HelpMessage).where(
            HelpMessage.help_request_id == row.id,
            HelpMessage.sender_admin_user_id == admin.id,
            HelpMessage.request_key_hash == key_hash,
        )
    )
    if existing:
        if existing.request_hash != input_hash:
            raise HTTPException(409, "Idempotency-Key 已用于不同请求。")
        return {"id": existing.id, "created_at": existing.created_at}
    if row.status == "closed":
        raise HTTPException(409, "联系记录已关闭，等学生再次提问后可继续回复。")
    message = HelpMessage(
        help_request_id=row.id,
        sender_admin_user_id=admin.id,
        body=plain_text(payload.body),
        request_key_hash=key_hash,
    )
    message.request_hash = input_hash
    db.add(message)
    db.flush()
    _bind_staged_attachments(
        db, attachment_ids=payload.attachment_ids, row=row, message=message,
        principal_id=admin.id, principal_kind="admin",
    )
    now = utcnow()
    row.last_message_at = now
    line = db.get(HelpChatLine, row.chat_line_id)
    line.last_message_at = now
    if row.status in {"open", "answered"}:
        old_status = row.status
        row.status = "answered"
        row.answered_at = utcnow()
    audit(
        db,
        request.app.state.settings,
        "help_request_reply",
        "success",
        client_ip(request),
        admin.id,
        resource_type="help_request",
        resource_id=row.id,
        user_id=row.student_id,
        summary=diff_summary({"status": old_status}, {"status": row.status}, ("status",)),
    )
    db.commit()
    _publish_line_change(db, line, "admin_message", row)
    return {"id": message.id, "created_at": message.created_at}


@admin_router.post("/{request_id}/attachments", status_code=201)
async def admin_upload_help_attachment(
    request_id: int,
    request: Request,
    file: UploadFile = File(...),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    admin=Depends(current_admin),
    db: Session = Depends(db_session),
):
    require_admin_csrf(request)
    _require_help_respond(admin, db)
    if not idempotency_key:
        raise HTTPException(422, "缺少 Idempotency-Key。")
    row = _admin_row_or_404(db, admin, request_id)
    attachment = await _help_attachment_upload(
        request=request, db=db, row=row, upload=file, principal_id=admin.id,
        principal_kind="admin", idempotency_key=idempotency_key,
    )
    return {"id": attachment.id, "kind": attachment.kind, "mime": attachment.mime,
            "byte_size": attachment.byte_size, "original_name": attachment.original_name}


@admin_message_router.post("/{message_id}/recall")
def admin_recall_help_message(
    message_id: int,
    request: Request,
    admin=Depends(current_admin),
    db: Session = Depends(db_session),
):
    require_admin_csrf(request)
    _require_help_respond(admin, db)
    limit(request, "help-message-recall", f"admin:{admin.id}", 20, 60)
    message = db.get(HelpMessage, message_id)
    if message is None:
        raise HTTPException(404, "消息不存在。")
    _admin_row_or_404(db, admin, message.help_request_id)
    audit(
        db, request.app.state.settings, "help_message_recall", "success", client_ip(request), admin.id,
        resource_type="help_message", resource_id=message.id,
        summary={"schema_version": 1},
    )
    result = _recall_message(request=request, db=db, message=message, actor_id=admin.id, actor_kind="admin")
    return result


@attachment_router.get("/{attachment_id}")
def read_help_attachment(
    attachment_id: int,
    request: Request,
    db: Session = Depends(db_session),
):
    attachment = db.get(HelpMessageAttachment, attachment_id)
    if attachment is None:
        raise HTTPException(404, "附件不存在。")
    message = db.get(HelpMessage, attachment.help_message_id) if attachment.help_message_id else None
    row = db.get(HelpRequest, message.help_request_id) if message else None
    if request.cookies.get("admin_access_token"):
        admin = current_admin(request, db)
        _require_help_respond(admin, db)
        if row is None or not _can_act_on_request(db, admin, row):
            if row is not None:
                log_scope_denial(admin, "help_attachment", attachment_id)
            raise HTTPException(404, "附件不存在。")
    else:
        user = current_user(request, db)
        if row is None or row.student_id != user.id:
            raise HTTPException(404, "附件不存在。")
    if attachment.purged_at is not None:
        raise HTTPException(410, "附件已过期。")
    path = _attachment_path(request.app.state.settings, attachment)
    if not path.is_file():
        raise HTTPException(410, "附件已过期。")
    return Response(content=path.read_bytes(), media_type=attachment.mime,
                    headers={"Cache-Control": "private, no-store"})


@admin_attachment_router.post("/{attachment_id}/purge")
def purge_help_attachment(
    attachment_id: int,
    request: Request,
    admin=Depends(current_admin),
    db: Session = Depends(db_session),
):
    require_admin_csrf(request)
    _require_help_respond(admin, db)
    attachment = db.get(HelpMessageAttachment, attachment_id)
    message = db.get(HelpMessage, attachment.help_message_id) if attachment else None
    row = db.get(HelpRequest, message.help_request_id) if message else None
    if attachment is None or row is None or not _can_act_on_request(db, admin, row):
        if attachment is not None:
            log_scope_denial(admin, "help_attachment", attachment_id)
        raise HTTPException(404, "附件不存在。")
    if attachment.purged_at is None:
        _attachment_path(request.app.state.settings, attachment).unlink(missing_ok=True)
        attachment.purged_at = utcnow()
        audit(
            db, request.app.state.settings, "help_attachment_purge", "success", client_ip(request), admin.id,
            resource_type="help_attachment", resource_id=attachment.id,
            summary={"schema_version": 1},
        )
        db.commit()
        _publish_line_change(db, db.get(HelpChatLine, row.chat_line_id), "attachment_purged", row)
    return {"id": attachment.id, "purged_at": attachment.purged_at}


@admin_router.post("/{request_id}/close")
def admin_close(
    request_id: int,
    request: Request,
    admin=Depends(current_admin),
    db: Session = Depends(db_session),
):
    require_admin_csrf(request)
    _require_help_respond(admin, db)
    row = _admin_row_or_404(db, admin, request_id)
    if row.status in {"open", "answered"}:
        old_status = row.status
        row.status, row.closed_at = "closed", utcnow()
        audit(
            db,
            request.app.state.settings,
            "help_request_close",
            "success",
            client_ip(request),
            admin.id,
            resource_type="help_request",
            resource_id=row.id,
            user_id=row.student_id,
            summary=diff_summary({"status": old_status}, {"status": row.status}, ("status",)),
        )
        db.commit()
        _publish_line_change(db, db.get(HelpChatLine, row.chat_line_id), "closed")
    return _serialize(db, row)
