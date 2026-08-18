"""学生任务的派生状态与 DTO 组装。

运行态只在这里实时计算；本模块不处理路由或写入副作用。
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .attempt_source import AttemptSource, from_exam_link
from .course_access import (
    Access, block_gate, completed_block_ids, enrolled_course_ids, lesson_access,
)
from .lesson_homework_kinds import KINDS
from .models import (
    ClassMember, Course, CourseLesson, CourseLessonBlock, ExamAssignment, ExamLink,
    LessonBlockCompletion, LessonProblemAttempt, LessonProblemBlock, Paper, PaperAttempt, User,
)
from .routers.exam import _phase
from .security import as_utc


HOMEWORK_PHASE_LABELS = {
    "todo": "待完成",
    "in_progress": "进行中",
    "submitted": "已提交",
    "graded": "已批改",
    "overdue": "已逾期",
}
SOURCE_LESSON_PRACTICE = "lesson_practice"

PRACTICE_PHASE_LABELS = {
    "todo": "未开始",
    "in_progress": "进行中",
    "done": "已完成",
}

EXAM_PHASE_GROUPS = {
    "waiting": "upcoming",
    "entry_open": "upcoming",
    "open": "running",
    "closed": "ended",
}

EXAM_PHASE_LABELS = {
    "upcoming": "即将开始",
    "running": "进行中",
    "ended": "已结束",
}

DUE_SOON_HOURS = 72
TASK_GROUP_LIMIT = 5


@dataclass(frozen=True)
class TaskFacts:
    """喂给任务状态函数的事实；不适用的时间字段传 ``None``。"""

    due_at: datetime | None
    has_open_attempt: bool
    submitted_at: datetime | None
    grading_done: bool


def _attempt_is_open(attempt: PaperAttempt, now: datetime) -> bool:
    """判断一次作答现在是否仍可继续，不能相信 cron 物化的状态列。"""
    if attempt.status != "ongoing":
        return False
    deadline = as_utc(attempt.deadline_at) if attempt.deadline_at else None
    return deadline is None or deadline > now


def homework_phase(facts: TaskFacts, now: datetime) -> str:
    if facts.has_open_attempt:
        return "in_progress"
    if facts.submitted_at is not None:
        return "graded" if facts.grading_done else "submitted"
    due = as_utc(facts.due_at) if facts.due_at else None
    if due is not None and due <= now:
        return "overdue"
    return "todo"


def practice_phase(completed: bool, tries: int) -> str:
    if completed:
        return "done"
    if tries > 0:
        return "in_progress"
    return "todo"


def _visible_blocks(db: Session, user: User,
                    block_types: list[str]) -> list[tuple[CourseLesson, CourseLessonBlock, Course]]:
    """已开通课包中当前可进入的块，作业与练习共用同一套两道闸门。"""
    course_ids = enrolled_course_ids(db, user)
    if not course_ids:
        return []

    candidates_by_lesson: dict[int, list[CourseLessonBlock]] = defaultdict(list)
    lessons: dict[int, CourseLesson] = {}
    courses: dict[int, Course] = {}
    for block, lesson, course in db.execute(
        select(CourseLessonBlock, CourseLesson, Course)
        .join(CourseLesson, CourseLesson.id == CourseLessonBlock.lesson_id)
        .join(Course, Course.id == CourseLesson.course_id)
        .where(
            CourseLesson.course_id.in_(course_ids),
            CourseLessonBlock.block_type.in_(block_types),
        )
        .order_by(CourseLesson.id, CourseLessonBlock.sort_order, CourseLessonBlock.id)
    ):
        candidates_by_lesson[lesson.id].append(block)
        lessons[lesson.id] = lesson
        courses[course.id] = course

    ordered_by_lesson: dict[int, list[CourseLessonBlock]] = defaultdict(list)
    if lessons:
        for block in db.scalars(
            select(CourseLessonBlock)
            .where(CourseLessonBlock.lesson_id.in_(lessons))
            .order_by(CourseLessonBlock.lesson_id, CourseLessonBlock.sort_order,
                      CourseLessonBlock.id)
        ):
            ordered_by_lesson[block.lesson_id].append(block)

    visible: list[tuple[CourseLesson, CourseLessonBlock, Course]] = []
    for lesson_id, lesson in lessons.items():
        ordered = ordered_by_lesson[lesson_id]
        completed = completed_block_ids(db, user, lesson_id)
        granted = lesson_access(db, user, lesson) is Access.GRANTED
        for block in candidates_by_lesson[lesson_id]:
            if block_gate(db, user, lesson, block, ordered, completed, granted)["lock_reason"] is None:
                visible.append((lesson, block, courses[lesson.course_id]))
    return visible


def collect_homework_candidates(db: Session, user: User) -> list[dict]:
    """返回当前学生可进入的课时作业及其状态事实。"""
    kinds_by_block_type = {kind.block_type: kind for kind in KINDS}
    visible = _visible_blocks(db, user, list(kinds_by_block_type))

    ids_by_kind: dict[object, list[int]] = defaultdict(list)
    for _lesson, block, _course in visible:
        kind = kinds_by_block_type[block.block_type]
        ids_by_kind[kind].append(block.id)
    facts_by_kind = {kind: kind.student_facts(db, user, ids)
                     for kind, ids in ids_by_kind.items()}
    return [{"source_type": kinds_by_block_type[block.block_type].student_source_type,
             "source_id": block.id, "lesson_id": lesson.id, "block_id": block.id,
             "course_id": course.id, "course_title": course.title,
             "lesson_title": lesson.title, "title": block.title,
             "kind": kind.key, "facts": facts_by_kind[kind][block.id]}
            for lesson, block, course in visible
            for kind in (kinds_by_block_type[block.block_type],)]


def collect_practice_candidates(db: Session, user: User) -> list[dict]:
    """批量收集可进入的课中练习及其完成/作答事实。"""
    visible = _visible_blocks(db, user, ["practice"])
    block_ids = [block.id for _lesson, block, _course in visible]
    details = {detail.block_id: detail for detail in db.scalars(
        select(LessonProblemBlock).where(LessonProblemBlock.block_id.in_(block_ids or [0]))
    )}
    completed = set(db.scalars(
        select(LessonBlockCompletion.block_id).where(
            LessonBlockCompletion.user_id == user.id,
            LessonBlockCompletion.block_id.in_(block_ids or [0]),
        )
    ))
    attempts = {attempt.block_id: attempt for attempt in db.scalars(
        select(LessonProblemAttempt).where(
            LessonProblemAttempt.user_id == user.id,
            LessonProblemAttempt.block_id.in_(block_ids or [0]),
        )
    )}
    return [{"source_type": SOURCE_LESSON_PRACTICE, "source_id": block.id,
             "title": block.title, "course_id": course.id, "course_title": course.title,
             "lesson_id": lesson.id, "lesson_title": lesson.title,
             "problem_id_no": details[block.id].problem_id_no,
             "completed": block.id in completed,
             "tries": attempts[block.id].tries if block.id in attempts else 0,
             "last_correct": attempts[block.id].last_correct if block.id in attempts else None}
            for lesson, block, course in visible if block.id in details]


def _iso(value: datetime | None) -> str | None:
    return as_utc(value).isoformat().replace("+00:00", "Z") if value else None


def build_homework_item(candidate: dict, phase: str) -> dict:
    return {
        "source_type": candidate["source_type"], "source_id": candidate["source_id"],
        "scope": {"key": f"{candidate['source_type']}:{candidate['source_id']}",
                  "title": candidate["title"]},
        "phase": phase, "phase_label": HOMEWORK_PHASE_LABELS[phase],
        "due_at": _iso(candidate["facts"].due_at),
        "origin": {"course_id": candidate["course_id"], "course_title": candidate["course_title"],
                   "lesson_id": candidate["lesson_id"], "lesson_title": candidate["lesson_title"]},
        "entry": {"kind": candidate["source_type"], "lesson_id": candidate["lesson_id"],
                  "block_id": candidate["block_id"]},
    }


def build_practice_item(candidate: dict, phase: str) -> dict:
    return {
        "source_type": candidate["source_type"], "source_id": candidate["source_id"],
        "scope": {"key": f"{candidate['source_type']}:{candidate['source_id']}",
                  "title": candidate["title"]},
        "phase": phase, "phase_label": PRACTICE_PHASE_LABELS[phase],
        "origin": {"course_id": candidate["course_id"], "course_title": candidate["course_title"],
                   "lesson_id": candidate["lesson_id"], "lesson_title": candidate["lesson_title"]},
        "entry": {"kind": SOURCE_LESSON_PRACTICE, "lesson_id": candidate["lesson_id"],
                  "block_id": candidate["source_id"]},
        "tries": candidate["tries"], "last_correct": candidate["last_correct"],
    }


def exam_phase(source: AttemptSource, now: datetime) -> str:
    """把考试入口的四态时间窗归并为任务中心的三态。"""
    return EXAM_PHASE_GROUPS[_phase(source, now)]


def collect_exam_candidates(db: Session, user: User) -> list[tuple[AttemptSource, Paper, str]]:
    """返回班级与直接指派的并集；退班立即失去班级指派可见性。"""
    from sqlalchemy import or_
    class_ids = set(db.scalars(select(ClassMember.class_id).where(
        ClassMember.student_id == user.id, ClassMember.status == "active",
        ClassMember.left_at.is_(None),
    )).all())
    assignments = db.scalars(select(ExamAssignment).where(
        ExamAssignment.status == "active",
        or_((ExamAssignment.target_type == "student") &
             (ExamAssignment.target_id == user.id),
            (ExamAssignment.target_type == "class") &
             ExamAssignment.target_id.in_(class_ids or [0])),
    ).order_by(ExamAssignment.exam_link_id, ExamAssignment.id)).all()
    link_ids = {row.exam_link_id for row in assignments}
    if not link_ids:
        return []
    links = db.scalars(select(ExamLink).where(
        ExamLink.id.in_(link_ids), ExamLink.status == "active")).all()
    papers = {paper.id: paper for paper in db.scalars(select(Paper).where(
        Paper.id.in_({link.paper_id for link in links}), Paper.status == "published")).all()}
    return [(from_exam_link(link), papers[link.paper_id], link.access_token)
            for link in sorted(links, key=lambda row: row.id)
            if link.paper_id in papers]


def build_exam_item(source: AttemptSource, phase: str, token: str) -> dict:
    return {
        "source_type": source.source_type, "source_id": source.source_id,
        "scope": {"key": f"{source.source_type}:{source.source_id}", "title": source.label},
        "phase": phase, "phase_label": EXAM_PHASE_LABELS[phase],
        "open_at": _iso(source.open_at), "close_at": _iso(source.close_at),
        "duration_minutes": source.duration_minutes, "attempt_limit": source.attempt_limit,
        "entry": {"kind": source.source_type, "token": token},
    }
