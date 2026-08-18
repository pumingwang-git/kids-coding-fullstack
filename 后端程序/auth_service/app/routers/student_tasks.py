"""学生任务中心的只读列表。状态与 DTO 全部委托给 ``app.student_tasks``。"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Problem, ProblemTag, StudentMistake, Tag
from ..routers.courses import continue_learning
from ..security import as_utc
from ..student_tasks import (
    DUE_SOON_HOURS, EXAM_PHASE_LABELS, TASK_GROUP_LIMIT, HOMEWORK_PHASE_LABELS,
    PRACTICE_PHASE_LABELS, build_exam_item, build_homework_item, build_practice_item,
    collect_exam_candidates, collect_homework_candidates, collect_practice_candidates,
    exam_phase, homework_phase, practice_phase,
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


def _group(items: list[dict]) -> dict:
    return {"items": items[:TASK_GROUP_LIMIT], "total": len(items)}


def _normalize_learning_times(items: list[dict]) -> list[dict]:
    for item in items:
        value = item.get("last_learned_at")
        if value:
            item["last_learned_at"] = value.replace("+00:00", "Z")
    return items


def _exam_rows(db: Session, user, now: datetime) -> list[tuple[dict, str]]:
    return [(build_exam_item(source, exam_phase(source, now), token), exam_phase(source, now))
            for source, _paper, token in collect_exam_candidates(db, user)]


@router.get("/exams")
def list_exams(
    request: Request, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    status: str | None = None, db: Session = Depends(db_session),
):
    user = current_user(request, db)
    if status is not None and status not in EXAM_PHASE_LABELS:
        raise HTTPException(422, "status 参数无效。")
    rows = _exam_rows(db, user, datetime.now(UTC))
    if status is not None:
        rows = [row for row in rows if row[1] == status]
    rows.sort(key=lambda row: (row[0]["open_at"] or "", row[0]["source_id"]))
    return _page([item for item, _phase in rows], page, page_size)


@router.get("/tasks/overview")
def tasks_overview(request: Request, db: Session = Depends(db_session)):
    user = current_user(request, db)
    now = datetime.now(UTC)
    homework_rows = [(candidate, homework_phase(candidate["facts"], now))
                     for candidate in collect_homework_candidates(db, user)]
    practice_rows = [(candidate, practice_phase(candidate["completed"], candidate["tries"]))
                     for candidate in collect_practice_candidates(db, user)]

    homework_items = {id(candidate): build_homework_item(candidate, phase)
                      for candidate, phase in homework_rows}
    practice_items = {id(candidate): build_practice_item(candidate, phase)
                      for candidate, phase in practice_rows}
    in_progress = [item for candidate, phase in homework_rows if phase == "in_progress"
                   for item in [homework_items[id(candidate)]]]
    in_progress.extend(item for item, phase in _exam_rows(db, user, now) if phase == "running")
    deadline = now + timedelta(hours=DUE_SOON_HOURS)
    due_soon = [homework_items[id(candidate)] for candidate, phase in homework_rows
                if phase == "todo" and candidate["facts"].due_at is not None
                and now <= as_utc(candidate["facts"].due_at) <= deadline]
    to_review = [homework_items[id(candidate)] for candidate, phase in homework_rows
                 if phase == "graded"]
    unfinished = [practice_items[id(candidate)] for candidate, phase in practice_rows
                  if phase == "in_progress"]
    unfinished.extend(homework_items[id(candidate)] for candidate, phase in homework_rows
                      if phase == "overdue")

    learning = continue_learning(request, db, limit_count=TASK_GROUP_LIMIT)
    pending_review = db.scalar(select(func.count()).select_from(StudentMistake).where(
        StudentMistake.student_id == user.id,
        StudentMistake.status == "pending_review",
        StudentMistake.next_review_at <= now,
    )) or 0
    next_up_items = _normalize_learning_times(learning.get("items", []))
    if pending_review:
        next_up_items.append({"kind": "mistakes_review", "total": pending_review,
                              "path": "/mistakes"})
    next_up = _group(next_up_items)
    return {
        "in_progress": _group(in_progress),
        "due_soon": _group(due_soon),
        "to_review": _group(to_review),
        "unfinished": _group(unfinished),
        "next_up": next_up,
    }
