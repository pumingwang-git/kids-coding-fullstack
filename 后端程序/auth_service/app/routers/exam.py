"""学员端考试作答：候考 → 开考 → 发题 → 自动保存 → 判题 → 交卷 → 看分。

三条贯穿全文件的红线，改这个文件前先读：

1. **答案零下发**。ChoiceOption.is_correct / FillAnswer.answer / ReferenceSolution.code /
   非样例 TestCase 的输入输出，在作答期的任何响应里都不能出现——用"键不出现"而不是
   给 null，给 null 等于告诉前端这里本来有东西。
2. **时间只信服务端**。deadline_at 开考时算死落库，之后永不重算；每个响应带 server_now。
3. **越权一律 404**。别人的 attempt 用 403 会泄露"这个 attempt 存在"。

组卷文档里 score_mode / attempt_limit / feedback_mode / show_analysis / show_score /
shuffle_* / partial_credit_multi 这九个字段的服务端强制点全部在本文件与 scoring.py。
"""

from __future__ import annotations

import json
import logging
import random
import secrets
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..judge import JUDGE_FAILED, JudgeCase, JudgeUnavailable
from ..mistake_book import record_wrong
from ..judge.runner import JudgeQueueFull, JudgeTask, judge_key
from ..attempt_source import (
    SOURCE_LESSON_HOMEWORK,
    AttemptSource,
    attempt_scope,
    from_lesson_homework,
    lesson_homework_block_for_attempt,
    resolve_by_exam_token,
    resolve_for_attempt,
)
from ..models import (
    AttemptAnswer,
    AuditEvent,
    ChoiceOption,
    CodeSubmission,
    Course,
    CourseLesson,
    CourseLessonBlock,
    FillAnswer,
    LessonBlockCompletion,
    LessonPaperBlock,
    Paper,
    PaperAttempt,
    PaperQuestion,
    Problem,
    ProblemTag,
    ProgrammingDetail,
    Tag,
    TestCase,
    User,
    Video,
    VideoVariant,
)
from ..audit_summary import ensure_known_event_type
from ..course_access import Access, block_gate, completed_block_ids, course_visible, lesson_access
from ..oj_testdata import JudgeDataUnavailable, read_case_content
from ..schemas import SaveAnswerPayload, SubmitCodePayload
from ..scoring import (
    CaseOutcome,
    QuestionSpec,
    parse_answer,
    parse_blank_alternatives,
    score_programming,
    score_question,
    strip_answer_keys,
)
from ..s3_multipart import play_token_minutes
from ..security import hash_ip, utcnow
from .auth_secure import client_ip, current_user, db_session, limit, require_csrf
from .video_play import build_play_response

router = APIRouter(prefix="/api/exam", tags=["exam"])
logger = logging.getLogger(__name__)

# 判题终态。非终态（queued / judging）意味着前端还得继续轮询。
TERMINAL_JUDGE_STATUSES = frozenset(
    {"accepted", "wrong_answer", "compile_error", "runtime_error",
     "time_limit", "memory_limit", JUDGE_FAILED}
)

# 卷没发布、链接停用、token 不存在，三种情况共用这一句：区分开就是给爆破者送信息。
LINK_NOT_FOUND = "考试链接不存在或已失效。"
CHOICE_TYPES = {"choice", "multi_choice", "judge"}


# ==================== 通用助手 ====================


def _as_utc(value: datetime | None) -> datetime | None:
    """SQLite 存回来的 datetime 没有 tzinfo，比较前统一补上 UTC。"""
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _iso(value: datetime | None) -> str | None:
    aware = _as_utc(value)
    return aware.isoformat() if aware else None


def _audit(db: Session, request: Request, event: str, outcome: str, user_id: int | None,
           *, resource_type: str | None = None, resource_id: int | None = None, summary: dict | None = None):
    ensure_known_event_type(event, request.app.state.settings.environment)
    db.add(AuditEvent(
        event_type=event, outcome=outcome, user_id=user_id,
        ip_hmac=hash_ip(request.app.state.settings, client_ip(request)),
        resource_type=resource_type, resource_id=resource_id,
        summary_json=json.dumps(summary, ensure_ascii=False, sort_keys=True) if summary else None,
    ))


def _load_source(db: Session, token: str) -> tuple[AttemptSource, Paper]:
    """考试链接 token → (作答来源, 试卷)。解析实现在 attempt_source，本文件不认 ExamLink。"""
    return resolve_by_exam_token(db, token)


def _load_lesson_homework_source(db: Session, lesson_id: int, block_id: int,
                                 user: User) -> tuple[AttemptSource, Paper]:
    lesson = db.get(CourseLesson, lesson_id)
    block = db.get(CourseLessonBlock, block_id)
    if lesson is None or block is None or block.lesson_id != lesson.id or block.block_type != "homework":
        raise HTTPException(404, "课后作业不存在。")
    if not course_visible(db.get(Course, lesson.course_id)):
        raise HTTPException(404, "课后作业不存在。")
    ordered = list(db.scalars(
        select(CourseLessonBlock).where(CourseLessonBlock.lesson_id == lesson.id)
        .order_by(CourseLessonBlock.sort_order, CourseLessonBlock.id)
    ).all())
    gate = block_gate(
        db, user, lesson, block, ordered, completed_block_ids(db, user, lesson.id),
        lesson_access(db, user, lesson) is Access.GRANTED,
    )
    if gate["lock_reason"] is not None:
        raise HTTPException(403, "请先完成前置学习内容或开通课程后再进入作业。")
    detail = db.get(LessonPaperBlock, block.id)
    paper = db.get(Paper, detail.paper_id) if detail else None
    if detail is None or paper is None or paper.status != "published":
        raise HTTPException(404, "课后作业不存在。")
    return from_lesson_homework(block, detail), paper


def _phase(source: AttemptSource, now: datetime) -> str:
    open_at, close_at = _as_utc(source.open_at), _as_utc(source.close_at)
    if close_at and now >= close_at:
        return "closed"
    if open_at and now < open_at:
        entry_from = open_at - timedelta(minutes=source.entry_open_minutes or 0)
        return "entry_open" if now >= entry_from else "waiting"
    return "open"


def _compute_deadline(source: AttemptSource, started: datetime) -> datetime | None:
    """开考时执行一次，落库后永不重算。见组卷文档 4.2。"""
    raw = started + timedelta(minutes=source.duration_minutes) if source.duration_minutes else None
    close_at = _as_utc(source.close_at)
    if source.late_start_policy == "overrun":
        return raw  # 练习卷语义：close_at 只是"最晚开始时间"
    candidates = [value for value in (raw, close_at) if value]
    return min(candidates) if candidates else None


def _seeded_shuffle(items: list, seed: int) -> list:
    """确定性洗牌：同一个 attempt 每次发题都得到同一个顺序。

    只在后端做——前端拿到什么顺序就渲染什么顺序，不实现任何洗牌算法。
    两端各写一遍 Fisher-Yates 只要有一端边界差一点就是偶发题序错乱，极难查；
    而且让前端持有原始顺序 + 种子等于把"能反推原始题序"的能力送出去。
    """
    rng = random.Random(seed)
    result = list(items)
    for index in range(len(result) - 1, 0, -1):
        swap = rng.randint(0, index)
        result[index], result[swap] = result[swap], result[index]
    return result


def _used_attempts(db: Session, source: AttemptSource, user_id: int) -> int:
    return db.scalar(
        select(func.count(PaperAttempt.id))
        .where(*attempt_scope(source), PaperAttempt.user_id == user_id)
    ) or 0


def _ongoing_attempt(db: Session, source: AttemptSource, user_id: int) -> PaperAttempt | None:
    return db.scalar(
        select(PaperAttempt)
        .where(*attempt_scope(source), PaperAttempt.user_id == user_id,
               PaperAttempt.status == "ongoing")
        .order_by(PaperAttempt.attempt_no.desc())
    )


# 候考页默认带几条历史。练习卷的主行动是"再来一次"而不是"回顾第 37 次"，
# 所以这里给的是最近几条，不是全部——全部走 /{token}/attempts 分页拿。
HISTORY_PREVIEW = 5
# 用时缺失时的排序兜底：视作无限长，别让 None 排到用时最短的位置上去
FAR_SECONDS = 1 << 30


def _chronological_key(attempt: PaperAttempt) -> tuple:
    """按时间给 attempt 排序的键。用 started_at 而不是 attempt_no：
    attempt_no 是**按来源**编号的；来源隔离后，同一张卷的不同场次也不会混排。"""
    return (attempt.started_at, attempt.id)


def counted_attempt(attempts: Sequence[PaperAttempt], policy: str) -> PaperAttempt | None:
    """按 score_policy 选出「算数的那一次」。只在已交卷的里面挑——进行中的还没成绩。

    **这个函数是 score_policy 唯一的解释处**。这个字段此前从未被作答链路读过：
    配了 last 的链接，排行榜照样按最好成绩排，配置项和实际行为对不上。补上之后
    候考页与排行榜必须共用它，否则学员会看到"候考页说第 3 次算数、排行榜用的却是第 7 次"。
    """
    done = [item for item in attempts if item.status == "submitted"]
    if not done:
        return None
    if policy == "first":
        return min(done, key=_chronological_key)
    if policy == "last":
        return max(done, key=_chronological_key)
    # best：分高者优先，同分取用时更短的那次
    return max(done, key=lambda item: (
        item.total_score, -(item.duration_seconds if item.duration_seconds is not None else FAR_SECONDS)))


def _attempt_brief(attempt: PaperAttempt, *, show_score: bool, counted_id: int | None) -> dict:
    """历史作答的一行。成绩是否可见沿用 _score_visible，不在这另开口子。"""
    item = {
        "attempt_id": attempt.id, "attempt_no": attempt.attempt_no, "status": attempt.status,
        "started_at": _iso(attempt.started_at), "submitted_at": _iso(attempt.submitted_at),
        "duration_seconds": attempt.duration_seconds,
        "counted": counted_id is not None and attempt.id == counted_id,
    }
    if attempt.status == "submitted" and show_score:
        item["total_score"] = attempt.total_score
    return item


def _attempt_or_404(db: Session, attempt_id: int, user: User) -> tuple[PaperAttempt, AttemptSource, Paper]:
    attempt = db.get(PaperAttempt, attempt_id)
    # 别人的 attempt 用 404 而不是 403：403 等于确认了这个 id 存在。
    if not attempt or attempt.user_id != user.id:
        raise HTTPException(404, "作答记录不存在。")
    try:
        source, paper = resolve_for_attempt(db, attempt)
    except HTTPException:
        # 来源或卷没了：对学员一律「作答记录不存在」，不区分是哪一个丢了
        raise HTTPException(404, "作答记录不存在。") from None
    return attempt, source, paper


def _questions(db: Session, paper_id: int) -> list[PaperQuestion]:
    return list(db.scalars(
        select(PaperQuestion).where(PaperQuestion.paper_id == paper_id)
        .order_by(PaperQuestion.sort_order, PaperQuestion.id)
    ))


def _resolve_problems(db: Session, id_nos: list[str]) -> dict[str, Problem]:
    if not id_nos:
        return {}
    rows = db.scalars(select(Problem).where(Problem.problem_id_no.in_(id_nos))).all()
    return {row.problem_id_no: row for row in rows if row.problem_id_no}


def _answers_by_problem(db: Session, attempt_id: int) -> dict[str, AttemptAnswer]:
    rows = db.scalars(select(AttemptAnswer).where(AttemptAnswer.attempt_id == attempt_id)).all()
    return {row.problem_id_no: row for row in rows}


# ==================== 题面组装（永远不含答案）====================


def _options_for(db: Session, problem: Problem) -> list[tuple[str, bool]]:
    """返回 [(原始 label, 是否正确)]。label 按 sort_order 生成，与整卷预览同口径。"""
    rows = db.scalars(
        select(ChoiceOption).where(ChoiceOption.problem_id == problem.id).order_by(ChoiceOption.sort_order)
    ).all()
    return [(chr(65 + index), row.is_correct) for index, row in enumerate(rows)]


def _option_contents(db: Session, problem: Problem) -> list[tuple[str, str]]:
    """返回 [(原始 label, 选项正文)]，**不带对错**。

    label 与正文的配对在洗牌前就定死了（作答页是先编号再洗牌），所以这里按原序发出去，
    学员当时点的 B 仍然对应这里的 B。
    """
    rows = db.scalars(
        select(ChoiceOption).where(ChoiceOption.problem_id == problem.id).order_by(ChoiceOption.sort_order)
    ).all()
    return [(chr(65 + index), row.content) for index, row in enumerate(rows)]


def _limit_range(db: Session, problem_id: int, column: str, fallback: int) -> list[int] | None:
    """逐点限制的聚合范围 [min, max]，按**生效值**统计：没设逐点值的点算题目级 fallback。

    别只统计显式设过的点。只有 1 个点设成 200ms、其余继承 1000ms 时，那样算出的是
    [200, 200]，min == max，前端回落到题目级显示「限时 1000 ms」——学员按 1000 写解法，
    在那个 200ms 的点上无声 TLE。把继承的点按 fallback 计入才是这道题真实的限制区间。

    一个点都没显式设过时返回 None，前端继续渲染题目级单值。
    """
    column_attr = getattr(TestCase, column)
    values = db.scalars(select(column_attr).where(TestCase.problem_id == problem_id)).all()
    if not values or all(value is None for value in values):
        return None
    effective = [value if value is not None else fallback for value in values]
    return [min(effective), max(effective)]


def _question_payload(row: PaperQuestion, problem: Problem | None, db: Session, source: AttemptSource,
                      seed: int, saved: AttemptAnswer | None) -> dict:
    """单题的作答期载荷。与 admin_papers._preview_question_payload(reveal=False) 同形状，
    差异只有三处：按 seed 洗选项、附上已存作答、填空只给 blank_key 不给答案。"""
    if problem is None:
        # 题被删或退审：给占位而不是 500，学员至少能做完其余题目。
        return {"sort_order": row.sort_order, "score": row.score,
                "problem_id_no": row.problem_id_no, "missing": True}

    payload = {
        "sort_order": row.sort_order, "score": row.score, "problem_id_no": row.problem_id_no,
        "missing": False, "type": problem.type, "sub_type": problem.sub_type, "stem": problem.stem,
        "answer": parse_answer(saved.answer_json) if saved else None,
    }

    if problem.type in CHOICE_TYPES:
        rows = db.scalars(
            select(ChoiceOption).where(ChoiceOption.problem_id == problem.id).order_by(ChoiceOption.sort_order)
        ).all()
        options = [{"label": chr(65 + index), "content": item.content} for index, item in enumerate(rows)]
        # 判断题不洗：「正确/错误」换了位置只会让人以为自己看错了。
        if source.shuffle_options and problem.type != "judge":
            # 每题一个派生种子，否则所有题的选项会以同一种方式重排。
            options = _seeded_shuffle(options, seed + row.id)
        payload["options"] = options
    elif problem.type == "fill":
        # 只给空的标识，不给答案——前端靠它把作答按 blank_key 回传。
        payload["blank_keys"] = [
            item.blank_key for item in db.scalars(
                select(FillAnswer).where(FillAnswer.problem_id == problem.id).order_by(FillAnswer.blank_index)
            )
        ]
    elif problem.type == "programming":
        detail = db.get(ProgrammingDetail, problem.id)
        samples = db.scalars(
            select(TestCase).where(TestCase.problem_id == problem.id, TestCase.is_sample.is_(True))
            .order_by(TestCase.sort_order)
        ).all()
        # 题目级的值同时是标量展示值和逐点范围的兜底值，两处必须是同一个数
        time_limit_ms = detail.time_limit_ms if detail else 1000
        memory_limit_mb = detail.memory_limit_mb if detail else 256
        payload["programming"] = {
            "title": problem.title,
            "input_format": detail.input_format if detail else "",
            "output_format": detail.output_format if detail else "",
            "hints": detail.hints if detail else "",
            # 满分条件是计分规则不是判分资产，必须让学员看见：编译通过型的题
            # 前端要挂徽章、不渲染测试点表格，否则「我全错了怎么还满分」没人看得懂。
            "pass_condition": detail.pass_condition if detail else "全测试点通过",
            "time_limit_ms": time_limit_ms,
            "memory_limit_mb": memory_limit_mb,
            # 逐点限制只下发聚合范围 [min, max]，不下发逐条明细：
            # 明细会暴露"第 7 个测试点特别重"这类信息，隐藏点的一切元数据都不该外流；
            # 范围是聚合值，不指向具体测试点。前端在 max ≠ min 时渲染成范围。
            "time_limit_range": _limit_range(db, problem.id, "time_limit_ms", time_limit_ms),
            "memory_limit_range": _limit_range(db, problem.id, "memory_limit_mb", memory_limit_mb),
            # 只给样例。隐藏测试点的输入输出是判分资产，任何配置下都不下发。
            "samples": [{"input": item.input, "output": item.output} for item in samples],
        }
    return payload


# ==================== 判分 ====================


def _spec_for(db: Session, problem: Problem | None, row: PaperQuestion) -> QuestionSpec | None:
    """把判一道题需要的题面事实从库里查出来。题没了返回 None，该题记 0 分。"""
    if problem is None:
        return None
    if problem.type in CHOICE_TYPES:
        return QuestionSpec(problem.type, row.score, options=_options_for(db, problem))
    if problem.type == "fill":
        blanks = [
            # 标准答案在前，其它写法在后；判分时平权，展示时只用第一条
            (item.blank_key, [item.answer, *parse_blank_alternatives(item.alternatives_json)])
            for item in db.scalars(
                select(FillAnswer).where(FillAnswer.problem_id == problem.id).order_by(FillAnswer.blank_index)
            )
        ]
        return QuestionSpec("fill", row.score, blanks=blanks)
    if problem.type == "programming":
        # 编程题在 /code 提交时就判完了，这里不重跑沙箱，直接沿用固化的成绩。
        return QuestionSpec("programming", row.score)
    return QuestionSpec(problem.type, row.score)


def _score_attempt(db: Session, attempt: PaperAttempt, paper: Paper) -> int:
    """交卷判分。编程题沿用 /code 已固化的分数，其余题型现算。"""
    rows = _questions(db, paper.id)
    problems = _resolve_problems(db, [row.problem_id_no for row in rows])
    saved_map = _answers_by_problem(db, attempt.id)
    now = utcnow()
    total = 0

    for row in rows:
        problem = problems.get(row.problem_id_no)
        saved = saved_map.get(row.problem_id_no)

        if problem is not None and problem.type == "programming":
            # 判题失败的题不能算学员 0 分：score 留 null，不计入总分，结果页标"判题异常"。
            if saved and saved.judge_status == "failed":
                continue
            if saved and saved.score is not None:
                total += saved.score
                saved.judge_status, saved.judged_at = "judged", now
            else:
                saved = _upsert_answer(db, attempt.id, row.problem_id_no, saved)
                saved.score, saved.is_correct = 0, False
                saved.judge_status, saved.judged_at = "judged", now
                saved.detail_json = json.dumps({"submitted": False}, ensure_ascii=False)
            continue

        spec = _spec_for(db, problem, row)
        answer = parse_answer(saved.answer_json) if saved else {}
        if spec is None:
            score, is_correct, detail = 0, False, {"missing": True}
        else:
            score, is_correct, detail = score_question(
                answer, spec, partial_credit_multi=paper.partial_credit_multi, score_mode=paper.score_mode
            )
        saved = _upsert_answer(db, attempt.id, row.problem_id_no, saved)
        saved.score, saved.is_correct = score, is_correct
        saved.judge_status, saved.judged_at = "judged", now
        saved.detail_json = json.dumps(detail, ensure_ascii=False, sort_keys=True)
        total += score

    return total


def _upsert_answer(db: Session, attempt_id: int, problem_id_no: str,
                   existing: AttemptAnswer | None) -> AttemptAnswer:
    if existing is not None:
        return existing
    row = AttemptAnswer(attempt_id=attempt_id, problem_id_no=problem_id_no, answer_json="")
    db.add(row)
    db.flush()
    return row


def _fail_pending_judges(db: Session, attempt: PaperAttempt) -> list[str]:
    """封卷前把没跑完的计分判题收编成 judge_failed，返回涉及的题号。

    自动封卷（超时 / cron 收卷）不经过前端，等不到判题跑完。 pending 的提交不能
    落 0 分——那是系统的等待，不是学员答错——按 judge_failed 口径 score 留 null、
    不计入总分，与 sweep_stale_judgings 同一标准。
    """
    pending = list(db.scalars(
        select(CodeSubmission).where(
            CodeSubmission.attempt_id == attempt.id,
            CodeSubmission.kind == "submit",
            CodeSubmission.status.in_(["queued", "judging"]),
        )
    ))
    for submission in pending:
        submission.status = JUDGE_FAILED
        submission.compile_message = "收卷时判题尚未结束，本次提交未计分。"
        _mark_judge_failed(db, attempt.id, submission.problem_id_no)
    return sorted({submission.problem_id_no for submission in pending})


def _seal(db: Session, attempt: PaperAttempt, paper: Paper, kind: str) -> None:
    """封卷：判分 + 固化。手动交卷、超时、窗口关闭三条路径共用。"""
    now = utcnow()
    failed_problems = _fail_pending_judges(db, attempt)
    if failed_problems:
        logger.warning("封卷时收编未完成判题：attempt=%s 题号=%s", attempt.id, failed_problems)
    attempt.total_score = _score_attempt(db, attempt, paper)
    attempt.submitted_at = now
    attempt.submit_kind = kind
    attempt.status = "submitted"
    started = _as_utc(attempt.started_at) or now
    attempt.duration_seconds = max(int((now - started).total_seconds()), 0)
    answers = list(db.scalars(select(AttemptAnswer).where(AttemptAnswer.attempt_id == attempt.id)))
    wrong_numbers = [answer.problem_id_no for answer in answers if answer.is_correct is False]
    problems = _resolve_problems(db, wrong_numbers)
    for answer in answers:
        problem = problems.get(answer.problem_id_no)
        if answer.is_correct is False and problem is not None:
            record_wrong(
                db, student_id=attempt.user_id, problem_id=problem.id,
                source_type=attempt.source_type, source_id=attempt.source_id,
            )
    block = lesson_homework_block_for_attempt(db, attempt)
    if block is not None and db.scalar(
            select(LessonBlockCompletion).where(
                LessonBlockCompletion.user_id == attempt.user_id,
                LessonBlockCompletion.block_id == block.id,
            )
        ) is None:
        db.add(LessonBlockCompletion(
            user_id=attempt.user_id, lesson_id=block.lesson_id, block_id=block.id,
            source="homework",
        ))


def _seal_if_expired(db: Session, request: Request, attempt: PaperAttempt, paper: Paper) -> bool:
    """过期就地封卷。学员关掉浏览器就再也不发请求了，光靠前端倒计时收不了卷。"""
    deadline = _as_utc(attempt.deadline_at)
    if attempt.status != "ongoing" or not deadline or utcnow() <= deadline:
        return False
    _seal(db, attempt, paper, "auto_timeout")
    source, _ = resolve_for_attempt(db, attempt)
    from ..notification_reminders import maybe_publish_result_notification
    maybe_publish_result_notification(
        db, attempt=attempt, paper_title=paper.title,
        source=source,
    )
    _audit(db, request, "exam_auto_seal", "success", attempt.user_id,
           resource_type="paper_attempt", resource_id=attempt.id,
           summary={"submit_kind": "auto_timeout"})
    db.commit()
    return True


# ==================== 呈现策略：服务端裁字段 ====================


def _score_visible(source: AttemptSource, now: datetime) -> bool:
    if source.show_score == "never":
        return False
    if source.show_score == "after_close":
        close_at = _as_utc(source.close_at)
        return bool(close_at and now >= close_at)
    return True


def _analysis_visible(source: AttemptSource, now: datetime, submitted: bool) -> bool:
    if source.show_analysis == "never":
        return False
    if source.show_analysis == "after_close":
        close_at = _as_utc(source.close_at)
        return bool(close_at and now >= close_at)
    return submitted


def _cases_visible(source: AttemptSource, now: datetime) -> bool:
    """编程题逐测试点结果什么时候能看到。compile_only 永远只给编译信息。"""
    if source.feedback_mode == "compile_only":
        return False
    if source.feedback_mode == "after_close":
        close_at = _as_utc(source.close_at)
        return bool(close_at and now >= close_at)
    return True


def _submission_payload(submission: CodeSubmission, source: AttemptSource, now: datetime) -> dict:
    """提交结果的对外形状，按 feedback_mode 裁剪。样例的输入输出本来就是公开的，
    隐藏测试点的内容在 judge 层就没进结果对象，这里不必再防一次。"""
    payload = {
        "id": submission.id, "kind": submission.kind, "language": submission.language,
        "status": submission.status, "compile_message": submission.compile_message,
        "created_at": _iso(submission.created_at),
    }
    # 还没判完就什么结果都不给。别在这里图省事给个 cases: []——前端把"键不存在"
    # 读作「暂不可见」、把空数组读作「真的没有测试点」，排队中给空数组会让它
    # 渲染成一张空表格而不是"判题中"。
    if submission.status not in TERMINAL_JUDGE_STATUSES:
        return payload
    detail = json.loads(submission.detail_json) if submission.detail_json else []
    if submission.kind == "trial" or _cases_visible(source, now):
        payload["cases"] = detail
        payload["time_ms"], payload["memory_kb"] = submission.time_ms, submission.memory_kb
    if submission.kind == "submit" and _score_visible(source, now) and submission.score is not None:
        payload["score"] = submission.score
    return payload


# ==================== 接口 ====================


def _history_preview(db: Session, source: AttemptSource, user: User, now: datetime) -> tuple[list[dict], dict]:
    """候考页的历史区：一个摘要 + 最近 HISTORY_PREVIEW 条。

    不给全部：候考页是每次进入都要拉的接口，而不限次数（attempt_limit=0）的练习卷
    作答记录会一直涨——把一个无上限的数组挂在必经之路上，迟早自己把自己拖垮。
    要全部走 /{token}/attempts 分页。

    列表里除了最近几条，还**固定带上"算数的那一次"**：它可能是第 71 次，早被挤出
    最近 5 条了，而学员最关心的恰恰是它。少了这一条，摘要说"最好成绩 92"，列表里
    却找不到那一次，只能靠展开全部去翻。
    """
    attempts = list(db.scalars(
        select(PaperAttempt)
        .where(*attempt_scope(source), PaperAttempt.user_id == user.id)
        .order_by(PaperAttempt.attempt_no)
    ))
    show_score = _score_visible(source, now)
    counted = counted_attempt(attempts, source.score_policy)
    # 成绩不公开时不能暴露"哪一次最好"——那是把分数的相对关系换个形式说出来。
    # 但 first / last 是纯时间口径，与分数无关，照给不误。
    hide_ranking = not show_score and source.score_policy == "best"
    counted_id = None if hide_ranking or counted is None else counted.id

    recent = attempts[-HISTORY_PREVIEW:]
    picked = {item.id: item for item in recent}
    if counted is not None and not hide_ranking:
        picked.setdefault(counted.id, counted)
    # 进行中的置顶（它是唯一可继续的），其余按次数倒序：最想看的最近一次在最上面
    ordered = sorted(picked.values(), key=lambda item: (item.status != "ongoing", -item.attempt_no))
    history = [_attempt_brief(item, show_score=show_score, counted_id=counted_id) for item in ordered]

    best = counted_attempt(attempts, "best")
    last = counted_attempt(attempts, "last")
    summary = {
        "count": len(attempts),
        "score_policy": source.score_policy,
        "counted_attempt_id": counted_id,
        "has_more": len(attempts) > len(history),
        "best": None if hide_ranking or best is None else _attempt_brief(best, show_score=show_score, counted_id=counted_id),
        "last": None if last is None else _attempt_brief(last, show_score=show_score, counted_id=counted_id),
    }
    return history, summary


def _entry_payload(source: AttemptSource, paper: Paper, request: Request, user: User,
                   db: Session) -> dict:
    """候考页。不需要 attempt 存在，也不返回任何题目。"""
    limit(request, "exam-entry", str(user.id), 60, 60)
    now = utcnow()
    phase = _phase(source, now)

    rows = _questions(db, paper.id)
    problems = _resolve_problems(db, [row.problem_id_no for row in rows])
    breakdown: dict[str, int] = {}
    for row in rows:
        problem = problems.get(row.problem_id_no)
        key = problem.type if problem else "missing"
        breakdown[key] = breakdown.get(key, 0) + 1

    # 课时作业的「题目列表」看板只发展示元数据（题名/题型/难度/来源/知识点/分值），
    # 题干、选项、答案仍按红线一零下发；考试链接来源不给这个清单，避免开考前泄卷面构成。
    outline = None
    if source.source_type == SOURCE_LESSON_HOMEWORK:
        tag_rows = db.execute(
            select(ProblemTag.problem_id, Tag.name)
            .join(Tag, Tag.id == ProblemTag.tag_id)
            .where(
                ProblemTag.problem_id.in_([p.id for p in problems.values()] or [0]),
                Tag.category == "knowledge",
            )
        ).all()
        tags_by_problem: dict[int, list[str]] = {}
        for problem_id, tag_name in tag_rows:
            tags_by_problem.setdefault(problem_id, []).append(tag_name)
        outline = []
        for row in rows:
            item = {"sort_order": row.sort_order, "problem_id_no": row.problem_id_no,
                    "score": row.score}
            problem = problems.get(row.problem_id_no)
            if problem is None:
                item["missing"] = True
            else:
                item.update({
                    "title": problem.title, "type": problem.type,
                    "difficulty": problem.difficulty, "source": problem.source,
                    "knowledge": tags_by_problem.get(problem.id, []),
                })
            outline.append(item)

        # 逐题通过状态按「任何一次已交卷作答里判对过」累计，而不是只投影计分那一次：
        # 学员分两次各做对一半的题，进度条也该涨。成绩不公开（show_score=never）时
        # 这个键整体不下发——给了它等于变相泄对错，前端据此整列降级为 "—"。
        if _score_visible(source, now):
            answered: set[str] = set()
            passed: set[str] = set()
            for problem_id_no, is_correct in db.execute(
                select(AttemptAnswer.problem_id_no, AttemptAnswer.is_correct)
                .join(PaperAttempt, PaperAttempt.id == AttemptAnswer.attempt_id)
                .where(
                    *attempt_scope(source),
                    PaperAttempt.user_id == user.id,
                    PaperAttempt.status == "submitted",
                )
            ):
                answered.add(problem_id_no)
                if is_correct:
                    passed.add(problem_id_no)
            for item in outline:
                # answered 区分「没碰过」与「答过但没对」——两者都显示 ✗ 会把
                # 从没做过的题说成失败，学员会以为记录丢了。
                item["answered"] = item.get("problem_id_no") in answered
                item["passed"] = item.get("problem_id_no") in passed

    ongoing = _ongoing_attempt(db, source, user.id)
    if ongoing and _seal_if_expired(db, request, ongoing, paper):
        ongoing = None
    used = _used_attempts(db, source, user.id)

    history, summary = _history_preview(db, source, user, now)

    blocked = _entry_blocker(source, now, used, ongoing)
    payload = {
        "paper": {
            "title": paper.title, "description": paper.description, "paper_type": paper.paper_type,
            "subject": paper.subject, "question_count": len(rows), "total_score": paper.total_score,
            "type_breakdown": breakdown,
        },
        # 响应 key 保持 "link"：这是对外契约，前端读的是 entry.link.*。
        # 内部变量改叫 source 是实现细节，不该穿透到 wire format。
        "link": {
            "name": source.label, "open_at": _iso(source.open_at), "close_at": _iso(source.close_at),
            "duration_minutes": source.duration_minutes, "attempt_limit": source.attempt_limit,
            "late_start_policy": source.late_start_policy, "notice": source.notice,
            # 多次作答时"哪一次算数"是候考页最该说清的一件事，之前整个 source 载荷里没有它
            "score_policy": source.score_policy,
            "notice_ack_required": source.notice_ack_required, "entry_open_minutes": source.entry_open_minutes,
            "remind_minutes": source.remind_minutes, "warn_unanswered": source.warn_unanswered,
        },
        "attempts": {"used": used, "limit": source.attempt_limit,
                     "ongoing_attempt_id": ongoing.id if ongoing else None,
                     "history": history, "summary": summary},
        "phase": phase,
        "can_start": blocked is None,
        "blocked_reason": blocked,
        "server_now": _iso(now),
    }
    if _score_visible(source, now) and paper.pass_score is not None:
        payload["paper"]["pass_score"] = paper.pass_score
    if outline is not None:
        payload["paper"]["questions"] = outline
    return payload


@router.get("/{token}")
def exam_entry(token: str, request: Request, user: User = Depends(current_user),
               db: Session = Depends(db_session)):
    return _entry_payload(*_load_source(db, token), request, user, db)


def _attempt_history_payload(source: AttemptSource, request: Request, page: int, size: int,
                             user: User, db: Session) -> dict:
    """历史作答的分页列表，供候考页的「查看全部 N 次记录」用。

    倒序：最近一次在第一页第一条。一百次记录里，学员要找的几乎总是最近的那几次
    或者算数的那一次，而不是"我第一次考了多少"。

    这里不做 _seal_if_expired：查历史是只读动作，时间到了也该让人看完自己考过什么。
    """
    limit(request, "exam-entry", str(user.id), 60, 60)
    now = utcnow()
    show_score = _score_visible(source, now)
    scope = (*attempt_scope(source), PaperAttempt.user_id == user.id)

    total = db.scalar(select(func.count(PaperAttempt.id)).where(*scope)) or 0
    rows = db.scalars(
        select(PaperAttempt).where(*scope)
        .order_by(PaperAttempt.attempt_no.desc())
        .offset((page - 1) * size).limit(size)
    ).all()
    # 计分那次要在整套记录里选，不是在当前这一页里选——按页算会翻一页换一个答案
    counted = counted_attempt(list(db.scalars(select(PaperAttempt).where(*scope))), source.score_policy)
    counted_id = None if (counted is None or (not show_score and source.score_policy == "best")) else counted.id
    return {
        "items": [_attempt_brief(row, show_score=show_score, counted_id=counted_id) for row in rows],
        "page": page, "size": size, "total": total,
        "counted_attempt_id": counted_id, "score_policy": source.score_policy,
    }


@router.get("/{token}/attempts")
def exam_attempt_history(token: str, request: Request, page: int = Query(1, ge=1),
                         size: int = Query(20, ge=1, le=100),
                         user: User = Depends(current_user), db: Session = Depends(db_session)):
    return _attempt_history_payload(_load_source(db, token)[0], request, page, size, user, db)


@router.get("/lesson-homework/{lesson_id}/blocks/{block_id}")
def lesson_homework_entry(lesson_id: int, block_id: int, request: Request,
                          user: User = Depends(current_user), db: Session = Depends(db_session)):
    limit(request, "exam-entry", str(user.id), 60, 60)
    return _entry_payload(*_load_lesson_homework_source(db, lesson_id, block_id, user), request, user, db)


@router.get("/lesson-homework/{lesson_id}/blocks/{block_id}/attempts")
def lesson_homework_history(lesson_id: int, block_id: int, request: Request,
                            page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100),
                            user: User = Depends(current_user), db: Session = Depends(db_session)):
    limit(request, "exam-entry", str(user.id), 60, 60)
    source, _paper = _load_lesson_homework_source(db, lesson_id, block_id, user)
    return _attempt_history_payload(source, request, page, size, user, db)


@router.post("/lesson-homework/{lesson_id}/blocks/{block_id}/start", status_code=201)
def start_lesson_homework(lesson_id: int, block_id: int, request: Request,
                          user: User = Depends(current_user), db: Session = Depends(db_session)):
    require_csrf(request)
    limit(request, "exam-start", str(user.id), 20, 60)
    return _start_source_attempt(*_load_lesson_homework_source(db, lesson_id, block_id, user), request, user, db)


def _entry_blocker(source: AttemptSource, now: datetime, used: int, ongoing: PaperAttempt | None) -> str | None:
    """入口校验，顺序即错误提示的优先级，见组卷文档 4.3。不能换序。"""
    open_at, close_at = _as_utc(source.open_at), _as_utc(source.close_at)
    if open_at and now < open_at:
        return f"考试尚未开始，开始时间 {open_at.astimezone(UTC).strftime('%Y-%m-%d %H:%M')} UTC。"
    if close_at and now >= close_at:
        return "作业已过截止时间，不能再提交了。" if source.source_type == SOURCE_LESSON_HOMEWORK else "考试已结束。"
    # 续做要排在次数检查之前，否则刷新页面会被自己的 ongoing 顶掉一次机会。
    if ongoing is not None:
        return None
    if source.attempt_limit and used >= source.attempt_limit:
        return "已达最大作答次数。"
    if source.late_start_policy == "block" and source.duration_minutes and close_at:
        if now > close_at - timedelta(minutes=source.duration_minutes):
            return "剩余时间不足以完成本卷。"
    return None


def _start_source_attempt(source: AttemptSource, paper: Paper, request: Request, user: User,
                          db: Session) -> dict:
    now = utcnow()

    ongoing = _ongoing_attempt(db, source, user.id)
    if ongoing and _seal_if_expired(db, request, ongoing, paper):
        ongoing = None
    if ongoing is not None:
        return {"attempt_id": ongoing.id, "resumed": True, "deadline_at": _iso(ongoing.deadline_at),
                "server_now": _iso(now)}

    used = _used_attempts(db, source, user.id)
    blocker = _entry_blocker(source, now, used, None)
    if blocker:
        # 这里曾经写 `token[:4]`——X1 把入口从"一个 token"抽象成 AttemptSource 之后，
        # 这个函数已经没有 token 参数了，于是**每一次开考被拒都是 500 而不是 403**：
        # 时间没到、次数用完这些正常拒绝，学生看到的是"请求失败，请稍后再试"，
        # 而前端 begin() 的 catch 本来是要把原因显示在候考页上的（ExamView.vue:81-86）。
        # 身份改记 (source_type, source_id)，它对两种来源都成立，也不必再截断什么。
        _audit(db, request, "exam_entry_denied", "failure", user.id,
               resource_type=source.source_type, resource_id=source.source_id,
               summary={"source_type": source.source_type, "source_id": source.source_id,
                        "reason": blocker})
        db.commit()
        raise HTTPException(403, blocker)

    attempt = PaperAttempt(
        # 权威身份是 (source_type, source_id)；exam_link_id 是考试来源的冗余外键，
        # 审计与既有报表还按它查，所以继续写（见《16、…作答来源改造设计》第二节末）。
        source_type=source.source_type, source_id=source.source_id,
        exam_link_id=source.legacy_exam_link_id,
        paper_id=paper.id, user_id=user.id, attempt_no=used + 1,
        started_at=now, deadline_at=_compute_deadline(source, now),
        shuffle_seed=secrets.randbelow(2**31), status="ongoing",
        ip_hmac=hash_ip(request.app.state.settings, client_ip(request)),
    )
    db.add(attempt)
    try:
        db.flush()
    except IntegrityError:
        # uq_attempt_source 兜住连点两下开考按钮的并发，转成人话而不是 500。
        db.rollback()
        raise HTTPException(409, "作答已在其他窗口开始，请刷新页面。") from None
    _audit(db, request, "exam_start", "success", user.id,
           resource_type="paper_attempt", resource_id=attempt.id,
           summary={"source_type": source.source_type, "source_id": source.source_id,
                    "paper_id": paper.id, "attempt_no": attempt.attempt_no,
                    "deadline_at": _iso(attempt.deadline_at)})
    db.commit()
    return {"attempt_id": attempt.id, "resumed": False, "deadline_at": _iso(attempt.deadline_at),
            "server_now": _iso(now)}


@router.post("/{token}/start", status_code=201)
def start_attempt(token: str, request: Request, user: User = Depends(current_user),
                  db: Session = Depends(db_session)):
    require_csrf(request)
    limit(request, "exam-start", str(user.id), 20, 60)
    return _start_source_attempt(*_load_source(db, token), request, user, db)


@router.get("/attempts/{attempt_id}")
def get_attempt(attempt_id: int, request: Request, user: User = Depends(current_user),
                db: Session = Depends(db_session)):
    """发题。响应里不含任何答案——这条有一个递归遍历的回归测试盯着。"""
    limit(request, "exam-entry", str(user.id), 120, 60)
    attempt, source, paper = _attempt_or_404(db, attempt_id, user)
    if _seal_if_expired(db, request, attempt, paper):
        raise HTTPException(409, "考试时间已到，本次作答已自动交卷。")

    rows = _questions(db, paper.id)
    problems = _resolve_problems(db, [row.problem_id_no for row in rows])
    saved_map = _answers_by_problem(db, attempt.id)
    if source.shuffle_questions:
        rows = _seeded_shuffle(rows, attempt.shuffle_seed)

    questions = [
        _question_payload(row, problems.get(row.problem_id_no), db, source,
                          attempt.shuffle_seed, saved_map.get(row.problem_id_no))
        for row in rows
    ]
    now = utcnow()
    # 编程题优先恢复自动保存的草稿；没有草稿时才回填最后一次提交代码。
    for question in questions:
        if question.get("type") != "programming":
            continue
        last = db.scalar(
            select(CodeSubmission)
            .where(CodeSubmission.attempt_id == attempt.id,
                   CodeSubmission.problem_id_no == question["problem_id_no"])
            .order_by(CodeSubmission.id.desc())
        )
        if last:
            question["last_submission"] = _submission_payload(last, source, now)
            question["last_code"] = last.code
        saved = question.get("answer") or {}
        if saved.get("draft_code") is not None:
            question["last_code"] = saved["draft_code"]

    return {
        "attempt": {"id": attempt.id, "attempt_no": attempt.attempt_no, "status": attempt.status,
                    "started_at": _iso(attempt.started_at), "deadline_at": _iso(attempt.deadline_at),
                    "submitted_at": _iso(attempt.submitted_at)},
        "paper": {"title": paper.title, "paper_type": paper.paper_type, "subject": paper.subject,
                  "total_score": paper.total_score, "question_count": len(rows)},
        "link": {"remind_minutes": source.remind_minutes, "warn_unanswered": source.warn_unanswered,
                 "feedback_mode": source.feedback_mode},
        "questions": questions,
        "server_now": _iso(now),
    }


@router.put("/attempts/{attempt_id}/answers")
def save_answer(attempt_id: int, payload: SaveAnswerPayload, request: Request,
                user: User = Depends(current_user), db: Session = Depends(db_session)):
    """自动保存。按题覆盖、幂等、不判分、不返回任何对错。"""
    require_csrf(request)
    limit(request, "exam-save", f"{user.id}:{attempt_id}", 120, 60)
    attempt, _source, paper = _attempt_or_404(db, attempt_id, user)
    if _seal_if_expired(db, request, attempt, paper):
        raise HTTPException(409, "考试时间已到，本次作答未保存。")
    if attempt.status != "ongoing":
        raise HTTPException(409, "本次作答已交卷。")

    row = db.scalar(
        select(PaperQuestion).where(PaperQuestion.paper_id == paper.id,
                                    PaperQuestion.problem_id_no == payload.problem_id_no)
    )
    if row is None:
        raise HTTPException(404, "题目不在本卷中。")
    # Schema 只保证载荷自身自洽（choice 带 picked、fill 带 blanks），挡不住
    # "把填空的答案存到选择题上"。脏数据进了库，要等交卷判分时才炸。
    problem = _resolve_problems(db, [payload.problem_id_no]).get(payload.problem_id_no)
    if problem is not None and payload.answer.type != problem.type:
        raise HTTPException(422, "作答类型与题目类型不一致。")

    saved = db.scalar(
        select(AttemptAnswer).where(AttemptAnswer.attempt_id == attempt.id,
                                    AttemptAnswer.problem_id_no == payload.problem_id_no)
    )
    saved = _upsert_answer(db, attempt.id, payload.problem_id_no, saved)
    saved.answer_json = payload.answer.model_dump_json(exclude_none=True)
    now = utcnow()
    db.commit()
    return {"saved_at": _iso(now), "server_now": _iso(now)}


@router.post("/attempts/{attempt_id}/code")
def run_code(attempt_id: int, payload: SubmitCodePayload, request: Request,
             user: User = Depends(current_user), db: Session = Depends(db_session)):
    """编程题试跑 / 提交判题。试跑只跑样例且不计分，提交跑全部测试点并固化成绩。"""
    require_csrf(request)
    # 判题是最贵的资源，限流必须严。
    limit(request, "exam-judge", str(user.id), 20, 60)
    attempt, source, paper = _attempt_or_404(db, attempt_id, user)
    if _seal_if_expired(db, request, attempt, paper):
        raise HTTPException(409, "考试时间已到，本次作答已自动交卷。")
    if attempt.status != "ongoing":
        raise HTTPException(409, "本次作答已交卷。")

    row = db.scalar(
        select(PaperQuestion).where(PaperQuestion.paper_id == paper.id,
                                    PaperQuestion.problem_id_no == payload.problem_id_no)
    )
    if row is None:
        raise HTTPException(404, "题目不在本卷中。")
    problem = _resolve_problems(db, [payload.problem_id_no]).get(payload.problem_id_no)
    if problem is None or problem.type != "programming":
        raise HTTPException(400, "该题不是编程题。")

    # 判题本身不在这个请求里做——落一条 queued 就返回，剩下的交给判题线程池。
    # 同步判题时这个请求会全程占着一个 DB 连接（数百毫秒到数秒），15 个人同时判题
    # 就能把连接池抽干，连"保存答案"都存不上。见 app/judge/runner.py 的模块注释。
    submission = CodeSubmission(
        attempt_id=attempt.id, problem_id_no=payload.problem_id_no, language=payload.language,
        code=payload.code, kind=payload.kind, status="queued",
    )
    db.add(submission)
    db.commit()

    try:
        ahead = request.app.state.judge_runner.enqueue(
            JudgeTask(submission_id=submission.id, custom_input=payload.custom_input)
        )
    except JudgeQueueFull as exc:
        # 队列满了就别让请求挂着等——挂着只会把等待变成超时，而且占着线程。
        submission.status = JUDGE_FAILED
        submission.compile_message = "判题排队已满，请稍后重试。"
        # 与其余失败路径同一口径：系统的锅记 judge_failed、成绩留 null。
        # 少了这一句，学员若没重试就按未作答记 0 分——排不上队变成答错了。
        if payload.kind == "submit":
            _mark_judge_failed(db, attempt.id, payload.problem_id_no)
        db.commit()
        raise HTTPException(429, "判题排队已满，请稍后重试。") from exc

    payload_out = _submission_payload(submission, source, utcnow())
    payload_out["queue_position"] = ahead
    return payload_out


def _judge_inputs(db: Session, submission: CodeSubmission, custom_input: str | None, settings):
    """把判一次题需要的一切从库里取成**普通 Python 值**。

    取成普通值是有意的：取完就 commit 放连接，判题期间一行 ORM 都不碰。
    测试点正文也在这一步读盘（ZIP 导入的点内容在磁盘上），同样是为了让判题期间
    不再碰任何 IO 上下文。

    返回 None 表示这条提交已经没法判了（题被删、卷被改），调用方按 judge_failed 处理；
    测试数据读不出来则抛 JudgeDataUnavailable，与"题没了"分开报，因为运维要看的错不一样。
    """
    attempt = db.get(PaperAttempt, submission.attempt_id)
    if attempt is None:
        return None
    try:
        source, paper = resolve_for_attempt(db, attempt)
    except HTTPException:
        return None  # 来源或卷没了：这条提交没法判了，调用方按 judge_failed 处理
    row = db.scalar(
        select(PaperQuestion).where(PaperQuestion.paper_id == paper.id,
                                    PaperQuestion.problem_id_no == submission.problem_id_no)
    )
    problem = _resolve_problems(db, [submission.problem_id_no]).get(submission.problem_id_no)
    if row is None or problem is None or problem.type != "programming":
        return None

    detail = db.get(ProgrammingDetail, problem.id)
    all_cases = list(db.scalars(
        select(TestCase).where(TestCase.problem_id == problem.id).order_by(TestCase.sort_order, TestCase.id)
    ))
    if custom_input is not None and submission.kind == "trial":
        # 自测：拿学员自己给的 stdin 跑一次，没有"期望输出"可比。expected 留空只是
        # 为了填满 JudgeCase 的形状——真沙箱仍会把 stdout 原样放进 actual，前端的
        # 自测页签只读 actual/时间/内存，不看 status（这里的 status 没有意义）。
        # is_sample=True 是必须的：judge 层按它决定 input/actual 进不进结果对象，
        # 置 False 会把学员自己的输入输出裁掉，自测就成了黑盒。
        weights: list[int] = []
        cases = [JudgeCase(input=custom_input, expected="", is_sample=True)]
    else:
        selected = [case for case in all_cases if case.is_sample] if submission.kind == "trial" else all_cases
        weights = [case.score if case.score is not None else 1 for case in selected]
        # 正文必须走 read_case_content：ZIP 导入的点 input/output 两列是空串，内容在磁盘。
        # 直接读这两列（本行原来的写法）会让所有隐藏测试点变成"空输入→期望空输出"，
        # 于是不输出任何东西的程序满分、正确解法 0 分。改这行前先读它的文档字符串。
        cases = []
        for case in selected:
            case_input, case_output = read_case_content(settings, case)
            cases.append(JudgeCase(
                input=case_input, expected=case_output, is_sample=case.is_sample,
                weight=case.score if case.score is not None else 1,
                time_limit_ms=case.time_limit_ms, memory_limit_mb=case.memory_limit_mb,
            ))
    return {
        "cases": cases,
        "weights": weights,
        "time_limit_ms": detail.time_limit_ms if detail else 1000,
        "memory_limit_mb": detail.memory_limit_mb if detail else 256,
        "compile_only": bool(detail and detail.pass_condition == "编译通过"),
        "full_score": row.score,
        "score_mode": paper.score_mode,
    }


def judge_submission(session_factory, judge, task: JudgeTask, settings) -> None:
    """在判题线程里跑完一次提交。**这个函数不在请求上下文里**，别碰 request。

    连接口径是本函数的重点，三段式：
      1. 开 session 把判题输入取成普通值 → commit（连接还回池子）
      2. 判题（数百毫秒到数秒，**期间一个连接都不占**）
      3. 再开事务写回结果与成绩
    第 1、3 段各只有毫秒级。漏掉中间那次 commit，异步化就白做了。

    settings 显式传进来而不是在函数里 get_settings()：测试里每套环境有各自的
    testdata_upload_root，读缓存的全局配置会让判题去另一个目录找测试数据。
    """
    db = session_factory()
    try:
        _judge_submission_inner(db, judge, task, settings)
    except Exception:
        # 任何未预期的异常都必须让这条提交落到终态。只记日志的话它会一直停在
        # judging，学员端对着转圈的界面等到僵尸清理为止——而那是十分钟起步。
        logger.exception("判题意外失败：submission_id=%s", task.submission_id)
        _fail_submission(db, task.submission_id, "判题过程出错，请重新提交。")
    finally:
        db.close()


def _fail_submission(db: Session, submission_id: int, message: str) -> None:
    """兜底收尾：把一条提交置成 judge_failed。自身再出错也不许往外抛。"""
    try:
        db.rollback()
        submission = db.get(CodeSubmission, submission_id)
        if submission is None or submission.status in TERMINAL_JUDGE_STATUSES:
            return
        submission.status = JUDGE_FAILED
        submission.compile_message = message
        if submission.kind == "submit":
            _mark_judge_failed(db, submission.attempt_id, submission.problem_id_no)
        db.commit()
    except Exception:
        logger.exception("兜底收尾也失败了：submission_id=%s", submission_id)


def _judge_submission_inner(db: Session, judge, task: JudgeTask, settings) -> None:
    submission = db.get(CodeSubmission, task.submission_id)
    # 已经被 sweep 判死或被重复投递，就别再跑一遍
    if submission is None or submission.status not in ("queued", "judging"):
        return
    try:
        inputs = _judge_inputs(db, submission, task.custom_input, settings)
    except JudgeDataUnavailable as exc:
        # 测试数据读不出来是运维问题（文件被清理脚本误删、磁盘挂了、单点超限），
        # 记 error 级日志带上原因；学员那边与其余系统故障同一口径，见下。
        logger.error("测试数据读取失败 submission=%s：%s", submission.id, exc)
        submission.status = JUDGE_FAILED
        submission.compile_message = "测试数据读取失败，请联系老师。"
        if submission.kind == "submit":
            _mark_judge_failed(db, submission.attempt_id, submission.problem_id_no)
        db.commit()
        return
    if inputs is None:
        submission.status = JUDGE_FAILED
        submission.compile_message = "题目已变更，无法判题，请联系老师。"
        # 这一句原先漏了：只置提交为 failed 而不标记 attempt_answers，交卷判分时
        # 会因为 score 仍是 None 而按"没提交"记 0 分——系统的锅算到了学员头上。
        if submission.kind == "submit":
            _mark_judge_failed(db, submission.attempt_id, submission.problem_id_no)
        db.commit()
        return
    attempt_id, problem_id_no = submission.attempt_id, submission.problem_id_no
    kind, language = submission.kind, submission.language
    code = submission.code
    submission.status = "judging"
    db.commit()  # ← 连接在这里还回池子，下面判题期间不持有

    try:
        result = judge.judge(
            language=language, code=code, cases=inputs["cases"],
            time_limit_ms=inputs["time_limit_ms"], memory_limit_mb=inputs["memory_limit_mb"],
        )
    except JudgeUnavailable as exc:
        submission.status = JUDGE_FAILED
        submission.compile_message = "判题服务暂时不可用，请稍后重试。"
        if kind == "submit":
            _mark_judge_failed(db, attempt_id, problem_id_no)
        logger.warning("判题失败 submission=%s：%s", submission.id, str(exc)[:200])
        db.commit()
        return

    # 判题跑的这几秒里交卷/收卷可能已经把这条提交收编成 judge_failed
    # （_fail_pending_judges）。那就别再改写它——与"已封存的成绩不改"同一口径，
    # 丢一次判题结果比把"未计分"改回"已判分"更糟。会话是 expire_on_commit=False，
    # 必须显式 refresh 才能看到另一个会话（收卷）写入的状态。
    db.refresh(submission)
    if submission.status not in ("queued", "judging"):
        return

    submission.status = result.status
    submission.compile_message = result.compile_message
    submission.time_ms, submission.memory_kb = result.time_ms, result.memory_kb
    submission.detail_json = json.dumps([case._asdict() for case in result.cases], ensure_ascii=False)

    if kind == "submit":
        outcomes = [
            CaseOutcome(passed=case.passed,
                        weight=inputs["weights"][index] if index < len(inputs["weights"]) else 1)
            for index, case in enumerate(result.cases)
        ]
        score, is_correct, score_detail = score_programming(
            outcomes, inputs["full_score"], inputs["score_mode"],
            compile_only=inputs["compile_only"], compiled=result.compiled,
        )
        submission.score = score
        # 判题跑完时学员可能已经交卷了。提交记录照留（那是审计），但成绩不再落——
        # 改一份已经封存的成绩比丢一次提交更糟。服务端在交卷时硬拦 pending 判题
        # （submit_attempt 409），自动封卷走 _fail_pending_judges 收编，所以
        # 走到这里且 attempt 仍 ongoing 时，成绩落库是安全的。
        attempt = db.get(PaperAttempt, attempt_id)
        if attempt is not None and attempt.status == "ongoing":
            saved = db.scalar(
                select(AttemptAnswer).where(AttemptAnswer.attempt_id == attempt_id,
                                            AttemptAnswer.problem_id_no == problem_id_no)
            )
            saved = _upsert_answer(db, attempt_id, problem_id_no, saved)
            previous = parse_answer(saved.answer_json)
            saved.answer_json = json.dumps(
                {
                    "type": "programming",
                    "language": language,
                    "submission_id": submission.id,
                    "draft_code": previous.get("draft_code", submission.code),
                },
                ensure_ascii=False,
            )
            saved.score, saved.is_correct = score, is_correct
            saved.judge_status, saved.judged_at = "judged", utcnow()
            saved.detail_json = json.dumps(score_detail, ensure_ascii=False, sort_keys=True)
    db.commit()


@router.get("/attempts/{attempt_id}/submissions")
def list_submissions(attempt_id: int, problem_id_no: str, request: Request,
                     page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100),
                     user: User = Depends(current_user), db: Session = Depends(db_session)):
    """某一道编程题的提交记录（供「提交记录 (n)」列表与判定详情弹窗用）。

    三条口径不能松：
    1. 只列 kind="submit"。试跑是草稿不是成绩，混进来会让「成绩以最后一次提交为准」失真；
    2. 逐点结果走 _submission_payload 同一套裁剪——feedback_mode 说不给就不给，
       换个接口就能绕过等于没裁；
    3. code 可以下发，因为那是学员自己写的；参考答案、隐藏点内容一个字都不带。
    """
    limit(request, "exam-entry", str(user.id), 120, 60)
    attempt, source, _paper = _attempt_or_404(db, attempt_id, user)
    # 这里不 _seal_if_expired：查历史是只读动作，时间到了也该让人看完自己交过什么。
    filters = (
        CodeSubmission.attempt_id == attempt.id,
        CodeSubmission.problem_id_no == problem_id_no,
        CodeSubmission.kind == "submit",
    )
    total = db.scalar(select(func.count()).select_from(CodeSubmission).where(*filters)) or 0
    rows = db.scalars(
        select(CodeSubmission)
        .where(*filters)
        .order_by(CodeSubmission.id.asc())
        .offset((page - 1) * size).limit(size)
    ).all()
    now = utcnow()
    return {
        "submissions": [{**_submission_payload(row, source, now), "code": row.code} for row in rows],
        "total": total, "page": page, "size": size,
    }


@router.get("/attempts/{attempt_id}/submissions/{submission_id}")
def get_submission(attempt_id: int, submission_id: int, request: Request,
                   user: User = Depends(current_user), db: Session = Depends(db_session)):
    """轮询单条提交的判题进度。

    限流比 exam-judge 松得多：这是个每 250ms 打一次的只读接口，用判题那把尺子量
    会把正常轮询判成攻击。但也不能不限——它带 attempt 归属校验，不限就是免费的探测器。
    """
    limit(request, "exam-poll", str(user.id), 600, 60)
    attempt, source, _paper = _attempt_or_404(db, attempt_id, user)
    submission = db.get(CodeSubmission, submission_id)
    # 别人的提交一律 404，不给"存在但不属于你"这种信息
    if submission is None or submission.attempt_id != attempt.id:
        raise HTTPException(404, "提交记录不存在。")

    payload = _submission_payload(submission, source, utcnow())
    payload["done"] = submission.status in TERMINAL_JUDGE_STATUSES
    if not payload["done"]:
        # 队列位次只是给人看的进度，取不到（比如刚好被别的进程判）就不给这个键
        position = request.app.state.judge_runner.position(judge_key("submission", submission.id))
        if position is not None:
            payload["queue_position"] = position
    return payload


def sweep_stale_judgings(session_factory, stale_seconds: int) -> int:
    """把卡死的判题收尾，返回处理条数。

    什么时候会卡死：进程重启。判题任务活在内存线程池里，进程一没就没了，
    而库里那条记录还停在 queued/judging，前端会一直转圈。

    置 judge_failed 而不是 0 分——这是系统的锅，不能算学员答错（验收手册四级）。
    """
    cutoff = utcnow() - timedelta(seconds=stale_seconds)
    db = session_factory()
    try:
        stale = list(db.scalars(
            select(CodeSubmission).where(
                CodeSubmission.status.in_(["queued", "judging"]),
                CodeSubmission.created_at < cutoff,
            )
        ))
        for submission in stale:
            submission.status = JUDGE_FAILED
            submission.compile_message = "判题未能完成（服务重启），请重新提交。"
            if submission.kind == "submit":
                _mark_judge_failed(db, submission.attempt_id, submission.problem_id_no)
        if stale:
            db.commit()
            logger.warning("清理僵尸判题 %s 条", len(stale))
        return len(stale)
    finally:
        db.close()


def _mark_judge_failed(db: Session, attempt_id: int, problem_id_no: str) -> None:
    """判题服务故障不能算学员 0 分：score 留 null，交卷时跳过这题。"""
    saved = db.scalar(
        select(AttemptAnswer).where(AttemptAnswer.attempt_id == attempt_id,
                                    AttemptAnswer.problem_id_no == problem_id_no)
    )
    saved = _upsert_answer(db, attempt_id, problem_id_no, saved)
    saved.judge_status, saved.score, saved.is_correct = "failed", None, None


@router.post("/attempts/{attempt_id}/submit")
def submit_attempt(attempt_id: int, request: Request, user: User = Depends(current_user),
                   db: Session = Depends(db_session)):
    require_csrf(request)
    limit(request, "exam-submit", str(user.id), 20, 60)
    attempt, _source, paper = _attempt_or_404(db, attempt_id, user)
    if _seal_if_expired(db, request, attempt, paper):
        return {"attempt_id": attempt.id, "submit_kind": attempt.submit_kind, "sealed": True}
    if attempt.status != "ongoing":
        # 幂等：重复交卷是网络重试的常态，不该是 500。
        raise HTTPException(409, "本次作答已交卷。")

    # 有计分判题没跑完就不许交卷：现在封卷，那些题只能按 judge_failed 不计分，
    # 而判题通常一秒内就出结果——拦一下让学员等判完再交，比丢成绩好得多。
    # detail 带 code 是因为前端把"已封卷"的 409 当跳结果页的信号，两种 409 必须可区分。
    # 僵尸提交（进程重启留下的 queued/judging）由 sweep 收编成终态后这里自然放行，
    # 不会把学员永远卡在交卷前。
    pending = sorted({row[0] for row in db.execute(
        select(CodeSubmission.problem_id_no).where(
            CodeSubmission.attempt_id == attempt.id,
            CodeSubmission.kind == "submit",
            CodeSubmission.status.in_(["queued", "judging"]),
        )
    )})
    if pending:
        # 学员认的是卷面序号（第 N 题），不是题库编号（Q000006）。
        order_of = {row.problem_id_no: index for index, row in enumerate(_questions(db, paper.id), start=1)}
        labels = [str(order_of.get(problem_id_no, problem_id_no)) for problem_id_no in pending]
        raise HTTPException(status_code=409, detail={
            "code": "judge_pending",
            "message": f"第 {'、'.join(labels)} 题的判题还没跑完，请稍候几秒再交卷。",
            "problems": pending,
        })

    # warn_unanswered 只是前端的二次确认，服务端不因未作答拒绝交卷。
    _seal(db, attempt, paper, "manual")
    from ..notification_reminders import maybe_publish_result_notification
    maybe_publish_result_notification(
        db, attempt=attempt, paper_title=paper.title,
        source=_source,
    )
    _audit(db, request, "exam_submit", "success", user.id,
           resource_type="paper_attempt", resource_id=attempt.id,
           summary={"paper_id": paper.id, "total_score": attempt.total_score,
                    "duration_seconds": attempt.duration_seconds, "submit_kind": "manual"})
    db.commit()
    return {"attempt_id": attempt.id, "submit_kind": attempt.submit_kind, "sealed": False}


@router.get("/attempts/{attempt_id}/result")
def attempt_result(attempt_id: int, request: Request, user: User = Depends(current_user),
                   db: Session = Depends(db_session)):
    limit(request, "exam-entry", str(user.id), 60, 60)
    attempt, source, paper = _attempt_or_404(db, attempt_id, user)
    _seal_if_expired(db, request, attempt, paper)
    if attempt.status == "ongoing":
        raise HTTPException(409, "本次作答尚未交卷。")

    now = utcnow()
    show_score = _score_visible(source, now)
    show_analysis = _analysis_visible(source, now, submitted=True)
    show_cases = _cases_visible(source, now)

    rows = _questions(db, paper.id)
    problems = _resolve_problems(db, [row.problem_id_no for row in rows])
    saved_map = _answers_by_problem(db, attempt.id)

    questions = []
    for row in rows:
        problem = problems.get(row.problem_id_no)
        saved = saved_map.get(row.problem_id_no)
        item = {"sort_order": row.sort_order, "problem_id_no": row.problem_id_no,
                "full_score": row.score, "missing": problem is None}
        if problem is not None:
            item["type"] = problem.type
            item["stem"] = problem.stem
            # 选项正文与空位标识：结果页要把「我的答案」显示成人话（B. print()），
            # 只给一个孤零零的 "B" 等于让学员回去翻题目。两者都不是判分资产——
            # 学员作答时就看过，is_correct 仍然只跟着 correct 走（受 show_analysis 管）。
            if problem.type in CHOICE_TYPES:
                item["options"] = [{"label": label, "content": content}
                                   for label, content in _option_contents(db, problem)]
            elif problem.type == "fill":
                item["blank_keys"] = [
                    row.blank_key for row in db.scalars(
                        select(FillAnswer).where(FillAnswer.problem_id == problem.id)
                        .order_by(FillAnswer.blank_index)
                    )
                ]
        if saved is not None:
            item["answer"] = parse_answer(saved.answer_json)
            item["judge_status"] = saved.judge_status
        if show_score and saved is not None:
            item["score"] = saved.score
            item["is_correct"] = saved.is_correct
            # detail 必须过 strip_answer_keys：判分明细里带着正确选项 label，
            # 而它受 show_score 管、正确答案受 show_analysis 管——两把闸门错位，
            # 于是 show_analysis=never 的卷子照样从 detail 把答案发了出去
            # （交卷一次读答案、再考一次满分）。答案的唯一出口是下面的 _correct_payload。
            item["detail"] = strip_answer_keys(
                json.loads(saved.detail_json) if saved.detail_json else None
            )
        if show_analysis and problem is not None:
            item["analysis"] = problem.analysis
            item["correct"] = _correct_payload(db, problem)
            if problem.analysis_video_id:
                video = db.get(Video, problem.analysis_video_id)
                item["analysis_video"] = {
                    "available": bool(video and video.status == "ready"),
                    "processing": bool(video and video.status != "ready"),
                    # 播放地址走独立端点再签一次（门控 = 本人 + 已交卷 + show_analysis），
                    # 与课中练习 analysis-play 同一范式，绝不把 video_id 直接下发。
                    "play_path": (
                        f"/api/exam/attempts/{attempt.id}/analysis-play"
                        f"?problem_id_no={row.problem_id_no}"
                    ),
                }
        if problem is not None and problem.type == "programming" and show_cases:
            detail = db.get(ProgrammingDetail, problem.id)
            # 满分条件是计分规则不是判分资产（与作答页同一口径）：结果页的提交详情
            # 要靠它决定渲染测试点网格还是编译横幅，缺了会把编译通过型显示成全错。
            item["programming"] = {"pass_condition": detail.pass_condition if detail else "全测试点通过"}
            last = db.scalar(
                select(CodeSubmission)
                .where(CodeSubmission.attempt_id == attempt.id,
                       CodeSubmission.problem_id_no == row.problem_id_no,
                       CodeSubmission.kind == "submit")
                .order_by(CodeSubmission.id.desc())
            )
            if last:
                # code 是学员自己写的，交卷后理应能回看（与 submissions 接口同一口径）；
                # 测试点内容仍走 _submission_payload 按 feedback_mode 裁剪，不在这破例。
                item["last_submission"] = {**_submission_payload(last, source, now), "code": last.code}
        questions.append(item)

    payload = {
        "attempt": {"id": attempt.id, "attempt_no": attempt.attempt_no, "status": attempt.status,
                    "submitted_at": _iso(attempt.submitted_at), "submit_kind": attempt.submit_kind,
                    "duration_seconds": attempt.duration_seconds},
        "paper": {"title": paper.title, "paper_type": paper.paper_type, "total_score": paper.total_score},
        "show_score": show_score, "show_analysis": show_analysis,
        "leaderboard_enabled": source.leaderboard_enabled,
        "questions": questions, "server_now": _iso(now),
    }
    if show_score:
        payload["attempt"]["total_score"] = attempt.total_score
        if paper.pass_score is not None:
            payload["paper"]["pass_score"] = paper.pass_score
            payload["attempt"]["passed"] = attempt.total_score >= paper.pass_score
    return payload


@router.post("/attempts/{attempt_id}/analysis-play")
def attempt_analysis_play(attempt_id: int, request: Request,
                          problem_id_no: str = Query(min_length=1, max_length=64),
                          user: User = Depends(current_user),
                          db: Session = Depends(db_session)):
    """考试结果页的解析视频播放地址签发。

    门控与结果页逐题可见性**同一套口径**，这里再判一次，不信任前端拿到的
    `play_path` 字符串本身：
    - `_attempt_or_404`：本人卷 + attempt 存在（别人的一律 404，不泄露存在性）；
    - 已交卷（ongoing 直接 409，作答中不给答案类资源）；
    - `_analysis_visible(..., submitted=True)`：与结果页下发 `analysis` 同一个闸门
      （never 不给、after_close 未到不给、after_submit 交卷即给）；
    - 题目存在、确实配了解析视频、视频转码就绪（primary 是 HLS master.m3u8）。

    与课中练习 / scratch 的 analysis-play 同一范式：video_id 永不下发，
    地址只从「本人已交卷 + 解析可见」的上下文里签发。
    """
    require_csrf(request)
    limit(request, "exam-analysis-play", str(user.id), 120, 60)
    attempt, source, paper = _attempt_or_404(db, attempt_id, user)
    _seal_if_expired(db, request, attempt, paper)
    if attempt.status == "ongoing":
        raise HTTPException(409, "本次作答尚未交卷。")
    if not _analysis_visible(source, utcnow(), submitted=True):
        raise HTTPException(403, "本场考试未开放解析。")
    problem = db.scalar(select(Problem).where(Problem.problem_id_no == problem_id_no))
    if problem is None or not problem.analysis_video_id:
        raise HTTPException(404, "该题暂未配置解析视频。")
    video = db.get(Video, problem.analysis_video_id)
    if video is None or video.status != "ready":
        raise HTTPException(404, "解析视频仍在处理中，请稍后再试。")
    primary = db.get(VideoVariant, video.primary_variant_id) if video.primary_variant_id else None
    if (primary is None or primary.status != "ready"
            or not primary.object_key.endswith("master.m3u8")):
        raise HTTPException(404, "解析视频仍在处理中，请稍后再试。")
    variants = db.scalars(
        select(VideoVariant)
        .where(VideoVariant.video_id == video.id, VideoVariant.status == "ready")
        .order_by(VideoVariant.bitrate_kbps.asc())
    ).all()
    settings = request.app.state.settings
    ttl = play_token_minutes(video.duration_seconds, settings.video_token_minutes)
    return build_play_response(settings, video.id, user.id, variants, ttl)


@router.get("/attempts/{attempt_id}/leaderboard")
def attempt_leaderboard(attempt_id: int, request: Request, user: User = Depends(current_user),
                        db: Session = Depends(db_session)):
    """当前作答入口的排行榜：每人取**按 score_policy 算数的那一次**，同分比用时，并列同名次。

    三条口径：
    1. 只在成绩公开时提供——show_score 说不给看分，排行榜就是变相泄分，直接 403；
    2. 只下发名次/用户名/分数/用时，不带任何答题内容。按作答入口聚合：同一张卷
       被投放到不同场次时，各场成绩、姓名和次数彼此隔离；
    3. 代表成绩用 counted_attempt() 选，与候考页同一个函数。这里曾经写死"取最高一次"，
       于是配了 score_policy=last 的链接，候考页说最后一次算数、榜上却按最好成绩排。
       policy 取当前来源的——排行榜是从这场进去看的，用别场的口径解释不通。
    4. 没有公开排名能力的来源（例如课时作业）直接 403。前端不请求只是体验优化，
       服务端能力开关才是隐私边界。
    """
    limit(request, "exam-entry", str(user.id), 60, 60)
    _attempt, source, paper = _attempt_or_404(db, attempt_id, user)
    if not source.leaderboard_enabled:
        raise HTTPException(403, "当前作答入口不提供成绩排名。")
    if not _score_visible(source, utcnow()):
        raise HTTPException(403, "本场考试的成绩暂不公布，暂无排行榜。")

    rows = db.execute(
        select(PaperAttempt, User.username)
        .join(User, User.id == PaperAttempt.user_id)
        .where(*attempt_scope(source), PaperAttempt.status == "submitted")
    ).all()

    FAR = FAR_SECONDS
    by_user: dict[int, list[PaperAttempt]] = {}
    names: dict[int, str] = {}
    for attempt, username in rows:
        by_user.setdefault(attempt.user_id, []).append(attempt)
        names[attempt.user_id] = username

    ranking = []
    for user_id, attempts in by_user.items():
        picked = counted_attempt(attempts, source.score_policy)
        if picked is None:
            continue
        ranking.append({"user_id": user_id, "username": names[user_id],
                        "total_score": picked.total_score, "duration_seconds": picked.duration_seconds})
    ranking.sort(key=lambda item: (-item["total_score"],
                                   item["duration_seconds"] if item["duration_seconds"] is not None else FAR))
    # 并列同名次（1、2、2、4）：跳名次会让学员以为榜单漏了人
    entries, me = [], None
    for index, item in enumerate(ranking):
        rank = entries[-1]["rank"] if index > 0 and item["total_score"] == ranking[index - 1]["total_score"] \
            else index + 1
        entry = {"rank": rank, "username": item["username"],
                 "total_score": item["total_score"], "duration_seconds": item["duration_seconds"]}
        if item["user_id"] == user.id:
            me = entry
        entries.append(entry)

    # 榜只展示前 50，但"我的名次"不受截断影响——自己排第 87 名也该看得见。
    return {"entries": entries[:50], "me": me, "participant_count": len(entries)}


def _correct_payload(db: Session, problem: Problem) -> dict | None:
    """正确答案与解析同门：给解析就给答案，不给解析就整个不出现。
    没有"给答案不给解析"这种组合——那对学员毫无价值。"""
    if problem.type in CHOICE_TYPES:
        return {"labels": [label for label, is_correct in _options_for(db, problem) if is_correct]}
    if problem.type == "fill":
        return {"blanks": [
            {"blank_key": item.blank_key, "answer": item.answer} for item in db.scalars(
                select(FillAnswer).where(FillAnswer.problem_id == problem.id).order_by(FillAnswer.blank_index)
            )
        ]}
    return None
