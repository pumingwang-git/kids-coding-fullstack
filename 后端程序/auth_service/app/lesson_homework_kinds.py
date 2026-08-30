"""课时作业类型注册表：一份「课时里的作业」可以是整卷作业，也可以是 Scratch 挑战。

**为什么要这一层**：课时作业成绩页原来只认 `block_type == "homework"` + 试卷明细，
Scratch 作业进不来，只好另开一页（`scratch-submissions.html`）。两个页面 =
两套筛选、两套统计口径、两套「哪一次算数」的解释，老师要在两个地方对同一节课的
作业表现——那不是两个功能，是同一个功能被切成了两半。

本模块把「一种课时作业」收敛成一个 `HomeworkKind`：它知道自己挂在哪种内容块上、
认得哪些筛选键、总览用哪几列、状态有哪些取值、怎么收集行、怎么出详情。路由与前端
页面只吃注册表给出的元数据（列、筛选项、状态词表），不认识任何具体类型。

**红线（沿用 `attempt_source.py` 文件头第三段的纪律）**：除本模块的 `KINDS` 分派
之外，成绩链路（`routers/admin_results.py`、`public/admin/homework-results.js`）
禁止出现 `if kind == "scratch"` 这类分支。新增一种课时作业（例如「课时编程题作业」）
= 在这里加一个 kind，路由、页面表头、筛选下拉、CSV 导出一行都不用改。

统计口径仍然只有一处解释：整卷作业走 `results_common`（与考试链接同一批函数），
Scratch 走本文件的 `_counted_submission`，两者都遵守「每位学员一条代表记录」——
汇总数字的分母永远是人数，不是人次。
"""
from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .attempt_source import SOURCE_LESSON_HOMEWORK, attempt_scope, from_lesson_homework
from .models import (
    Course,
    CourseLesson,
    CourseLessonBlock,
    CourseSection,
    AttemptAnswer,
    LessonPaperBlock,
    LessonScratchBlock,
    Paper,
    PaperAttempt,
    ScratchChallenge,
    ScratchProjectRevision,
    ScratchSubmission,
    User,
)
from .results_common import (
    attempts_by_user,
    build_students,
    build_summary,
    counted_scores,
    distribution_of,
    full_score,
    score_summary,
)
from .routers.exam import counted_attempt
from .routers.admin_papers import _as_utc

# ---------------------------------------------------------------------------
# 呈现描述符
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Column:
    """一列的呈现契约。前端按 `key` 到行的 `cells` 里取值，不认识列的业务含义。"""

    key: str
    label: str
    align: str = "left"
    width: str | None = None

    def as_dict(self) -> dict:
        return {"key": self.key, "label": self.label, "align": self.align,
                **({"width": self.width} if self.width else {})}


def cell(text: object, *, sub: str | None = None, tone: str | None = None,
         badge: str | None = None) -> dict:
    """一个文本单元格。`tone` 只给语义（ok/warn/danger/muted），配色由前端主题决定。

    文案在服务端成型（"82 分" / "78%" / "长期有效"）：同一列会同时装整卷作业的
    分数和 Scratch 的规则通过率，让前端按列名去猜单位，等于把口径又分叉一次。
    """
    return {"text": "—" if text is None or text == "" else str(text),
            **({"sub": sub} if sub else {}),
            **({"tone": tone} if tone else {}),
            **({"badge": badge} if badge else {})}


def badges_cell(badges: list[dict]) -> dict:
    """一格标记。空列表也要返回这个形状，前端才知道该列是标记列而不是文本列。"""
    return {"badges": badges}


def actions_cell(actions: list[dict]) -> dict:
    """一格操作。`type` 是前端能力表里的键——服务端点名要执行哪个动作，
    前端不按列名或作业类型自己推断该画什么按钮。"""
    return {"actions": actions}


@dataclass(frozen=True)
class Stat:
    key: str
    label: str


@dataclass(frozen=True)
class Option:
    value: str
    label: str

    def as_dict(self) -> dict:
        return {"value": self.value, "label": self.label}


# 总览表的**全部**可用列，按最终呈现顺序排列。每个 kind 只声明自己用到的 key；
# 实际表头 = 结果集中出现过的 kind 所声明列的并集（按本目录顺序）。因此「只看
# Scratch 作业」时不会留下一排试卷专用的空列，混排时也不会有人自己拼表头。
OVERVIEW_COLUMNS: tuple[Column, ...] = (
    Column("homework", "作业"),
    Column("path", "所在章节 / 课时"),
    Column("deadline", "截止时间", width="170px"),
    Column("people", "参与人数"),
    Column("submitted", "已交人数"),
    Column("passed", "通过人数"),
    Column("pending", "待点评"),
    Column("attempts", "作答人次"),
    Column("avg", "平均成绩"),
    Column("pass_rate", "达标率"),
    Column("actions", "操作", align="right"),
)

# 总览四张统计卡。同样按 key 取值，kind 声明自己算得出哪几张。
OVERVIEW_STATS: tuple[Stat, ...] = (
    Stat("homework_count", "课时作业"),
    Stat("people", "参与人数（当前范围）"),
    Stat("submitted", "已交人数（当前范围）"),
    Stat("passed", "通过人数（当前范围）"),
    Stat("pending", "待点评（当前范围）"),
    Stat("attempts", "作答人次（当前范围）"),
)

_COLUMN_INDEX = {column.key: column for column in OVERVIEW_COLUMNS}
_STAT_INDEX = {stat.key: stat for stat in OVERVIEW_STATS}


# ---------------------------------------------------------------------------
# 类型定义
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HomeworkFilters:
    """一次总览查询的全部筛选条件。新增筛选键时只加字段，不改任何 kind 的签名。"""

    keyword: str = ""
    course_id: int | None = None
    section_id: int | None = None
    lesson_id: int | None = None
    kind: str = ""
    status: str = ""
    paper_type: str = ""
    subject: str = ""

    def active_keys(self) -> set[str]:
        """真正生效的筛选键（不含 kind：那是选类型本身，不是类型的能力）。"""
        return {name for name in ("keyword", "course_id", "section_id", "lesson_id",
                                  "status", "paper_type", "subject")
                if getattr(self, name) not in ("", None)}


@dataclass(frozen=True)
class HomeworkKind:
    """一种课时作业。所有类型差异都必须落在这个结构里，不许散到调用方。"""

    key: str
    label: str
    block_type: str
    # 学生任务中心的来源身份和事实收集同样是类型能力，调用方不得按 kind 分支。
    student_source_type: str
    student_facts: Callable[[Session, User, list[int]], dict[int, TaskFacts]]
    class_facts: Callable[[Session, int, set[int]], dict[int, TaskFacts]]
    class_attempt_counts: Callable[[Session, int, set[int]], tuple[set[int], int]]
    # 详情页的呈现形态。前端按它选渲染器与行为，不按 key 猜。
    detail_view: str
    column_keys: tuple[str, ...]
    stat_keys: tuple[str, ...]
    # 本类型认得的筛选键。用户筛了一个本类型不认得的键（比如给 Scratch 筛「试卷类型」），
    # 本类型整体退出结果集——这比悄悄忽略该条件、把不相干的行混进来诚实。
    filter_keys: frozenset[str]
    statuses: tuple[Option, ...]
    detail_columns: tuple[Column, ...]
    detail_stats: tuple[Stat, ...]
    collect: Callable[[Session, HomeworkFilters, set[int] | None], list[dict]]
    detail: Callable[[Session, int, set[int] | None], dict]
    student_history: Callable[[Session, int, int, set[int] | None], dict]
    record: Callable[[Session, int, int, set[int] | None], dict] | None = None
    # 详情页顶部那句口径说明。措辞属于类型知识，不该由页面拼。
    insight: str = ""
    empty_hint: str = "还没有学员开始这份作业"

    def accepts(self, filters: HomeworkFilters) -> bool:
        if filters.kind and filters.kind != self.key:
            return False
        if filters.active_keys() - self.filter_keys:
            return False
        if filters.status and filters.status not in {s.value for s in self.statuses}:
            return False
        return True


def _iso(value: datetime | None) -> str | None:
    aware = _as_utc(value) if value is not None else None
    return aware.isoformat() if aware else None


def _matches_keyword(keyword: str, *fields: object) -> bool:
    if not keyword:
        return True
    needle = keyword.strip().lower()
    return any(needle in str(f).lower() for f in fields if f)


def _path_query(filters: HomeworkFilters, block_type: str):
    """课包 → 章节 → 课时 → 内容块 的公共骨架。目录筛选对所有类型同一套写法。"""
    query = (
        select(CourseLessonBlock, CourseLesson, CourseSection, Course)
        .join(CourseLesson, CourseLesson.id == CourseLessonBlock.lesson_id)
        .join(CourseSection, CourseSection.id == CourseLesson.section_id)
        .join(Course, Course.id == CourseLesson.course_id)
        .where(CourseLessonBlock.block_type == block_type)
        .order_by(Course.sort_order, Course.id, CourseSection.sort_order, CourseSection.id,
                  CourseLesson.sort_order, CourseLesson.id, CourseLessonBlock.sort_order)
    )
    if filters.course_id is not None:
        query = query.where(Course.id == filters.course_id)
    if filters.section_id is not None:
        query = query.where(CourseSection.id == filters.section_id)
    if filters.lesson_id is not None:
        query = query.where(CourseLesson.id == filters.lesson_id)
    return query


def _base_path(kind: HomeworkKind, block: CourseLessonBlock, lesson: CourseLesson,
               section: CourseSection, course: Course, homework: dict) -> dict:
    """所有类型共有的行骨架：来源身份 + 目录路径 + 作业本身。"""
    return {
        "source": SOURCE_LESSON_HOMEWORK,
        "source_id": block.id,
        "kind": kind.key,
        "kind_label": kind.label,
        "detail_view": kind.detail_view,
        "course": {"id": course.id, "title": course.title},
        "section": {"id": section.id, "title": section.title},
        "lesson": {"id": lesson.id, "title": lesson.title},
        "homework": homework,
    }


def _percent(part: int, whole: int) -> int | None:
    return round(part / whole * 100) if whole else None


def _scope_students(stmt, student_column, student_ids: set[int] | None):
    """把 ``None``（不受限）与空集（稳定空结果）的区别集中在一处。"""
    if student_ids is not None:
        stmt = stmt.where(student_column.in_(student_ids))
    return stmt


class ScopeDenied(LookupError):
    """请求的学员不在调用方的数据范围内。

    继承 ``LookupError`` 是刻意的：按《39、API错误码与分页排序规范》§3.2，范围闸
    必须与「不存在」返回**逐字相同**的 404，否则遍历 user_id 就能问出某个学员
    有没有作答记录。单独立一个类型只是为了让上层能记一条日志（§6）。
    """


def _require_visible_student(user_id: int, student_ids: set[int] | None,
                             missing_message: str) -> None:
    """范围外时抛出该端点自己的「不存在」文案，让两种情况无法区分。"""
    if student_ids is not None and user_id not in student_ids:
        raise ScopeDenied(missing_message)


# ---------------------------------------------------------------------------
# 类型一：整卷作业（LessonPaperBlock）
# ---------------------------------------------------------------------------


PAPER_BLOCK_TYPE = "homework"


def _paper_student_facts(db: Session, user: User, block_ids: list[int]) -> dict[int, TaskFacts]:
    """批量收集整卷作业的运行事实；空答卷的 all([]) 有意视为已判完。"""
    from .student_tasks import TaskFacts, _attempt_is_open

    if not block_ids:
        return {}
    config_rows = db.execute(
        select(LessonPaperBlock.block_id, LessonPaperBlock.due_at, LessonPaperBlock.attempt_limit)
        .where(LessonPaperBlock.block_id.in_(block_ids))
    ).all()
    config_by_block = {row[0]: (row[1], row[2]) for row in config_rows}
    attempts = list(db.scalars(
        select(PaperAttempt).where(
            PaperAttempt.source_type == SOURCE_LESSON_HOMEWORK,
            PaperAttempt.source_id.in_(block_ids),
            PaperAttempt.user_id == user.id,
        )
    ))
    submitted = [attempt for attempt in attempts if attempt.status == "submitted"]
    answer_statuses: dict[int, list[str]] = {attempt.id: [] for attempt in submitted}
    if answer_statuses:
        for attempt_id, judge_status in db.execute(
            select(AttemptAnswer.attempt_id, AttemptAnswer.judge_status)
            .where(AttemptAnswer.attempt_id.in_(answer_statuses))
        ):
            answer_statuses[attempt_id].append(judge_status)

    by_block: dict[int, list[PaperAttempt]] = {}
    for attempt in attempts:
        by_block.setdefault(attempt.source_id, []).append(attempt)
    now = datetime.now(UTC)
    facts = {}
    for block_id in block_ids:
        rows = by_block.get(block_id, [])
        latest = max((row for row in rows if row.status == "submitted"),
                     key=lambda row: (row.submitted_at or row.created_at, row.id), default=None)
        due_at, limit = config_by_block.get(block_id, (None, None))
        facts[block_id] = TaskFacts(
            due_at=due_at,
            has_open_attempt=any(_attempt_is_open(row, now) for row in rows),
            submitted_at=latest.submitted_at if latest else None,
            grading_done=(all(status != "pending" for status in answer_statuses[latest.id])
                          if latest else False),
            attempts_left=None if not limit else max(0, limit - len(rows)),
        )
    return facts


def _paper_class_facts(db: Session, block_id: int,
                       user_ids: set[int]) -> dict[int, TaskFacts]:
    """Collect one homework block's facts for a whole class in bounded queries."""
    from .student_tasks import TaskFacts, _attempt_is_open

    if not user_ids:
        return {}
    config_rows = db.execute(
        select(LessonPaperBlock.due_at, LessonPaperBlock.attempt_limit)
        .where(LessonPaperBlock.block_id == block_id)
    ).all()
    due_at, limit = config_rows[0] if config_rows else (None, None)
    attempts = list(db.scalars(
        select(PaperAttempt).where(
            PaperAttempt.source_type == SOURCE_LESSON_HOMEWORK,
            PaperAttempt.source_id == block_id,
            PaperAttempt.user_id.in_(user_ids),
        )
    ))
    submitted = [attempt for attempt in attempts if attempt.status == "submitted"]
    answer_statuses: dict[int, list[str]] = {attempt.id: [] for attempt in submitted}
    if answer_statuses:
        for attempt_id, judge_status in db.execute(
            select(AttemptAnswer.attempt_id, AttemptAnswer.judge_status)
            .where(AttemptAnswer.attempt_id.in_(answer_statuses))
        ):
            answer_statuses[attempt_id].append(judge_status)
    by_user: dict[int, list[PaperAttempt]] = {}
    for attempt in attempts:
        by_user.setdefault(attempt.user_id, []).append(attempt)
    now = datetime.now(UTC)
    facts = {}
    for user_id in user_ids:
        rows = by_user.get(user_id, [])
        latest = max((row for row in rows if row.status == "submitted"),
                     key=lambda row: (row.submitted_at or row.created_at, row.id),
                     default=None)
        facts[user_id] = TaskFacts(
            due_at=due_at,
            has_open_attempt=any(_attempt_is_open(row, now) for row in rows),
            submitted_at=latest.submitted_at if latest else None,
            grading_done=(all(status != "pending" for status in answer_statuses[latest.id])
                          if latest else False),
            attempts_left=None if not limit else max(0, limit - len(rows)),
        )
    return facts


def _paper_class_attempt_counts(db: Session, block_id: int,
                                user_ids: set[int]) -> tuple[set[int], int]:
    """Return counted paper submitters and all attempts for one class block."""
    if not user_ids:
        return set(), 0
    attempts = list(db.scalars(select(PaperAttempt).where(
        PaperAttempt.source_type == SOURCE_LESSON_HOMEWORK,
        PaperAttempt.source_id == block_id,
        PaperAttempt.user_id.in_(user_ids),
    )))
    by_user: dict[int, list[PaperAttempt]] = {}
    for attempt in attempts:
        by_user.setdefault(attempt.user_id, []).append(attempt)
    return ({user_id for user_id, rows in by_user.items()
             if counted_attempt(rows, "best") is not None}, len(attempts))


def _paper_deadline(detail: LessonPaperBlock) -> dict:
    """截止状态由服务端判定：前端拿本地时钟比 due_at 会在跨时区/时钟偏移时说谎。"""
    if detail.due_at is None:
        return {"status": "open", "label": "长期有效", "detail": "未设置作业截止时间",
                "tone": "ok"}
    due = _as_utc(detail.due_at)
    if datetime.now(UTC) >= due:
        return {"status": "closed", "label": "已截止",
                "detail": f"截止于 {_iso(detail.due_at)}", "tone": "muted"}
    return {"status": "open", "label": "进行中", "detail": f"截止于 {_iso(detail.due_at)}",
            "tone": "ok"}


def paper_context(db: Session, block_id: int):
    block = db.get(CourseLessonBlock, block_id)
    detail = db.get(LessonPaperBlock, block_id)
    lesson = db.get(CourseLesson, block.lesson_id) if block else None
    section = db.get(CourseSection, lesson.section_id) if lesson else None
    course = db.get(Course, lesson.course_id) if lesson else None
    paper = db.get(Paper, detail.paper_id) if detail else None
    if (block is None or detail is None or lesson is None or section is None
            or course is None or paper is None or block.block_type != PAPER_BLOCK_TYPE
            or section.course_id != course.id):
        return None
    return block, detail, paper, lesson, section, course


def _paper_row(block, detail, paper, lesson, section, course) -> dict:
    deadline = _paper_deadline(detail)
    return _base_path(PAPER_KIND, block, lesson, section, course, {
        "id": block.id, "title": block.title, "due_at": _iso(detail.due_at),
        "status": deadline["status"], "status_label": deadline["label"],
        "score_policy": "best", "attempt_limit": detail.attempt_limit,
    }) | {
        "paper": {"id": paper.id, "paper_id_no": paper.paper_id_no, "title": paper.title,
                  "paper_type": paper.paper_type, "subject": paper.subject},
        "subtitle": f"{paper.paper_id_no or ''} · {paper.title}".strip(" ·"),
        "deadline": deadline,
    }


def _collect_paper_rows(db: Session, filters: HomeworkFilters,
                        student_ids: set[int] | None) -> list[dict]:
    query = (
        _path_query(filters, PAPER_BLOCK_TYPE)
        .join(LessonPaperBlock, LessonPaperBlock.block_id == CourseLessonBlock.id)
        .join(Paper, Paper.id == LessonPaperBlock.paper_id)
        .add_columns(LessonPaperBlock, Paper)
    )
    if filters.paper_type:
        query = query.where(Paper.paper_type == filters.paper_type)
    if filters.subject:
        query = query.where(Paper.subject == filters.subject)

    rows = []
    for block, lesson, section, course, detail, paper in db.execute(query).all():
        if not _matches_keyword(filters.keyword, block.title, lesson.title, paper.title,
                                paper.paper_id_no):
            continue
        row = _paper_row(block, detail, paper, lesson, section, course)
        if filters.status and row["homework"]["status"] != filters.status:
            continue
        source = from_lesson_homework(block, detail)
        attempt_query = select(PaperAttempt).where(*attempt_scope(source))
        attempts = list(db.scalars(
            _scope_students(attempt_query, PaperAttempt.user_id, student_ids)
        ))
        if student_ids is not None and not attempts:
            continue
        submitted = [a for a in attempts if a.status == "submitted"]
        people = len(attempts_by_user(attempts))
        submitted_people = len({a.user_id for a in submitted})
        score = score_summary(counted_scores(attempts, source.score_policy), paper.pass_score)
        row.update({
            "full_score": full_score(db, paper.id),
            "pass_score": paper.pass_score,
            "participants": people,
            "submitted_participants": submitted_people,
            "attempts": len(attempts),
            "submitted": len(submitted),
            "ongoing": len(attempts) - len(submitted),
            "score": score,
            "metrics": {"people": people, "submitted": submitted_people,
                        "attempts": len(attempts)},
            "cells": {
                "homework": cell(block.title, sub=row["subtitle"], badge=PAPER_KIND.label),
                "path": cell(section.title, sub=lesson.title),
                "deadline": cell(row["deadline"]["label"], sub=row["deadline"]["detail"],
                                 tone=row["deadline"]["tone"]),
                "people": cell(people),
                "submitted": cell(submitted_people),
                "attempts": cell(len(attempts)),
                "avg": cell(f"{score['avg']} 分" if score else None),
                "pass_rate": cell(f"{score['pass_rate']}%"
                                  if score and score.get("pass_rate") is not None else None),
                "actions": actions_cell([{"type": "open_detail", "label": "查看成绩"}]),
            },
        })
        rows.append(row)
    return rows


def _paper_detail(db: Session, block_id: int, student_ids: set[int] | None) -> dict:
    context = paper_context(db, block_id)
    if context is None:
        raise LookupError("课时作业不存在。")
    block, detail, paper, lesson, section, course = context
    source = from_lesson_homework(block, detail)
    attempt_query = (
        select(PaperAttempt).where(*attempt_scope(source))
        .order_by(PaperAttempt.started_at.desc(), PaperAttempt.id.desc())
    )
    attempts = list(db.scalars(
        _scope_students(attempt_query, PaperAttempt.user_id, student_ids)
    ))
    full = full_score(db, paper.id)
    students = build_students(db, attempts, source.score_policy, include_history=False)
    summary = build_summary(attempts, source.score_policy, paper.pass_score,
                            participants=len(students))
    row = _paper_row(block, detail, paper, lesson, section, course)
    return row | {
        "full_score": full,
        "pass_score": paper.pass_score,
        "summary": summary,
        "distribution": distribution_of(counted_scores(attempts, source.score_policy), full),
        "students": [_paper_student_row(block_id, student) for student in students],
        "stats": [
            {"key": "people", "label": "参与人数", "text": str(summary["participants"])},
            {"key": "attempts", "label": "作答人次", "text": str(summary["attempts"])},
            {"key": "submitted", "label": "已交人数",
             "text": str(summary["submitted_participants"])},
            {"key": "avg", "label": "平均分（按人）",
             "text": "—" if summary["avg"] is None else str(summary["avg"])},
            {"key": "range", "label": "分数区间",
             "text": "—" if summary["min"] is None else f"{summary['min']} ~ {summary['max']}"},
            {"key": "pass_rate", "label": "及格率（按人）",
             "text": "—" if summary["pass_rate"] is None else f"{summary['pass_rate']}%"},
        ],
        "tags": [
            {"label": "试卷作业"},
            {"label": f"{paper.paper_id_no or ''} · {paper.title}".strip(" ·")},
            {"label": row["deadline"]["label"], "tone": row["deadline"]["tone"]},
            {"label": row["deadline"]["detail"], "tone": "muted"},
            {"label": f"满分 {full}" + ("" if paper.pass_score is None
                                        else f" / 及格 {paper.pass_score}"), "tone": "muted"},
        ],
    }


SUBMIT_KIND_LABEL = {"manual": "手动交卷", "auto_timeout": "超时收卷",
                     "auto_close": "系统收卷"}
ATTEMPT_STATUS_LABEL = {"submitted": "已交卷", "ongoing": "作答中", "expired": "已过期"}


def _duration(seconds: int | None) -> str | None:
    if seconds is None:
        return None
    return f"{seconds // 60}:{seconds % 60:02d}"


def _paper_student_row(block_id: int, student: dict) -> dict:
    counted = student.get("counted")
    tags = []
    if counted is None:
        tags.append({"label": "未交卷", "tone": "muted"})
    if student.get("ongoing"):
        tags.append({"label": "作答中", "tone": "muted"})
    if student.get("has_judge_failed"):
        tags.append({"label": "判题异常", "tone": "danger"})
    return {
        **student,
        "row_id": f"user-{student['user']['id']}",
        "name": student["user"]["username"],
        "cells": {
            "name": cell(student["user"]["username"]),
            "attempt_count": cell(student["attempt_count"]),
            "tags": badges_cell(tags),
            "score": cell(None if counted is None else counted["total_score"]),
            "duration": cell(None if counted is None else _duration(counted["duration_seconds"])),
            "submit_kind": cell(None if counted is None
                                else SUBMIT_KIND_LABEL.get(counted["submit_kind"])),
            "started_at": cell(None if counted is None else counted["started_at"]),
            "submitted_at": cell(None if counted is None else counted["submitted_at"]),
            "actions": actions_cell([] if counted is None else
                                    [{"type": "attempt_review", "label": "答卷回看",
                                      "attempt_id": counted["attempt_id"]}]),
        },
        # 反复作答的学员才值得展开；只交过一次的行没有历史可看。
        "history_endpoint": (f"/lesson-homework/{block_id}/students/"
                             f"{student['user']['id']}/attempts"
                             if student["attempt_count"] > 1 else None),
    }


def _paper_history(db: Session, block_id: int, user_id: int,
                   student_ids: set[int] | None) -> dict:
    # 范围校验放在作业存在性之后：作业块本身是课程内容、存在与否不是秘密，
    # 而「这名学员有没有作答」必须与「不在我范围内」不可区分。
    context = paper_context(db, block_id)
    if context is None:
        raise LookupError("课时作业不存在。")
    _require_visible_student(user_id, student_ids, "该学员没有这份作业的作答记录。")
    block, detail, _paper, _lesson, _section, _course = context
    source = from_lesson_homework(block, detail)
    attempts = list(db.scalars(
        select(PaperAttempt).where(*attempt_scope(source), PaperAttempt.user_id == user_id)
        .order_by(PaperAttempt.started_at.asc(), PaperAttempt.id.asc())
    ))
    students = build_students(db, attempts, source.score_policy)
    if not students:
        raise LookupError("该学员没有这份作业的作答记录。")
    student = students[0]
    counted_id = student["counted"]["attempt_id"] if student["counted"] else None
    return {
        "student": student,
        "columns": [c.as_dict() for c in PAPER_HISTORY_COLUMNS],
        "rows": [{
            "row_id": f"attempt-{a['attempt_id']}",
            "counted": a["attempt_id"] == counted_id,
            "cells": {
                "attempt_no": cell(f"第 {a['attempt_no']} 次"),
                "status": cell(ATTEMPT_STATUS_LABEL.get(a["status"], a["status"])),
                "score": cell(a["total_score"]),
                "duration": cell(_duration(a["duration_seconds"])),
                "started_at": cell(a["started_at"]),
                "submitted_at": cell(a["submitted_at"]),
                "actions": actions_cell([{"type": "attempt_review", "label": "答题详情",
                                          "attempt_id": a["attempt_id"]}]
                                        if a["status"] == "submitted" else []),
            },
        } for a in student["attempts"]],
    }


PAPER_HISTORY_COLUMNS = (
    Column("attempt_no", "次数"),
    Column("status", "状态"),
    Column("score", "成绩"),
    Column("duration", "用时"),
    Column("started_at", "开始"),
    Column("submitted_at", "提交"),
    Column("actions", "操作", align="right"),
)


PAPER_KIND = HomeworkKind(
    key="paper",
    label="试卷作业",
    block_type=PAPER_BLOCK_TYPE,
    student_source_type=SOURCE_LESSON_HOMEWORK,
    student_facts=_paper_student_facts,
    class_facts=_paper_class_facts,
    class_attempt_counts=_paper_class_attempt_counts,
    detail_view="attempts",
    column_keys=("homework", "path", "deadline", "people", "submitted", "attempts",
                 "avg", "pass_rate", "actions"),
    stat_keys=("homework_count", "people", "submitted", "attempts"),
    filter_keys=frozenset({"keyword", "course_id", "section_id", "lesson_id", "status",
                           "paper_type", "subject"}),
    statuses=(Option("open", "进行中（含长期有效）"), Option("closed", "已截止")),
    detail_columns=(
        Column("name", "学员"),
        Column("attempt_count", "作答次数"),
        Column("tags", "状态"),
        Column("score", "计分成绩"),
        Column("duration", "用时"),
        Column("submit_kind", "交卷方式"),
        Column("started_at", "开始时间"),
        Column("submitted_at", "交卷时间"),
        Column("actions", "操作", align="right"),
    ),
    detail_stats=(),
    collect=_collect_paper_rows,
    detail=_paper_detail,
    student_history=_paper_history,
    insight="统计按每位学员的最佳已交成绩计算。作答人次保留全部提交，用于查看练习频率；"
            "没有班级名单时，不展示「未交人数」。",
)


# ---------------------------------------------------------------------------
# 类型二：Scratch 作业（LessonScratchBlock）
# ---------------------------------------------------------------------------

SCRATCH_BLOCK_TYPE = "scratch"


def _scratch_student_facts(db: Session, user: User, block_ids: list[int]) -> dict[int, TaskFacts]:
    from .student_tasks import TaskFacts

    if not block_ids:
        return {}
    submissions = list(db.scalars(
        select(ScratchSubmission).where(
            ScratchSubmission.lesson_block_id.in_(block_ids),
            ScratchSubmission.user_id == user.id,
        )
    ))
    latest_by_block: dict[int, ScratchSubmission] = {}
    for submission in submissions:
        previous = latest_by_block.get(submission.lesson_block_id)
        if previous is None or (submission.submitted_at, submission.id) > (
                previous.submitted_at, previous.id):
            latest_by_block[submission.lesson_block_id] = submission
    facts = {}
    for block_id in block_ids:
        latest = latest_by_block.get(block_id)
        facts[block_id] = TaskFacts(
            due_at=None,
            has_open_attempt=latest is not None and latest.status in {"evaluating", "returned"},
            submitted_at=latest.submitted_at if latest else None,
            grading_done=(latest is not None and (latest.reviewed_at is not None
                                                  or latest.status in {"passed", "failed"})),
        )
    return facts


def _scratch_class_facts(db: Session, block_id: int,
                         user_ids: set[int]) -> dict[int, TaskFacts]:
    """Collect Scratch facts for a whole class with one submissions query."""
    from .student_tasks import TaskFacts

    if not user_ids:
        return {}
    submissions = list(db.scalars(
        select(ScratchSubmission).where(
            ScratchSubmission.lesson_block_id == block_id,
            ScratchSubmission.user_id.in_(user_ids),
        )
    ))
    by_user: dict[int, list[ScratchSubmission]] = {}
    for submission in submissions:
        by_user.setdefault(submission.user_id, []).append(submission)
    facts = {}
    for user_id in user_ids:
        rows = by_user.get(user_id, [])
        latest = max(rows, key=lambda row: (row.submitted_at, row.id), default=None)
        facts[user_id] = TaskFacts(
            due_at=None,
            has_open_attempt=latest is not None and latest.status in {"evaluating", "returned"},
            submitted_at=latest.submitted_at if latest else None,
            grading_done=(latest is not None and (latest.reviewed_at is not None
                                                  or latest.status in {"passed", "failed"})),
        )
    return facts

SUBMISSION_STATUS = {
    "passed": ("已通过", "ok"),
    "failed": ("未通过", "danger"),
    "needs_review": ("待点评", "warn"),
    "evaluating": ("判定中", "warn"),
    "pending_review": ("待点评", "warn"),
}


def scratch_context(db: Session, block_id: int):
    block = db.get(CourseLessonBlock, block_id)
    detail = db.get(LessonScratchBlock, block_id)
    lesson = db.get(CourseLesson, block.lesson_id) if block else None
    section = db.get(CourseSection, lesson.section_id) if lesson else None
    course = db.get(Course, lesson.course_id) if lesson else None
    challenge = db.get(ScratchChallenge, detail.challenge_id) if detail else None
    if (block is None or detail is None or lesson is None or section is None
            or course is None or challenge is None
            or block.block_type != SCRATCH_BLOCK_TYPE or section.course_id != course.id):
        return None
    return block, detail, challenge, lesson, section, course


def _counted_submission(submissions: list[ScratchSubmission]) -> ScratchSubmission | None:
    """一位学员「算数的那一次」提交。

    与整卷作业的 `score_policy="best"` 同一口径：先看有没有通过的那次，没有就取
    规则通过率最高的一次，仍并列时取最后一次。**不能取最后一次**——学生通过之后
    继续改着玩，一次退步的提交会把已经拿到的通过判掉。
    """
    if not submissions:
        return None
    return max(submissions, key=lambda s: (s.passed, s.score if s.score is not None else -1,
                                           s.attempt_no))


def _scratch_class_attempt_counts(db: Session, block_id: int,
                                  user_ids: set[int]) -> tuple[set[int], int]:
    """Return counted Scratch submitters and all submissions for one class block."""
    if not user_ids:
        return set(), 0
    submissions = list(db.scalars(select(ScratchSubmission).where(
        ScratchSubmission.lesson_block_id == block_id,
        ScratchSubmission.user_id.in_(user_ids),
    )))
    by_user: dict[int, list[ScratchSubmission]] = {}
    for submission in submissions:
        by_user.setdefault(submission.user_id, []).append(submission)
    return ({user_id for user_id, rows in by_user.items()
             if _counted_submission(rows) is not None}, len(submissions))


def _scratch_stats(submissions: list[ScratchSubmission]) -> dict:
    by_user: dict[int, list[ScratchSubmission]] = {}
    for submission in submissions:
        by_user.setdefault(submission.user_id, []).append(submission)
    counted = [c for c in (_counted_submission(rows) for rows in by_user.values())
               if c is not None]
    scores = [c.score for c in counted if c.score is not None]
    passed = len([c for c in counted if c.passed])
    pending = len([c for c in counted if not c.passed and c.status not in ("failed",)])
    return {
        "people": len(by_user),
        "passed": passed,
        "pending": pending,
        "attempts": len(submissions),
        "avg": round(sum(scores) / len(scores)) if scores else None,
        "pass_rate": _percent(passed, len(counted)),
        "counted": counted,
        "by_user": by_user,
    }


def _scratch_row(block, challenge, lesson, section, course) -> dict:
    """Scratch 作业没有截止时间：块上没有 due_at，挑战也不管投放窗口。

    这里如实写「长期有效」，而不是造一个假的截止态——课时作业成绩页的状态筛选
    因此对 Scratch 只有「进行中」一个取值，`HomeworkKind.statuses` 已经声明。
    """
    deadline = {"status": "open", "label": "长期有效",
                "detail": "Scratch 挑战不设作业截止时间", "tone": "ok"}
    return _base_path(SCRATCH_KIND, block, lesson, section, course, {
        "id": block.id, "title": block.title, "due_at": None,
        "status": "open", "status_label": deadline["label"],
        "score_policy": "best", "attempt_limit": 0,
    }) | {
        "challenge": {"id": challenge.id, "title": challenge.title,
                      "status": challenge.status, "version": challenge.version},
        "subtitle": f"挑战 #{challenge.id} · {challenge.title}",
        "deadline": deadline,
    }


def _collect_scratch_rows(db: Session, filters: HomeworkFilters,
                          student_ids: set[int] | None) -> list[dict]:
    query = (
        _path_query(filters, SCRATCH_BLOCK_TYPE)
        .join(LessonScratchBlock, LessonScratchBlock.block_id == CourseLessonBlock.id)
        .join(ScratchChallenge, ScratchChallenge.id == LessonScratchBlock.challenge_id)
        .add_columns(LessonScratchBlock, ScratchChallenge)
    )
    rows = []
    for block, lesson, section, course, _detail, challenge in db.execute(query).all():
        if not _matches_keyword(filters.keyword, block.title, lesson.title, challenge.title):
            continue
        row = _scratch_row(block, challenge, lesson, section, course)
        if filters.status and row["homework"]["status"] != filters.status:
            continue
        submission_query = select(ScratchSubmission).where(
            ScratchSubmission.lesson_block_id == block.id
        )
        submissions = list(db.scalars(
            _scope_students(submission_query, ScratchSubmission.user_id, student_ids)
        ))
        if student_ids is not None and not submissions:
            continue
        stats = _scratch_stats(submissions)
        row.update({
            "full_score": 100,
            "pass_score": 100,
            "participants": stats["people"],
            "submitted_participants": stats["people"],
            "attempts": stats["attempts"],
            "submitted": stats["attempts"],
            "ongoing": 0,
            "score": None if stats["avg"] is None else {
                "avg": stats["avg"], "min": None, "max": None,
                "pass_rate": stats["pass_rate"],
            },
            "metrics": {"people": stats["people"], "passed": stats["passed"],
                        "pending": stats["pending"], "attempts": stats["attempts"]},
            "cells": {
                "homework": cell(block.title, sub=row["subtitle"], badge=SCRATCH_KIND.label),
                "path": cell(section.title, sub=lesson.title),
                "deadline": cell(row["deadline"]["label"], sub=row["deadline"]["detail"],
                                 tone=row["deadline"]["tone"]),
                "people": cell(stats["people"]),
                "passed": cell(stats["passed"]),
                "pending": cell(stats["pending"],
                                tone="warn" if stats["pending"] else None),
                "attempts": cell(stats["attempts"]),
                "avg": cell(None if stats["avg"] is None else f"{stats['avg']}% 规则通过"),
                "pass_rate": cell(None if stats["pass_rate"] is None
                                  else f"{stats['pass_rate']}%"),
                "actions": actions_cell([{"type": "open_detail", "label": "查看成绩"}]),
            },
        })
        rows.append(row)
    return rows


def _submission_cells(db: Session, submission: ScratchSubmission | None) -> dict:
    if submission is None:
        return {"status": cell(None), "score": cell(None), "revision": cell(None),
                "submitted_at": cell(None)}
    label, tone = SUBMISSION_STATUS.get(submission.status, (submission.status, "muted"))
    revision = db.get(ScratchProjectRevision, submission.project_revision_id)
    return {
        "status": cell(label, tone=tone),
        "score": cell(None if submission.score is None else f"{submission.score}%"),
        "revision": cell(f"第 {revision.revision_no} 版" if revision else None,
                         sub=f"挑战 v{submission.challenge_version}"),
        "submitted_at": cell(_iso(submission.submitted_at)),
    }


def _scratch_student_row(db: Session, block_id: int, user: User | None, user_id: int,
                         submissions: list[ScratchSubmission]) -> dict:
    counted = _counted_submission(submissions)
    tags = []
    if counted is not None and counted.status in ("needs_review", "pending_review"):
        tags.append({"label": "等待人工点评", "tone": "warn"})
    if counted is not None and counted.review_comment:
        tags.append({"label": "已点评", "tone": "muted"})
    return {
        "row_id": f"user-{user_id}",
        "user": {"id": user_id, "username": user.username if user else "已注销"},
        "name": user.username if user else "已注销",
        "attempt_count": len(submissions),
        "cells": {
            "name": cell(user.username if user else "已注销"),
            "attempt_count": cell(len(submissions)),
            "tags": badges_cell(tags),
            **_submission_cells(db, counted),
            "actions": actions_cell([] if counted is None else [
                {"type": "record_detail", "label": "快照与反馈", "record_id": counted.id},
                {"type": "scratch_studio", "label": "Studio 只读查看",
                 "challenge_id": counted.challenge_id, "submission_id": counted.id},
            ]),
        },
        "history_endpoint": (f"/lesson-homework/{block_id}/students/{user_id}/attempts"
                             if len(submissions) > 1 else None),
    }


def _scratch_students(db: Session, block_id: int,
                      submissions: list[ScratchSubmission]) -> list[dict]:
    by_user: dict[int, list[ScratchSubmission]] = {}
    for submission in submissions:
        by_user.setdefault(submission.user_id, []).append(submission)
    users = {u.id: u for u in db.scalars(
        select(User).where(User.id.in_(by_user.keys())))} if by_user else {}
    rows = [_scratch_student_row(db, block_id, users.get(user_id), user_id,
                                 sorted(items, key=lambda s: s.attempt_no))
            for user_id, items in by_user.items()]
    # 待点评的顶到最前：那是唯一需要老师动手的一批，排在第三页等于没做这个闭环。
    # 其后是未通过，最后是已通过——与整卷作业「先看谁需要帮」的阅读习惯一致。
    order = {"warn": 0, "danger": 1}
    rows.sort(key=lambda row: (order.get(row["cells"]["status"].get("tone"), 2),
                               row["name"]))
    return rows


def _scratch_detail(db: Session, block_id: int, student_ids: set[int] | None) -> dict:
    context = scratch_context(db, block_id)
    if context is None:
        raise LookupError("课时作业不存在。")
    block, _detail, challenge, lesson, section, course = context
    submission_query = (
        select(ScratchSubmission).where(ScratchSubmission.lesson_block_id == block.id)
        .order_by(ScratchSubmission.submitted_at.desc(), ScratchSubmission.id.desc())
    )
    submissions = list(db.scalars(
        _scope_students(submission_query, ScratchSubmission.user_id, student_ids)
    ))
    stats = _scratch_stats(submissions)
    row = _scratch_row(block, challenge, lesson, section, course)
    challenge_label = {"draft": "草稿", "published": "已发布",
                       "archived": "已归档"}.get(challenge.status, challenge.status)
    return row | {
        "full_score": 100,
        "pass_score": 100,
        "summary": {"participants": stats["people"], "attempts": stats["attempts"],
                    "submitted_participants": stats["people"], "avg": stats["avg"],
                    "min": None, "max": None, "pass_rate": stats["pass_rate"]},
        "distribution": [],
        "students": _scratch_students(db, block.id, submissions),
        "stats": [
            {"key": "people", "label": "提交学员", "text": str(stats["people"])},
            {"key": "attempts", "label": "提交人次", "text": str(stats["attempts"])},
            {"key": "passed", "label": "已通过", "text": str(stats["passed"])},
            {"key": "pending", "label": "待点评", "text": str(stats["pending"])},
            {"key": "avg", "label": "平均规则通过率",
             "text": "—" if stats["avg"] is None else f"{stats['avg']}%"},
            {"key": "pass_rate", "label": "通过率（按人）",
             "text": "—" if stats["pass_rate"] is None else f"{stats['pass_rate']}%"},
        ],
        "tags": [
            {"label": "Scratch 作业"},
            {"label": f"挑战 #{challenge.id} · {challenge.title}"},
            {"label": f"{challenge_label} · v{challenge.version}",
             "tone": "ok" if challenge.status == "published" else "warn"},
            {"label": "不设截止时间", "tone": "muted"},
        ],
    }


SCRATCH_HISTORY_COLUMNS = (
    Column("attempt_no", "次数"),
    Column("status", "判定"),
    Column("score", "规则通过率"),
    Column("revision", "快照版本"),
    Column("submitted_at", "提交"),
    Column("actions", "操作", align="right"),
)


def _scratch_history(db: Session, block_id: int, user_id: int,
                     student_ids: set[int] | None) -> dict:
    context = scratch_context(db, block_id)
    if context is None:
        raise LookupError("课时作业不存在。")
    _require_visible_student(user_id, student_ids, "该学员没有这份作业的提交记录。")
    block, *_ = context
    submissions = list(db.scalars(
        select(ScratchSubmission)
        .where(ScratchSubmission.lesson_block_id == block.id,
               ScratchSubmission.user_id == user_id)
        .order_by(ScratchSubmission.attempt_no.asc())
    ))
    if not submissions:
        raise LookupError("该学员没有这份作业的提交记录。")
    counted = _counted_submission(submissions)
    return {
        "student": {"user_id": user_id, "attempt_count": len(submissions)},
        "columns": [c.as_dict() for c in SCRATCH_HISTORY_COLUMNS],
        "rows": [{
            "row_id": f"submission-{s.id}",
            "counted": counted is not None and s.id == counted.id,
            "cells": {
                "attempt_no": cell(f"第 {s.attempt_no} 次"),
                **_submission_cells(db, s),
                "actions": actions_cell([
                    {"type": "record_detail", "label": "快照与反馈", "record_id": s.id},
                    {"type": "scratch_studio", "label": "Studio 只读查看",
                     "challenge_id": s.challenge_id, "submission_id": s.id},
                ]),
            },
        } for s in submissions],
    }


def _scratch_record(db: Session, block_id: int, record_id: int,
                    student_ids: set[int] | None) -> dict:
    """一次提交的快照与判定证据。字段成对下发，弹窗不认识 Scratch 的任何概念。"""
    context = scratch_context(db, block_id)
    if context is None:
        raise LookupError("课时作业不存在。")
    block, _detail, challenge, *_ = context
    submission = db.get(ScratchSubmission, record_id)
    if submission is None or submission.lesson_block_id != block.id:
        raise LookupError("提交记录不存在。")
    _require_visible_student(submission.user_id, student_ids, "提交记录不存在。")
    revision = db.get(ScratchProjectRevision, submission.project_revision_id)
    student = db.get(User, submission.user_id)
    label, _tone = SUBMISSION_STATUS.get(submission.status, (submission.status, "muted"))
    try:
        evaluation = json.loads(submission.evaluation_json or "{}")
    except (TypeError, ValueError):
        evaluation = {}
    rules = [r for r in (evaluation.get("rules") or []) if isinstance(r, dict)]
    missing = [r.get("label") or r.get("type") for r in rules if not r.get("passed")]
    return {
        "title": "提交快照与反馈",
        "note": "快照为提交时刻的不可变版本；此处不提供任何修改入口。",
        "fields": [
            {"label": "学员 / 挑战",
             "value": f"{student.username if student else '已注销'} · {challenge.title}"},
            {"label": "提交次数", "value": f"第 {submission.attempt_no} 次"},
            {"label": "快照版本",
             "value": (f"第 {revision.revision_no} 版 · 保存于 {_iso(revision.saved_at)}"
                       if revision else "—")},
            {"label": "内容指纹",
             "value": (f"sha256:{revision.sha256} · {revision.size_bytes} 字节"
                       if revision else "—"), "tone": "muted"},
            {"label": "判定结果",
             "value": f"{label}（规则通过 {len([r for r in rules if r.get('passed')])}"
                      f"/{len(rules)}，判定时挑战 v{submission.challenge_version}）"},
            {"label": "未通过的规则", "value": "、".join(missing) if missing else "无"},
            {"label": "反馈",
             "value": submission.review_comment or evaluation.get("note") or "暂无反馈。"},
        ],
    }


SCRATCH_KIND = HomeworkKind(
    key="scratch",
    label="Scratch 作业",
    block_type=SCRATCH_BLOCK_TYPE,
    student_source_type="lesson_scratch",
    student_facts=_scratch_student_facts,
    class_facts=_scratch_class_facts,
    class_attempt_counts=_scratch_class_attempt_counts,
    detail_view="submissions",
    column_keys=("homework", "path", "deadline", "people", "passed", "pending",
                 "attempts", "avg", "pass_rate", "actions"),
    stat_keys=("homework_count", "people", "passed", "pending", "attempts"),
    filter_keys=frozenset({"keyword", "course_id", "section_id", "lesson_id", "status"}),
    statuses=(Option("open", "进行中（含长期有效）"),),
    detail_columns=(
        Column("name", "学员"),
        Column("attempt_count", "提交次数"),
        Column("tags", "标记"),
        Column("status", "判定"),
        Column("score", "规则通过率"),
        Column("revision", "快照版本"),
        Column("submitted_at", "最后提交"),
        Column("actions", "操作", align="right"),
    ),
    detail_stats=(),
    collect=_collect_scratch_rows,
    detail=_scratch_detail,
    student_history=_scratch_history,
    record=_scratch_record,
    insight="统计按每位学员的最佳提交计算：先取通过的那次，没有通过则取规则通过率最高的一次。"
            "「待点评」是含运行型规则、系统判不了的提交，需要老师给终态。",
    empty_hint="还没有学员提交这份 Scratch 作业",
)


# ---------------------------------------------------------------------------
# 注册表
# ---------------------------------------------------------------------------

KINDS: tuple[HomeworkKind, ...] = (PAPER_KIND, SCRATCH_KIND)
_BY_KEY = {kind.key: kind for kind in KINDS}
_BY_BLOCK_TYPE = {kind.block_type: kind for kind in KINDS}


def kind_by_key(key: str) -> HomeworkKind | None:
    return _BY_KEY.get(key)


def kind_by_block_type(block_type: str) -> HomeworkKind | None:
    return _BY_BLOCK_TYPE.get(block_type)


def kind_for_block(db: Session, block_id: int) -> HomeworkKind | None:
    """按块反查作业类型。**这里是本模块唯一的类型分派点**，等价于
    `attempt_source.resolve_for_attempt` 之于作答来源。"""
    block = db.get(CourseLessonBlock, block_id)
    return kind_by_block_type(block.block_type) if block else None


def collect_rows(db: Session, filters: HomeworkFilters,
                 student_ids: set[int] | None) -> tuple[list[dict], list[HomeworkKind]]:
    """按注册表顺序收集全部类型的行，返回 (行, 真正参与了本次查询的类型)。"""
    rows: list[dict] = []
    used: list[HomeworkKind] = []
    for kind in KINDS:
        if not kind.accepts(filters):
            continue
        used.append(kind)
        rows += kind.collect(db, filters, student_ids)
    return rows, used


def columns_for(rows: Iterable[dict]) -> list[dict]:
    """表头 = 结果集中出现过的类型所声明列的并集，按 OVERVIEW_COLUMNS 的顺序。

    用「出现过的类型」而不是「全部注册类型」：只筛 Scratch 时不该留下一排恒为「—」
    的试卷列。空结果集退回全部注册类型的并集，免得表头在加载后突然变形。
    """
    keys = {row["kind"] for row in rows}
    kinds = [k for k in KINDS if k.key in keys] or list(KINDS)
    used: set[str] = set()
    for kind in kinds:
        used |= set(kind.column_keys)
    return [column.as_dict() for column in OVERVIEW_COLUMNS if column.key in used]


def stats_for(rows: list[dict]) -> list[dict]:
    """总览统计卡。同一张卡的分母只累加声明了该指标的行，避免把 0 当作真实值。"""
    keys = {row["kind"] for row in rows}
    kinds = [k for k in KINDS if k.key in keys] or list(KINDS)
    used: set[str] = set()
    for kind in kinds:
        used |= set(kind.stat_keys)
    tiles = []
    for stat in OVERVIEW_STATS:
        if stat.key not in used:
            continue
        if stat.key == "homework_count":
            tiles.append({"key": stat.key, "label": stat.label, "text": str(len(rows))})
            continue
        total = sum(row.get("metrics", {}).get(stat.key, 0) for row in rows)
        tiles.append({"key": stat.key, "label": stat.label, "text": str(total)})
    return tiles


def filters_for(rows: list[dict]) -> list[dict]:
    """筛选器描述。页面按它生成下拉框——所以下拉里永远不会出现前端自己编的取值。"""
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["kind"]] = counts.get(row["kind"], 0) + 1
    statuses: list[dict] = []
    seen: set[str] = set()
    for kind in KINDS:
        for option in kind.statuses:
            if option.value in seen:
                continue
            seen.add(option.value)
            statuses.append(option.as_dict())
    return [
        {"key": "kind", "label": "作业类型", "placeholder": "全部类型",
         "options": [{"value": kind.key, "label": kind.label,
                      "count": counts.get(kind.key, 0)} for kind in KINDS]},
        {"key": "status", "label": "作业状态", "placeholder": "全部状态",
         "options": statuses},
    ]


def tree_for(rows: list[dict]) -> list[dict]:
    """管理端目录树；只包含确实存在课时作业的节点，计数按类型分开给。"""
    courses: dict[int, dict] = {}
    for row in rows:
        course = courses.setdefault(row["course"]["id"], {**row["course"], "sections": {}})
        section = course["sections"].setdefault(
            row["section"]["id"], {**row["section"], "lessons": {}})
        lesson = section["lessons"].setdefault(
            row["lesson"]["id"], {**row["lesson"], "homework_count": 0, "kinds": {}})
        lesson["homework_count"] += 1
        lesson["kinds"][row["kind"]] = lesson["kinds"].get(row["kind"], 0) + 1
    return [
        {"id": course["id"], "title": course["title"], "sections": [
            {"id": section["id"], "title": section["title"],
             "lessons": list(section["lessons"].values())}
            for section in course["sections"].values()
        ]}
        for course in courses.values()
    ]


def kinds_meta() -> list[dict]:
    """类型元数据。详情页的列、口径说明、空状态文案全部由这里下发。"""
    return [{
        "key": kind.key,
        "label": kind.label,
        "detail_view": kind.detail_view,
        "insight": kind.insight,
        "empty_hint": kind.empty_hint,
        "columns": [column.as_dict() for column in kind.detail_columns],
    } for kind in KINDS]
