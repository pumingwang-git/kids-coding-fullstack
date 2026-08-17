"""作答来源（AttemptSource）：一次整卷作答挂在什么东西上。

**为什么要这一层**：`PaperAttempt.exam_link_id` 曾是 NOT NULL 外键，把「一次作答」
焊死在考试链接上——课时里的整卷作业、将来的班级测验都开不出 attempt。绕过去的唯一
办法是造假 exam_link，而那正是 `ProblemDryRun`（models.py:513）明令反对的做法。

本模块把入口、策略、呈现三层需要的能力收敛成一个只读值对象，`exam.py` 从此吃
`AttemptSource` 而不是 `ExamLink`。判分（scoring.py）、判题（judge/）、存答案三层
与来源无关，一行都不用改。

**红线（《7、…-计划评测报告》第六节第三条新纪律）**：
    除本模块的 `resolve_for_attempt` 之外，全项目禁止出现 `if source_type == ...`。
散落的来源分支是这次改造唯一不可逆的技术债——它会让下一个来源的接入成本从
「写一个适配器」变成「翻遍全文件找分支」。

字段名一律照抄 `ExamLink`：适配器因此是纯搬运，`exam.py` 的函数体几乎一字不改，
改造风险压到最低。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import CourseLessonBlock, ExamLink, LessonPaperBlock, Paper, PaperAttempt

# 来源类型枚举。新增来源时在这里加一个值 + 写一个适配器 + 在 resolve_for_attempt
# 里加一条分派，别的地方都不用动。
SOURCE_EXAM_LINK = "exam_link"
SOURCE_LESSON_HOMEWORK = "lesson_homework"
SOURCE_TYPES = {SOURCE_EXAM_LINK, SOURCE_LESSON_HOMEWORK}

LINK_NOT_FOUND = "链接无效或已停用。"


@dataclass(frozen=True)
class AttemptSource:
    """一次作答的来源，提供七组能力。

    冻结 dataclass 而不是 Protocol/ABC：这些字段在 exam.py 里被读几十次、从不被写。
    冻结让「适配一次、之后只读」成为类型层面的事实；用 ABC 则每个来源都要实现
    二十个 property，纯属噪音。
    """

    source_type: str
    source_id: int
    paper_id: int
    label: str          # 学生看得到的名字（链接名 / 课时块标题）
    active: bool
    # 兼容旧报表的冗余外键属于“考试链接”这一种来源，不能让调用方再按 source_type 猜。
    legacy_exam_link_id: int | None
    # 公开排名是来源能力，而不是“某一类来源”的路由层例外。新来源必须明确作出选择。
    leaderboard_enabled: bool

    # ① 时间窗
    open_at: datetime | None
    close_at: datetime | None
    entry_open_minutes: int

    # ② 时长
    duration_minutes: int | None
    late_start_policy: str  # truncate/block/overrun

    # ③ 次数
    attempt_limit: int      # 0 = 不限

    # ④ 计分
    score_policy: str       # best/last/first
    penalty_minutes: int

    # ⑤⑥⑦ 呈现
    show_score: str         # immediate/after_close/never
    show_analysis: str      # never/after_submit/after_close
    feedback_mode: str      # realtime/compile_only/after_close

    # 卷面呈现
    shuffle_questions: bool
    shuffle_options: bool

    # 候考页
    notice: str
    notice_ack_required: bool
    remind_minutes: str
    warn_unanswered: bool


# ---------------------------------------------------------------------------
# 适配器
# ---------------------------------------------------------------------------


def from_exam_link(link: ExamLink) -> AttemptSource:
    """考试链接 → 作答来源。字段一一对应，纯搬运。"""
    return AttemptSource(
        source_type=SOURCE_EXAM_LINK,
        source_id=link.id,
        paper_id=link.paper_id,
        label=link.name,
        active=link.status == "active",
        legacy_exam_link_id=link.id,
        leaderboard_enabled=True,
        open_at=link.open_at,
        close_at=link.close_at,
        entry_open_minutes=link.entry_open_minutes or 0,
        duration_minutes=link.duration_minutes,
        late_start_policy=link.late_start_policy,
        attempt_limit=link.attempt_limit or 0,
        score_policy=link.score_policy,
        penalty_minutes=link.penalty_minutes or 0,
        show_score=link.show_score,
        show_analysis=link.show_analysis,
        feedback_mode=link.feedback_mode,
        shuffle_questions=link.shuffle_questions,
        shuffle_options=link.shuffle_options,
        notice=link.notice or "",
        notice_ack_required=link.notice_ack_required,
        remind_minutes=link.remind_minutes or "",
        warn_unanswered=link.warn_unanswered,
    )


def from_lesson_homework(block: CourseLessonBlock, detail: LessonPaperBlock) -> AttemptSource:
    """课时作业块映射为整卷作答来源，投放规则只读块自身配置。"""
    return AttemptSource(
        source_type=SOURCE_LESSON_HOMEWORK, source_id=block.id, paper_id=detail.paper_id,
        label=block.title, active=True, legacy_exam_link_id=None, leaderboard_enabled=False,
        open_at=None, close_at=detail.due_at,
        entry_open_minutes=0, duration_minutes=None, late_start_policy="truncate",
        attempt_limit=detail.attempt_limit or 0, score_policy="best", penalty_minutes=0,
        show_score="immediate" if detail.show_score else "never",
        show_analysis="after_submit" if detail.show_analysis else "never",
        feedback_mode="realtime", shuffle_questions=detail.shuffle_questions,
        shuffle_options=detail.shuffle_options, notice="", notice_ack_required=False,
        remind_minutes="", warn_unanswered=True,
    )


# 课后作业块（LessonPaperBlock）→ 作答来源的映射已在《16、paper_attempts 作答来源
# 改造设计》§3.2 定稿，实现随 X2（课时整卷作业入场）落地：
#   open_at=None（能不能进由 course_access 两道闸门管，不在这层重复判）
#   close_at=due_at / duration=None（作业不限时）/ late_start_policy="truncate"
#   （用 overrun 会让 deadline 变 None，把截止时间架空）
#   score_policy="best" / feedback_mode="realtime" / show_* 由块上的 bool 映射两端取值
# 课时作业适配器由入口、结果与后台成绩链路共同调用，保持来源策略集中。


# ---------------------------------------------------------------------------
# 解析入口
# ---------------------------------------------------------------------------


def resolve_by_exam_token(db: Session, token: str) -> tuple[AttemptSource, Paper]:
    """考试链接 token → (来源, 试卷)。替代原 exam._load_link。"""
    link = db.scalar(select(ExamLink).where(ExamLink.access_token == token))
    if not link or link.status != "active":
        raise HTTPException(404, LINK_NOT_FOUND)
    paper = db.get(Paper, link.paper_id)
    if not paper or paper.status != "published":
        raise HTTPException(404, LINK_NOT_FOUND)
    return from_exam_link(link), paper


def resolve_for_attempt(db: Session, attempt: PaperAttempt) -> tuple[AttemptSource, Paper]:
    """按 attempt 反查来源。

    **这里是全项目唯一允许按 source_type 分派的地方**——它就是那个工厂。
    加新来源时只改这一处的分派表，调用方一行都不用动。
    """
    if attempt.source_type == SOURCE_EXAM_LINK:
        link = db.get(ExamLink, attempt.source_id)
        if link is None:
            raise HTTPException(404, LINK_NOT_FOUND)
        paper = db.get(Paper, attempt.paper_id)
        if paper is None:
            raise HTTPException(404, LINK_NOT_FOUND)
        return from_exam_link(link), paper
    if attempt.source_type == SOURCE_LESSON_HOMEWORK:
        block = db.get(CourseLessonBlock, attempt.source_id)
        detail = db.get(LessonPaperBlock, attempt.source_id)
        paper = db.get(Paper, attempt.paper_id)
        if block is None or detail is None or paper is None or block.block_type != "homework":
            raise HTTPException(404, LINK_NOT_FOUND)
        if detail.paper_id != paper.id:
            raise HTTPException(404, LINK_NOT_FOUND)
        return from_lesson_homework(block, detail), paper
    raise HTTPException(404, LINK_NOT_FOUND)


def lesson_homework_block_for_attempt(db: Session, attempt: PaperAttempt) -> CourseLessonBlock | None:
    """返回需要写回课时完成度的作业块；来源分派保持收敛在本模块。"""
    if attempt.source_type != SOURCE_LESSON_HOMEWORK:
        return None
    return db.get(CourseLessonBlock, attempt.source_id)


def attempt_scope(source: AttemptSource):
    """按来源筛 attempt 的查询条件。

    抽成函数是为了让「一次作答属于哪个来源」只有一处定义——散在各处写
    `PaperAttempt.source_type == x, PaperAttempt.source_id == y` 迟早会漏一个。
    """
    return (
        PaperAttempt.source_type == source.source_type,
        PaperAttempt.source_id == source.source_id,
    )


def attempt_count_for(db: Session, source_type: str, source_id: int) -> int:
    """Return the number of attempts owned by one polymorphic source."""
    return int(db.scalar(
        select(func.count(PaperAttempt.id)).where(
            PaperAttempt.source_type == source_type,
            PaperAttempt.source_id == source_id,
        )
    ) or 0)
