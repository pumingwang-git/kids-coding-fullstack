"""学生错题本的领域规则：自动归档与掌握度更新。

调用方负责自己的事务；本模块不 commit，确保判题结果与错题档案同生共死。
"""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .mistake_cache import mark_dirty
from .models import StudentMistake, StudentMistakeReview
from .security import utcnow


def mistake_summary(db: Session, student_id: int, now=None) -> dict:
    """某学生的错题摘要。错题本 summary 接口与个人资料页共用同一口径，
    改规则只改这一处，两个入口不会漂移。"""
    now = now or utcnow()
    base = StudentMistake.student_id == student_id
    total = db.scalar(select(func.count()).select_from(StudentMistake).where(base)) or 0
    due = db.scalar(select(func.count()).select_from(StudentMistake).where(
        base, StudentMistake.status == "pending_review", StudentMistake.next_review_at <= now
    )) or 0
    mastered = db.scalar(select(func.count()).select_from(StudentMistake).where(
        base, StudentMistake.status == "mastered"
    )) or 0
    review_rows = list(db.scalars(
        select(StudentMistakeReview.is_correct).join(StudentMistake)
        .where(StudentMistake.student_id == student_id)
        .order_by(StudentMistakeReview.reviewed_at.desc()).limit(7)
    ))
    accuracy = round(sum(1 for value in review_rows if value) / len(review_rows) * 100, 1) if review_rows else None
    return {"total": total, "due": due, "mastered": mastered, "recent_review_accuracy": accuracy}


MASTERY_RULES = (
    (0, "unmastered", "pending_review", 1),
    (1, "basic", "pending_review", 3),
    (2, "strengthening", "pending_review", 7),
    (3, "mastered", "mastered", 30),
)


def _mastery(consecutive_correct_count: int) -> tuple[str, str, int]:
    for minimum, level, status, days in reversed(MASTERY_RULES):
        if consecutive_correct_count >= minimum:
            return level, status, days
    return MASTERY_RULES[0][1], MASTERY_RULES[0][2], MASTERY_RULES[0][3]


def record_wrong(db: Session, *, student_id: int, problem_id: int,
                 source_type: str, source_id: str | int) -> StudentMistake:
    """记录正式判错。重复错误只更新档案，不重复建错题。"""
    now = utcnow()
    source_id = str(source_id)
    mistake = db.scalar(select(StudentMistake).where(
        StudentMistake.student_id == student_id,
        StudentMistake.problem_id == problem_id,
    ))
    if mistake is None:
        mistake = StudentMistake(
            student_id=student_id, problem_id=problem_id,
            first_wrong_at=now, last_wrong_at=now, wrong_count=1,
            next_review_at=now, first_source_type=source_type,
            first_source_id=source_id, latest_source_type=source_type,
            latest_source_id=source_id,
        )
        db.add(mistake)
        mark_dirty(db, student_id)
        return mistake
    mistake.last_wrong_at = now
    mistake.wrong_count += 1
    mistake.consecutive_correct_count = 0
    mistake.mastery_level = "unmastered"
    mistake.status = "pending_review"
    mistake.next_review_at = now
    mistake.latest_source_type = source_type
    mistake.latest_source_id = source_id
    mark_dirty(db, student_id)
    return mistake


def record_review(db: Session, *, mistake: StudentMistake, answer_json: str,
                  is_correct: bool, source: str = "single") -> StudentMistakeReview:
    """追加一次重做记录，并按首版固定规则刷新掌握度。"""
    now = utcnow()
    mistake.review_count += 1
    if is_correct:
        mistake.review_correct_count += 1
        mistake.consecutive_correct_count += 1
    else:
        mistake.consecutive_correct_count = 0
    level, status, days = _mastery(mistake.consecutive_correct_count)
    mistake.mastery_level = level
    mistake.status = status
    mistake.next_review_at = now + timedelta(days=days)
    review = StudentMistakeReview(
        student_mistake_id=mistake.id, answer_json=answer_json,
        is_correct=is_correct, source=source, reviewed_at=now,
    )
    db.add(review)
    mark_dirty(db, mistake.student_id)
    return review
