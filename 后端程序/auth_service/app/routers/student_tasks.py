"""学生任务中心的只读列表。状态与 DTO 全部委托给 ``app.student_tasks``。"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

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


def _homework_segment(candidate: dict, phase: str, now: datetime, week_end: datetime) -> str:
    if phase in {"overdue", "submitted", "graded"}:
        return phase
    due_at = candidate["facts"].due_at
    if due_at is None:
        return "later"
    due = as_utc(due_at)
    if due <= now + timedelta(hours=48):
        return "due_48h"
    if due > week_end:
        return "later"
    return "this_week"


def _week_end_utc(now: datetime) -> datetime:
    local_now = now.astimezone(ZoneInfo("Asia/Shanghai"))
    return (
        local_now + timedelta(days=6 - local_now.weekday())
    ).replace(
        hour=23, minute=59, second=59, microsecond=999999,
    ).astimezone(UTC)


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
    week_end = _week_end_utc(now)
    counts = {
        "due_48h": 0, "this_week": 0, "later": 0,
        "overdue": 0, "submitted": 0, "graded": 0,
    }
    items = []
    for candidate, phase in rows:
        segment = _homework_segment(candidate, phase, now, week_end)
        counts[segment] += 1
        item = build_homework_item(candidate, phase)
        item["segment"] = segment
        items.append(item)
    result = _page(items, page, page_size)
    result["counts"] = counts
    return result


@router.get("/practice")
def list_practice(
    request: Request, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    course_id: int | None = None, lesson_id: int | None = None, knowledge: str | None = None,
    section_id: int | None = None, status: str | None = None,
    db: Session = Depends(db_session),
):
    user = current_user(request, db)
    if status is not None and status not in PRACTICE_PHASE_LABELS:
        raise HTTPException(422, "status 参数无效。")
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
    if section_id is not None:
        rows = [row for row in rows if row["section_id"] == section_id]
    rows.sort(key=lambda row: (
        row["course_id"], row["section_sort"], row["lesson_sort"],
        row["block_sort"], row["source_id"],
    ))
    if status is not None:
        rows = [row for row in rows if practice_phase(row["completed"], row["tries"]) == status]
    return _page([build_practice_item(row, practice_phase(row["completed"], row["tries"]))
                  for row in rows], page, page_size)


def _practice_filters(db: Session, rows: list[dict]) -> dict:
    """筛选项只列该学生实际有的课包 / 章节 / 知识点。

    **必须用未筛选的候选集算**：若跟着当前选择一起收窄，选了某个课包之后章节下拉
    会塌成只剩那一条，学生再也切不回去。筛选项描述的是「可选范围」，不是「当前结果」。
    """
    courses = {row["course_id"]: row["course_title"] for row in rows}
    sections = {
        row["section_id"]: (row["section_title"], row["course_id"], row["section_sort"])
        for row in rows
    }
    numbers = {row["problem_id_no"] for row in rows}
    knowledge = sorted(set(db.scalars(
        select(Tag.name)
        .join(ProblemTag, ProblemTag.tag_id == Tag.id)
        .join(Problem, Problem.id == ProblemTag.problem_id)
        .where(Tag.category == "knowledge", Problem.problem_id_no.in_(numbers or [""]))
    )))
    return {
        "courses": [{"id": course_id, "title": title}
                    for course_id, title in sorted(courses.items())],
        "sections": [{"id": section_id, "title": title, "course_id": course_id}
                     for section_id, (title, course_id, _sort) in sorted(
                         sections.items(), key=lambda row: (row[1][1], row[1][2], row[0]))],
        "knowledge": knowledge,
    }


@router.get("/practice/queue")
def practice_queue(
    request: Request, course_id: int | None = None, section_id: int | None = None,
    knowledge: str | None = None, preview: int = Query(3, ge=1, le=10),
    db: Session = Depends(db_session),
):
    user = current_user(request, db)
    all_rows = collect_practice_candidates(db, user)
    rows = all_rows
    if course_id is not None:
        rows = [row for row in rows if row["course_id"] == course_id]
    if section_id is not None:
        rows = [row for row in rows if row["section_id"] == section_id]
    if knowledge:
        problem_numbers = set(db.scalars(
            select(Problem.problem_id_no)
            .join(ProblemTag, ProblemTag.problem_id == Problem.id)
            .join(Tag, Tag.id == ProblemTag.tag_id)
            .where(Tag.category == "knowledge", Tag.name == knowledge)
        ))
        rows = [row for row in rows if row["problem_id_no"] in problem_numbers]
    now = datetime.now(UTC)
    current_ids = {
        item.get("continue_lesson_id")
        for item in continue_learning(request, db, limit_count=20).get("items", [])
    }
    mistakes = db.scalars(select(StudentMistake).where(
        StudentMistake.student_id == user.id,
        StudentMistake.status == "pending_review",
        StudentMistake.next_review_at <= now,
    )).all()
    problem_ids = [mistake.problem_id for mistake in mistakes]
    problems = {problem.id: problem for problem in db.scalars(
        select(Problem).where(Problem.id.in_(problem_ids or [0]))
    )}
    mistake_items = [{
        "source_type": "mistake",
        "source_id": mistake.id,
        "scope": {
            "key": f"mistake:{mistake.id}",
            "title": problems[mistake.problem_id].title
            if mistake.problem_id in problems else "错题",
        },
        "phase": "todo",
        "phase_label": "该复习了",
        "reason": "review",
        "reason_label": "该复习了",
        "origin": {},
        "entry": {"kind": "mistake", "mistake_id": mistake.id},
        "tries": mistake.review_count,
    } for mistake in mistakes]
    items = []
    reason_labels = {
        "retry": "上次没做对",
        "current_lesson": "正在学的这节",
        "todo": "接着往下练",
    }
    for row in rows:
        phase = practice_phase(row["completed"], row["tries"])
        if phase == "done":
            continue
        reason = "retry" if row["tries"] > 0 else (
            "current_lesson" if row["lesson_id"] in current_ids else "todo"
        )
        item = build_practice_item(row, phase)
        item.update(reason=reason, reason_label=reason_labels[reason])
        items.append(item)
    priority = {"retry": 0, "review": 1, "current_lesson": 2, "todo": 3}
    items = mistake_items + items
    items.sort(key=lambda item: (
        priority[item["reason"]],
        item.get("origin", {}).get("course_id", 0),
        item.get("origin", {}).get("section_sort", 0),
        item.get("origin", {}).get("lesson_sort", 0),
        item.get("origin", {}).get("block_sort", 0),
        item.get("source_id", 0),
    ))
    counts = {
        "retry": sum(item["reason"] == "retry" for item in items),
        "review": sum(item["reason"] == "review" for item in items),
        "todo": sum(item["reason"] in {"todo", "current_lesson"} for item in items),
        "done": sum(row["completed"] for row in rows),
    }
    return {
        "current": items[0] if items else None,
        "upcoming": items[1:1 + preview],
        "counts": counts,
        "filters": _practice_filters(db, all_rows),
    }


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

    week_end = _week_end_utc(now)
    homework_items = {}
    for candidate, phase in homework_rows:
        item = build_homework_item(candidate, phase)
        item["segment"] = _homework_segment(candidate, phase, now, week_end)
        homework_items[id(candidate)] = item
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
