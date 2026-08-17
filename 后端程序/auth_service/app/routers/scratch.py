"""学生端 Scratch 挑战：读挑战 / 存版本 / 提交判定 / 看历史（任务书 21b「API 契约」）。

单独一个 router 而不是塞进 courses.py：那边职责是"浏览课程"，这里是"做作品"——
有文件上传、结构检查、版本冻结、静态判定和完成回写五件事。

## 四条红线

1. **门控只有一份实现**。所有端点一律走 `course_access.block_gate`，与课时详情、
   完成上报、课中练习同一套判定；本文件不复刻任何规则。未登录 401、
   课包未发布/块不属于该课时 404、两种锁 403，且**未解锁一律读不到初始项目**。
2. **通过与否只由服务端说了算**。提交请求的 payload 模型里没有 `passed` / `score` /
   `completed` 字段，客户端传了也会被 pydantic 丢掉。判定在
   `scratch_rules.evaluate()` 里，输入是服务端自己从存储读回来、自己解析的字节。
3. **提交冻结**。提交指向一条不可变的 `ScratchProjectRevision`，并把挑战版本与
   规则原文快照进提交行。学生交完继续改、老师之后改规则，都不会改写这条记录。
4. **不在请求进程里跑学生项目**。判定全是对 `project.json` 的静态遍历，没有 VM、
   没有绿旗、没有子进程。运行型规则的出口是 `needs_review`（见 scratch_rules）。

## 端点

    GET  /api/scratch/lesson-blocks/{block_id}              挑战 + 我的作品 + 最近判定
    GET  /api/scratch/lesson-blocks/{block_id}/starter.sb3  初始项目（逐次鉴权下发）
    PUT  /api/scratch/projects/{project_id}                 保存新版本（multipart .sb3）
    GET  /api/scratch/projects/{project_id}/content.sb3     取回我自己的当前版本
    POST /api/scratch/lesson-blocks/{block_id}/submit       冻结版本 → 判定 → 完成/解锁
    GET  /api/scratch/lesson-blocks/{block_id}/submissions  我的提交历史
    GET  /api/scratch/lesson-blocks/{block_id}/demo.sb3     教师示范项目（提交后才下发）

契约里的四个端点各自需要一条取文件的路径（Studio 得先能把 `.sb3` 拿到手、
再把它存回去），所以另加了两个 `.sb3` 端点；它们过的是同一道门控。
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..course_access import (
    Access,
    block_gate,
    completed_block_ids,
    course_visible,
    lesson_access,
    lesson_progress,
)
from ..models import (
    Course,
    CourseLesson,
    CourseLessonBlock,
    LessonScratchBlock,
    ScratchChallenge,
    ScratchProject,
    ScratchProjectRevision,
    ScratchSubmission,
    Video,
    VideoVariant,
)
from ..scratch_rules import (
    NEEDS_REVIEW,
    PASSED,
    TERMINAL_STATUSES,
    checklist,
    evaluate,
)
from ..scratch_sb3 import Sb3Invalid, inspect_sb3, read_sb3, store_sb3
from .auth_secure import current_user, db_session, limit, require_csrf

# 完成写入与"本次新解锁的块"**复用 courses.py 的实现**，不在这里另写一份。
# 那两个函数的注释里写明了理由：complete / watch 两个端点必须给出同一个答案，
# 算法一分叉就会出现"用 Scratch 通过的块不刷新锁图标"这种没人查得出来的差异。
# 现在多了第三个入口，理由只会更强。
from .courses import _newly_unlocked, _record_completion
from .video_play import build_play_response
from ..s3_multipart import play_token_minutes

router = APIRouter(prefix="/api/scratch", tags=["student-scratch"])

SB3_MEDIA_TYPE = "application/x.scratch.sb3"
COMPLETION_SOURCE = "scratch"  # LessonBlockCompletion.source 的新取值，服务端自己写


# ---------- 载入与门控 ----------


def _gated(db: Session, request: Request, block_id: int):
    """解析块 → 过两道闸 → 取挑战。返回 (user, lesson, block, ordered, completed_ids,
    granted, challenge)。

    失败姿态与 lesson_practice._load 一字不差：块不存在/不是 scratch 块/课包未发布
    一律 404（不泄露"有这么个东西但你看不了"），两种锁 403 且给不同文案。

    **挑战未发布按 404**：草稿关卡对学生等同不存在，否则老师在编辑器里改了一半的
    题面和初始项目就能被学生拉走。
    """
    user = current_user(request, db)
    block = db.get(CourseLessonBlock, block_id)
    if block is None or block.block_type != "scratch":
        raise HTTPException(404, "该内容块不存在。")
    lesson = db.get(CourseLesson, block.lesson_id)
    if lesson is None or not course_visible(db.get(Course, lesson.course_id)):
        raise HTTPException(404, "该内容块不存在。")

    ordered = list(db.scalars(
        select(CourseLessonBlock).where(CourseLessonBlock.lesson_id == lesson.id)
        .order_by(CourseLessonBlock.sort_order, CourseLessonBlock.id)
    ).all())
    completed_ids = completed_block_ids(db, user, lesson.id)
    granted = lesson_access(db, user, lesson) is Access.GRANTED
    reason = block_gate(db, user, lesson, block, ordered, completed_ids, granted)["lock_reason"]
    if reason == "not_enrolled":
        raise HTTPException(403, "该内容尚未对你开放。")
    if reason == "sequential":
        raise HTTPException(403, "请先完成前面的内容块。")

    detail = db.get(LessonScratchBlock, block.id)
    challenge = db.get(ScratchChallenge, detail.challenge_id) if detail else None
    if challenge is None or challenge.status != "published":
        raise HTTPException(404, "该挑战尚未发布。")
    return user, lesson, block, ordered, completed_ids, granted, challenge


def _project_for(db: Session, user, challenge: ScratchChallenge,
                 block_id: int) -> ScratchProject:
    """取或建学生的工作副本（一人一挑战一份）。

    建档放在 GET 里是有意的：Studio 必须先拿到 `project_id` 才知道往哪儿保存，
    而契约里没有"开始做题"这个动作。写入量有上界——这条路径已经过完课时门控，
    只有真的能学这一块的学生才会建出行来。

    并发双开标签页会同时插入，靠唯一约束挡下再回查，不做"先查再插"的假防护。
    """
    project = db.scalar(
        select(ScratchProject).where(
            ScratchProject.student_id == user.id,
            ScratchProject.challenge_id == challenge.id,
        )
    )
    if project is not None:
        return project
    project = ScratchProject(
        student_id=user.id, challenge_id=challenge.id, lesson_block_id=block_id,
        current_revision_no=0, revision_count=0,
    )
    db.add(project)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        project = db.scalar(
            select(ScratchProject).where(
                ScratchProject.student_id == user.id,
                ScratchProject.challenge_id == challenge.id,
            )
        )
        if project is None:  # pragma: no cover - 唯一约束以外的插入失败
            raise HTTPException(500, "作品初始化失败，请刷新重试。") from None
    return project


def _last_submission(db: Session, user, block_id: int) -> ScratchSubmission | None:
    """该学生在该块的最近一次提交（按 attempt_no）。None = 从没交过。"""
    return db.scalar(
        select(ScratchSubmission)
        .where(ScratchSubmission.user_id == user.id,
               ScratchSubmission.lesson_block_id == block_id)
        .order_by(ScratchSubmission.attempt_no.desc())
        .limit(1)
    )


def _is_terminal(submission: ScratchSubmission | None) -> bool:
    """本次提交是否已出结果。`evaluating` 与未提交都是 False。"""
    return submission is not None and submission.status in TERMINAL_STATUSES


def _last_terminal_submission(db: Session, user, block_id: int) -> ScratchSubmission | None:
    """最近一次提交，且已出结果。

    抽出来是因为它有三个调用方：解析视频签发、示范项目下发，以及详情接口里那两个
    `available` 字段。三处必须给出同一个答案——否则会出现"按钮亮着但点进去 403"
    这种只有学生本人能复现的 bug。
    """
    last = _last_submission(db, user, block_id)
    return last if _is_terminal(last) else None


def _current_revision(db: Session, project: ScratchProject) -> ScratchProjectRevision | None:
    if project.current_revision_no <= 0:
        return None
    return db.scalar(
        select(ScratchProjectRevision).where(
            ScratchProjectRevision.project_id == project.id,
            ScratchProjectRevision.revision_no == project.current_revision_no,
        )
    )


def _allowed_extensions(challenge: ScratchChallenge) -> list[str]:
    try:
        parsed = json.loads(challenge.allowed_extensions or "[]")
    except (TypeError, json.JSONDecodeError):
        return []
    return [e for e in parsed if isinstance(e, str)] if isinstance(parsed, list) else []


def _revision_payload(revision: ScratchProjectRevision | None) -> dict | None:
    if revision is None:
        return None
    try:
        extensions = json.loads(revision.extensions_json or "[]")
    except (TypeError, json.JSONDecodeError):
        extensions = []
    return {
        "revision_id": revision.id,
        "revision_no": revision.revision_no,
        "size_bytes": revision.size_bytes,
        "sprite_count": revision.sprite_count,
        "extensions": extensions,
        "saved_at": revision.saved_at.isoformat() if revision.saved_at else None,
    }


def _submission_payload(submission: ScratchSubmission | None) -> dict | None:
    """提交记录的对外形状。**不下发 rules_snapshot**：那是判定参数（含期望值），
    等于把答案发给学生；反馈只出 label + message。
    """
    if submission is None:
        return None
    try:
        evaluation = json.loads(submission.evaluation_json or "{}")
    except (TypeError, json.JSONDecodeError):
        evaluation = {}
    return {
        "submission_id": submission.id,
        "attempt_no": submission.attempt_no,
        "status": submission.status,
        "passed": submission.passed,
        "score": submission.score,
        "submitted_at": submission.submitted_at.isoformat() if submission.submitted_at else None,
        "revision_no": db_revision_no(submission),
        "feedback": _feedback(evaluation),
        "review_comment": submission.review_comment,
        "reviewed": submission.reviewed_at is not None,
        "teacher": _teacher_feedback(submission),
    }


def db_revision_no(submission: ScratchSubmission) -> int | None:
    """提交时冻结的版本号。写在 evaluation_json 里，避免列表接口逐条回查版本表。"""
    try:
        return json.loads(submission.evaluation_json or "{}").get("revision_no")
    except (TypeError, json.JSONDecodeError):
        return None


def _feedback(evaluation: dict) -> dict:
    """判定结论 → 学生可见反馈。逐条给「要求 + 是否达成 + 怎么改」，不给内部证据。"""
    rules = evaluation.get("rules") or []
    return {
        "note": evaluation.get("note") or "",
        "items": [
            {
                "label": rule.get("label") or "",
                "passed": bool(rule.get("passed")),
                "message": rule.get("message") or "",
            }
            for rule in rules
            if isinstance(rule, dict)
        ],
    }


def _teacher_feedback(submission: ScratchSubmission) -> dict | None:
    """教师人工批改 → 学生可见反馈。未批改过返回 None。

    逐项评语 `note` **给学生看**——批改的价值就在这儿。`evidence` 之类内部证据不下发
    （与 `_feedback` 同口径）。`label` / `level_label` / 每项 `max` 从冻结的
    `rubric_snapshot` 查回，不重算：量规改版后学生看到的仍是批改当时那一版。
    """
    if submission.reviewed_at is None:
        return None
    try:
        rubric = json.loads(submission.rubric_snapshot or "{}")
    except (TypeError, json.JSONDecodeError):
        rubric = {}
    if not isinstance(rubric, dict):
        rubric = {}
    try:
        scores = json.loads(submission.rubric_scores_json or "{}")
    except (TypeError, json.JSONDecodeError):
        scores = {}
    if not isinstance(scores, dict):
        scores = {}
    teacher: dict = {
        "verdict": submission.status,
        "comment": submission.review_comment or "",
        "reviewed_at": submission.reviewed_at.isoformat() if submission.reviewed_at else None,
        "rubric": None,
    }
    items = scores.get("items")
    if isinstance(items, list) and items:
        rubric_items: list[dict] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            cid = item.get("criterion_id")
            criterion = next(
                (c for c in rubric.get("criteria", [])
                 if isinstance(c, dict) and c.get("id") == cid),
                None,
            )
            if criterion is None:
                continue
            level = item.get("level")
            level_label = next(
                (lvl.get("label", "") for lvl in criterion.get("levels", [])
                 if isinstance(lvl, dict) and lvl.get("value") == level),
                "",
            )
            criterion_max = max(
                (lvl.get("points", 0) for lvl in criterion.get("levels", [])
                 if isinstance(lvl, dict)),
                default=0,
            )
            rubric_items.append({
                "label": criterion.get("label", ""),
                "level_label": level_label,
                "points": item.get("points"),
                "max": criterion_max,
                "note": item.get("note", ""),
            })
        teacher["rubric"] = {
            "total": scores.get("total"),
            "max": rubric.get("max_score"),
            "items": rubric_items,
        }
    return teacher


# ---------- 挑战详情 ----------


@router.get("/lesson-blocks/{block_id}")
def scratch_block_detail(block_id: int, request: Request, db: Session = Depends(db_session)):
    """挑战说明 + 我的作品摘要 + 最近一次判定 + Studio 需要的上限值。

    `checklist` 只给规则的中文说明，不给规则参数——参数里带着期望值（要说的那句话、
    要求的坐标），下发等于把答案印在题面上（scratch_rules.checklist 同注）。
    """
    user, lesson, block, _ordered, completed_ids, _granted, challenge = _gated(
        db, request, block_id)
    settings = request.app.state.settings
    project = _project_for(db, user, challenge, block.id)
    revision = _current_revision(db, project)
    last = _last_submission(db, user, block.id)
    # 示范项目 = 答案：与解析视频同一道闸（课时门控之外还要一次终态提交）。
    demo_open = bool(challenge.demo_sb3_key) and _is_terminal(last)
    try:
        hints = json.loads(challenge.hints_json or "[]")
    except (TypeError, json.JSONDecodeError):
        hints = []
    return {
        "block": {
            "id": block.id,
            "lesson_id": lesson.id,
            "title": block.title,
            "required": block.required,
            "completed": block.id in completed_ids,
        },
        "challenge": {
            "id": challenge.id,
            "title": challenge.title,
            "instructions_md": challenge.instructions_md,
            "version": challenge.version,
            "allowed_extensions": _allowed_extensions(challenge),
            "hints": [h for h in hints if isinstance(h, str)],
            "checklist": checklist(challenge.rules_json),
            "has_starter": bool(challenge.starter_sb3_key),
            # 相对路径：学员端与 API 同源，没有 base_url 可配（与课包封面同口径）。
            "starter_url": (f"/api/scratch/lesson-blocks/{block.id}/starter.sb3"
                            if challenge.starter_sb3_key else None),
        },
        "project": {
            "id": project.id,
            "current_revision_no": project.current_revision_no,
            "revision_count": project.revision_count,
            "updated_at": project.updated_at.isoformat() if project.updated_at else None,
            "content_url": (f"/api/scratch/projects/{project.id}/content.sb3"
                            if project.current_revision_no > 0 else None),
            "revision": _revision_payload(revision),
        },
        "last_submission": _submission_payload(last),
        "analysis": {
            "available": bool(challenge.analysis_video_id and _is_terminal(last)),
            "notice": "提交并得到结果后可观看教师解析。"
            if challenge.analysis_video_id and last is None
            else None,
        },
        "demo": {
            "has_demo": bool(challenge.demo_sb3_key),
            "available": demo_open,
            # **未开放时必须是 null**，不能"反正后端还会再判一次"就照发。详情接口是
            # 学生随手 F12 就能看的东西，发出地址等于告诉他答案在哪个门后面。
            "url": (f"/api/scratch/lesson-blocks/{block.id}/demo.sb3"
                    if demo_open else None),
            "notice": "提交作品并得到结果后可查看教师示范项目。"
            if challenge.demo_sb3_key and not demo_open
            else None,
        },
        "limits": {
            "max_bytes": settings.scratch_sb3_max_bytes,
            "save_rate_max": settings.scratch_save_rate_max,
            "save_rate_seconds": settings.scratch_save_rate_seconds,
        },
    }


@router.post("/lesson-blocks/{block_id}/analysis-play")
def scratch_analysis_play(block_id: int, request: Request, db: Session = Depends(db_session)):
    """为已提交学生签发解析视频播放地址。

    不复用课程视频的 /lessons/{id}/play：解析视频并非一个 LessonVideoBlock，若把
    video_id 交给客户端再让它换取令牌，就会把任意后台视频变成可枚举资源。
    """
    require_csrf(request)
    user, _lesson, block, _ordered, _completed, _granted, challenge = _gated(db, request, block_id)
    if _last_terminal_submission(db, user, block.id) is None:
        raise HTTPException(403, "请先提交作品并等待本次结果，再观看解析视频。")
    video = db.get(Video, challenge.analysis_video_id) if challenge.analysis_video_id else None
    if video is None or video.status != "ready":
        raise HTTPException(404, "该题暂未配置可播放的解析视频。")
    primary = db.get(VideoVariant, video.primary_variant_id) if video.primary_variant_id else None
    if primary is None or primary.status != "ready" or not primary.object_key.endswith("master.m3u8"):
        raise HTTPException(404, "解析视频仍在处理，请稍后再试。")
    variants = db.scalars(
        select(VideoVariant)
        .where(VideoVariant.video_id == video.id, VideoVariant.status == "ready")
        .order_by(VideoVariant.bitrate_kbps.asc())
    ).all()
    settings = request.app.state.settings
    ttl = play_token_minutes(video.duration_seconds, settings.video_token_minutes)
    return build_play_response(settings, video.id, user.id, variants, ttl)


@router.get("/lesson-blocks/{block_id}/starter.sb3")
def scratch_starter(block_id: int, request: Request, db: Session = Depends(db_session)):
    """初始项目下发。**每次都重跑门控**——存储 key 不是权限凭证。"""
    _user, _lesson, _block, _ordered, _done, _granted, challenge = _gated(db, request, block_id)
    if not challenge.starter_sb3_key:
        raise HTTPException(404, "该挑战还没有初始项目。")
    data = read_sb3(challenge.starter_sb3_key, request.app.state.settings)
    if data is None:
        raise HTTPException(404, "初始项目文件丢失，请联系老师。")
    return Response(
        content=data, media_type=SB3_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="challenge-{challenge.id}.sb3"',
                 "Cache-Control": "private, no-store"},
    )


@router.get("/lesson-blocks/{block_id}/demo.sb3")
def scratch_demo(block_id: int, request: Request, db: Session = Depends(db_session)):
    """教师示范项目下发。门控 = 课时门控 + 一次终态提交。

    与 `starter.sb3` 走同一个 `_gated()`，**每次都重跑**——存储 key 不是权限凭证。
    比 starter 多一道提交闸：初始项目是题面，示范项目是答案。

    三条刻意没做的事：

    - **不走 `_load_own_project()`**。那是"按 project_id 找本人作品"，示范项目不属于
      任何学生，套上去只会让权限判据变得似是而非。
    - **不在这条路径上建 `ScratchProject` 行**。建档是 GET 详情的职责；下发答案的
      路径上不该有写操作。
    - **不收 `challenge_id` 查询参数**。`block_id` 已唯一确定挑战，多一个参数就多一条
      "换个 id 试试"的攻击面。

    未提交按 **403**（与 `analysis-play` 同码同文案）：两个"交完才开放"的资源给出
    不同失败姿态，前端就会写两套分支，迟早有一套是错的。
    """
    user, _lesson, block, _ordered, _done, _granted, challenge = _gated(db, request, block_id)
    if _last_terminal_submission(db, user, block.id) is None:
        raise HTTPException(403, "请先提交作品并得到本次结果，再查看示范项目。")
    if not challenge.demo_sb3_key:
        raise HTTPException(404, "该题暂未提供示范项目。")
    data = read_sb3(challenge.demo_sb3_key, request.app.state.settings)
    if data is None:
        raise HTTPException(404, "示范项目文件丢失，请联系老师。")
    return Response(
        content=data, media_type=SB3_MEDIA_TYPE,
        # 文件名用 block_id 而不是 challenge_id：挑战 id 是跨学生的全局标识，
        # 文件名会落到学生磁盘上，没必要多给一个可枚举的号。
        headers={"Content-Disposition": f'attachment; filename="demo-block-{block.id}.sb3"',
                 "Cache-Control": "private, no-store"},
    )


# ---------- 保存版本 ----------


def _load_own_project(db: Session, request: Request, project_id: int):
    """取本人项目并**按建档来源块重跑课时门控**，返回 (user, project, challenge)。

    别人的项目一律 404 而不是 403：403 等于确认"这个 id 存在，只是不属于你"，
    足够让人枚举出全站有多少作品（与 `_gated` 里"未发布=不存在"同一条口径）。

    来源块被删/被换成别的类型时拒绝写入：URL 上没有课时，不重跑门控就等于给
    未解锁、已下架的内容留了一扇只要知道 project_id 就能写的后门。
    """
    user = current_user(request, db)
    project = db.get(ScratchProject, project_id)
    if project is None or project.student_id != user.id:
        raise HTTPException(404, "作品不存在。")
    challenge = db.get(ScratchChallenge, project.challenge_id)
    if challenge is None:
        raise HTTPException(404, "该挑战已不存在。")
    if project.lesson_block_id is None:
        raise HTTPException(403, "该作品所在的课时内容已下线。")
    _gated(db, request, project.lesson_block_id)
    return user, project, challenge


@router.put("/projects/{project_id}")
async def save_project(project_id: int, request: Request,
                       file: UploadFile = File(...),
                       challenge_id: int | None = Form(default=None),
                       source: str = Form(default="autosave"),
                       db: Session = Depends(db_session)):
    """保存一个新的不可变版本。

    校验顺序是有讲究的：**先归属、再门控、再频率、最后才读文件体**。反过来先读
    10MB 再判权限，等于给任何登录用户开了一条免费的带宽/磁盘消耗通道。

    内容没变时不新建版本（Studio 每隔几秒就自动保存一次，不去重的话一节课能堆出
    几百行只有时间戳不同的版本）。返回 `unchanged: true`，前端据此不必刷新版本号。
    """
    require_csrf(request)
    user, project, challenge = _load_own_project(db, request, project_id)
    # 挑战匹配：Studio 侧状态过期（学生开着两个课时的标签页）时，宁可 409 让它重载，
    # 也不能把 A 关的作品写进 B 关的项目里。
    if challenge_id is not None and challenge_id != challenge.id:
        raise HTTPException(409, "作品与当前挑战不匹配，请刷新页面后重试。")

    settings = request.app.state.settings
    limit(request, "scratch-save", f"{user.id}:{project.id}",
          settings.scratch_save_rate_max, settings.scratch_save_rate_seconds)

    # 多读一个字节才能区分"正好等于上限"和"超了"（与图片/ZIP 上传同一套写法）。
    raw = await file.read(settings.scratch_sb3_max_bytes + 1)
    if len(raw) > settings.scratch_sb3_max_bytes:
        raise HTTPException(
            413, f"作品文件不能超过 {settings.scratch_sb3_max_bytes // (1024 * 1024)} MB。")
    try:
        summary = inspect_sb3(raw, settings)
        sb3_key, digest = store_sb3(raw, settings)
    except Sb3Invalid as exc:
        raise HTTPException(400, exc.message) from exc

    current = _current_revision(db, project)
    if current is not None and current.sha256 == digest:
        return {"project_id": project.id, "unchanged": True,
                "revision": _revision_payload(current)}

    revision = ScratchProjectRevision(
        project_id=project.id,
        revision_no=project.current_revision_no + 1,
        sb3_key=sb3_key,
        sha256=digest,
        size_bytes=len(raw),
        sprite_count=summary.sprite_count,
        extensions_json=json.dumps(summary.extensions, ensure_ascii=False),
        source="manual" if source == "manual" else "autosave",
    )
    db.add(revision)
    project.current_revision_no = revision.revision_no
    project.revision_count = project.revision_count + 1
    try:
        db.commit()
    except IntegrityError:
        # 双标签页并发保存撞 uq_scratch_revision_no：回滚后让客户端重试，
        # 绝不"顺手加一号再写一次"——那会把两份不同的作品交错成一条版本链。
        db.rollback()
        raise HTTPException(409, "作品正在另一处保存，请稍后重试。") from None
    db.refresh(revision)
    return {"project_id": project.id, "unchanged": False,
            "revision": _revision_payload(revision)}


@router.get("/projects/{project_id}/content.sb3")
def project_content(project_id: int, request: Request, db: Session = Depends(db_session)):
    """取回本人作品的当前版本（Studio 续做时加载）。同样每次重跑门控。"""
    _user, project, _challenge = _load_own_project(db, request, project_id)
    revision = _current_revision(db, project)
    if revision is None:
        raise HTTPException(404, "还没有保存过作品。")
    data = read_sb3(revision.sb3_key, request.app.state.settings)
    if data is None:
        raise HTTPException(404, "作品文件丢失，请重新保存。")
    return Response(
        content=data, media_type=SB3_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="project-{project.id}.sb3"',
                 "Cache-Control": "private, no-store"},
    )


# ---------- 提交与判定 ----------


def _extension_violation(challenge: ScratchChallenge, extensions: list[str]) -> list[str]:
    """挑战白名单之外的扩展。空白名单 = 不限制（教研没配就别拦人）。"""
    allowed = _allowed_extensions(challenge)
    if not allowed:
        return []
    return sorted({e for e in extensions if e not in allowed})


@router.post("/lesson-blocks/{block_id}/submit")
def submit_scratch(block_id: int, request: Request, db: Session = Depends(db_session)):
    """冻结当前版本 → 服务端判定 → 通过才写完成记录。

    **请求没有 body**，这是设计的一部分：客户端能决定的只有"什么时候交"，
    交的是哪一份由服务端从 `current_revision_no` 取，判定结果由服务端自己算。
    任务书 21b 强制约束第 5 条——客户端不能传 `passed` / `score` / 完成状态。

    通过后调用的是**既有**完成流程（`courses._record_completion` +
    `_newly_unlocked`），返回值形状与 `/complete`、`/watch` 完全一致，前端一套
    进度刷新逻辑就够。
    """
    require_csrf(request)
    user, lesson, block, ordered, before_ids, granted, challenge = _gated(db, request, block_id)
    settings = request.app.state.settings
    limit(request, "scratch-submit", f"{user.id}:{block.id}",
          settings.scratch_submit_rate_max, settings.scratch_submit_rate_seconds)

    project = _project_for(db, user, challenge, block.id)
    revision = _current_revision(db, project)
    if revision is None:
        raise HTTPException(400, "请先保存作品再提交。")

    data = read_sb3(revision.sb3_key, settings)
    if data is None:
        raise HTTPException(409, "作品文件丢失，请重新保存后再提交。")
    try:
        summary = inspect_sb3(data, settings)
    except Sb3Invalid as exc:
        # 存进来时验过一次，这里再验一次是防"存储被换/迁移损坏"，不是重复劳动。
        raise HTTPException(400, exc.message) from exc

    evaluation = evaluate(challenge.rules_json, summary)
    payload = evaluation.to_json()
    payload["revision_no"] = revision.revision_no
    illegal = _extension_violation(challenge, summary.extensions)
    if illegal:
        # 扩展白名单在**提交**时裁决而不是保存时：保存时拒收会让学生的工作丢失，
        # 而他可能只是想先存一下再回头删掉那个扩展。
        payload["status"] = "failed"
        payload["passed"] = False
        payload["note"] = f"作品使用了本关不允许的扩展：{'、'.join(illegal)}。"
        payload["rules"].append({
            "index": len(payload["rules"]), "type": "allowed_extensions", "label": "只使用本关允许的扩展",
            "passed": False, "message": f"请移除扩展：{'、'.join(illegal)}。", "evidence": {},
        })
        payload["score"] = None

    attempt_no = (db.scalar(
        select(func.max(ScratchSubmission.attempt_no)).where(
            ScratchSubmission.user_id == user.id,
            ScratchSubmission.lesson_block_id == block.id,
        )
    ) or 0) + 1
    submission = ScratchSubmission(
        user_id=user.id,
        lesson_block_id=block.id,
        lesson_id=lesson.id,
        project_id=project.id,
        project_revision_id=revision.id,
        challenge_id=challenge.id,
        challenge_version=challenge.version,   # 冻结：此后老师改题面也不改写这条判定
        rules_snapshot=challenge.rules_json,   # 冻结：判定证据要能自证按哪版规则判的
        attempt_no=attempt_no,
        status=payload["status"],
        passed=bool(payload["passed"]),
        score=payload["score"],
        evaluation_json=json.dumps(payload, ensure_ascii=False),
    )
    db.add(submission)
    try:
        db.commit()
    except IntegrityError:
        # 并发双击撞 uq_scratch_submission_attempt：判定是幂等的（同一份版本 + 同一版
        # 规则必然同一个结论），直接告诉前端刷新看结果，不重排 attempt_no。
        db.rollback()
        raise HTTPException(409, "上一次提交正在处理，请稍后刷新查看结果。") from None

    completed = block.id in before_ids
    unlocked: list[int] = []
    after_ids = before_ids
    if payload["status"] == PASSED:
        _record_completion(db, user, block, lesson.id, COMPLETION_SOURCE, before_ids)
        after_ids = completed_block_ids(db, user, lesson.id)
        unlocked = _newly_unlocked(db, user, lesson, ordered, before_ids, after_ids,
                                   granted, block.id)
        completed = True

    return {
        "submission_id": submission.id,
        "attempt_no": attempt_no,
        "submission_status": payload["status"],
        "passed": bool(payload["passed"]),
        "score": payload["score"],
        "revision_no": revision.revision_no,
        "feedback": _feedback(payload),
        "needs_review": payload["status"] == NEEDS_REVIEW,
        "teacher": _teacher_feedback(submission),
        "completed": completed,
        "progress": lesson_progress(ordered, after_ids),
        "unlocked_block_ids": unlocked,
    }


@router.get("/lesson-blocks/{block_id}/submissions")
def list_submissions(block_id: int, request: Request, db: Session = Depends(db_session)):
    """我在这一块的提交历史（最新在前，最多 50 条）。

    **只回本人的**。教师/教研查全班作品是管理端的事（第二阶段），不能靠给学生端
    加一个 `user_id` 查询参数来实现——那等于把越权查询做成了功能。
    """
    user, _lesson, block, _ordered, completed_ids, _granted, _challenge = _gated(
        db, request, block_id)
    rows = db.scalars(
        select(ScratchSubmission)
        .where(ScratchSubmission.user_id == user.id,
               ScratchSubmission.lesson_block_id == block.id)
        .order_by(ScratchSubmission.attempt_no.desc())
        .limit(50)
    ).all()
    return {
        "block_id": block.id,
        "completed": block.id in completed_ids,
        "submissions": [_submission_payload(row) for row in rows],
    }
