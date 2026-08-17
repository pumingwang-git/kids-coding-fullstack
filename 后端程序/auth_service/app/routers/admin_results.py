"""后台成绩查看：「组卷 → 发链接 → 看结果」动线的最后一步，全部只读。

三个端点，权限复用试卷域的 _can_read（能看卷的人才能看这场成绩）：

  GET /api/admin/exam-results               跨场次总览，运营 / 成绩统计页用
  GET /api/admin/links/{link_id}/results    单场明细 + 分数分布
  GET /api/admin/attempts/{id}/review       单份答卷逐题回看（含编程题提交与代码）

设计要点：

- 来源可扩展。总览每行带 source 字段，收集器按来源一个函数：
  本期只有 _collect_exam_link_rows（考试链接）；课包作业（lesson）与练一练
  （practice）落地时各追加一个收集器、返回同一套行 DTO 即可并入总览。
  练一练是自由练习，没有"应到/已交"概念，任务型字段对它置 null，前端显示 "—"。
- 没有"未交"口径。链接是谁拿到谁能考（无名单），系统只知道谁来考过，
  不知道谁该来——明细按作答记录列，"谁没交"要等名单/班级做了才有。
- 只读不审计。看成绩是老师的日常动作，不是越界取用；对照 reveal-url 每次必审，
  是因为取用完整地址等于把考试入口交出去，性质不同。
- 单次作答可能有 judge_failed 的题（score 留 null 不计分）：明细与回看都必须把
  "判题异常"和"答错的 0 分"区分开，前者是系统口径，不能当学员表现展示。
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..attempt_source import SOURCE_LESSON_HOMEWORK, attempt_scope, from_lesson_homework
from ..lesson_homework_kinds import (
    HomeworkFilters,
    collect_rows,
    columns_for,
    filters_for,
    kind_for_block,
    kinds_meta,
    paper_context,
    stats_for,
    tree_for,
)
from ..models import (
    AdminUser,
    AttemptAnswer,
    ChoiceOption,
    CodeSubmission,
    Course,
    CourseLesson,
    CourseLessonBlock,
    CourseSection,
    ExamLink,
    FillAnswer,
    LessonPaperBlock,
    Paper,
    PaperAttempt,
    PaperQuestion,
    Problem,
    User,
)
from ..permissions import is_reviewer
from ..results_common import (
    build_item_analysis,
    build_students,
    build_summary,
    counted_scores as _counted_scores,
    distribution_of,
    full_score,
    attempts_by_user as _attempts_by_user,
    score_summary as _score_summary,
)
from ..scoring import parse_answer, parse_blank_alternatives
from .admin_auth import client_ip, current_admin, db_session, limit
from .admin_papers import _as_utc, _can_read, _link_phase

# 「哪一次算数」全系统只有这一个解释处。后台若自己写死"取最高一次"，配了
# score_policy=last 的场次就会出现：老师看到 92 分、学员端候考页和排行榜按 78 分算。
from .exam import counted_attempt

router = APIRouter(prefix="/api/admin", tags=["admin-results"])

def _iso(value: datetime | None) -> str | None:
    aware = _as_utc(value) if value is not None else None
    return aware.isoformat() if aware else None


def _sees_all(admin: AdminUser) -> bool:
    """与 _can_read 的 SQL 版：超管与审核员看全部，其余只看自己录入/负责的卷。"""
    return is_reviewer(admin)


def _full_score(db: Session, paper_id: int) -> int:
    return full_score(db, paper_id)


# 统计口径（每人一次代表作答、分布桶数、判题异常剔除）收敛在 results_common.py，
# 考试链接与课时作业共用同一套实现——两个来源的页面对着的数字必须一致。
# 这里只保留本地再包装：名字带下划线是历史约定，import 别名见文件头。


# ==================== 来源收集器 ====================


def _collect_exam_link_rows(db: Session, admin: AdminUser, *,
                            keyword: str, paper_type: str, subject: str) -> list[dict]:
    """考试链接来源的总览行。课包作业 / 练一练落地时按这个 DTO 形状各加一个收集器。"""
    query = (
        select(ExamLink, Paper)
        .join(Paper, Paper.id == ExamLink.paper_id)
        .order_by(ExamLink.id.desc())
    )
    if not _sees_all(admin):
        query = query.where((Paper.owner_id == admin.id) | (Paper.created_by == admin.id))
    if paper_type:
        query = query.where(Paper.paper_type == paper_type)
    if subject:
        query = query.where(Paper.subject == subject)
    if keyword:
        like = f"%{keyword}%"
        query = query.where(
            (ExamLink.name.like(like)) | (Paper.title.like(like)) | (Paper.paper_id_no.like(like))
        )

    now = datetime.now(UTC)
    rows = []
    for link, paper in db.execute(query).all():
        attempts = list(db.scalars(
            select(PaperAttempt).where(PaperAttempt.exam_link_id == link.id)
        ))
        by_user = _attempts_by_user(attempts)
        submitted_attempts = [a for a in attempts if a.status == "submitted"]
        # 人数与人次分开报。练习卷允许反复作答，一个学员考 100 次时
        # "参考 1 人 / 作答 100 次"才是真相；只给人次会让运营以为来了 100 个人。
        rows.append({
            "source": "exam_link",
            "link": {"id": link.id, "name": link.name, "status": link.status,
                     "phase": _link_phase(link, now), "score_policy": link.score_policy},
            "paper": {"id": paper.id, "paper_id_no": paper.paper_id_no, "title": paper.title,
                      "paper_type": paper.paper_type, "subject": paper.subject},
            "full_score": _full_score(db, paper.id),
            "pass_score": paper.pass_score,
            "participants": len(by_user),
            "submitted_participants": len({a.user_id for a in submitted_attempts}),
            "attempts": len(attempts),
            "submitted": len(submitted_attempts),
            "ongoing": len(attempts) - len(submitted_attempts),
            # 汇总按"每人一个代表成绩"算，不是按人次——理由见 _counted_scores
            "score": _score_summary(_counted_scores(attempts, link.score_policy), paper.pass_score),
        })
    return rows


def _homework_kind_or_404(db: Session, block_id: int):
    """块 → 作业类型。**成绩链路唯一的类型分派点**，等价于 attempt_source 的工厂。

    注册表不认识的块（markdown/video/…）在这里就是「课时作业不存在」，不是
    「暂不支持」——它本来就不是一份作业。
    """
    kind = kind_for_block(db, block_id)
    if kind is None:
        raise HTTPException(404, "课时作业不存在。")
    return kind


def _dispatch(call, *args):
    """把注册表抛出的领域异常翻成 HTTP。类型自己不认识 FastAPI，也不该认识。"""
    try:
        return call(*args)
    except PermissionError as error:
        raise HTTPException(403, str(error)) from error
    except LookupError as error:
        raise HTTPException(404, str(error)) from error


def _paper_context_or_404(db: Session, block_id: int, admin: AdminUser):
    """逐题分析只对整卷作业成立（Scratch 没有题目），故不走通用分派。"""
    context = _dispatch(paper_context, db, block_id, admin)
    if context is None:
        raise HTTPException(404, "课时作业不存在。")
    return context


# ==================== 端点 ====================


@router.get("/exam-results")
def list_exam_results(request: Request, keyword: str = "", paper_type: str = "",
                      subject: str = "", source: str = "",
                      page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100),
                      db: Session = Depends(db_session)):
    """跨场次总览。source 为空 = 全部已实现的来源；未知的来源值是 422 不是空列表。"""
    admin = current_admin(request, db)
    limit(request, "admin-results", client_ip(request), 60, 60)
    known_sources = {"exam_link"}  # lesson / practice 落地时加进来
    if source and source not in known_sources:
        raise HTTPException(422, f"未知的成绩来源：{source}")

    rows = []
    if source in ("", "exam_link"):
        rows += _collect_exam_link_rows(db, admin, keyword=keyword, paper_type=paper_type,
                                        subject=subject)
    rows.sort(key=lambda row: row["link"]["id"], reverse=True)
    total = len(rows)
    return {"items": rows[(page - 1) * size: page * size], "total": total,
            "page": page, "size": size}


@router.get("/lesson-homework-results")
def list_lesson_homework_results(request: Request, keyword: str = "", paper_type: str = "",
                                 subject: str = "", course_id: int | None = None,
                                 section_id: int | None = None, lesson_id: int | None = None,
                                 kind: str = "", status: str = "",
                                 page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100),
                                 db: Session = Depends(db_session)):
    """课时作业成绩总览：整卷作业与 Scratch 作业同表，行由类型注册表收集。

    **筛选全部在服务端**（关键词、类型、状态、目录）。原来关键词与状态是前端在
    本页数据里过滤的，翻页一到第二页就只筛得到当前这一页——分页与筛选分处两端，
    结果必然对不上。

    响应里的 `columns` / `stats` / `filters` / `kinds` 是**呈现契约**：页面按它
    生成表头、统计卡和下拉框，因此前端不持有任何作业类型的业务白名单。
    """
    admin = current_admin(request, db)
    limit(request, "admin-results", client_ip(request), 60, 60)
    if kind and kind not in {meta["key"] for meta in kinds_meta()}:
        raise HTTPException(422, f"未知的作业类型：{kind}")
    filters = HomeworkFilters(keyword=keyword, course_id=course_id, section_id=section_id,
                              lesson_id=lesson_id, kind=kind, status=status,
                              paper_type=paper_type, subject=subject)
    rows, _used = collect_rows(db, admin, filters)
    return {
        "items": rows[(page - 1) * size: page * size],
        "total": len(rows), "page": page, "size": size,
        "tree": tree_for(rows),
        "kinds": kinds_meta(),
        "columns": columns_for(rows),
        "stats": stats_for(rows),
        "filters": filters_for(rows),
        "server_now": datetime.now(UTC).isoformat(),
    }


@router.get("/lesson-homework/{block_id}/results")
def lesson_homework_results(block_id: int, request: Request,
                            db: Session = Depends(db_session)):
    """单份课时作业成绩详情。哪一种作业由块类型决定，路由不认识具体类型。"""
    admin = current_admin(request, db)
    limit(request, "admin-results", client_ip(request), 60, 60)
    kind = _homework_kind_or_404(db, block_id)
    payload = _dispatch(kind.detail, db, admin, block_id)
    return {**payload,
            "columns": [column.as_dict() for column in kind.detail_columns],
            "insight": kind.insight,
            "empty_hint": kind.empty_hint,
            "server_now": datetime.now(UTC).isoformat()}


@router.get("/lesson-homework/{block_id}/students/{user_id}/attempts")
def lesson_homework_student_attempts(block_id: int, user_id: int, request: Request,
                                    db: Session = Depends(db_session)):
    """按需返回一位学员在这份作业上的全部记录，避免详情页为每人预传历史。"""
    admin = current_admin(request, db)
    limit(request, "admin-results", client_ip(request), 60, 60)
    kind = _homework_kind_or_404(db, block_id)
    return _dispatch(kind.student_history, db, admin, block_id, user_id)


@router.get("/lesson-homework/{block_id}/records/{record_id}")
def lesson_homework_record(block_id: int, record_id: int, request: Request,
                           db: Session = Depends(db_session)):
    """一条作答记录的只读详情（字段成对下发）。

    整卷作业的答卷回看有自己的富文本回看端点（/attempts/{id}/review），因此
    `record` 只由需要它的类型声明；没声明的类型这里是 404，不是空壳弹窗。
    """
    admin = current_admin(request, db)
    limit(request, "admin-results", client_ip(request), 60, 60)
    kind = _homework_kind_or_404(db, block_id)
    if kind.record is None:
        raise HTTPException(404, "该作业类型没有可单独查看的记录详情。")
    return _dispatch(kind.record, db, admin, block_id, record_id)


@router.get("/lesson-homework/{block_id}/item-analysis")
def lesson_homework_item_analysis(block_id: int, request: Request,
                                  db: Session = Depends(db_session)):
    """课时作业逐题分析。只对整卷作业成立：Scratch 作业没有题目可逐题看。"""
    admin = current_admin(request, db)
    limit(request, "admin-results", client_ip(request), 60, 60)
    block, detail, paper, lesson, section, course = _paper_context_or_404(db, block_id, admin)
    source = from_lesson_homework(block, detail)
    attempts = list(db.scalars(select(PaperAttempt).where(*attempt_scope(source))))
    grouping, items = build_item_analysis(db, paper, attempts, source.score_policy)
    return {
        "source": source.source_type, "source_id": block.id,
        "course": {"id": course.id, "title": course.title},
        "section": {"id": section.id, "title": section.title},
        "lesson": {"id": lesson.id, "title": lesson.title},
        "homework": {"id": block.id, "title": block.title},
        "paper": {"id": paper.id, "paper_id_no": paper.paper_id_no, "title": paper.title,
                  "paper_type": paper.paper_type, "subject": paper.subject},
        "grouping": grouping,
        "items": items,
    }


@router.get("/links/{link_id}/results")
def link_results(link_id: int, request: Request, db: Session = Depends(db_session)):
    """单场明细：汇总 + 分数分布 + **每学员一行**，行内挂该学员的全部作答历史。

    为什么不是"每次作答一行"（原实现）：练习卷允许反复作答，一个学员练 100 次就占
    100 行，运营看到的"开考 100"其实是 1 个人。老师要看的是"这个班每个人考得怎么样"，
    需要翻历史时再展开。

    代表成绩由 counted_attempt() 按**本条链接的 score_policy** 选，与学员端候考页、
    排行榜同一个函数——三处口径必须一致，否则老师和学员对着不同的分数说话。
    """
    admin = current_admin(request, db)
    limit(request, "admin-results", client_ip(request), 60, 60)
    link = db.get(ExamLink, link_id)
    paper = db.get(Paper, link.paper_id) if link else None
    if not link or not paper:
        raise HTTPException(404, "考试链接不存在。")
    if not _can_read(paper, admin):
        raise HTTPException(403, "没有查看该场成绩的权限。")

    attempts = list(db.scalars(
        select(PaperAttempt).where(PaperAttempt.exam_link_id == link.id)
        .order_by(PaperAttempt.started_at.desc(), PaperAttempt.id.desc())
    ))

    full = _full_score(db, paper.id)
    students = build_students(db, attempts, link.score_policy)
    # 汇总与分布都按"每人一个代表成绩"算。按人次算的话，一个人练 100 次
    # 就把平均分和分布图整个带成他一个人的形状（这正是本次要修的口径问题）。
    summary = build_summary(attempts, link.score_policy, paper.pass_score,
                            participants=len(students))
    # 分布：桶数随人数走，不是固定 10 个。满分 0 的卷没有分布意义。
    distribution = distribution_of(_counted_scores(attempts, link.score_policy), full)

    return {
        "link": {"id": link.id, "name": link.name, "status": link.status,
                 "phase": _link_phase(link, datetime.now(UTC)),
                 # 前端要靠它标明「本场按最好/最后/首次成绩计分」，不许自己假设
                 "score_policy": link.score_policy,
                 # 「用时 × 分数」视图拿它画限时参考线。不给的话前端只能按实际最大用时
                 # 定标尺，于是"几乎所有人都用满了"会看起来像"大家都很宽裕"。
                 "duration_minutes": link.duration_minutes},
        "paper": {"id": paper.id, "paper_id_no": paper.paper_id_no, "title": paper.title,
                  "paper_type": paper.paper_type, "subject": paper.subject},
        "full_score": full,
        "pass_score": paper.pass_score,
        "summary": summary,
        "distribution": distribution,
        "students": students,
    }


# 高低分组取总分排序的前 / 后 27%。这是教育测量学里的经典分组（Kelley 1939）：
# 正态分布下它让区分度这个统计量的方差最小，比"前后各一半"更稳、比"前后 10%"样本更足。
# 区分度稳不稳由**每组人数 k** 决定，不是总人数。前 / 后 27% 分组时 k ≈ 0.27n，
# 而单个学员对 D 的影响是 1/k：
#     k=2（n≈7）  ±0.50 ← 这不是统计量，是噪声
#     k=5（n≈19） ±0.32   下限，只够看方向
#     k=10（n≈37）±0.22   开始可信
# 所以两道门槛：20 人以下不给分组数据；20–36 人给，但标成参考值。
# 阈值与怀疑信号（negative_discrimination / all_low）的推导见 results_common.py，
# 考试链接与课时作业共用同一份实现，这里保留历史常量名供前端阈值对照。
GROUP_RATIO = 0.27
ITEM_ANALYSIS_MIN_PARTICIPANTS = 20
ITEM_ANALYSIS_STABLE_PARTICIPANTS = 37
# 直方图的下限。低于它前端画点带图（一人一个点）而不是直方图——8 个人的成绩，
# 逐点画比任何直方图都清楚，而"样本过少暂不展示"对老师是个坏答复：他有 8 个真实成绩想看。
DISTRIBUTION_MIN_PEOPLE = 12


@router.get("/links/{link_id}/item-analysis")
def link_item_analysis(link_id: int, request: Request, db: Session = Depends(db_session)):
    """逐题分析：得分率 + 高低分组区分度。前端「逐题得分率」与「题目诊断」两个视图共用。

    单开一个端点而不是并进 /results：这份聚合要把一场所有 attempt_answers 按题分组，
    比 /results 明显贵，而它只在老师点开「题目分析」时才需要——挂在 /results 上等于
    每次打开成绩页都为多数人不看的东西付钱。

    与 /results 必须一致的两条口径（改之前先读 results_common.counted_attempts 的文档字符串）：
      1. 只统计**代表作答**，一人一次；
      2. `judge_status == "failed"` 的答题从分母剔除、另计 judge_failed——
         把系统故障算进得分率，等于把判题挂了说成学生不会。

    `suspect` 是给老师的质检信号，不是评价学生：
      - `negative_discrimination`：低分组得分率**高于**高分组。统计上几乎不可能是巧合，
        基本就是答案配错了（选项 is_correct 配反、填空 alternatives 漏配一种写法）。
      - `all_low`：得分率极低且高分组也没做对——先查题，再谈讲评。
    """
    admin = current_admin(request, db)
    limit(request, "admin-results", client_ip(request), 60, 60)
    link = db.get(ExamLink, link_id)
    paper = db.get(Paper, link.paper_id) if link else None
    if not link or not paper:
        raise HTTPException(404, "考试链接不存在。")
    if not _can_read(paper, admin):
        raise HTTPException(403, "没有查看该场成绩的权限。")

    attempts = list(db.scalars(
        select(PaperAttempt).where(PaperAttempt.exam_link_id == link.id)))
    grouping, items = build_item_analysis(db, paper, attempts, link.score_policy)

    return {
        "link": {"id": link.id, "name": link.name, "score_policy": link.score_policy},
        "grouping": grouping,
        "items": items,
    }


@router.get("/attempts/{attempt_id}/review")
def attempt_review(attempt_id: int, request: Request, db: Session = Depends(db_session)):
    """单份答卷逐题回看。管理员本就能 preview 整卷答案，所以这里不下发限制：
    正确答案、学员答案、编程题代码与逐测试点结果全给——这是老师复核成绩的工作台。"""
    admin = current_admin(request, db)
    limit(request, "admin-results", client_ip(request), 60, 60)
    attempt = db.get(PaperAttempt, attempt_id)
    paper = db.get(Paper, attempt.paper_id) if attempt else None
    if not attempt or not paper:
        raise HTTPException(404, "作答记录不存在。")
    if attempt.source_type == SOURCE_LESSON_HOMEWORK:
        # 课时作业的答卷额外受课包侧范围约束，口径与作业成绩页同一处实现。
        _paper_context_or_404(db, attempt.source_id, admin)
    elif not _can_read(paper, admin):
        raise HTTPException(403, "没有查看该份答卷的权限。")

    rows = list(db.scalars(
        select(PaperQuestion).where(PaperQuestion.paper_id == paper.id)
        .order_by(PaperQuestion.sort_order, PaperQuestion.id)
    ))
    problems = {p.problem_id_no: p for p in db.scalars(
        select(Problem).where(Problem.problem_id_no.in_([r.problem_id_no for r in rows]))
    ) if p.problem_id_no} if rows else {}
    saved_map = {a.problem_id_no: a for a in db.scalars(
        select(AttemptAnswer).where(AttemptAnswer.attempt_id == attempt.id)
    )}

    questions = []
    for index, row in enumerate(rows, start=1):
        problem = problems.get(row.problem_id_no)
        saved = saved_map.get(row.problem_id_no)
        answer = parse_answer(saved.answer_json) if saved else {}
        item = {
            "sort_order": index,
            "problem_id_no": row.problem_id_no,
            "full_score": row.score,
            "missing": problem is None,
            "answer": answer,
            "score": saved.score if saved else None,
            "is_correct": saved.is_correct if saved else None,
            "judge_status": saved.judge_status if saved else "pending",
            "detail": json.loads(saved.detail_json) if saved and saved.detail_json else None,
        }
        if problem is not None:
            item["type"] = problem.type
            item["stem"] = problem.stem
            if problem.type in ("choice", "multi_choice", "judge"):
                item["options"] = [
                    {"option_label": o.option_label, "content": o.content, "is_correct": o.is_correct}
                    for o in db.scalars(
                        select(ChoiceOption).where(ChoiceOption.problem_id == problem.id)
                        .order_by(ChoiceOption.sort_order, ChoiceOption.id)
                    )
                ]
            elif problem.type == "fill":
                item["blanks"] = [
                    {"blank_key": b.blank_key,
                     "answers": [b.answer, *parse_blank_alternatives(b.alternatives_json)]}
                    for b in db.scalars(
                        select(FillAnswer).where(FillAnswer.problem_id == problem.id)
                        .order_by(FillAnswer.blank_index)
                    )
                ]
            elif problem.type == "programming":
                # 只给 kind="submit" 的计分提交，与学员端「提交记录」同口径
                item["submissions"] = [{
                    "id": s.id, "language": s.language, "status": s.status,
                    "score": s.score, "time_ms": s.time_ms, "memory_kb": s.memory_kb,
                    "compile_message": s.compile_message,
                    "detail": json.loads(s.detail_json) if s.detail_json else None,
                    "code": s.code, "created_at": _iso(s.created_at),
                } for s in db.scalars(
                    select(CodeSubmission).where(
                        CodeSubmission.attempt_id == attempt.id,
                        CodeSubmission.problem_id_no == row.problem_id_no,
                        CodeSubmission.kind == "submit")
                    .order_by(CodeSubmission.id)
                )]
        questions.append(item)

    user = db.get(User, attempt.user_id)
    return {
        "attempt": {
            "id": attempt.id, "attempt_no": attempt.attempt_no, "status": attempt.status,
            "total_score": attempt.total_score if attempt.status == "submitted" else None,
            "duration_seconds": attempt.duration_seconds, "submit_kind": attempt.submit_kind,
            "started_at": _iso(attempt.started_at), "submitted_at": _iso(attempt.submitted_at),
        },
        "user": {"id": attempt.user_id, "username": user.username if user else "已注销"},
        "paper": {"id": paper.id, "paper_id_no": paper.paper_id_no, "title": paper.title,
                  "paper_type": paper.paper_type, "subject": paper.subject},
        "full_score": _full_score(db, paper.id),
        "pass_score": paper.pass_score,
        "questions": questions,
    }
