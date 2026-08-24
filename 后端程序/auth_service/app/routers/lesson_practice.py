"""课中练习：单题取题与作答（交接文档 15 第三节 · 形态 A「块内直答」）。

单独一个 router 而不是塞进 courses.py：那边已经 700+ 行，且职责是"浏览"（列表/目录/
课时正文/资料流）；这里是"作答"，有判分、计次、写完成记录三件事，混在一起没人找得到。

**三条红线**

1. **答案与解析绝不随取题下发**。`GET …/problem` 只给题干与选项正文，判定与解析只在
   `POST …/answer` 的响应里出现，且 `show_analysis=false` 时永不出现。照抄考试体系
   「答案零下发」的回归传统（test_exam.py 的 walk_keys 递归断言）。
2. **不下发 `problem_id_no`**。延续 courses.py 的保密口径：学生端只拿 block_id，
   拿不到题目在题库里的身份，否则可以拿它去别处捞题。
3. **判分只用 app/scoring.py**。那是纯函数模块（不认 attempt、不认试卷），
   与考试页判的是同一套逻辑；这里绝不另写一份判分。

**门控**：两道闸门都要过，一律走 `course_access.block_gate`，不在本文件复刻判定。
"""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..course_access import Access, block_gate, completed_block_ids, lesson_access
from ..judge import JUDGE_FAILED, JudgeCase, JudgeUnavailable
from ..mistake_book import record_wrong
from ..judge.runner import JudgeQueueFull, JudgeTask
from ..models import (
    ChoiceOption,
    Course,
    CourseLesson,
    CourseLessonBlock,
    FillAnswer,
    LessonBlockCompletion,
    LessonCodeRun,
    LessonProblemAttempt,
    LessonProblemBlock,
    Problem,
    ProgrammingDetail,
    TestCase,
    Video,
    VideoVariant,
)
from ..oj_testdata import JudgeDataUnavailable, read_case_content
from ..s3_multipart import play_token_minutes
from ..scoring import (
    QuestionSpec,
    parse_answer,
    parse_blank_alternatives,
    score_question,
    strip_answer_keys,
)
from ..security import as_utc, utcnow
from .auth_secure import current_user, db_session, limit, require_csrf
from .video_play import build_play_response

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["lesson-practice"])

CHOICE_TYPES = {"choice", "multi_choice", "judge"}
# 单题没有试卷层的计分策略，取与试卷默认一致的口径：
# 多选按部分给分（少选得部分分、多选得 0），编程题按全测试点通过计分。
SINGLE_PARTIAL_CREDIT_MULTI = True
SINGLE_SCORE_MODE = "all_or_nothing"


# ---------- 载入与门控 ----------


def _load(db: Session, request: Request, lesson_id: int, block_id: int):
    """校验课时/块/门控，返回 (user, lesson, block, detail, problem)。

    任一环节不通过就抛：块不属于该课时 → 404（不能拿别的课时的 block_id 来取题）；
    两道闸门未过 → 403，且两种锁给不同文案（与前端的两套出口对应）。
    """
    user = current_user(request, db)
    lesson = db.get(CourseLesson, lesson_id)
    if lesson is None:
        raise HTTPException(404, "课时不存在。")
    course = db.get(Course, lesson.course_id)
    if course is None or course.status != "published":
        raise HTTPException(404, "课时不存在。")
    block = db.get(CourseLessonBlock, block_id)
    if block is None or block.lesson_id != lesson_id:
        raise HTTPException(404, "该课时没有这个内容块。")
    if block.block_type != "practice":
        raise HTTPException(400, "该内容块不是课中练习。")

    ordered = list(db.scalars(
        select(CourseLessonBlock).where(CourseLessonBlock.lesson_id == lesson_id)
        .order_by(CourseLessonBlock.sort_order, CourseLessonBlock.id)
    ).all())
    granted = lesson_access(db, user, lesson) is Access.GRANTED
    reason = block_gate(
        db, user, lesson, block, ordered, completed_block_ids(db, user, lesson_id), granted
    )["lock_reason"]
    if reason == "not_enrolled":
        raise HTTPException(403, "该内容尚未对你开放。")
    if reason == "sequential":
        raise HTTPException(403, "请先完成前面的内容块。")

    detail = db.get(LessonProblemBlock, block.id)
    if detail is None or not detail.problem_id_no:
        raise HTTPException(404, "该练习尚未绑定题目。")
    # 与 exam._resolve_problems 同口径：按 problem_id_no 直查（该列唯一），**不加 status 过滤**。
    # 加了的话，老师一把题目改回 draft，正在做这道题的学生就当场撞 404——
    # 题目是否 approved 由发布检查在上架时把关，不该在作答期二次裁决。
    problem = db.scalar(select(Problem).where(Problem.problem_id_no == detail.problem_id_no))
    if problem is None:
        raise HTTPException(404, "题目已不存在。")
    return user, lesson, block, detail, problem


def _attempt_of(db: Session, user_id: int, block_id: int) -> LessonProblemAttempt | None:
    return db.scalar(
        select(LessonProblemAttempt).where(
            LessonProblemAttempt.user_id == user_id,
            LessonProblemAttempt.block_id == block_id,
        )
    )


def _lock_attempt(db: Session, user_id: int, block_id: int,
                  lesson_id: int) -> LessonProblemAttempt:
    """取或建作答记录，**带行锁**。凡是要裁决 attempt_limit 的路径都得走它。

    两件事只能在这里做：

    1. **行锁**。次数裁决是「读 tries → 判分/入队 → tries+1」这一段读-改-写。
       不上锁的话两个并发提交会读到同一个 tries，各自 +1 却只生效一次——次数上限
       被绕过，而且连点两下就能触发。SQLite 上 with_for_update 是 no-op，
       但生产跑 PostgreSQL，那里这行是真的在挡人（写法同 auth_secure.lock_user）。
    2. **并发首建的兜底**。uq_lesson_problem_attempt 挡住同一 (user, block) 的第二次
       INSERT；抢输的那个必须回滚重读，而不是把 IntegrityError 抛成 500——
       并发首次提交在连点场景下是常态，不是异常。
    """
    attempt = db.scalar(
        select(LessonProblemAttempt).where(
            LessonProblemAttempt.user_id == user_id,
            LessonProblemAttempt.block_id == block_id,
        ).with_for_update()
    )
    if attempt is not None:
        return attempt
    attempt = LessonProblemAttempt(
        user_id=user_id, block_id=block_id, lesson_id=lesson_id, tries=0,
    )
    db.add(attempt)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        attempt = db.scalar(
            select(LessonProblemAttempt).where(
                LessonProblemAttempt.user_id == user_id,
                LessonProblemAttempt.block_id == block_id,
            ).with_for_update()
        )
        if attempt is None:  # 理论上不可达：唯一约束冲突意味着另一方已经建好了
            raise HTTPException(409, "作答记录正在并发写入，请重试。") from None
    return attempt


def _tries_left(detail: LessonProblemBlock, attempt: LessonProblemAttempt | None) -> int | None:
    """剩余次数。attempt_limit 为空/0 = 不限，返回 None。"""
    if not detail.attempt_limit:
        return None
    return max(0, detail.attempt_limit - (attempt.tries if attempt else 0))


def _refund_charge(db: Session, run: LessonCodeRun, message: str) -> str:
    """判题没出结果 → 退还这条 run 扣掉的计分次数，并在文案里说明原因（0048）。

    `run.charged` 既是凭据也是幂等闸：只退 charged=True 的 run，退完翻回 False。
    同一条 run 被失败收尾走到两次（判题线程里异常了、又落到 _fail_run 兜底），
    第二次看到 charged 已是 False 就什么都不做，不会退第二次。

    **这里推翻了本文件原先写明的口径**（旧注释：「次数已经在入队时扣掉了——这是有意的，
    宁可学生少一次机会，也不能让判题故障变成刷次数的口子」）。推翻的理由：

    - 那条注释防的是「学生故意刷次数」，但能走到退次的六条路径——队列满、沙箱不可用、
      测试数据缺失、题目已变更、无测试点、判题线程崩溃——**全是系统侧故障，
      学生的代码一条也触发不了**；真正由学生代码决定的 compile_error / wrong_answer
      是正常判定，走 _record_submission 记成绩，根本进不到这里。退次堵不出刷次数的口子。
    - 它援引的考试链路 _fail_pending_judges 只管「不落 0 分」，考试那条路径压根没有
      单题次数上限的概念，类比不成立。
    - attempt_limit 配 1~3 是常见配置，两次运维抖动就能让学生失去正常完成这道题的机会，
      而失败不写成绩，学生连"这次到底算不算"都无从判断。

    口径因此从「次数管点击几次」收敛成「次数管判分几次」——与 attempt_limit
    的字面意思一致，也与客观题（判分是同步的，判完才算一次）对齐。
    """
    if not run.charged:
        return message
    # 与提交/重做抢同一把行锁：退次是读-改-写，不锁会和并发提交互相覆盖。
    attempt = _lock_attempt(db, run.user_id, run.block_id, run.lesson_id)
    attempt.tries = max(0, attempt.tries - 1)
    run.charged = False
    # **必须说清"不计次"**：次数是学生自己盯着的数字，只说"判题失败了"会让他
    # 以为机会白没了，转头去问老师，而老师同样没有依据能回答。
    return f"{message}（系统原因，本次不计次、不计分）"


# ---------- 题面（不含答案与解析） ----------


def _question_payload(db: Session, problem: Problem, detail: LessonProblemBlock) -> dict:
    """单题的作答期载荷。形状对齐 exam._question_payload，供前端复用 Question* 组件。

    **有意省掉 problem_id_no**（红线 2）：考试页那份带它是因为作答按题号回传，
    单题这里的键是 block_id，不需要题目身份。
    """
    payload = {
        # uid 只是给前端拼 DOM id 用的稳定串（QuestionFill 的空位输入框要它）。
        # 用 block_id 而不是 problem_id_no：block_id 客户端本来就知道，不泄露题目身份。
        "uid": f"block-{detail.block_id}",
        "type": problem.type,
        "sub_type": problem.sub_type,
        "stem": problem.stem,
    }
    if problem.type in CHOICE_TYPES:
        rows = db.scalars(
            select(ChoiceOption).where(ChoiceOption.problem_id == problem.id)
            .order_by(ChoiceOption.sort_order)
        ).all()
        options = [
            {"label": chr(65 + i), "content": row.content} for i, row in enumerate(rows)
        ]
        # 判断题不洗：「正确/错误」换了位置只会让人以为自己看错了（同 exam.py 口径）。
        if detail.shuffle_options and problem.type != "judge":
            # 按 block_id 做种子：同一个学生每次进来看到的顺序一致，刷新不会重排——
            # 重排会让"我上次选的 B"对不上，而作答态是要保留的。
            options = _seeded_shuffle(options, detail.block_id)
        payload["options"] = options
    elif problem.type == "fill":
        # 只给空的标识，不给答案
        payload["blank_keys"] = [
            row.blank_key for row in db.scalars(
                select(FillAnswer).where(FillAnswer.problem_id == problem.id)
                .order_by(FillAnswer.blank_index)
            )
        ]
    elif problem.type == "programming":
        payload["programming"] = _programming_payload(db, problem)
    return payload


def _seeded_shuffle(items: list, seed: int) -> list:
    """确定性洗牌（同 exam._seeded_shuffle 的做法，独立实现避免跨模块耦合考试逻辑）。"""
    out = list(items)
    state = seed & 0x7FFFFFFF or 1
    for i in range(len(out) - 1, 0, -1):
        state = (state * 1103515245 + 12345) & 0x7FFFFFFF
        j = state % (i + 1)
        out[i], out[j] = out[j], out[i]
    return out


def _spec_for(db: Session, problem: Problem, detail: LessonProblemBlock) -> QuestionSpec | None:
    """判这道题需要的题面事实。与 exam._spec_for 同口径，分值取块上的 score。"""
    if problem.type in CHOICE_TYPES:
        rows = db.scalars(
            select(ChoiceOption).where(ChoiceOption.problem_id == problem.id)
            .order_by(ChoiceOption.sort_order)
        ).all()
        options = [(chr(65 + i), row.is_correct) for i, row in enumerate(rows)]
        return QuestionSpec(problem.type, detail.score or 0, options=options)
    if problem.type == "fill":
        blanks = [
            (row.blank_key, [row.answer, *parse_blank_alternatives(row.alternatives_json)])
            for row in db.scalars(
                select(FillAnswer).where(FillAnswer.problem_id == problem.id)
                .order_by(FillAnswer.blank_index)
            )
        ]
        return QuestionSpec("fill", detail.score or 0, blanks=blanks)
    # 编程题不在本接口判分（要跑沙箱），由 P3 的运行/提交链路处理
    return None


def _last_code(db: Session, user_id: int, block_id: int,
               attempt: LessonProblemAttempt | None) -> str:
    """编程题的"现场"：优先取草稿，没有草稿就取最近一次运行/提交的代码。

    没有这个字段时 QuestionCoding 的编辑器初值是空串（QuestionCoding.vue:46），
    学生切到下一块再切回来，代码就没了——而课时页的练习块**不在 keep-alive 白名单里**
    （LessonPlayer.vue:497），切块必然销毁组件。代码是学生唯一无法从别处找回的东西。
    """
    saved = parse_answer(attempt.answer_json) if attempt else {}
    if isinstance(saved, dict) and saved.get("draft_code"):
        return saved["draft_code"]
    run = db.scalar(
        select(LessonCodeRun).where(
            LessonCodeRun.user_id == user_id, LessonCodeRun.block_id == block_id
        ).order_by(LessonCodeRun.id.desc())
    )
    if run is None:
        return ""
    # 重做之后编辑器必须是空的。草稿是清了，但运行记录不能删（它是判题履历），
    # 于是这里要拿重做时刻当水位线：比重做更早的运行记录不再回填，
    # 否则"重做"点完一刷新，上一版代码又自己回来了。
    reset_at = as_utc(attempt.last_reset_at) if attempt and attempt.last_reset_at else None
    if reset_at and as_utc(run.created_at) <= reset_at:
        return ""
    return run.code


def _analysis_video_payload(db: Session, problem: Problem, lesson_id: int,
                            block_id: int, *, allow: bool) -> dict | None:
    """解析视频的作答期状态。`allow=False`（未提交）时一律不返回任何信息。

    返回 None = 本题没配解析视频；有配时给出：
    - `available`：视频转码就绪、可以签发播放地址；
    - `processing`：已上传但还在转码（播放端提示稍后再试）；
    - `play_path`：提交门控的签发端点，由 VideoPlayer 用 `playPath` 直接调。

    与 scratch 的 analysis（`routers/scratch.py`）同一条纪律：**显示与否只看服务端
    下发的布尔，前端不自己推断**；播放地址永远不在题面里出现，只走门控端点。
    """
    if not allow or not problem.analysis_video_id:
        return None
    video = db.get(Video, problem.analysis_video_id)
    ready = bool(video and video.status == "ready")
    return {
        "available": ready,
        "processing": bool(video and video.status != "ready"),
        "play_path": f"/api/lessons/{lesson_id}/blocks/{block_id}/analysis-play",
    }


def _state_payload(detail: LessonProblemBlock, attempt: LessonProblemAttempt | None,
                   problem: Problem, *, reveal: bool, lesson_id: int,
                   db: Session) -> dict:
    """作答状态。reveal=False 时**不含判定与解析**——取题接口一律 False。

    `submitted` 是「**当前**有一份已判定的作答」，不是「曾经交过」：重做之后 tries 还在
    （次数不返还），但作答态被清空了，此时必须回 false，否则前端会继续锁着作答区、
    继续显示上一次的判定——那样"重做"就只是个不起作用的按钮。判定区同理，用同一个
    条件把门，两处分开写迟早会分叉。
    """
    left = _tries_left(detail, attempt)
    saved = parse_answer(attempt.answer_json) if attempt else None
    has_verdict = bool(attempt and attempt.tries and attempt.answer_json)
    out = {
        "display_no": detail.display_no,
        "score": detail.score or 0,
        "attempt_limit": detail.attempt_limit or 0,
        "tries": attempt.tries if attempt else 0,
        "tries_left": left,
        "can_answer": left is None or left > 0,
        "answer": saved,
        "submitted": has_verdict,
    }
    if reveal and has_verdict:
        out["verdict"] = {
            "score": attempt.last_score,
            "is_correct": attempt.last_correct,
            # strip_answer_keys 不能省：判分明细里带着正确选项 label，而这里
            # **没有任何闸门**——show_analysis 只挡住了解析文本。少了这一层，
            # 配 show_analysis=False + attempt_limit=3 的练习，学生第一次随便答，
            # 从 verdict.detail.correct 读出答案，第二次必满分。
            "detail": strip_answer_keys(
                json.loads(attempt.detail_json) if attempt.detail_json else {}
            ),
        }
        if detail.show_analysis:
            out["verdict"]["analysis"] = problem.analysis or ""
            analysis_video = _analysis_video_payload(
                db, problem, lesson_id, detail.block_id, allow=True)
            if analysis_video:
                out["verdict"]["analysis_video"] = analysis_video
    elif reveal and left == 0 and detail.show_analysis:
        # **自测态**：次数用尽 + 当前没有判定（= 学生用「重做本题（不计分）」清空重来）。
        # 不给解析的话这条路是死胡同：提交按钮禁着、判定区不显示，学生答完拿不到
        # 任何反馈，"复习自测"的设计目标在最后一公里断掉——他完成了自测的动作，
        # 却验证不了"我现在到底会不会"。
        #
        # 放行的边界：**只给解析文本，绝不给 verdict.detail**。那里面带着正确选项的
        # label（所以 verdict 分支才要 strip_answer_keys），顺着这条路下发等于给
        # show_analysis 开了后门。泄题风险为零的理由也很直接——次数已经用尽，
        # 这道题再也提交不上去，看到解析也换不成分数。
        #
        # left == 0 而不是 can_answer：attempt_limit 为空/0（不限次）时 left 是 None，
        # 那种题永远进不了自测态，也不该进——它随时能再交一次，走正常判定就行。
        out["self_test"] = True
        out["analysis"] = problem.analysis or ""
        analysis_video = _analysis_video_payload(
            db, problem, lesson_id, detail.block_id, allow=True)
        if analysis_video:
            out["analysis_video"] = analysis_video
    return out


# ---------- 端点 ----------


@router.get("/lessons/{lesson_id}/blocks/{block_id}/problem")
def get_practice_problem(lesson_id: int, block_id: int, request: Request,
                         db: Session = Depends(db_session)):
    """取题：题干 + 选项 + 我的作答态。**不含答案、不含解析、不含 problem_id_no。**

    已经答过的学生重新进来，这里连同上次的判定一起给（reveal=True）——否则刷新一次
    判定就没了，学生会以为自己没答过而重复消耗次数。
    """
    user, lesson, block, detail, problem = _load(db, request, lesson_id, block_id)
    attempt = _attempt_of(db, user.id, block.id)
    question = _question_payload(db, problem, detail)
    if problem.type == "programming":
        # 学生自己的代码，回显给他自己——与"答案零下发"无关。
        question["last_code"] = _last_code(db, user.id, block.id, attempt)
    return {
        "block_id": block.id,
        "title": block.title,
        "question": question,
        # 已提交过就把判定一起回：这不是泄题，是回显自己的历史作答
        **_state_payload(detail, attempt, problem, reveal=True, lesson_id=lesson_id, db=db),
    }


@router.post("/lessons/{lesson_id}/blocks/{block_id}/reset")
def reset_practice_answer(lesson_id: int, block_id: int, request: Request,
                          db: Session = Depends(db_session)):
    """重做本题：清作答态，**保留次数与完成记录**（文档 18 §2.4）。

    三条口径，改之前先读完：

    1. **不动 tries**。重做不消耗次数，也不返还次数——次数管的是"能提交几次记分作答"，
       复习不该消耗它，也不该变成刷次数的后门。
    2. **不动 LessonBlockCompletion**。完成度是学习履历，只增不减；一旦回收，顺序锁
       会把后面已经学过的块重新锁上，学生复习一道题就被踢回闯关起点。
    3. **次数用尽也允许重做**，此时返回体的 can_answer 仍是 false —— 学生可以清空重来
       自测「我现在会不会」，只是提交不上去。这一条把"复习"和"刷分"拆开了。

    幂等：没有作答记录时直接回当前状态，不报错。
    """
    require_csrf(request)
    user, lesson, block, detail, problem = _load(db, request, lesson_id, block_id)
    # 它会写库、又极廉价，正好是被人拿去当放大器的形状，限流不能省。
    limit(request, "lesson-practice-reset", str(user.id), 30, 60)

    # **重做与提交必须抢同一把行锁**。submit_practice_answer / submit_lesson_code
    # 判分期间持着 attempt 的行锁；这里若走普通读直接 UPDATE，PostgreSQL 上会等它们
    # 提交完再执行，正好把刚写好的作答与判定清掉——留下 tries 已 +1 但 answer_json
    # 为空的中间态：次数消耗了，成绩没了，而正常流程产生不出这个状态，事后也查不出
    # 这次作答存在过。save_practice_draft 早就是这么做的（它连草稿都上锁），漏的是这里。
    #
    # 先普通读判空、有记录才升级成锁读：没作答过本就是幂等快路径，
    # 不该为「重做一道没做过的题」平白建出一行空记录来。
    attempt = _attempt_of(db, user.id, block.id)
    if attempt is not None:
        attempt = _lock_attempt(db, user.id, block.id, lesson_id)
        attempt.answer_json = ""
        attempt.last_score = None
        attempt.last_correct = None
        attempt.detail_json = None
        attempt.reset_count = (attempt.reset_count or 0) + 1
        attempt.last_reset_at = utcnow()
        db.commit()
        db.refresh(attempt)

    question_state = _state_payload(detail, attempt, problem, reveal=True,
                                    lesson_id=lesson_id, db=db)
    payload = {"block_id": block.id, **question_state}
    if problem.type == "programming":
        # 编程题的"作答"是代码，重做同样要把编辑器清干净——只留题面。
        payload["last_code"] = ""
    return payload


class DraftPayload(BaseModel):
    """编程题草稿。只存代码，不判分、不计次、不写完成度。"""

    language: str = Field(default="", max_length=16)
    code: str = Field(default="", max_length=64_000)


@router.put("/lessons/{lesson_id}/blocks/{block_id}/draft")
def save_practice_draft(lesson_id: int, block_id: int, payload: DraftPayload,
                        request: Request, db: Session = Depends(db_session)):
    """暂存编程题草稿（防抖 1.5s 调一次）。

    **为什么不放 localStorage**：这是带权限的私有内容，落磁盘会活过登出——与
    services/prefetch.js 开头那条纪律同一个理由。存在服务端还顺带解决了换设备的问题。

    写的是 answer_json 而不是新表：`submitted` 的判定是 `bool(attempt and attempt.tries)`，
    草稿不碰 tries，因此一份只有草稿的记录在所有接口眼里都还是"未作答"。
    """
    require_csrf(request)
    user, lesson, block, detail, problem = _load(db, request, lesson_id, block_id)
    if problem.type != "programming":
        raise HTTPException(400, "只有编程题需要暂存草稿。")
    limit(request, "lesson-practice-draft", str(user.id), 120, 60)

    # 草稿不碰 tries，但同样可能与首次提交并发首建同一行——走同一个兜底，
    # 免得唯一约束冲突把一次自动保存变成 500。
    attempt = _lock_attempt(db, user.id, block.id, lesson_id)
    saved = parse_answer(attempt.answer_json)
    attempt.answer_json = json.dumps(
        {
            "type": "programming",
            "language": payload.language or saved.get("language") or problem.sub_type or "cpp",
            "draft_code": payload.code,
        },
        ensure_ascii=False, sort_keys=True,
    )
    db.commit()
    return {"saved": True}


class AnswerPayload(BaseModel):
    """作答载荷。形状与 Question* 组件 emit 的 change 事件一致：
    选择/判断 → {picked: "A"} 或 {picked: ["A","C"]}；填空 → {blanks: {key: value}}。
    """

    answer: dict = Field(default_factory=dict)


@router.post("/lessons/{lesson_id}/blocks/{block_id}/answer")
def submit_practice_answer(lesson_id: int, block_id: int, payload: AnswerPayload,
                           request: Request, db: Session = Depends(db_session)):
    """提交作答：服务端判分 → 计次 → 写完成记录 → 回判定（含解析）。

    完成口径（交接文档 14 §5.1）：**提交即完成，不论对错**。练习是学的过程，
    答错也学到了；按对错才算完成会让学生卡在一道题上过不去。
    """
    require_csrf(request)
    user, lesson, block, detail, problem = _load(db, request, lesson_id, block_id)
    if problem.type == "programming":
        raise HTTPException(400, "编程题请使用运行/提交接口作答。")

    # 先上锁再判次数：读 tries 与写 tries 之间隔着判分，不锁就能并发绕过 attempt_limit。
    attempt = _lock_attempt(db, user.id, block.id, lesson_id)
    left = _tries_left(detail, attempt)
    if left is not None and left <= 0:
        raise HTTPException(409, "本题作答次数已用完。")

    spec = _spec_for(db, problem, detail)
    if spec is None:
        raise HTTPException(400, "该题型暂不支持在课中练习内作答。")
    score, is_correct, verdict_detail = score_question(
        payload.answer, spec,
        partial_credit_multi=SINGLE_PARTIAL_CREDIT_MULTI, score_mode=SINGLE_SCORE_MODE,
    )

    attempt.tries += 1
    attempt.answer_json = json.dumps(payload.answer, ensure_ascii=False, sort_keys=True)
    attempt.last_score = score
    attempt.last_correct = is_correct
    attempt.detail_json = json.dumps(verdict_detail, ensure_ascii=False, sort_keys=True)
    if not is_correct:
        record_wrong(
            db, student_id=user.id, problem_id=problem.id,
            source_type="lesson_practice", source_id=block.id,
        )

    # 提交即完成（不论对错）。已完成则不重复写，唯一约束兜底。
    if not db.scalar(
        select(LessonBlockCompletion).where(
            LessonBlockCompletion.user_id == user.id,
            LessonBlockCompletion.block_id == block.id,
        )
    ):
        db.add(LessonBlockCompletion(
            user_id=user.id, block_id=block.id, lesson_id=lesson_id, source="practice",
        ))
    db.commit()
    db.refresh(attempt)

    return {
        "block_id": block.id,
        **_state_payload(detail, attempt, problem, reveal=True, lesson_id=lesson_id, db=db),
    }


@router.post("/lessons/{lesson_id}/blocks/{block_id}/analysis-play")
def practice_analysis_play(lesson_id: int, block_id: int, request: Request,
                           db: Session = Depends(db_session)):
    """课中练习的解析视频播放地址签发：提交并判定后才放行。

    与 scratch 的 `analysis-play`（`routers/scratch.py`）同一范式：
    - **门控在服务端重跑**：取题接口只下发 `play_path`，真正的地址签发在这里再判一次
      （已提交 + show_analysis 开放 + 视频转码就绪），杜绝"拿到路径就能看"。
    - **不从 lesson 播放端点走**：解析视频不是课时视频内容块，若把 video_id 交给客户端
      再换令牌，任意后台视频都会变成可枚举资源。
    """
    require_csrf(request)
    user, lesson, block, detail, problem = _load(db, request, lesson_id, block_id)
    attempt = _attempt_of(db, user.id, block.id)
    has_verdict = bool(attempt and attempt.tries and attempt.answer_json)
    if not has_verdict:
        raise HTTPException(403, "请先提交本题作答，再观看解析视频。")
    if not detail.show_analysis:
        raise HTTPException(403, "本题未开放解析。")
    if not problem.analysis_video_id:
        raise HTTPException(404, "本题暂未配置解析视频。")
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


# ==================== 编程题试跑（形态 B · 只运行不计分） ====================
#
# 只跑「题目样例」或「学生自填输入」。隐藏测试点在任何配置下都不进入本链路——
# 那是判分资产，而这条链路的定位就是"不计分"。计分提交依赖 X1（paper_attempts
# 来源改造），本期不做。

# 与 app/judge/base.py 的枚举逐字对齐（是 time_limit / memory_limit，不是 *_exceeded），
# 也与 admin_dryrun.TERMINAL_STATUSES、前端 verdict.js 的同名集合一致。
# 对不上的后果不是报错，是前端永远轮询不到终态。
TERMINAL_STATUSES = frozenset(
    {"accepted", "wrong_answer", "compile_error", "runtime_error",
     "time_limit", "memory_limit", JUDGE_FAILED}
)
RUN_FIELD_MAX_CHARS = 2000  # 单个字段（输入/期望/实际）的截断长度

# scope 的三个取值。samples/custom 不计分，all 是计分提交（跑全部测试点）。
SCOPE_SAMPLES = "samples"
SCOPE_CUSTOM = "custom"
SCOPE_ALL = "all"
RUN_SCOPES = frozenset({SCOPE_SAMPLES, SCOPE_CUSTOM})


def _limit_range(db: Session, problem_id: int, column: str, fallback: int) -> list[int] | None:
    """逐点限制的聚合范围 [min, max]，按**生效值**统计（口径与 exam._limit_range 一字不差）。

    独立实现而不是从 exam.py 导：那边是考试链路，本文件不依赖它——但两处口径必须
    同步改。只发聚合范围、不发逐条明细，是为了不暴露"第 7 个点特别重"这类信息。
    """
    column_attr = getattr(TestCase, column)
    values = db.scalars(select(column_attr).where(TestCase.problem_id == problem_id)).all()
    if not values or all(value is None for value in values):
        return None
    effective = [value if value is not None else fallback for value in values]
    return [min(effective), max(effective)]


def _programming_payload(db: Session, problem: Problem) -> dict:
    """编程题题面：样例、限制、提示。**隐藏测试点一条都不给。**

    字段与 exam._question_payload 的编程题分支对齐——同一个 QuestionCoding 组件在
    两个壳里渲染，少一个字段就是一处"考试页和课时页说法不一样"：
      pass_condition 缺失 → isCompileOnly() 恒为 false，编译通过型的题判定文案全错；
      *_limit_range 缺失 → 逐点限制的题只显示题目级限制，学生按错的限制写解法。
    """
    detail = db.get(ProgrammingDetail, problem.id)
    samples = db.scalars(
        select(TestCase).where(TestCase.problem_id == problem.id, TestCase.is_sample.is_(True))
        .order_by(TestCase.sort_order)
    ).all()
    time_limit_ms = detail.time_limit_ms if detail else 1000
    memory_limit_mb = detail.memory_limit_mb if detail else 256
    return {
        "title": problem.title,
        "input_format": detail.input_format if detail else "",
        "output_format": detail.output_format if detail else "",
        "hints": detail.hints if detail else "",
        "pass_condition": detail.pass_condition if detail else "全测试点通过",
        "time_limit_ms": time_limit_ms,
        "memory_limit_mb": memory_limit_mb,
        "time_limit_range": _limit_range(db, problem.id, "time_limit_ms", time_limit_ms),
        "memory_limit_range": _limit_range(db, problem.id, "memory_limit_mb", memory_limit_mb),
        "samples": [{"input": s.input, "output": s.output} for s in samples],
    }


def _run_payload(run: LessonCodeRun, attempt: LessonProblemAttempt | None = None) -> dict:
    """一次运行/提交的对外形状。

    cases 里逐点的 input/expected/actual **在写库时就已经按样例与否裁剪过**
    （见 _cases_payload），这里不再二次防护——防护点只该有一个，两处都做的下场是
    改了一处以为改完了。
    """
    out = {
        "run_id": run.id,
        "status": run.status,
        "compile_message": run.compile_message,
        "time_ms": run.time_ms,
        "memory_kb": run.memory_kb,
        "cases": json.loads(run.detail_json) if run.detail_json else [],
        # 键名叫 done：前端 QuestionCoding / runCodeAndWait 认的就是这个名字
        "done": run.status in TERMINAL_STATUSES,
    }
    # 计分提交才有成绩。判完之前不给 score 键——前端把"键不存在"读作"还没有成绩"，
    # 给个 0 会被渲染成"这次得了 0 分"。
    if run.scope == SCOPE_ALL:
        out["scored"] = True
        if run.status in TERMINAL_STATUSES and attempt is not None:
            out["score"] = attempt.last_score
            out["is_correct"] = attempt.last_correct
    return out


class RunPayload(BaseModel):
    language: str = Field(default="cpp", max_length=16)
    code: str = Field(default="", max_length=64_000)
    scope: str = Field(default="samples", max_length=8)  # samples / custom
    custom_input: str | None = Field(default=None, max_length=16_000)


@router.post("/lessons/{lesson_id}/blocks/{block_id}/run", status_code=201)
def start_lesson_code_run(lesson_id: int, block_id: int, payload: RunPayload,
                          request: Request, db: Session = Depends(db_session)):
    """课时内编程题试跑：落一条 queued 就返回，判题交给线程池（同 exam.run_code 的口径）。

    同步判题会让请求全程占着一个 DB 连接（数百毫秒到数秒），十几个人同时跑就能把
    连接池抽干——见 app/judge/runner.py 的模块注释。
    """
    require_csrf(request)
    user, lesson, block, detail, problem = _load(db, request, lesson_id, block_id)
    # 判题是最贵的资源，限流必须严（与 exam-judge 同一尺子）
    if problem.type != "programming":
        raise HTTPException(400, "该题不是编程题。")
    _ensure_supported_programming_shape(db, problem)
    limit(request, "lesson-judge", str(user.id), 20, 60)
    if not payload.code.strip():
        raise HTTPException(400, "请先写点代码再运行。")
    language = payload.language if payload.language in {"cpp", "python"} else (
        problem.sub_type or "cpp"
    )
    scope = payload.scope if payload.scope in RUN_SCOPES else SCOPE_SAMPLES

    run, ahead = _enqueue_run(db, request, user, lesson_id, block, language, scope,
                              payload.code, payload.custom_input)
    return {**_run_payload(run), "queue_position": ahead}


class SubmitPayload(BaseModel):
    language: str = Field(default="cpp", max_length=16)
    code: str = Field(default="", max_length=64_000)


@router.post("/lessons/{lesson_id}/blocks/{block_id}/submit", status_code=201)
def submit_lesson_code(lesson_id: int, block_id: int, payload: SubmitPayload,
                       request: Request, db: Session = Depends(db_session)):
    """编程题**计分提交**：跑全部测试点，判完写成绩与完成度（文档 18 §3.1 方案③）。

    与 `/run` 的差别只有三处，但每一处都关乎口径：
      scope=all —— 隐藏测试点进入判题（但结果里的输入输出不下发，见 _cases_payload）；
      **入队前先扣次数** —— 判完再扣会被"连点提交"绕过；
      判完写回 LessonProblemAttempt + LessonBlockCompletion —— 与客观题共用同一张表、
      同一条「提交即完成，不论对错」的口径（本文件 submit_practice_answer 的注释）。

    没有为此造 PaperAttempt：单题块没有卷，为一道题造假卷是 models.py:513 明令
    反对的做法。成绩取最后一次提交（last_score 直接覆盖），与考试页的
    「成绩以最后一次提交为准」同口径。
    """
    require_csrf(request)
    user, lesson, block, detail, problem = _load(db, request, lesson_id, block_id)
    # 计分提交比试跑贵（跑全部测试点），限流单独一把尺子，不与 20/min 的调试共用。
    if problem.type != "programming":
        raise HTTPException(400, "该题不是编程题，请用作答接口提交。")
    _ensure_supported_programming_shape(db, problem)
    limit(request, "lesson-submit", str(user.id), 10, 60)
    if not payload.code.strip():
        raise HTTPException(400, "请先写点代码再提交。")

    # 先上锁再判次数，理由同 submit_practice_answer：不锁的话并发提交读到同一个 tries。
    attempt = _lock_attempt(db, user.id, block.id, lesson_id)
    left = _tries_left(detail, attempt)
    if left is not None and left <= 0:
        raise HTTPException(409, "本题作答次数已用完。")

    language = payload.language if payload.language in {"cpp", "python"} else (
        problem.sub_type or "cpp"
    )
    # 次数在入队前就扣掉：判题是异步的，等判完再扣，连点两次提交就只会扣一次。
    attempt.tries += 1
    attempt.answer_json = json.dumps(
        {"type": "programming", "language": language, "draft_code": payload.code},
        ensure_ascii=False, sort_keys=True,
    )
    # **这里不 commit**：扣次数与建 run（charged=True）必须落在同一个事务里，
    # 由 _enqueue_run 一次提交。分成两次提交的话，进程死在中间就会留下
    # 「次数扣了、却没有凭据能退」的记录——那正是 0048 要消灭的状态。

    run, ahead = _enqueue_run(db, request, user, lesson_id, block, language, SCOPE_ALL,
                              payload.code, None, charged=True)
    return {**_run_payload(run, attempt), "queue_position": ahead}


def _enqueue_run(db: Session, request: Request, user, lesson_id: int, block,
                 language: str, scope: str, code: str, custom_input: str | None,
                 *, charged: bool = False) -> tuple[LessonCodeRun, int]:
    """落一条 queued 记录并入队。请求线程只负责这些，判题在线程池里跑——
    同步判题会全程占着一个 DB 连接，十几个人同时跑就能把连接池抽干
    （见 app/judge/runner.py 的模块注释）。

    `charged` 只有计分提交会传 True：调用方在**同一个事务里**已经把 tries 扣掉，
    这行 run 就是那次扣减的凭据，下面那次 commit 同时提交两者（0048）。
    试跑不计分，一律 False。
    """
    run = LessonCodeRun(
        user_id=user.id, block_id=block.id, lesson_id=lesson_id,
        language=language, scope=scope, code=code, status="queued", charged=charged,
    )
    db.add(run)
    db.commit()

    try:
        ahead = request.app.state.judge_runner.enqueue(
            JudgeTask(submission_id=run.id, custom_input=custom_input, kind="lesson_run")
        )
    except JudgeQueueFull as exc:
        # 排队满是最典型的「系统忙，学生没做错任何事」——次数必须退回去，
        # 否则热门题一开课，一批人同时提交，挤不进队列的那些白丢一次机会。
        run.status = JUDGE_FAILED
        run.compile_message = _refund_charge(db, run, "判题排队已满，请稍后重试。")
        db.commit()
        raise HTTPException(429, run.compile_message) from exc
    return run, ahead


@router.get("/lessons/{lesson_id}/blocks/{block_id}/runs/{run_id}")
def get_lesson_code_run(lesson_id: int, block_id: int, run_id: int, request: Request,
                        db: Session = Depends(db_session)):
    """轮询试跑/提交进度。限流按轮询的尺子（每 250ms 一次），不是判题的尺子。"""
    user, lesson, block, detail, problem = _load(db, request, lesson_id, block_id)
    limit(request, "lesson-judge-poll", str(user.id), 600, 60)
    run = db.get(LessonCodeRun, run_id)
    # 认 user + block 双重归属：光看 run_id 就能查别人的运行结果和代码。
    if run is None or run.user_id != user.id or run.block_id != block.id:
        raise HTTPException(404, "运行记录不存在。")
    # 计分提交要把成绩一起回，成绩在 attempt 上（判题线程写的）
    attempt = _attempt_of(db, user.id, block.id) if run.scope == SCOPE_ALL else None
    return _run_payload(run, attempt)


# ---------- 判题线程里的执行体（不在请求上下文，别碰 request） ----------


def run_lesson_code(session_factory, judge, task: JudgeTask, settings) -> None:
    """在判题线程里跑完一次课时试跑。连接口径同 admin_dryrun.run_dry_run：
    取输入 → commit 放连接 → 判题 → 再开事务写回。"""
    db = session_factory()
    try:
        _run_lesson_code_inner(db, judge, task, settings)
    except Exception:
        logger.exception("课时试跑意外失败：run_id=%s", task.submission_id)
        _fail_run(db, task.submission_id, "运行过程出错，请重试。")
    finally:
        db.close()


def _fail_run(db: Session, run_id: int, message: str) -> None:
    try:
        db.rollback()
        run = db.get(LessonCodeRun, run_id)
        if run is None or run.status in TERMINAL_STATUSES:
            return
        run.status = JUDGE_FAILED
        # 判题线程崩了同样是系统的锅，次数退回去（0048）。这是最后一道兜底：
        # 前面每条失败分支都各自退过，charged 已经翻成 False，这里不会退第二次。
        run.compile_message = _refund_charge(db, run, message)
        db.commit()
    except Exception:
        logger.exception("课时试跑兜底收尾也失败了：run_id=%s", run_id)


def _clip(text: str | None, limit_chars: int = RUN_FIELD_MAX_CHARS) -> str:
    value = text or ""
    return value if len(value) <= limit_chars else value[:limit_chars] + "\n…（已截断）"


def _run_lesson_code_inner(db: Session, judge, task: JudgeTask, settings) -> None:
    run = db.get(LessonCodeRun, task.submission_id)
    if run is None or run.status not in ("queued", "judging"):
        return
    block_detail = db.get(LessonProblemBlock, run.block_id)
    problem = db.scalar(
        select(Problem).where(Problem.problem_id_no == block_detail.problem_id_no)
    ) if block_detail else None
    if problem is None:
        run.status = JUDGE_FAILED
        run.compile_message = _refund_charge(db, run, "题目已变更，无法运行。")
        db.commit()
        return

    detail = db.get(ProgrammingDetail, problem.id)
    time_limit_ms = detail.time_limit_ms if detail else 1000
    memory_limit_mb = detail.memory_limit_mb if detail else 256

    try:
        if run.scope == SCOPE_CUSTOM:
            # 自定义输入没有期望输出可比，只看程序跑出了什么
            cases = [JudgeCase(input=task.custom_input or "", expected="", is_sample=True)]
            expectations = [""]
        else:
            # scope=samples 只取样例（不计分的调试）；scope=all 取全部（计分提交）。
            # **隐藏点即使参与判题，输入/期望/实际也一律不下发**——见 _cases_payload。
            query = select(TestCase).where(TestCase.problem_id == problem.id)
            if run.scope != SCOPE_ALL:
                query = query.where(TestCase.is_sample.is_(True))
            rows = list(db.scalars(query.order_by(TestCase.sort_order, TestCase.id)))
            cases, expectations = [], []
            for row in rows:
                case_input, case_output = read_case_content(settings, row)
                cases.append(JudgeCase(
                    input=case_input, expected=case_output, is_sample=bool(row.is_sample),
                    time_limit_ms=row.time_limit_ms, memory_limit_mb=row.memory_limit_mb,
                ))
                expectations.append(case_output)
    except JudgeDataUnavailable as exc:
        logger.error("课时试跑读测试数据失败 run=%s：%s", run.id, exc)
        run.status = JUDGE_FAILED
        run.compile_message = _refund_charge(db, run, f"测试数据读取失败：{exc}")
        db.commit()
        return

    if not cases:
        run.status = JUDGE_FAILED
        run.compile_message = _refund_charge(db, run, (
            "这道题还没有测试点，无法评测。" if run.scope == SCOPE_ALL
            else "这道题还没有样例，无法运行。填个自定义输入试试。"
        ))
        db.commit()
        return

    code, language = run.code, run.language
    run.status = "judging"
    db.commit()  # ← 连接在这里还回池子，下面判题期间不持有

    try:
        result = judge.judge(language=language, code=code, cases=cases,
                             time_limit_ms=time_limit_ms, memory_limit_mb=memory_limit_mb)
    except JudgeUnavailable as exc:
        run.status = JUDGE_FAILED
        run.compile_message = _refund_charge(db, run, "判题服务暂时不可用，请稍后重试。")
        logger.warning("课时试跑失败 run=%s：%s", run.id, str(exc)[:200])
        db.commit()
        return

    cases_payload = _cases_payload(result.cases, expectations)
    run.status = result.status
    run.compile_message = result.compile_message
    run.time_ms, run.memory_kb = result.time_ms, result.memory_kb
    run.detail_json = json.dumps(cases_payload, ensure_ascii=False)
    if run.scope == SCOPE_ALL:
        _record_submission(db, run, block_detail, problem, detail, result, cases_payload)
    db.commit()


def _cases_payload(cases, expectations: list[str]) -> list[dict]:
    """逐测试点结果的对外形状。

    **红线**：样例点的输入/期望本来就在题面里公开，回传不涉及泄题；**隐藏点的
    input / expected / actual 一律 null**，只给状态与耗时。这道裁剪必须做在写库这一层，
    不能留给读接口——判分资产一旦落进 detail_json，此后任何一条读路径漏防都是全量泄露。

    前端 verdict.casesVisible() 认的是"cases 键在不在"，逐条置 null 不影响渲染，
    QuestionCoding 的展开行对 expected == null 的点本来就不展开。
    """
    out = []
    for i, case in enumerate(cases):
        is_sample = bool(getattr(case, "is_sample", False))
        item = {
            "index": i,
            "status": case.status,
            "passed": case.passed,
            "time_ms": case.time_ms,
            "memory_kb": case.memory_kb,
            "is_sample": is_sample,
        }
        if is_sample:
            item["input"] = _clip(case.input)
            item["expected"] = _clip(expectations[i] if i < len(expectations) else "")
            item["actual"] = _clip(case.actual)
        else:
            item["input"] = item["expected"] = item["actual"] = None
        out.append(item)
    return out


def _ensure_supported_programming_shape(db: Session, problem: Problem) -> None:
    """Reject project questions until their dedicated submission workflow exists."""
    detail = db.get(ProgrammingDetail, problem.id)
    if detail is not None and detail.shape == "project":
        raise HTTPException(409, "作品题提交暂未开放。")


def _record_submission(db: Session, run: LessonCodeRun, block_detail: LessonProblemBlock,
                       problem: Problem, prog: ProgrammingDetail | None, result,
                       cases_payload: list[dict]) -> None:
    """计分提交判完之后的回写：成绩 + 完成度。**在判题线程里做，不在请求线程里做。**

    完成口径与客观题一字不差（submit_practice_answer）：**提交即完成，不论对错**。
    练习是学的过程，答错也学到了；按对错才算完成会让学生卡在一道题上过不去。

    判题异常（judge_failed）不写成绩、也不写完成：那是系统的问题，不是学生答错了，
    把它记成 0 分和"已完成"两头都不对。**次数也一并退回**（0048）——判题器自己报
    judge_failed 说明这次根本没判出结果，让它吃掉一次机会等于把运维事故记在学生账上。
    退次不会变成刷次数的口子，理由见 _refund_charge 的注释。
    """
    if result.status == JUDGE_FAILED:
        run.compile_message = _refund_charge(
            db, run, run.compile_message or "判题未能完成，请重试。"
        )
        return
    attempt = _attempt_of(db, run.user_id, run.block_id)
    if attempt is None:  # 理论上不会：提交时已经建过
        return
    full = (block_detail.score or 0) if block_detail else 0
    # 编译通过型的题以"编译过没过"为满分条件，与判题器给的 status 不是一回事：
    # 代码编译通过但测试点全错时 status 仍是 wrong_answer，而这题该判满分。
    # 口径与前端 verdict.isCompileOnly / exam.py:996 的 compile_only 完全一致。
    if prog is not None and prog.pass_condition == "编译通过":
        is_correct = result.status != "compile_error"
    else:
        is_correct = result.status == "accepted"
    attempt.last_score = full if is_correct else 0
    attempt.last_correct = is_correct
    attempt.detail_json = json.dumps(
        {"cases": cases_payload, "status": result.status}, ensure_ascii=False
    )
    if not is_correct:
        record_wrong(
            db, student_id=run.user_id, problem_id=problem.id,
            source_type="lesson_practice", source_id=run.block_id,
        )
    if not db.scalar(
        select(LessonBlockCompletion).where(
            LessonBlockCompletion.user_id == run.user_id,
            LessonBlockCompletion.block_id == run.block_id,
        )
    ):
        db.add(LessonBlockCompletion(
            user_id=run.user_id, block_id=run.block_id, lesson_id=run.lesson_id,
            source="practice",
        ))
