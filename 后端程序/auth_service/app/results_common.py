"""后台成绩统计的通用聚合层（admin_results / 课时作业成绩共用）。

**为什么拆这一层**：考试链接成绩（admin_results.py）与课时作业成绩共用同一套
统计口径——「每人一次代表作答」算平均分与及格率、分布桶数随人数走、逐题分析
按前/后 27% 分组、判题异常从得分率分母剔除。把口径收敛在**一个文件**里，
两个来源的页面对着的数字才能对得上（任务 19 设计文档第六节）。

本模块不含任何来源概念：函数只吃 (attempts, score_policy, paper) 这类
与来源无关的输入。来源差异（怎么查 attempts、权限怎么验、路径怎么显示）
留在各自的路由层，用 `attempt_source.attempt_scope` 收敛查询条件。
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from sqlalchemy import func

from .models import AttemptAnswer, Paper, PaperAttempt, PaperQuestion, User
from .routers.exam import counted_attempt


def full_score(db: Session, paper_id: int) -> int:
    """卷面满分 = 题目分值之和。放这一层是因为课时作业、考试链接和逐题分析
    都要用它做分母，各自 `select(sum(score))` 一遍迟早写出三个口径。"""
    return db.scalar(
        select(func.coalesce(func.sum(PaperQuestion.score), 0))
        .where(PaperQuestion.paper_id == paper_id)
    ) or 0


def _iso(value: datetime | None) -> str | None:
    """时间统一按 UTC 解释再输出（与 admin_results._iso 同口径）。

    SQLite 的 DateTime(timezone=True) 读回是无时区值（写入时已归一到 UTC），
    直接 isoformat() 会丢 Z 后缀、且和带时区的 now 比较会炸。
    """
    if value is None:
        return None
    aware = value if value.tzinfo else value.replace(tzinfo=UTC)
    return aware.isoformat()


def attempts_by_user(attempts: list[PaperAttempt]) -> dict[int, list[PaperAttempt]]:
    grouped: dict[int, list[PaperAttempt]] = {}
    for attempt in attempts:
        grouped.setdefault(attempt.user_id, []).append(attempt)
    return grouped


def counted_attempts(attempts: list[PaperAttempt], score_policy: str) -> list[PaperAttempt]:
    """每个学员「算数的那一次」，**一人一条**。与学员端候考页、排行榜同一函数。

    汇总、分布、逐题分析必须站在**同一批**作答上：任何一处自己重新挑一遍，
    老师就会看到"分布图 28 人、逐题分析 100 人次"这种对不上的数。
    """
    picked = []
    for user_attempts in attempts_by_user(attempts).values():
        one = counted_attempt(user_attempts, score_policy)
        if one is not None:
            picked.append(one)
    return picked


def counted_scores(attempts: list[PaperAttempt], score_policy: str) -> list[int]:
    return [a.total_score for a in counted_attempts(attempts, score_policy)]


def score_summary(scores: list[int], pass_score: int | None) -> dict | None:
    """已交卷总分的汇总；pass_score 为空的卷没有及格率口径。"""
    if not scores:
        return None
    return {
        "avg": round(sum(scores) / len(scores)),
        "min": min(scores),
        "max": max(scores),
        "pass_rate": (
            round(len([s for s in scores if s >= pass_score]) / len(scores) * 100)
            if pass_score is not None else None
        ),
    }


def distribution_bins(people: int) -> int:
    """直方图分几个桶。**跟着人数走，不是写死 10 个。**（见 admin_results 同注释）"""
    return max(4, min(10, round(people ** 0.5)))


def distribution_of(scores: list[int], full_score: int) -> list[dict]:
    """分数分布：桶数随人数走，满分 0 的卷没有分布意义。"""
    if full_score <= 0:
        return []
    bins = distribution_bins(len(scores))
    buckets = [0] * bins
    for score in scores:
        buckets[min(int(score / full_score * bins), bins - 1)] += 1
    step = full_score / bins
    return [{"range": f"{round(i * step)}–{round((i + 1) * step)}", "count": count}
            for i, count in enumerate(buckets)]


def judge_failed_attempt_ids(db: Session, attempts: list[PaperAttempt]) -> set[int]:
    """哪些作答里有判题异常的题（score 留 null 的那批），明细行要打标。"""
    if not attempts:
        return set()
    return set(db.scalars(
        select(AttemptAnswer.attempt_id).where(
            AttemptAnswer.attempt_id.in_([a.id for a in attempts]),
            AttemptAnswer.judge_status == "failed")
    ).all())


def users_of(db: Session, attempts: list[PaperAttempt]) -> dict[int, User]:
    if not attempts:
        return {}
    return {u.id: u for u in db.scalars(
        select(User).where(User.id.in_({a.user_id for a in attempts})))}


def build_summary(attempts: list[PaperAttempt], score_policy: str,
                  pass_score: int | None, participants: int) -> dict:
    """汇总卡片。avg/pass_rate 的分母是人数（每人一次代表作答），不是人次。"""
    scores = counted_scores(attempts, score_policy)
    summary = score_summary(scores, pass_score) or {"avg": None, "min": None,
                                                    "max": None, "pass_rate": None}
    submitted_attempts = [a for a in attempts if a.status == "submitted"]
    return {
        **summary,
        "participants": participants,
        "submitted_participants": len(scores),
        "attempts": len(attempts),
        "submitted_attempts": len(submitted_attempts),
        "ongoing_attempts": len(attempts) - len(submitted_attempts),
    }


def build_students(db: Session, attempts: list[PaperAttempt], score_policy: str,
                   *, include_history: bool = True) -> list[dict]:
    """每学员一行，行内挂该学员的全部作答历史。

    为什么不是"每次作答一行"：练习卷/作业允许反复作答，一个学员刷 100 次就占
    100 行。老师要看的是"每个人怎么样"，需要翻历史时再展开。

    代表成绩由 counted_attempt() 按本来源的 score_policy 选，与学员端同一个函数。
    """
    failed_ids = judge_failed_attempt_ids(db, attempts)
    users = users_of(db, attempts)

    def attempt_row(attempt: PaperAttempt) -> dict:
        return {
            "attempt_id": attempt.id,
            "attempt_no": attempt.attempt_no,
            "status": attempt.status,
            "total_score": attempt.total_score if attempt.status == "submitted" else None,
            "duration_seconds": attempt.duration_seconds,
            "submit_kind": attempt.submit_kind,
            "started_at": _iso(attempt.started_at),
            "submitted_at": _iso(attempt.submitted_at),
            "has_judge_failed": attempt.id in failed_ids,
        }

    students = []
    for user_id, user_attempts in attempts_by_user(attempts).items():
        history = sorted(user_attempts, key=lambda a: (a.started_at, a.id))
        counted = counted_attempt(history, score_policy)
        students.append({
            "user": {"id": user_id,
                     "username": users[user_id].username if user_id in users else "已注销"},
            "counted": attempt_row(counted) if counted is not None else None,
            "attempt_count": len(history),
            "submitted_count": len([a for a in history if a.status == "submitted"]),
            "ongoing": any(a.status == "ongoing" for a in history),
            "has_judge_failed": any(a.id in failed_ids for a in history),
            **({"attempts": [attempt_row(a) for a in history]} if include_history else {}),
        })
    # 有成绩的按代表成绩降序，没交过卷的（只有进行中）沉底
    students.sort(key=lambda s: (s["counted"] is None,
                                 -(s["counted"]["total_score"] if s["counted"] else 0)))
    return students


# ==================== 逐题分析（题目诊断） ====================
#
# 高低分组取总分排序的前 / 后 27%。这是教育测量学里的经典分组（Kelley 1939）：
# 正态分布下它让区分度这个统计量的方差最小，比"前后各一半"更稳、比"前后 10%"样本更足。
# 阈值与怀疑信号判据的推导见 admin_results.py 同名常量注释，本模块只搬口径不另定。
GROUP_RATIO = 0.27
ITEM_ANALYSIS_MIN_PARTICIPANTS = 20
ITEM_ANALYSIS_STABLE_PARTICIPANTS = 37
SUSPECT_NEGATIVE_D = -0.2
SUSPECT_LOW_GROUP_FLOOR = 0.5
SUSPECT_ALL_LOW_RATE = 0.2
SUSPECT_ALL_LOW_HIGH_GROUP = 0.4


def suspect_flag(score_rate: float | None, high_rate: float | None,
                 low_rate: float | None, discrimination: float | None) -> str | None:
    """这道题要不要提示老师"先查题、再讲评"（推导见 admin_results 同名函数注释）。"""
    if (discrimination is not None and discrimination <= SUSPECT_NEGATIVE_D
            and low_rate is not None and low_rate >= SUSPECT_LOW_GROUP_FLOOR):
        return "negative_discrimination"
    if (score_rate is not None and score_rate < SUSPECT_ALL_LOW_RATE
            and (high_rate is None or high_rate < SUSPECT_ALL_LOW_HIGH_GROUP)):
        return "all_low"
    return None


def build_item_analysis(db: Session, paper: Paper, attempts: list[PaperAttempt],
                        score_policy: str) -> tuple[dict, list[dict]]:
    """逐题得分率 + 高低分组区分度。返回 (grouping, items)。

    与成绩详情必须一致的两条口径（改之前先读 counted_attempts 的文档字符串）：
      1. 只统计**代表作答**，一人一次；
      2. `judge_status == "failed"` 的答题从分母剔除、另计 judge_failed——
         把系统故障算进得分率，等于把判题挂了说成学生不会。
    """
    from .models import PaperQuestion, Problem

    counted = counted_attempts(attempts, score_policy)
    counted.sort(key=lambda a: a.total_score, reverse=True)
    group_size = int(len(counted) * GROUP_RATIO) or (1 if counted else 0)
    grouped = len(counted) >= ITEM_ANALYSIS_MIN_PARTICIPANTS
    high_ids = {a.id for a in counted[:group_size]} if grouped else set()
    low_ids = {a.id for a in counted[-group_size:]} if grouped else set()

    rows = list(db.scalars(
        select(PaperQuestion).where(PaperQuestion.paper_id == paper.id)
        .order_by(PaperQuestion.sort_order, PaperQuestion.id)))
    problems = {p.problem_id_no: p for p in db.scalars(
        select(Problem).where(Problem.problem_id_no.in_([r.problem_id_no for r in rows]))
    ) if p.problem_id_no} if rows else {}
    answers = list(db.scalars(
        select(AttemptAnswer).where(AttemptAnswer.attempt_id.in_({a.id for a in counted}))
    )) if counted else []
    by_problem: dict[str, list[AttemptAnswer]] = {}
    for answer in answers:
        by_problem.setdefault(answer.problem_id_no, []).append(answer)

    def rate(subset: list[AttemptAnswer], full: int) -> float | None:
        """一批答题的得分率。用得分而不是对错：编程题、多选题拿部分分是常态。"""
        if not subset or full <= 0:
            return None
        return round(sum(a.score or 0 for a in subset) / (len(subset) * full), 4)

    items = []
    for index, row in enumerate(rows, start=1):
        problem = problems.get(row.problem_id_no)
        graded = [a for a in by_problem.get(row.problem_id_no, []) if a.judge_status != "failed"]
        failed = len(by_problem.get(row.problem_id_no, [])) - len(graded)
        score_rate = rate(graded, row.score)
        high_rate = rate([a for a in graded if a.attempt_id in high_ids], row.score) if grouped else None
        low_rate = rate([a for a in graded if a.attempt_id in low_ids], row.score) if grouped else None
        discrimination = (round(high_rate - low_rate, 4)
                          if high_rate is not None and low_rate is not None else None)
        items.append({
            "sort_order": index,
            "problem_id_no": row.problem_id_no,
            "full_score": row.score,
            "type": problem.type if problem else None,
            "title": (problem.title or "")[:60] if problem else "",
            "missing": problem is None,
            "answered": len(graded),
            "judge_failed": failed,
            "score_rate": score_rate,
            "high_rate": high_rate,
            "low_rate": low_rate,
            "discrimination": discrimination,
            "suspect": suspect_flag(score_rate, high_rate, low_rate, discrimination),
        })

    grouping = {
        "enabled": grouped,
        "stable": len(counted) >= ITEM_ANALYSIS_STABLE_PARTICIPANTS,
        "group_size": group_size if grouped else 0,
        "participants": len(counted),
        "min_participants": ITEM_ANALYSIS_MIN_PARTICIPANTS,
        "stable_participants": ITEM_ANALYSIS_STABLE_PARTICIPANTS,
    }
    return grouping, items
