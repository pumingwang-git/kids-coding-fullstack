"""班级低正确率题目的只读取数。"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .attempt_source import attempt_scope, from_exam_link, from_lesson_homework
from .class_groups import active_student_ids_for_classes
from .models import (
    ClassGroup,
    CourseLesson,
    CourseLessonBlock,
    ExamAssignment,
    ExamLink,
    LessonPaperBlock,
    LessonProblemAttempt,
    LessonProblemBlock,
    Paper,
    PaperAttempt,
    Problem,
)
from .results_common import build_item_analysis


def _paper_items(db: Session, *, source: str, source_id: int, title: str,
                 paper: Paper, attempts: list[PaperAttempt], score_policy: str) -> list[dict]:
    """Attach source context to the existing item-analysis result without changing it."""
    _grouping, items = build_item_analysis(db, paper, attempts, score_policy)
    return [
        {"source": source, "source_id": source_id, "source_title": title, **item}
        for item in items
        if item["score_rate"] is not None
    ]


def build_weak_items(db: Session, class_id: int) -> list[dict]:
    """Return attempted items for one class, ordered from the lowest score rate upward.

    Paper homework and assigned exam links deliberately delegate all item statistics to
    ``build_item_analysis``.  Lesson practice is not a paper attempt, so its one-row-per-
    student attempt table is the only rate calculated here.
    """
    class_group = db.get(ClassGroup, class_id)
    if class_group is None:
        raise LookupError("班级不存在。")

    student_ids = active_student_ids_for_classes(db, {class_id})
    if not student_ids:
        return []

    items: list[dict] = []

    homework_rows = db.execute(
        select(CourseLessonBlock, LessonPaperBlock, Paper)
        .join(LessonPaperBlock, LessonPaperBlock.block_id == CourseLessonBlock.id)
        .join(Paper, Paper.id == LessonPaperBlock.paper_id)
        .join(CourseLesson, CourseLesson.id == CourseLessonBlock.lesson_id)
        .where(
            CourseLesson.course_id == class_group.course_id,
            CourseLessonBlock.block_type == "homework",
        )
        .order_by(CourseLessonBlock.id)
    ).all()
    for block, detail, paper in homework_rows:
        source = from_lesson_homework(block, detail)
        attempts = db.scalars(select(PaperAttempt).where(
            *attempt_scope(source), PaperAttempt.user_id.in_(student_ids)
        )).all()
        items.extend(_paper_items(
            db, source=source.source_type, source_id=source.source_id, title=block.title,
            paper=paper, attempts=attempts, score_policy=source.score_policy,
        ))

    links = db.scalars(
        select(ExamLink)
        .join(ExamAssignment, ExamAssignment.exam_link_id == ExamLink.id)
        .where(
            ExamAssignment.target_type == "class",
            ExamAssignment.target_id == class_id,
            ExamAssignment.status == "active",
        )
        .order_by(ExamLink.id)
    ).all()
    for link in links:
        paper = db.get(Paper, link.paper_id)
        if paper is None:
            continue
        source = from_exam_link(link)
        attempts = db.scalars(select(PaperAttempt).where(
            *attempt_scope(source), PaperAttempt.user_id.in_(student_ids)
        )).all()
        items.extend(_paper_items(
            db, source=source.source_type, source_id=source.source_id, title=link.name,
            paper=paper, attempts=attempts, score_policy=source.score_policy,
        ))

    practice_rows = db.execute(
        select(CourseLessonBlock, LessonProblemBlock, Problem)
        .join(LessonProblemBlock, LessonProblemBlock.block_id == CourseLessonBlock.id)
        .join(CourseLesson, CourseLesson.id == CourseLessonBlock.lesson_id)
        .outerjoin(Problem, Problem.problem_id_no == LessonProblemBlock.problem_id_no)
        .where(
            CourseLesson.course_id == class_group.course_id,
            CourseLessonBlock.block_type == "practice",
        )
        .order_by(CourseLessonBlock.id)
    ).all()
    for block, detail, problem in practice_rows:
        attempts = db.scalars(select(LessonProblemAttempt).where(
            LessonProblemAttempt.block_id == block.id,
            LessonProblemAttempt.user_id.in_(student_ids),
            LessonProblemAttempt.last_correct.is_not(None),
        )).all()
        if not attempts:
            continue
        answered = len(attempts)
        correct = sum(attempt.last_correct is True for attempt in attempts)
        items.append({
            "source": "lesson_practice",
            "source_id": block.id,
            "source_title": block.title,
            "sort_order": detail.display_no or str(block.sort_order + 1),
            "problem_id_no": detail.problem_id_no,
            "full_score": detail.score,
            "type": problem.type if problem else detail.problem_type,
            "title": (problem.title or "")[:60] if problem else "",
            "missing": problem is None,
            "answered": answered,
            "correct": correct,
            "score_rate": round(correct / answered, 4),
        })

    return sorted(
        items,
        key=lambda item: (item["score_rate"], item["source"], item["source_id"], str(item["sort_order"])),
    )
