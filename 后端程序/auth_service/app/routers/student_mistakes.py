"""学生端“我的错题”：只读取服务端自动归档的正式错题。"""
from __future__ import annotations

import json
from collections import Counter
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..mistake_cache import (
    LIST_TTL_SECONDS,
    SUMMARY_TTL_SECONDS,
    get_json,
    list_key,
    set_json,
    summary_key,
    version,
)
from ..mistake_book import mistake_summary, record_review
from ..models import ChoiceOption, FillAnswer, Problem, StudentMistake, StudentMistakeReview
from ..scoring import QuestionSpec, parse_blank_alternatives, score_question
from ..security import as_utc
from .auth_secure import current_user, db_session, limit, require_csrf


router = APIRouter(prefix="/api/student/mistakes", tags=["student-mistakes"])
CHOICE_TYPES = {"choice", "multi_choice", "judge"}
OBJECTIVE_TYPES = CHOICE_TYPES | {"fill"}


class ReviewPayload(BaseModel):
    answer: dict = Field(default_factory=dict)
    source: str = Field(default="single", max_length=24)


def _iso(value: datetime | None) -> str | None:
    return as_utc(value).isoformat() if value else None


def _source_text(value: str) -> str:
    return {"lesson_practice": "课程练习", "exam_link": "考试", "lesson_homework": "课后作业"}.get(value, "练习")


def _parse_date(value: str | None, field: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(422, f"{field} 需要使用 YYYY-MM-DD 格式。") from exc
    return datetime.combine(parsed, datetime.min.time(), tzinfo=timezone.utc)


def _item(mistake: StudentMistake, problem: Problem) -> dict:
    return {
        "id": mistake.id,
        "title": problem.title or "未命名题目",
        "stem": problem.stem,
        "type": problem.type,
        "difficulty": problem.difficulty,
        "status": mistake.status,
        "mastery_level": mistake.mastery_level,
        "wrong_count": mistake.wrong_count,
        "review_count": mistake.review_count,
        "review_correct_count": mistake.review_correct_count,
        "first_wrong_at": _iso(mistake.first_wrong_at),
        "last_wrong_at": _iso(mistake.last_wrong_at),
        "next_review_at": _iso(mistake.next_review_at),
        "source_type": mistake.latest_source_type,
        "source_label": _source_text(mistake.latest_source_type),
        "can_review_here": problem.type in OBJECTIVE_TYPES,
    }


def _problem_payload(db: Session, problem: Problem) -> dict:
    payload = {"title": problem.title, "stem": problem.stem, "type": problem.type}
    if problem.type in CHOICE_TYPES:
        payload["options"] = [
            {"label": row.option_label, "content": row.content}
            for row in db.scalars(
                select(ChoiceOption).where(ChoiceOption.problem_id == problem.id)
                .order_by(ChoiceOption.sort_order, ChoiceOption.id)
            )
        ]
    if problem.type == "fill":
        payload["blank_keys"] = [
            row.blank_key for row in db.scalars(
                select(FillAnswer).where(FillAnswer.problem_id == problem.id)
                .order_by(FillAnswer.blank_index, FillAnswer.id)
            )
        ]
    return payload


def _spec(db: Session, problem: Problem) -> QuestionSpec:
    if problem.type in CHOICE_TYPES:
        options = list(db.execute(
            select(ChoiceOption.option_label, ChoiceOption.is_correct)
            .where(ChoiceOption.problem_id == problem.id)
            .order_by(ChoiceOption.sort_order, ChoiceOption.id)
        ).all())
        return QuestionSpec(type=problem.type, full=1, options=options)
    if problem.type == "fill":
        blanks = [
            (row.blank_key, [row.answer, *parse_blank_alternatives(row.alternatives_json)])
            for row in db.scalars(
                select(FillAnswer).where(FillAnswer.problem_id == problem.id)
                .order_by(FillAnswer.blank_index, FillAnswer.id)
            )
        ]
        return QuestionSpec(type="fill", full=1, blanks=blanks)
    raise HTTPException(409, "这道编程题请从原课程、作业或考试入口重做。")


def _correct_payload(db: Session, problem: Problem) -> dict:
    if problem.type in CHOICE_TYPES:
        return {"labels": list(db.scalars(
            select(ChoiceOption.option_label).where(
                ChoiceOption.problem_id == problem.id, ChoiceOption.is_correct.is_(True)
            ).order_by(ChoiceOption.sort_order, ChoiceOption.id)
        ))}
    if problem.type == "fill":
        return {"blanks": [
            {"blank_key": row.blank_key, "answer": row.answer}
            for row in db.scalars(
                select(FillAnswer).where(FillAnswer.problem_id == problem.id)
                .order_by(FillAnswer.blank_index, FillAnswer.id)
            )
        ]}
    return {}


@router.get("")
def list_mistakes(
    request: Request, status: str | None = Query(default=None, max_length=24),
    source_type: str | None = Query(default=None, max_length=32),
    from_date: str | None = Query(default=None, alias="from", max_length=10),
    to_date: str | None = Query(default=None, alias="to", max_length=10),
    page: int = Query(default=1, ge=1), size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(db_session),
):
    user = current_user(request, db)
    limit(request, "student-mistakes-read", str(user.id), 120, 60)
    redis_url = request.app.state.settings.redis_url
    cache_version = version(redis_url, user.id)
    start_at = _parse_date(from_date, "from")
    end_at = _parse_date(to_date, "to")
    if start_at and end_at and end_at < start_at:
        raise HTTPException(422, "结束日期不能早于开始日期。")
    filter_key = "|".join((source_type or "", from_date or "", to_date or ""))
    cache_key = list_key(user.id, status or "", page, size, cache_version, filter_key)
    cached = get_json(redis_url, cache_key)
    if cached is not None:
        return cached
    filters = [StudentMistake.student_id == user.id]
    if status:
        filters.append(StudentMistake.status == status)
    if source_type:
        filters.append(StudentMistake.latest_source_type == source_type)
    if start_at:
        filters.append(StudentMistake.last_wrong_at >= start_at)
    if end_at:
        filters.append(StudentMistake.last_wrong_at < end_at + timedelta(days=1))
    total = db.scalar(select(func.count()).select_from(StudentMistake).where(*filters)) or 0
    rows = list(db.execute(
        select(StudentMistake, Problem).join(Problem, Problem.id == StudentMistake.problem_id)
        .where(*filters)
        .order_by(StudentMistake.next_review_at.asc(), StudentMistake.last_wrong_at.desc())
        .offset((page - 1) * size).limit(size)
    ).all())
    payload = {"items": [_item(mistake, problem) for mistake, problem in rows], "total": total, "page": page, "size": size}
    set_json(redis_url, cache_key, payload, LIST_TTL_SECONDS)
    return payload


@router.get("/review-tasks")
def review_tasks(
    request: Request, limit_count: int = Query(default=20, alias="limit", ge=1, le=100),
    db: Session = Depends(db_session),
):
    """返回当前学生到期的复习任务，按建议复习时间优先。"""
    user = current_user(request, db)
    limit(request, "student-mistakes-review-tasks", str(user.id), 60, 60)
    now = datetime.now(timezone.utc)
    rows = list(db.execute(
        select(StudentMistake, Problem)
        .join(Problem, Problem.id == StudentMistake.problem_id)
        .where(
            StudentMistake.student_id == user.id,
            StudentMistake.status == "pending_review",
            StudentMistake.next_review_at <= now,
        )
        .order_by(StudentMistake.next_review_at.asc(), StudentMistake.last_wrong_at.desc())
        .limit(limit_count)
    ).all())
    return {"items": [_item(mistake, problem) for mistake, problem in rows], "total": len(rows), "generated_at": _iso(now)}


@router.get("/stats")
def stats(request: Request, days: int = Query(default=30, ge=7, le=365), db: Session = Depends(db_session)):
    """返回统计页所需的真实聚合数据。"""
    user = current_user(request, db)
    limit(request, "student-mistakes-stats", str(user.id), 30, 60)
    mistakes = list(db.scalars(select(StudentMistake).where(StudentMistake.student_id == user.id)))
    mistake_ids = [row.id for row in mistakes]
    reviews = list(db.scalars(
        select(StudentMistakeReview).where(StudentMistakeReview.student_mistake_id.in_(mistake_ids))
    )) if mistake_ids else []
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    recent_reviews = [row for row in reviews if row.reviewed_at and as_utc(row.reviewed_at) >= cutoff]
    level_labels = {"unmastered": "未掌握", "basic": "初步掌握", "strengthening": "巩固中", "mastered": "已掌握"}
    source_counts = Counter(_source_text(row.latest_source_type) for row in mistakes)
    level_counts = Counter(row.mastery_level for row in mistakes)
    daily = Counter(as_utc(row.reviewed_at).date().isoformat() for row in recent_reviews)
    accuracy = round(sum(1 for row in recent_reviews if row.is_correct) / len(recent_reviews) * 100, 1) if recent_reviews else None
    return {
        "days": days,
        "summary": mistake_summary(db, user.id),
        "review_count": len(recent_reviews),
        "review_accuracy": accuracy,
        "mastery_breakdown": [{"key": key, "label": level_labels[key], "count": level_counts.get(key, 0)} for key in level_labels],
        "source_breakdown": [{"label": key, "count": value} for key, value in source_counts.most_common()],
        "daily_reviews": [{"date": key, "count": daily[key]} for key in sorted(daily)],
    }


@router.get("/summary")
def summary(request: Request, db: Session = Depends(db_session)):
    user = current_user(request, db)
    redis_url = request.app.state.settings.redis_url
    cache_key = summary_key(user.id, version(redis_url, user.id))
    cached = get_json(redis_url, cache_key)
    if cached is not None:
        return cached
    payload = mistake_summary(db, user.id)
    set_json(redis_url, cache_key, payload, SUMMARY_TTL_SECONDS)
    return payload


@router.get("/{mistake_id}")
def get_mistake(mistake_id: int, request: Request, db: Session = Depends(db_session)):
    user = current_user(request, db)
    row = db.execute(
        select(StudentMistake, Problem).join(Problem, Problem.id == StudentMistake.problem_id)
        .where(StudentMistake.id == mistake_id, StudentMistake.student_id == user.id)
    ).first()
    if row is None:
        raise HTTPException(404, "错题不存在。")
    mistake, problem = row
    reviews = list(db.scalars(
        select(StudentMistakeReview).where(StudentMistakeReview.student_mistake_id == mistake.id)
        .order_by(StudentMistakeReview.reviewed_at.desc()).limit(30)
    ))
    return {
        "mistake": _item(mistake, problem),
        "question": _problem_payload(db, problem),
        "reviews": [{"id": item.id, "is_correct": item.is_correct, "reviewed_at": _iso(item.reviewed_at), "source": item.source} for item in reviews],
    }


@router.post("/{mistake_id}/review")
def review_mistake(mistake_id: int, payload: ReviewPayload, request: Request,
                   db: Session = Depends(db_session)):
    require_csrf(request)
    user = current_user(request, db)
    limit(request, "student-mistakes-review", str(user.id), 30, 60)
    row = db.execute(
        select(StudentMistake, Problem).join(Problem, Problem.id == StudentMistake.problem_id)
        .where(StudentMistake.id == mistake_id, StudentMistake.student_id == user.id)
    ).first()
    if row is None:
        raise HTTPException(404, "错题不存在。")
    mistake, problem = row
    result = score_question(payload.answer, _spec(db, problem), partial_credit_multi=True, score_mode="all_or_nothing")
    record_review(
        db, mistake=mistake, answer_json=json.dumps(payload.answer, ensure_ascii=False, sort_keys=True),
        is_correct=result.is_correct, source=payload.source,
    )
    db.commit()
    db.refresh(mistake)
    return {
        "is_correct": result.is_correct,
        "mastery_level": mistake.mastery_level,
        "status": mistake.status,
        "next_review_at": _iso(mistake.next_review_at),
        "correct": _correct_payload(db, problem),
        "analysis": problem.analysis,
    }
