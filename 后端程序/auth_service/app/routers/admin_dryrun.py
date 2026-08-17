"""参考代码试跑：用题目自己的参考代码跑一遍题目自己的测试数据。

它回答一个问题：**这份参考代码，在这道题现有的测试数据上，能不能全过？**
过不了时，录题人要能分辨是数据错了还是代码错了，所以逐点 diff 必须给到位。

单独成一个 router 而不是并进 admin_questions.py：那个文件已经 900 行；而且本模块
是全系统**唯一主动下发隐藏测试点内容**的地方，独立一个文件让这条口径显眼一点。

与学员端 exam.py 的三处关键差异（改之前先读）：
  1. 隐藏点的 input/expected/actual **全部下发**——学员端那边是 build_case_result()
     按 is_sample 裁掉的。这里要的正是被裁掉的那部分。
  2. 逐点结果无条件可见，不受 feedback_mode 管——那是考试呈现策略，与录题人无关。
  3. **不算分**。参考代码的意义是"这份数据自洽"，不是"参考代码能得几分"；
     给个 100 分只会让人误以为学员也能拿满分。
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..judge import JUDGE_FAILED, JudgeCase, JudgeUnavailable
from ..judge.runner import JudgeQueueFull, JudgeTask, judge_key
from ..models import (
    AdminUser,
    PaperAttempt,
    Problem,
    ProblemDryRun,
    ProgrammingDetail,
    ReferenceSolution,
    TestCase,
)
from ..oj_testdata import JudgeDataUnavailable, read_case_content
from ..schemas import DryRunPayload
from .admin_auth import audit, client_ip, current_admin, db_session, limit, require_csrf

router = APIRouter(prefix="/api/admin", tags=["admin-dryrun"])
logger = logging.getLogger(__name__)

EDITOR_ROLES = {"editor", "admin"}
REVIEWER_ROLES = {"reviewer"}
SUPER_ROLE = "super_admin"

TERMINAL_STATUSES = frozenset(
    {"accepted", "wrong_answer", "compile_error", "runtime_error",
     "time_limit", "memory_limit", JUDGE_FAILED}
)


def _can_dry_run(problem: Problem, admin: AdminUser) -> bool:
    """谁能试跑。

    比 edit 宽一档：**审核员对 pending 的题必须能跑**——"核验参考答案是否正确"正是
    审核这一步要干的事，让审核员只能读代码用眼睛编译，这个功能就白做了。
    比 read 窄一档：能读不等于能消耗判题资源。

    已发布（approved）的题不能跑：想验证就走 revise 开草稿副本。保持"approved 是冻结态"
    这条贯穿题库的规则——已发布的题连内容都不让改，没道理让它去占判题机。
    """
    if admin.role == SUPER_ROLE:
        return problem.status in {"draft", "pending"}
    if admin.role in EDITOR_ROLES and problem.owner_id == admin.id:
        return problem.status in {"draft", "pending"}
    return admin.role in REVIEWER_ROLES and problem.status == "pending"


def _load_problem(db: Session, problem_id: int, admin: AdminUser) -> Problem:
    problem = db.get(Problem, problem_id)
    if not problem:
        raise HTTPException(404, "题目不存在。")
    if not _can_dry_run(problem, admin):
        raise HTTPException(403, "没有试跑该题参考代码的权限（已发布的题请先创建修订稿）。")
    if problem.type != "programming":
        raise HTTPException(400, "只有操作题可以试跑参考代码。")
    return problem


@router.post("/problems/{problem_id}/dry-run", status_code=201)
def start_dry_run(problem_id: int, payload: DryRunPayload, request: Request,
                  db: Session = Depends(db_session)):
    require_csrf(request)
    admin = current_admin(request, db)
    # 按管理员限流而不是按 IP：办公室共用出口 IP 是常态，按 IP 限会互相拖累。
    limit(request, "admin-dry-run", str(admin.id), 30, 300)
    problem = _load_problem(db, problem_id, admin)

    language = payload.language or problem.sub_type
    if language not in {"cpp", "python"}:
        raise HTTPException(400, "请先为这道题选择语言。")
    solution = db.scalar(
        select(ReferenceSolution).where(ReferenceSolution.problem_id == problem.id,
                                        ReferenceSolution.language == language)
    )
    if not solution or not solution.code.strip():
        raise HTTPException(422, f"这道题还没有 {language} 参考代码。")

    # 试跑与学员判题共用同一个 go-judge。考试进行中让老师批量试跑，等于跟考生抢沙箱。
    # 拒绝而不是降优先级：真在考试的时候，老师本来也不该在改题。
    ongoing = db.scalar(
        select(func.count()).select_from(PaperAttempt).where(PaperAttempt.status == "ongoing")
    ) or 0
    if ongoing:
        raise HTTPException(409, f"当前有 {ongoing} 场考试正在进行，请等考试结束后再试跑。")

    dry_run = ProblemDryRun(
        problem_id=problem.id, problem_revision=problem.revision, admin_user_id=admin.id,
        language=language, scope=payload.scope, status="queued",
    )
    db.add(dry_run)
    audit(db, request.app.state.settings, "problem_dry_run", "queued", client_ip(request), admin.id,
          resource_type="problem", resource_id=problem.id,
          summary={"scope": payload.scope, "language": language, "revision": problem.revision})
    db.commit()

    try:
        ahead = request.app.state.judge_runner.enqueue(
            JudgeTask(submission_id=dry_run.id, custom_input=payload.custom_input, kind="dry_run")
        )
    except JudgeQueueFull as exc:
        dry_run.status = JUDGE_FAILED
        dry_run.compile_message = "判题排队已满，请稍后重试。"
        db.commit()
        raise HTTPException(429, "判题排队已满，请稍后重试。") from exc
    return {**_payload(dry_run), "queue_position": ahead}


@router.get("/dry-runs/{dry_run_id}")
def get_dry_run(dry_run_id: int, request: Request, db: Session = Depends(db_session)):
    """轮询试跑进度。每 250ms 打一次，限流按轮询的尺子而不是判题的尺子。"""
    admin = current_admin(request, db)
    limit(request, "admin-dry-run-poll", str(admin.id), 600, 60)
    dry_run = db.get(ProblemDryRun, dry_run_id)
    if not dry_run:
        raise HTTPException(404, "试跑记录不存在。")
    # 权限每次都重新判：否则"先试跑、再把题转让给别人、然后继续轮询"就是一条
    # 越权读隐藏测试点内容的路。
    _load_problem(db, dry_run.problem_id, admin)
    payload = _payload(dry_run)
    payload["done"] = dry_run.status in TERMINAL_STATUSES
    if not payload["done"]:
        position = request.app.state.judge_runner.position(judge_key("dry_run", dry_run.id))
        if position is not None:
            payload["queue_position"] = position
    return payload


@router.get("/problems/{problem_id}/dry-runs/latest")
def latest_dry_run(problem_id: int, request: Request, db: Session = Depends(db_session)):
    """这道题最近一次试跑。录题界面重新打开时用它回填结果面板。

    带上 stale 标记：试跑之后题目又改过的，结果不能当成"现在也通过"来显示。
    """
    admin = current_admin(request, db)
    problem = _load_problem(db, problem_id, admin)
    dry_run = db.scalar(
        select(ProblemDryRun).where(ProblemDryRun.problem_id == problem.id)
        .order_by(ProblemDryRun.id.desc())
    )
    if not dry_run:
        return {"dry_run": None}
    payload = _payload(dry_run)
    payload["done"] = dry_run.status in TERMINAL_STATUSES
    return {"dry_run": payload, "problem_revision": problem.revision}


def _payload(dry_run: ProblemDryRun) -> dict:
    payload = {
        "id": dry_run.id, "problem_id": dry_run.problem_id, "status": dry_run.status,
        "scope": dry_run.scope, "language": dry_run.language,
        "problem_revision": dry_run.problem_revision,
        "compile_message": dry_run.compile_message,
        "time_ms": dry_run.time_ms, "memory_kb": dry_run.memory_kb,
        "created_at": dry_run.created_at,
    }
    # 与学员端同一条口径：没判完就什么结果都不给。给个空数组会被前端读成
    # "真的没有测试点"，渲染成一张空表格而不是"判题中"。
    if dry_run.status in TERMINAL_STATUSES and dry_run.detail_json:
        payload["cases"] = json.loads(dry_run.detail_json)
    return payload


# ==================== 判题线程里执行 ====================


def _diff_line(actual: str, expected: str) -> int | None:
    """第一处不同的行号（1 起）。两边都按 outputs_match 的口径规范化后再比，
    否则会出现"试跑说过、正式判题说不过"——最伤信任的一种 bug。"""
    def lines(text: str) -> list[str]:
        rows = [row.rstrip() for row in (text or "").replace("\r\n", "\n").split("\n")]
        while rows and not rows[-1]:
            rows.pop()
        return rows

    left, right = lines(actual), lines(expected)
    for index in range(max(len(left), len(right))):
        if index >= len(left) or index >= len(right) or left[index] != right[index]:
            return index + 1
    return None


def _clip(text: str | None, limit_chars: int) -> str:
    text = text or ""
    return text if len(text) <= limit_chars else text[:limit_chars] + "…（已截断）"


def _context(text: str | None, around: int | None, limit_chars: int, span: int = 3) -> str:
    """只回差异行前后 span 行。一个 10 万行的 .out 整个丢给前端会把浏览器卡死。"""
    if around is None:
        return _clip(text, limit_chars)
    rows = (text or "").replace("\r\n", "\n").split("\n")
    start, end = max(0, around - 1 - span), min(len(rows), around + span)
    excerpt = "\n".join(f"{start + offset + 1:>5} | {row}" for offset, row in enumerate(rows[start:end]))
    return _clip(excerpt, limit_chars)


def run_dry_run(session_factory, judge, task: JudgeTask, settings) -> None:
    """在判题线程里跑完一次试跑。**不在请求上下文里**，别碰 request。

    连接口径与 judge_submission 完全一致：取输入 → commit 放连接 → 判题 → 再开事务写回。
    """
    db = session_factory()
    try:
        _run_dry_run_inner(db, judge, task, settings)
    except Exception:
        logger.exception("试跑意外失败：dry_run_id=%s", task.submission_id)
        _fail(db, task.submission_id, "试跑过程出错，请重试。")
    finally:
        db.close()


def _fail(db: Session, dry_run_id: int, message: str) -> None:
    try:
        db.rollback()
        dry_run = db.get(ProblemDryRun, dry_run_id)
        if dry_run is None or dry_run.status in TERMINAL_STATUSES:
            return
        dry_run.status = JUDGE_FAILED
        dry_run.compile_message = message
        db.commit()
    except Exception:
        logger.exception("试跑兜底收尾也失败了：dry_run_id=%s", dry_run_id)


def _run_dry_run_inner(db: Session, judge, task: JudgeTask, settings) -> None:
    dry_run = db.get(ProblemDryRun, task.submission_id)
    if dry_run is None or dry_run.status not in ("queued", "judging"):
        return
    problem = db.get(Problem, dry_run.problem_id)
    solution = db.scalar(
        select(ReferenceSolution).where(ReferenceSolution.problem_id == dry_run.problem_id,
                                        ReferenceSolution.language == dry_run.language)
    )
    if problem is None or solution is None:
        dry_run.status = JUDGE_FAILED
        dry_run.compile_message = "题目或参考代码已变更，无法试跑。"
        db.commit()
        return

    detail = db.get(ProgrammingDetail, problem.id)
    rows = list(db.scalars(
        select(TestCase).where(TestCase.problem_id == problem.id)
        .order_by(TestCase.sort_order, TestCase.id)
    ))
    if dry_run.scope == "samples":
        rows = [row for row in rows if row.is_sample]

    try:
        if dry_run.scope == "custom":
            # 自定义输入没有"期望输出"可比，只看程序跑出了什么。is_sample=True 是必须的：
            # judge 层按它决定 input/actual 进不进结果对象。
            cases = [JudgeCase(input=task.custom_input or "", expected="", is_sample=True)]
            expectations = [""]
        else:
            cases, expectations = [], []
            for row in rows:
                case_input, case_output = read_case_content(settings, row)
                # is_sample 一律置 True：本模块要的就是被学员端裁掉的那部分内容。
                # 结果对象里的 input/expected/actual 只发给管理员，见模块注释。
                cases.append(JudgeCase(
                    input=case_input, expected=case_output, is_sample=True,
                    time_limit_ms=row.time_limit_ms, memory_limit_mb=row.memory_limit_mb,
                ))
                expectations.append(case_output)
    except JudgeDataUnavailable as exc:
        logger.error("试跑读测试数据失败 dry_run=%s：%s", dry_run.id, exc)
        dry_run.status = JUDGE_FAILED
        dry_run.compile_message = f"测试数据读取失败：{exc}"
        db.commit()
        return

    if not cases:
        dry_run.status = JUDGE_FAILED
        dry_run.compile_message = "这道题还没有可以试跑的测试点。"
        db.commit()
        return

    code, language = solution.code, dry_run.language
    time_limit_ms = detail.time_limit_ms if detail else 1000
    memory_limit_mb = detail.memory_limit_mb if detail else 256
    case_numbers = [row.case_no for row in rows] if dry_run.scope != "custom" else [None]
    is_sample_flags = [row.is_sample for row in rows] if dry_run.scope != "custom" else [True]
    dry_run.status = "judging"
    db.commit()  # ← 连接在这里还回池子，下面判题期间不持有

    try:
        result = judge.judge(language=language, code=code, cases=cases,
                             time_limit_ms=time_limit_ms, memory_limit_mb=memory_limit_mb)
    except JudgeUnavailable as exc:
        dry_run.status = JUDGE_FAILED
        dry_run.compile_message = "判题服务暂时不可用，请稍后重试。"
        logger.warning("试跑失败 dry_run=%s：%s", dry_run.id, str(exc)[:200])
        db.commit()
        return

    clip = settings.dry_run_field_max_chars
    cases_payload = []
    for index, case in enumerate(result.cases):
        expected = expectations[index] if index < len(expectations) else ""
        around = None if case.passed else _diff_line(case.actual or "", expected)
        cases_payload.append({
            "index": index,
            "case_no": case_numbers[index] if index < len(case_numbers) else None,
            "is_sample": is_sample_flags[index] if index < len(is_sample_flags) else True,
            "status": case.status, "passed": case.passed,
            "time_ms": case.time_ms, "memory_kb": case.memory_kb,
            "diff_line": around,
            "input": _context(case.input, None, clip),
            "expected": _context(expected, around, clip),
            "actual": _context(case.actual, around, clip),
        })
    dry_run.status = result.status
    dry_run.compile_message = result.compile_message
    dry_run.time_ms, dry_run.memory_kb = result.time_ms, result.memory_kb
    dry_run.detail_json = json.dumps(cases_payload, ensure_ascii=False)
    db.commit()
