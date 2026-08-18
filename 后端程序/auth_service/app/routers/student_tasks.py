"""学生任务中心的只读列表。状态与 DTO 全部委托给 ``app.student_tasks``。"""
from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Problem, ProblemTag, Tag
from ..security import as_utc
from ..student_tasks import (
    HOMEWORK_PHASE_LABELS, PRACTICE_PHASE_LABELS, build_homework_item,
    build_practice_item, collect_homework_candidates, collect_practice_candidates,
    homework_phase, practice_phase,
)
from .auth_secure import current_user, db_session


router = APIRouter(prefix="/api/student", tags=["student-tasks"])


def _page(items: list[dict], page: int, page_size: int) -> dict:
    total = len(items)
    start = (page - 1) * page_size
    return {"items": items[start:start + page_size], "total": total,
            "page": page, "page_size": page_size}


@router.get("/homework")
def list_homework(
    request: Request, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    status: str | None = None, course_id: int | None = None, sort: str = "due_at",
    db: Session = Depends(db_session),
):
    user = current_user(request, db)
    if status is not None and status not in HOMEWORK_PHASE_LABELS:
        raise HTTPException(422, "status 参数无效。")
    if sort not in {"due_at", "-due_at"}:
        raise HTTPException(422, "sort 参数无效。")
    now = datetime.now(UTC)
    rows = [(candidate, homework_phase(candidate["facts"], now))
            for candidate in collect_homework_candidates(db, user)]
    if status is not None:
        rows = [row for row in rows if row[1] == status]
    if course_id is not None:
        rows = [row for row in rows if row[0]["course_id"] == course_id]
    dated = [row for row in rows if row[0]["facts"].due_at is not None]
    undated = [row for row in rows if row[0]["facts"].due_at is None]
    dated.sort(key=lambda row: row[0]["source_id"])
    dated.sort(key=lambda row: as_utc(row[0]["facts"].due_at), reverse=sort == "-due_at")
    undated.sort(key=lambda row: row[0]["source_id"])
    rows = dated + undated
    return _page([build_homework_item(candidate, phase) for candidate, phase in rows], page, page_size)


@router.get("/practice")
def list_practice(
    request: Request, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    course_id: int | None = None, lesson_id: int | None = None, knowledge: str | None = None,
    db: Session = Depends(db_session),
):
    user = current_user(request, db)
    rows = collect_practice_candidates(db, user)
    if course_id is not None:
        rows = [row for row in rows if row["course_id"] == course_id]
    if lesson_id is not None:
        rows = [row for row in rows if row["lesson_id"] == lesson_id]
    if knowledge:
        ids = set(db.scalars(
            select(Problem.problem_id_no)
            .join(ProblemTag, ProblemTag.problem_id == Problem.id)
            .join(Tag, Tag.id == ProblemTag.tag_id)
            .where(Tag.category == "knowledge", Tag.name == knowledge)
        ))
        rows = [row for row in rows if row["problem_id_no"] in ids]
    rows.sort(key=lambda row: row["source_id"])
    return _page([build_practice_item(row, practice_phase(row["completed"], row["tries"]))
                  for row in rows], page, page_size)
