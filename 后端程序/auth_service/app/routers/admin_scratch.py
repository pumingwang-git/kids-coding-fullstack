"""管理端 Scratch 挑战：草稿 → 初始项目 → 规则 → 发布（任务书 21b 的最小配套面）。

## 为什么任务书没列这几个端点，这里却实现了

契约里的四个学生端点全都从 `lesson_scratch_blocks.challenge_id` 出发。挑战本身
没有任何写入入口的话，整条链路只能靠直接改数据库才跑得起来——那既没法交付给
Kimi 的管理端（21c 明确不许绕过权限写库），也没法用公开接口证明"未发布挑战学生
读不到"。所以补齐**最小**的挑战管理面：建草稿、传初始项目、填规则、发布/撤回。

此后又补了三条 GET（Studio 落地后才发现缺）：初始项目 / 示范项目的取回，以及
`/studio-context`——教研在 Studio 里编初始项目，走的是这条而不是学生端那条，
理由见该端点的注释。

不做的事（留给第三阶段的内容生产台，见计划文档 §6 P3）：素材库与班级统计。
（原先列在这里的挑战复制、示范项目预览、教师点评都已实现，别再照着这句话判断。）

## 编辑纪律

**已发布的挑战不能直接改**，要先撤回成草稿——与"已发布课包请先下架再编辑"
（admin_course_content._require_editable）同一条口径。理由不是洁癖：学生正在做的
关卡，题面和规则不能在他手底下变。

`version` = 第几次发布。首次发布保持 1，每次撤回再发 +1，提交记录把它连同规则原文
一起冻结，于是任何一条历史判定都能自证"当时按第几版、哪些规则判的"。草稿保存
不动 `version`——编辑次数由 `edit_seq` 单独计数（乐观锁用），两个口径不互相污染。
"""
from __future__ import annotations

import hashlib
import json
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from ..course_access import completed_block_ids
from ..notification_links import lesson_homework_link
from ..models import (
    AdminUser,
    Course,
    CourseLesson,
    CourseLessonBlock,
    LessonScratchBlock,
    ScratchChallenge,
    ScratchProjectRevision,
    ScratchSubmission,
    User,
    Video,
)
from ..notification_service import create_notification, request_hash
from ..permissions import (
    ACADEMIC_ADMIN_ROLE,
    ASSISTANT_ROLE,
    TEACHER_ROLE,
    is_editor,
    log_scope_denial,
    visible_student_ids,
)
from ..rubric import parse_rubric, validate_rubric
from ..scratch_rules import KNOWN_TYPES, UNSUPPORTED, checklist, parse_rules
from ..scratch_sb3 import Sb3Invalid, inspect_sb3, read_project_json, read_sb3, store_sb3
from ..security import utcnow
from .admin_auth import audit, client_ip, current_admin, db_session, require_csrf
from .courses import _record_completion

# 完成写入复用学生端那一份实现（理由见 routers/scratch.py 顶部同款注释）：
# 自动判定通过、人工点评通过、/complete、/watch 必须是同一条写入路径。
from .scratch import COMPLETION_SOURCE, SB3_MEDIA_TYPE

router = APIRouter(prefix="/api/admin/scratch", tags=["admin-scratch"])

CHALLENGE_STATUSES = {"draft", "pending", "published", "archived"}


class ChallengePayload(BaseModel):
    """挑战题面。`status` / `version` / `starter_sb3_key` 不在这里——它们分别由
    发布接口和上传接口写，不接受前端直接赋值。

    `rules` 与 `rules_json` 两个键都收：21c 的管理端已经按 `rules_json` 写好了
    （那边的 mock 契约用的是这个名字）。真要把两边统一成一个名字是 Codex 裁决的事，
    在此之前多认一个键的成本远低于让管理端整页发不出请求。取值以 `rules` 优先。

    `base_version` 是可选的乐观锁：管理端传了就比对 `edit_seq`（GET 响应里的
    `edit_seq` 字段），不等于当前值直接 409（两个教研同时编辑同一关卡时，后保存的
    那个不该静默覆盖前一个）。字段名保持 `base_version` 不变；比对目标从
    `version`（发布版次）拆出为 `edit_seq`（编辑序号）后，**前端应改从响应里的
    `edit_seq` 取锁值**，继续传 `version` 会在第二次保存时拿到误报 409。
    """

    title: str = Field(min_length=1, max_length=200)
    instructions_md: str = Field(default="", max_length=20000)
    analysis_video_id: int | None = Field(default=None, ge=1)
    allowed_extensions: list[str] = Field(default_factory=list)
    hints: list[str] = Field(default_factory=list)
    rules: list[dict] = Field(default_factory=list)
    rules_json: list[dict] | None = Field(default=None)
    rubric: dict = Field(default_factory=dict)
    base_version: int | None = Field(default=None)

    @property
    def effective_rules(self) -> list[dict]:
        return self.rules if self.rules else (self.rules_json or [])


class RejectScratchPayload(BaseModel):
    """挑战打回：原因必填（对齐题目 `RejectProblemPayload` 口径），落库可追溯。"""

    model_config = {"extra": "forbid"}
    reason: str = Field(min_length=1, max_length=500)


class ReviewPayload(BaseModel):
    """人工点评。`verdict` 只有两种终态——挂起态不能由点评再写回挂起。
    `rubric` 是逐项打分 `[{"criterion_id", "level", "note"}]`，**没有 points 字段**：
    分数由后端按 `criterion_id + level` 从挑战当前量规查表得出，客户端传值一律丢弃
    （同 `passed` / `score` 的处理）。
    """

    verdict: str = Field(pattern="^(passed|failed)$")
    comment: str = Field(default="", max_length=2000)
    rubric: list[dict] = Field(default_factory=list)


class ReturnPayload(BaseModel):
    """退回重做。与 `/review` 的差别只在：`comment` 必填、`status` 写成 `returned`。

    不写完成记录、也不撤销已有完成记录（见 `_record_completion` 与 models 注释）。
    """

    comment: str = Field(min_length=1, max_length=2000)
    rubric: list[dict] = Field(default_factory=list)


def _require_editor(request: Request, db: Session):
    admin = current_admin(request, db)
    if not is_editor(admin):
        raise HTTPException(403, "没有编辑课程内容的权限。")
    return admin


def _require_submission_reader(request: Request, db: Session):
    """学生作品与批改端点的功能闸；数据范围由调用点另行收窄。"""
    admin = current_admin(request, db)
    grading_roles = {TEACHER_ROLE, ASSISTANT_ROLE, ACADEMIC_ADMIN_ROLE}
    if not is_editor(admin) and admin.role not in grading_roles:
        raise HTTPException(403, "没有查看或批改学生作品的权限。")
    return admin


def _load_visible_submission(db: Session, admin, submission_id: int,
                             student_ids: set[int] | None) -> ScratchSubmission:
    """按 ID 取一份学生作品；越界与不存在返回**完全相同**的 404。

    《39、API错误码与分页排序规范》§3.2：范围闸不能用 403——那等于告诉调用方
    「这条记录存在，只是不归你管」，靠遍历 ID 就能枚举出全站有哪些提交。
    两种情况共用下面这一处 raise，正是为了防止文案日后漂移出差别。
    """
    submission = db.get(ScratchSubmission, submission_id)
    out_of_scope = (
        submission is not None
        and student_ids is not None
        and submission.user_id not in student_ids
    )
    if out_of_scope:
        log_scope_denial(admin, "scratch_submission", submission_id)
    if submission is None or out_of_scope:
        raise HTTPException(404, "提交记录不存在。")
    return submission


def _validate_rules(rules: list[dict]) -> list[dict]:
    """规则写入时就校验类型，不留到判定时才发现。

    未知 type 在判定期会走 `needs_review`（fail closed，学生不会被误放行），但那是
    **兜底**不是设计：教研把 `require_opcode` 拼成 `require_opcodes`，整个班级的提交
    会静静地全部挂起等人工，而没人知道是打错了字。所以写入即拒。
    """
    cleaned: list[dict] = []
    for index, rule in enumerate(rules):
        kind = rule.get("type")
        if not isinstance(kind, str) or kind not in KNOWN_TYPES:
            raise HTTPException(
                400, f"第 {index + 1} 条规则的类型无效：{kind}。"
                     f"可用类型：{'、'.join(sorted(KNOWN_TYPES))}。")
        cleaned.append(rule)
    return cleaned


def _parse_rubric(rubric_json: str) -> dict:
    """`rubric.parse_rubric` 的本地别名，保留原调用点不动。"""
    return parse_rubric(rubric_json)


def _validate_rubric(rubric: dict) -> dict:
    """量规写入即校验。实现搬去 `app/rubric.py` 与 Python 作品题共用——
    两处各留一份，max_score 口径、id 字符集、档位下限任何一处改动都要记得改两遍，
    漏掉的那一遍不会报错，只会让某一类题静默走上另一套规矩。

    这里只负责把领域异常翻成 HTTP 400：`rubric.py` 抛 `ValueError`，不认识 FastAPI。
    """
    try:
        return validate_rubric(rubric)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


def _apply_rubric(challenge: ScratchChallenge,
                  review_rubric: list[dict]) -> tuple[dict, int, int] | None:
    """校验批改请求的量规打分并算总分。

    返回 `(rubric_scores_dict, manual_score, manual_score_max)`；挑战无量规时返回 `None`
    （此时请求带 rubric 一律 400，不接受"临时发明一套量规"）。

    规则（见文档 §6.3）：
    - 挑战有量规 → 请求 rubric 必填，且必须**覆盖全部准则、不能有多余项**，缺一项 400。
      半张量规比没有量规更糟：学生会以为没打分的项是 0 分，而老师以为自己没评价那一项。
    - `points` 由 `criterion_id + level` 查表得出，客户端传值一律丢弃（这里根本不读）。
    """
    rubric = _parse_rubric(challenge.rubric_json)
    has_rubric = bool(rubric.get("criteria"))
    if not has_rubric:
        if review_rubric:
            raise HTTPException(400, "该挑战未配置量规，不能提交量规打分。")
        return None
    if not review_rubric:
        raise HTTPException(400, "该挑战配置了量规，批改必须覆盖全部准则。")
    by_id = {c["id"]: c for c in rubric["criteria"]}
    provided = {str(item.get("criterion_id")) for item in review_rubric if isinstance(item, dict)}
    if provided != set(by_id):
        raise HTTPException(400, "量规打分必须覆盖全部准则，且不能有多余项。")
    items: list[dict] = []
    total = 0
    for item in review_rubric:
        cid = str(item.get("criterion_id"))
        criterion = by_id[cid]
        level = item.get("level")
        points = next((lvl["points"] for lvl in criterion["levels"] if lvl["value"] == level), None)
        if points is None:
            raise HTTPException(400, f"准则「{criterion['label']}」的档位值 {level} 不在量规中。")
        items.append({
            "criterion_id": cid, "level": level, "points": points,
            "note": str(item.get("note") or "").strip(),
        })
        total += points
    return ({"items": items, "total": total}, total, rubric["max_score"])


def _analysis_video_status(db: Session, video_id: int | None) -> str | None:
    """解析视频的转码状态（管理端上传卡片展示用）。"""
    if video_id is None:
        return None
    video = db.get(Video, video_id)
    return video.status if video else None


def _validate_analysis_video(db: Session, video_id: int | None) -> int | None:
    """解析视频复用平台视频资产；未转码完成的素材不能被绑定为学生可观看内容。"""
    if video_id is None:
        return None
    video = db.get(Video, video_id)
    if video is None:
        raise HTTPException(400, "解析视频不存在。")
    if video.status != "ready":
        raise HTTPException(400, "解析视频尚未转码完成，暂不能绑定。")
    return video.id


def _serialize(db: Session, challenge: ScratchChallenge) -> dict:
    def _loads(raw: str, fallback):
        try:
            parsed = json.loads(raw or "null")
        except (TypeError, json.JSONDecodeError):
            return fallback
        return parsed if isinstance(parsed, type(fallback)) else fallback

    bound = db.scalar(
        select(func.count()).select_from(LessonScratchBlock)
        .where(LessonScratchBlock.challenge_id == challenge.id)
    ) or 0
    submissions = db.scalar(
        select(func.count()).select_from(ScratchSubmission)
        .where(ScratchSubmission.challenge_id == challenge.id)
    ) or 0
    return {
        "id": challenge.id,
        "title": challenge.title,
        "instructions_md": challenge.instructions_md,
        "status": challenge.status,
        "version": challenge.version,
        "edit_seq": challenge.edit_seq,
        "allowed_extensions": _loads(challenge.allowed_extensions, []),
        "hints": _loads(challenge.hints_json, []),
        "rules": _loads(challenge.rules_json, []),
        "rubric": _parse_rubric(challenge.rubric_json),
        "checklist": checklist(challenge.rules_json),
        "has_starter": bool(challenge.starter_sb3_key),
        "has_demo": bool(challenge.demo_sb3_key),
        # 下载地址由后端下发而不是让前端拼：与学生端 `starter_url` 同口径，
        # 将来换对象存储直链时只改这一处。相对路径——管理端与 API 同源。
        "starter_url": (f"/api/admin/scratch/challenges/{challenge.id}/starter.sb3"
                        if challenge.starter_sb3_key else None),
        "demo_url": (f"/api/admin/scratch/challenges/{challenge.id}/demo.sb3"
                     if challenge.demo_sb3_key else None),
        "analysis_video_id": challenge.analysis_video_id,
        "has_analysis_video": bool(challenge.analysis_video_id),
        "analysis_video_status": _analysis_video_status(db, challenge.analysis_video_id),
        "starter_size_bytes": challenge.starter_size_bytes,
        "starter_sha256": challenge.starter_sha256,
        "bound_block_count": bound,
        "submission_count": submissions,
        # 审核人/打回记录：与题目 `_problem_to_payload` 同构（前端列表 ⚑ 标志与详情共用）。
        "reviewed_by": _person_payload(db, challenge.reviewed_by),
        "reviewed_at": challenge.reviewed_at,
        "rejection": ({
            "by": _person_payload(db, challenge.rejected_by),
            "at": challenge.rejected_at,
            "reason": challenge.rejection_reason,
        } if challenge.rejection_reason else None),
        "created_at": challenge.created_at.isoformat() if challenge.created_at else None,
        "updated_at": challenge.updated_at.isoformat() if challenge.updated_at else None,
    }


def _person_payload(db: Session, admin_id: int | None) -> dict | None:
    """管理员摘要（与题目 `_problem_to_payload` 的 `_person_payload` 同构）。"""
    admin = db.get(AdminUser, admin_id) if admin_id else None
    return {"id": admin.id, "display_name": admin.display_name} if admin else None


def _get_or_404(db: Session, challenge_id: int) -> ScratchChallenge:
    challenge = db.get(ScratchChallenge, challenge_id)
    if challenge is None:
        raise HTTPException(404, "挑战不存在。")
    return challenge


def _require_draft(challenge: ScratchChallenge) -> None:
    if challenge.status != "draft":
        raise HTTPException(
            409, "只有草稿挑战可以编辑；已发布挑战请先点「修改」撤回为草稿。"
        )


def _require_publish_ready(challenge: ScratchChallenge) -> list[str]:
    """提交审核和兼容旧入口的直接发布共用同一份完整性门槛。"""
    if not challenge.title.strip():
        raise HTTPException(400, "挑战标题不能为空。")
    if not challenge.instructions_md.strip():
        raise HTTPException(400, "挑战任务说明不能为空。")
    rules = parse_rules(challenge.rules_json)
    _validate_rules(rules)
    _validate_rubric(_parse_rubric(challenge.rubric_json))
    if not challenge.starter_sb3_key:
        raise HTTPException(400, "提交审核前必须上传初始项目（.sb3）。")
    if not rules:
        raise HTTPException(400, "提交审核前至少配置一条声明式规则。")
    return sorted({r["type"] for r in rules if r["type"] in UNSUPPORTED})


@router.get("/challenges")
def list_challenges(request: Request, db: Session = Depends(db_session),
                    status: str | None = Query(default=None),
                    keyword: str | None = Query(default=None, max_length=100),
                    page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100)):
    current_admin(request, db)
    stmt = select(ScratchChallenge)
    if status:
        if status not in CHALLENGE_STATUSES:
            raise HTTPException(400, "status 只允许 draft / pending / published / archived。")
        stmt = stmt.where(ScratchChallenge.status == status)
    if keyword:
        like = f"%{keyword}%"
        stmt = stmt.where(or_(ScratchChallenge.title.like(like),
                              ScratchChallenge.instructions_md.like(like)))
    total = db.scalar(stmt.with_only_columns(func.count(ScratchChallenge.id)).order_by(None)) or 0
    rows = db.scalars(
        stmt.order_by(ScratchChallenge.id.desc()).offset((page - 1) * size).limit(size)
    ).all()
    return {"total": total, "page": page, "size": size,
            "items": [_serialize(db, row) for row in rows]}


@router.get("/challenges/options")
def challenge_options(request: Request, db: Session = Depends(db_session)):
    """绑定下拉用的精简列表。

    **必须声明在 `/challenges/{challenge_id}` 之前**：FastAPI 按声明顺序匹配，
    反过来的话 "options" 会先撞上 int 路径参数，直接 422。

    带上 status/version：未发布的挑战要在下拉里标出来，否则教研绑完以为配好了，
    课包发布时才被拦下。
    """
    current_admin(request, db)
    rows = db.scalars(select(ScratchChallenge).order_by(ScratchChallenge.id.desc())).all()
    return {"items": [{"id": c.id, "title": c.title, "status": c.status, "version": c.version}
                      for c in rows]}


@router.get("/challenges/{challenge_id}")
def get_challenge(challenge_id: int, request: Request, db: Session = Depends(db_session)):
    current_admin(request, db)
    return _serialize(db, _get_or_404(db, challenge_id))


@router.post("/challenges", status_code=201)
def create_challenge(payload: ChallengePayload, request: Request,
                     db: Session = Depends(db_session)):
    require_csrf(request)
    admin = _require_editor(request, db)
    rules = _validate_rules(payload.effective_rules)
    rubric = _validate_rubric(payload.rubric)
    analysis_video_id = _validate_analysis_video(db, payload.analysis_video_id)
    challenge = ScratchChallenge(
        title=payload.title,
        instructions_md=payload.instructions_md,
        analysis_video_id=analysis_video_id,
        allowed_extensions=json.dumps(payload.allowed_extensions, ensure_ascii=False),
        hints_json=json.dumps(payload.hints, ensure_ascii=False),
        rules_json=json.dumps(rules, ensure_ascii=False),
        rubric_json=json.dumps(rubric, ensure_ascii=False),
        status="draft",
        version=1,
        created_by=admin.id,
    )
    db.add(challenge)
    db.flush()
    audit(db, request.app.state.settings, "scratch_challenge_create", "success",
          client_ip(request), admin.id, resource_type="scratch_challenge",
          resource_id=challenge.id, summary={"title": payload.title})
    db.commit()
    return _serialize(db, challenge)


@router.put("/challenges/{challenge_id}")
def update_challenge(challenge_id: int, payload: ChallengePayload, request: Request,
                     db: Session = Depends(db_session)):
    require_csrf(request)
    admin = _require_editor(request, db)
    challenge = _get_or_404(db, challenge_id)
    _require_draft(challenge)
    if payload.base_version is not None and payload.base_version != challenge.edit_seq:
        raise HTTPException(409, "保存冲突：该挑战刚被其他人修改，请刷新后基于最新版本重试。")
    rules = _validate_rules(payload.effective_rules)
    rubric = _validate_rubric(payload.rubric)
    analysis_video_id = _validate_analysis_video(db, payload.analysis_video_id)
    challenge.title = payload.title
    challenge.instructions_md = payload.instructions_md
    challenge.analysis_video_id = analysis_video_id
    challenge.allowed_extensions = json.dumps(payload.allowed_extensions, ensure_ascii=False)
    challenge.hints_json = json.dumps(payload.hints, ensure_ascii=False)
    challenge.rules_json = json.dumps(rules, ensure_ascii=False)
    challenge.rubric_json = json.dumps(rubric, ensure_ascii=False)
    # 只 bump edit_seq：version 是发布版次（撤回再发时才动），草稿编辑不该污染它。
    challenge.edit_seq = challenge.edit_seq + 1
    challenge.updated_at = utcnow()
    audit(db, request.app.state.settings, "scratch_challenge_update", "success",
          client_ip(request), admin.id, resource_type="scratch_challenge",
          resource_id=challenge.id)
    db.commit()
    return _serialize(db, challenge)


@router.post("/challenges/{challenge_id}/duplicate", status_code=201)
def duplicate_challenge(challenge_id: int, request: Request,
                        db: Session = Depends(db_session)):
    """复制挑战为新的草稿版本。

    初始/示范项目按内容寻址 key 复用，提交、项目副本和课程内容块绝不复制；教师必须
    在新版本发布后手动把课时块绑定切换过去，历史学生记录才不会被题面变更污染。
    """
    require_csrf(request)
    admin = _require_editor(request, db)
    source = _get_or_404(db, challenge_id)
    suffix = "（新版本）"
    title = f"{source.title[: max(0, 200 - len(suffix))]}{suffix}"
    copied = ScratchChallenge(
        title=title,
        instructions_md=source.instructions_md,
        starter_sb3_key=source.starter_sb3_key,
        starter_sha256=source.starter_sha256,
        starter_size_bytes=source.starter_size_bytes,
        demo_sb3_key=source.demo_sb3_key,
        analysis_video_id=source.analysis_video_id,
        allowed_extensions=source.allowed_extensions,
        rules_json=source.rules_json,
        hints_json=source.hints_json,
        rubric_json=source.rubric_json,
        status="draft",
        version=1,
        created_by=admin.id,
    )
    db.add(copied)
    db.flush()
    audit(db, request.app.state.settings, "scratch_challenge_duplicate", "success",
          client_ip(request), admin.id, resource_type="scratch_challenge",
          resource_id=copied.id, summary={"source_id": source.id})
    db.commit()
    return _serialize(db, copied)


async def _store_challenge_project(challenge_id: int, request: Request, file: UploadFile,
                                   db: Session, *, kind: str):
    """初始项目 / 示范项目上传。走与学生保存**同一套**结构检查，不因为来源是老师就放宽。"""
    require_csrf(request)
    admin = _require_editor(request, db)
    challenge = _get_or_404(db, challenge_id)
    _require_draft(challenge)
    settings = request.app.state.settings
    raw = await file.read(settings.scratch_sb3_max_bytes + 1)
    if len(raw) > settings.scratch_sb3_max_bytes:
        raise HTTPException(
            413, f"项目文件不能超过 {settings.scratch_sb3_max_bytes // (1024 * 1024)} MB。")
    try:
        summary = inspect_sb3(raw, settings)
        sb3_key, digest = store_sb3(raw, settings)
    except Sb3Invalid as exc:
        raise HTTPException(400, exc.message) from exc
    if kind == "starter":
        challenge.starter_sb3_key = sb3_key
        challenge.starter_sha256 = digest
        challenge.starter_size_bytes = len(raw)
    else:
        # 示范项目只存 key：它不下发给学生（那是答案），只给教研在管理端预览。
        challenge.demo_sb3_key = sb3_key
    audit(db, settings, f"scratch_challenge_{kind}", "success",
          client_ip(request), admin.id, resource_type="scratch_challenge",
          resource_id=challenge.id,
          summary={"sha256": digest, "size_bytes": len(raw),
                   "sprite_count": summary.sprite_count})
    db.commit()
    return _serialize(db, challenge)


@router.post("/challenges/{challenge_id}/starter")
async def upload_starter(challenge_id: int, request: Request,
                         file: UploadFile = File(...), db: Session = Depends(db_session)):
    return await _store_challenge_project(challenge_id, request, file, db, kind="starter")


@router.post("/challenges/{challenge_id}/starter-project")
async def upload_starter_alias(challenge_id: int, request: Request,
                               file: UploadFile = File(...), db: Session = Depends(db_session)):
    """`/starter` 的别名：21c 的管理端按 `starter-project` 写好了。

    别名而不是改主路由名：学生端契约文档里已经写的是 `/starter`，两边都留着，
    等 Codex 裁决统一后删掉其中一条即可（删别名不影响任何已实现的判定逻辑）。
    """
    return await _store_challenge_project(challenge_id, request, file, db, kind="starter")


@router.post("/challenges/{challenge_id}/demo-project")
async def upload_demo(challenge_id: int, request: Request,
                      file: UploadFile = File(...), db: Session = Depends(db_session)):
    return await _store_challenge_project(challenge_id, request, file, db, kind="demo")


def _challenge_project_response(challenge_id: int, request: Request, db: Session, *, kind: str):
    """取回教研自己传上去的 `.sb3`。

    补这两条 GET 的原因很实在：在此之前初始项目只进不出，教研想在上一版基础上改，
    只能指望本地还留着底稿——换个人接手这一关就等于从零重做。Studio 要能装载已有
    初始项目续做，也必须先有这条路。

    卡 `_require_editor` 而不是 `current_admin`：示范项目就是答案，初始项目属于
    未发布的题面，两者都不该对只有教学权限的人开放（作品快照才是那边的东西）。
    """
    _require_editor(request, db)
    challenge = _get_or_404(db, challenge_id)
    key = challenge.starter_sb3_key if kind == "starter" else challenge.demo_sb3_key
    if not key:
        raise HTTPException(404, "尚未上传初始项目。" if kind == "starter" else "尚未上传示范项目。")
    data = read_sb3(key, request.app.state.settings)
    if data is None:
        raise HTTPException(404, "项目文件丢失，请重新上传。")
    return Response(
        content=data, media_type=SB3_MEDIA_TYPE,
        headers={"Content-Disposition":
                 f'attachment; filename="challenge-{challenge.id}-{kind}.sb3"',
                 "Cache-Control": "private, no-store"},
    )


@router.get("/challenges/{challenge_id}/starter.sb3")
def download_starter(challenge_id: int, request: Request, db: Session = Depends(db_session)):
    return _challenge_project_response(challenge_id, request, db, kind="starter")


@router.get("/challenges/{challenge_id}/demo.sb3")
def download_demo(challenge_id: int, request: Request, db: Session = Depends(db_session)):
    return _challenge_project_response(challenge_id, request, db, kind="demo")


@router.get("/challenges/{challenge_id}/studio-context")
def studio_context(challenge_id: int, request: Request, db: Session = Depends(db_session)):
    """Studio 的管理端上下文：教研直接在 Studio 里做初始项目，做完写回本挑战。

    ## 为什么不能复用学生端的 `/lesson-blocks/{block_id}`

    那条路要过 `_gated()`：块存在、课包已发布、两道解锁闸、**且挑战已发布**。教研要
    预览/编写的恰恰是草稿，而草稿挑战通常还没绑到任何课时块上——从设计上就走不通，
    不是配一配就能通的事。所以按 `challenge_id` 另开一条，门是编辑权限。

    ## 形状与学生端对齐

    `block` / `project` / `last_submission` 一律给 null 而不是省略：Studio 的渲染
    分支照着学生端 payload 写的，键在值为空，比键缺失少一整类 undefined 崩溃。

    `authoring` 段是唯一的写回入口，两条（初始项目 / 示范项目）**已发布时一律为
    null**——把"已发布不能直接改"这条判定留在服务端。Studio 只需照着有没有 URL 决定
    按钮灰不灰，不必自己复述状态机（复述就会有第二份口径，迟早对不上）。

    示范项目的**下载地址放在 `authoring` 而不是 `challenge` 段**：`challenge` 的形状
    要与学生端 payload 对齐，而学生端永远不会有示范项目的下载地址。

    规则原文不在这里下发：Studio 只渲染 `checklist` 中文说明（与学生端同一份），
    要看规则参数请走 `GET /challenges/{id}`，避免同一份数据两处下发后不同步。
    """
    _require_editor(request, db)
    challenge = _get_or_404(db, challenge_id)
    card = _serialize(db, challenge)
    settings = request.app.state.settings
    editable = challenge.status == "draft"
    return {
        "mode": "admin_preview",
        # 只读指的是"不写学生数据"：教研永远不该在预览里产生一条学生作品/提交记录。
        # 写初始项目是另一回事，看 authoring。
        "readonly": True,
        "block": None,
        "challenge": {
            "id": challenge.id,
            "title": challenge.title,
            "instructions_md": challenge.instructions_md,
            "status": challenge.status,
            "version": challenge.version,
            "allowed_extensions": card["allowed_extensions"],
            "hints": card["hints"],
            "checklist": card["checklist"],
            "has_starter": card["has_starter"],
            "starter_url": card["starter_url"],
        },
        "project": None,
        "last_submission": None,
        "analysis": {"available": False, "notice": None},
        "authoring": {
            "can_write_starter": editable,
            # 与 starter 同值，但**必须是独立字段**：Studio 的纪律是"能不能写由服务端
            # 下发的布尔值决定"。让 demo 分支去读 starter 的布尔值，就等于埋了一个
            # "哪天两者规则分叉就默默判错"的坑。
            "can_write_demo": editable,
            "starter_write_url": (
                f"/api/admin/scratch/challenges/{challenge.id}/starter-project"
                if editable else None),
            "demo_write_url": (
                f"/api/admin/scratch/challenges/{challenge.id}/demo-project"
                if editable else None),
            "has_demo": card["has_demo"],
            "demo_url": card["demo_url"],
            "locked_reason": None if editable else
            "已发布的挑战不能直接改，请先撤回为草稿或复制为新版本。",
        },
        "limits": {
            "max_bytes": settings.scratch_sb3_max_bytes,
            "save_rate_max": settings.scratch_save_rate_max,
            "save_rate_seconds": settings.scratch_save_rate_seconds,
        },
    }


@router.post("/challenges/{challenge_id}/submit")
def submit_challenge(challenge_id: int, request: Request, db: Session = Depends(db_session)):
    require_csrf(request)
    admin = _require_editor(request, db)
    challenge = _get_or_404(db, challenge_id)
    if challenge.status != "draft":
        raise HTTPException(409, "只有草稿挑战可以提交审核。")
    _require_publish_ready(challenge)
    challenge.status = "pending"
    challenge.updated_at = utcnow()
    audit(db, request.app.state.settings, "scratch_challenge_submit", "success",
          client_ip(request), admin.id, resource_type="scratch_challenge", resource_id=challenge.id)
    db.commit()
    return _serialize(db, challenge)


@router.post("/challenges/{challenge_id}/approve")
def approve_challenge(challenge_id: int, request: Request, db: Session = Depends(db_session)):
    require_csrf(request)
    admin = _require_editor(request, db)
    challenge = _get_or_404(db, challenge_id)
    if challenge.status != "pending":
        raise HTTPException(409, "只有待审核挑战可以通过。")
    runtime = _require_publish_ready(challenge)
    challenge.status = "published"
    # 审核人记录落库（对齐题目 approve 口径）：即使自审也有据可查。
    challenge.reviewed_by = admin.id
    challenge.reviewed_at = utcnow()
    challenge.updated_at = utcnow()
    audit(db, request.app.state.settings, "scratch_challenge_approve", "success",
          client_ip(request), admin.id, resource_type="scratch_challenge", resource_id=challenge.id,
          summary={"warnings": runtime})
    db.commit()
    db.refresh(challenge)
    return {"challenge": _serialize(db, challenge), "warnings": runtime}


@router.post("/challenges/{challenge_id}/reject")
def reject_challenge(challenge_id: int, payload: RejectScratchPayload,
                     request: Request, db: Session = Depends(db_session)):
    """打回：必填原因落库（对齐题目 `RejectProblemPayload` 口径）。

    录入员在列表就能看到 ⚑ 打回原因，不用打开详情才知道为什么被退；
    审核历史可追溯（rejected_by / rejected_at）。
    """
    require_csrf(request)
    admin = _require_editor(request, db)
    challenge = _get_or_404(db, challenge_id)
    if challenge.status != "pending":
        raise HTTPException(409, "只有待审核挑战可以打回。")
    challenge.status = "draft"
    challenge.rejected_by = admin.id
    challenge.rejected_at = utcnow()
    challenge.rejection_reason = payload.reason.strip()
    challenge.updated_at = utcnow()
    audit(db, request.app.state.settings, "scratch_challenge_reject", "success",
          client_ip(request), admin.id, resource_type="scratch_challenge",
          resource_id=challenge.id, summary={"reason": challenge.rejection_reason})
    db.commit()
    db.refresh(challenge)
    return _serialize(db, challenge)


@router.delete("/challenges/{challenge_id}", status_code=204)
def delete_challenge(challenge_id: int, request: Request, db: Session = Depends(db_session)):
    """删除挑战。与既有题目 `delete_problem` 同一条口径：

    - **draft / published 可删，pending 不可删**（审核中删了，审核员手里的列表就悬空了，
      与既有题目「待审核不给删除」一致）。
    - published 删除同样受「绑定课时块 / 已有学生提交」引用检查约束——被引用的挑战
      409 并说明，删不掉也讲得清为什么（对齐 `_reference_blockers` 的范式）。
    """
    require_csrf(request)
    admin = _require_editor(request, db)
    challenge = _get_or_404(db, challenge_id)
    if challenge.status == "pending":
        raise HTTPException(409, "待审核的挑战不能删除，请先打回。")
    bound = db.scalar(select(func.count()).select_from(LessonScratchBlock)
                      .where(LessonScratchBlock.challenge_id == challenge.id)) or 0
    submissions = db.scalar(select(func.count()).select_from(ScratchSubmission)
                            .where(ScratchSubmission.challenge_id == challenge.id)) or 0
    if bound or submissions:
        raise HTTPException(409, "已绑定课时或已有学生提交的挑战不能删除。")
    db.delete(challenge)
    audit(db, request.app.state.settings, "scratch_challenge_delete", "success",
          client_ip(request), admin.id, resource_type="scratch_challenge", resource_id=challenge_id)
    db.commit()
    return Response(status_code=204)


@router.post("/challenges/{challenge_id}/publish")
def publish_challenge(challenge_id: int, request: Request, db: Session = Depends(db_session)):
    """发布：题面完整性检查 → status=published，并把 version 记成"第几次发布"。

    返回 `warnings`：**不拦截**的提示。含运行型规则的挑战照样能发（教研就是要人工
    点评那一条），但必须让发布的人当场知道"这一关不会自动判过"。
    """
    require_csrf(request)
    admin = _require_editor(request, db)
    challenge = _get_or_404(db, challenge_id)
    if challenge.status == "published":
        return {"challenge": _serialize(db, challenge), "warnings": []}
    runtime = _require_publish_ready(challenge)

    warnings: list[str] = []
    if runtime:
        warnings.append(f"含需要真实运行的规则（{'、'.join(runtime)}），本版会转人工点评。")

    # version = 第几次发布。首次发布保持 1，撤回再发才 +1（提交记录冻结的就是这个数）。
    if challenge.version < 1:
        challenge.version = 1
    challenge.status = "published"
    audit(db, request.app.state.settings, "scratch_challenge_publish", "success",
          client_ip(request), admin.id, resource_type="scratch_challenge",
          resource_id=challenge.id,
          summary={"version": challenge.version, "warnings": warnings})
    db.commit()
    return {"challenge": _serialize(db, challenge), "warnings": warnings}


@router.post("/challenges/{challenge_id}/unpublish")
def unpublish_challenge(challenge_id: int, request: Request,
                        db: Session = Depends(db_session)):
    """撤回成草稿。**版本号在这里 +1**：下一次发布出去的就是新的一版。

    正在被已发布课包引用时拒绝撤回——撤回等于让那节课的学生当场看到"挑战尚未发布"
    的 404，而课包在售、课时可学。要改先下架课包，与内容块编辑同一条链路。
    """
    require_csrf(request)
    admin = _require_editor(request, db)
    challenge = _get_or_404(db, challenge_id)
    if challenge.status != "published":
        return _serialize(db, challenge)
    live = db.scalar(
        select(func.count())
        .select_from(LessonScratchBlock)
        .join(CourseLessonBlock, CourseLessonBlock.id == LessonScratchBlock.block_id)
        .join(CourseLesson, CourseLesson.id == CourseLessonBlock.lesson_id)
        .join(Course, Course.id == CourseLesson.course_id)
        .where(LessonScratchBlock.challenge_id == challenge.id, Course.status == "published")
    ) or 0
    if live:
        raise HTTPException(409, "该挑战正被已发布课包使用，请先下架相关课包。")
    challenge.status = "draft"
    challenge.version = challenge.version + 1
    challenge.updated_at = utcnow()
    audit(db, request.app.state.settings, "scratch_challenge_unpublish", "success",
          client_ip(request), admin.id, resource_type="scratch_challenge",
          resource_id=challenge.id, summary={"next_version": challenge.version})
    db.commit()
    return _serialize(db, challenge)


@router.post("/challenges/{challenge_id}/withdraw")
def withdraw_challenge(challenge_id: int, request: Request, db: Session = Depends(db_session)):
    """`/unpublish` 的别名（21c 管理端按 `withdraw` 写的）。见 upload_starter_alias 的说明。"""
    return unpublish_challenge(challenge_id, request, db)


# ---------------------------------------------------------------------------
# 学生作品（教师侧）：只读列表 / 详情 / 快照下载 / 人工点评
#
# 这一段是 `needs_review` 的闭环。少了它，含运行型规则的挑战交上来就永远挂着：
# 学生看到"已转人工点评"，而系统里没有任何人能点评——那还不如不提供第三态。
# ---------------------------------------------------------------------------


def _review_payload(submission: ScratchSubmission) -> dict | None:
    """教师批改结论的对外形状。未批改过返回 None。

    `items` 直接给 `rubric_scores_json` 里冻结的逐项打分（criterion_id/level/points/note），
    由批改台按「当前量规」渲染勾选态；量规改版后详情页据此提示"本条按旧量规批改"。
    """
    if submission.reviewed_at is None:
        return None
    try:
        scores = json.loads(submission.rubric_scores_json or "{}")
    except (TypeError, json.JSONDecodeError):
        scores = {}
    items = scores.get("items") if isinstance(scores, dict) else None
    return {
        "verdict": submission.status,
        "comment": submission.review_comment or "",
        "reviewed_at": submission.reviewed_at.isoformat() if submission.reviewed_at else None,
        "reviewed_by": submission.reviewed_by,
        "manual_score": submission.manual_score,
        "manual_score_max": submission.manual_score_max,
        "items": items if isinstance(items, list) else [],
    }


def _review_idempotency(
    submission: ScratchSubmission, *, action: str, payload: BaseModel,
    idempotency_key: str | None,
) -> bool:
    """Validate a review retry and return whether it is an accepted duplicate."""
    key = idempotency_key or f"legacy-scratch-{action}:{submission.id}:{uuid4()}"
    key_hash = hashlib.sha256(key.encode("utf-8")).hexdigest()
    input_hash = request_hash({
        "action": action,
        "submission_id": submission.id,
        "payload": payload.model_dump(),
    })
    if submission.last_review_idempotency_key_hash == key_hash:
        if submission.last_review_request_hash != input_hash:
            raise HTTPException(409, "Idempotency-Key 已用于不同请求。")
        return True
    submission.last_review_idempotency_key_hash = key_hash
    submission.last_review_request_hash = input_hash
    return False


def _submission_row(db: Session, submission: ScratchSubmission, *, detail: bool) -> dict:
    try:
        evaluation = json.loads(submission.evaluation_json or "{}")
    except (TypeError, json.JSONDecodeError):
        evaluation = {}
    rules = [r for r in (evaluation.get("rules") or []) if isinstance(r, dict)]
    student = db.get(User, submission.user_id)
    challenge = db.get(ScratchChallenge, submission.challenge_id)
    revision = db.get(ScratchProjectRevision, submission.project_revision_id)
    block = db.get(CourseLessonBlock, submission.lesson_block_id)
    lesson = db.get(CourseLesson, submission.lesson_id)
    row = {
        "id": submission.id,
        "student_id": submission.user_id,
        "student_name": student.username if student else None,
        "challenge_id": submission.challenge_id,
        "challenge_title": challenge.title if challenge else None,
        "challenge_version": submission.challenge_version,
        "lesson_block_id": submission.lesson_block_id,
        "lesson_id": submission.lesson_id,
        "lesson_title": lesson.title if lesson else None,
        "block_title": block.title if block else None,
        "status": submission.status,
        "passed": submission.passed,
        "score": submission.score,
        "attempt_count": submission.attempt_no,
        "submitted_at": submission.submitted_at.isoformat() if submission.submitted_at else None,
        # 快照 = 提交时刻冻结的那一版，**不是**学生当前的工作副本。
        "snapshot": {
            "revision_id": submission.project_revision_id,
            "revision_no": revision.revision_no if revision else None,
            "saved_at": revision.saved_at.isoformat() if revision and revision.saved_at else None,
            "content_hash": f"sha256:{revision.sha256}" if revision else None,
            "size_bytes": revision.size_bytes if revision else None,
            "download_url": f"/api/admin/scratch/submissions/{submission.id}/project.sb3",
        },
        "evaluation": {
            "rules_total": len(rules),
            "rules_passed": sum(1 for r in rules if r.get("passed")),
            "missing": [r.get("label") or r.get("type") for r in rules if not r.get("passed")],
            "unsupported": evaluation.get("unsupported") or [],
        },
        "feedback": submission.review_comment or evaluation.get("note") or "",
        "reviewed": submission.reviewed_at is not None,
        "reviewed_at": submission.reviewed_at.isoformat() if submission.reviewed_at else None,
        "reviewed_by": submission.reviewed_by,
        "review_comment": submission.review_comment,
        # 量规：批改台用「挑战当前量规」打分；`review` 是批改当时冻结的结果。
        "rubric": _parse_rubric(challenge.rubric_json) if challenge else {},
        "review": _review_payload(submission),
        "scripts_url": f"/api/admin/scratch/submissions/{submission.id}/project.json",
    }
    if detail:
        # 详情才给逐条判定与冻结的规则原文：教师要能自证"当时按哪一版规则判的"。
        row["rules"] = rules
        try:
            # 与 evaluation_json / rubric_json 同一条口径：脏数据当空数组，
            # 教师详情页不该因为一条历史脏快照 500。
            rules_snapshot = json.loads(submission.rules_snapshot or "[]")
        except (TypeError, json.JSONDecodeError):
            rules_snapshot = []
        row["rules_snapshot"] = rules_snapshot if isinstance(rules_snapshot, list) else []
    return row


@router.get("/submissions")
def list_submissions(request: Request, db: Session = Depends(db_session),
                     challenge_id: int | None = Query(default=None),
                     lesson_id: int | None = Query(default=None),
                     status: str | None = Query(default=None),
                     keyword: str | None = Query(default=None, max_length=100),
                     latest_only: bool = Query(default=False),
                     page: int = Query(1, ge=1),
                     size: int = Query(20, ge=1, le=100),
                     page_size: int | None = Query(default=None, ge=1, le=100)):
    """按挑战 / 课时 / 状态 / 学生名筛选的只读作品列表。

    `page_size` 与 `size` 都收：管理端按 `page_size` 写的，学生端与其它管理列表用
    `size`。两个都留着比让一整页分页失效便宜（同 rules_json 的处理）。

    `latest_only=true` 时按 `(user_id, lesson_block_id)` 只取 `attempt_no` 最大的那一行
    （批改队列用——一个学生交五次就只排一条）。默认 false，保持"学生作品"只读列表
    看完整历史的行为不变。

    `keyword` 是学生用户名模糊搜索，所以这条与 `.sb3` 下载同级：先过功能角色闸，
    再由 `visible_student_ids()` 把查询收窄到当前可见学生。
    """
    admin = _require_submission_reader(request, db)
    student_ids = visible_student_ids(admin, db)
    limit_size = page_size or size
    stmt = select(ScratchSubmission)
    if student_ids is not None:
        stmt = stmt.where(ScratchSubmission.user_id.in_(student_ids))
    if challenge_id:
        stmt = stmt.where(ScratchSubmission.challenge_id == challenge_id)
    if lesson_id:
        stmt = stmt.where(ScratchSubmission.lesson_id == lesson_id)
    if status:
        stmt = stmt.where(ScratchSubmission.status == status)
    if keyword:
        stmt = stmt.join(User, User.id == ScratchSubmission.user_id).where(
            User.username.like(f"%{keyword}%"))
    if latest_only:
        # 子查询求每组最大 attempt_no 再 join 回来，避开窗口函数（SQLite 老版本兼容）。
        latest = (
            select(
                ScratchSubmission.user_id,
                ScratchSubmission.lesson_block_id,
                func.max(ScratchSubmission.attempt_no).label("max_attempt"),
            )
            .group_by(ScratchSubmission.user_id, ScratchSubmission.lesson_block_id)
            .subquery()
        )
        stmt = stmt.join(
            latest,
            and_(
                ScratchSubmission.user_id == latest.c.user_id,
                ScratchSubmission.lesson_block_id == latest.c.lesson_block_id,
                ScratchSubmission.attempt_no == latest.c.max_attempt,
            ),
        )
    total = db.scalar(stmt.with_only_columns(func.count(ScratchSubmission.id)).order_by(None)) or 0
    rows = db.scalars(
        stmt.order_by(ScratchSubmission.submitted_at.desc(), ScratchSubmission.id.desc())
        .offset((page - 1) * limit_size).limit(limit_size)
    ).all()
    return {"total": total, "page": page, "page_size": limit_size,
            "items": [_submission_row(db, row, detail=False) for row in rows]}


@router.get("/submissions/{submission_id}")
def get_submission(submission_id: int, request: Request, db: Session = Depends(db_session)):
    """单份提交详情；角色闸与学生范围校验都先于响应序列化。"""
    admin = _require_submission_reader(request, db)
    student_ids = visible_student_ids(admin, db)
    submission = _load_visible_submission(db, admin, submission_id, student_ids)
    return _submission_row(db, submission, detail=True)


@router.get("/submissions/{submission_id}/project.sb3")
def download_submission_project(submission_id: int, request: Request,
                                db: Session = Depends(db_session)):
    """下载**提交时冻结的那一版**作品。

    刻意不提供"下载学生当前工作副本"的入口：老师看到的必须是判定时的那份，
    否则学生交完再改两下，老师回看到的作品与判定证据对不上（模型注释同）。

    这是本模块泄露面最大的一条（整份作品源文件），鉴权见 `_require_submission_reader`。
    """
    admin = _require_submission_reader(request, db)
    student_ids = visible_student_ids(admin, db)
    submission = _load_visible_submission(db, admin, submission_id, student_ids)
    revision = db.get(ScratchProjectRevision, submission.project_revision_id)
    data = read_sb3(revision.sb3_key, request.app.state.settings) if revision else None
    if data is None:
        raise HTTPException(404, "作品快照文件丢失。")
    return Response(
        content=data, media_type="application/x.scratch.sb3",
        headers={"Content-Disposition":
                 f'attachment; filename="submission-{submission.id}.sb3"',
                 "Cache-Control": "private, no-store"},
    )


@router.get("/submissions/{submission_id}/project.json")
def download_submission_project_json(submission_id: int, request: Request,
                                     db: Session = Depends(db_session)):
    """只返回提交时冻结版本的 `project.json`（批改台画积木图用）。

    整包 `.sb3` 含素材，动辄几 MB；这里只解出 `project.json` 一个条目，前端不必
    再引 JSZip 自己解压。鉴权口径与 `.sb3` 下载一致：卡 `_require_submission_reader`。
    """
    admin = _require_submission_reader(request, db)
    student_ids = visible_student_ids(admin, db)
    submission = _load_visible_submission(db, admin, submission_id, student_ids)
    revision = db.get(ScratchProjectRevision, submission.project_revision_id)
    if revision is None:
        raise HTTPException(404, "作品快照文件丢失。")
    raw = read_sb3(revision.sb3_key, request.app.state.settings)
    if raw is None:
        raise HTTPException(404, "作品快照文件丢失。")
    try:
        project = read_project_json(raw)
    except Sb3Invalid as exc:
        raise HTTPException(400, exc.message) from exc
    return Response(
        content=json.dumps(project, ensure_ascii=False),
        media_type="application/json",
        headers={"Cache-Control": "private, no-store"},
    )


@router.post("/submissions/{submission_id}/review")
def review_submission(submission_id: int, payload: ReviewPayload, request: Request,
                      idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
                      db: Session = Depends(db_session)):
    """人工点评：给挂起（或误判）的提交一个终态。

    点评为通过时**走的是既有完成流程**（`courses._record_completion`），与自动判定
    通过、`/complete`、`/watch` 是同一条写入路径——完成记录只增不减，重复点评幂等。

    点评为未通过时**不撤销**已经写下的完成记录：`lesson_block_completions` 是只增
    不减的事实表（models 里那条注释），把学生已经拿到的进度收回去会让课时进度
    反向抖动，也不是"点评"这个动作该有的破坏力。要退回重做是另一个动作（`/return`）。

    量规打分（`payload.rubric`）见 `_apply_rubric`：挑战绑了量规则必填且须覆盖全部
    准则，没绑则必须为空；`manual_score` 由后端查表汇总，写库时把挑战当前量规冻结
    进 `rubric_snapshot`。
    """
    require_csrf(request)
    admin = _require_submission_reader(request, db)
    student_ids = visible_student_ids(admin, db)
    submission = _load_visible_submission(db, admin, submission_id, student_ids)
    if _review_idempotency(submission, action="review", payload=payload,
                           idempotency_key=idempotency_key):
        return {"submission": _submission_row(db, submission, detail=True),
                "completed": submission.status == "passed", "idempotent": True}
    challenge = db.get(ScratchChallenge, submission.challenge_id)

    rubric_result = _apply_rubric(challenge, payload.rubric) if challenge else None
    if rubric_result is not None:
        scores_dict, manual_score, manual_score_max = rubric_result
        submission.rubric_snapshot = challenge.rubric_json
        submission.rubric_scores_json = json.dumps(scores_dict, ensure_ascii=False)
        submission.manual_score = manual_score
        submission.manual_score_max = manual_score_max

    submission.status = payload.verdict
    submission.passed = payload.verdict == "passed"
    submission.review_comment = payload.comment or None
    submission.reviewed_by = admin.id
    submission.reviewed_at = utcnow()
    submission.review_revision += 1

    completed = False
    if submission.passed:
        student = db.get(User, submission.user_id)
        block = db.get(CourseLessonBlock, submission.lesson_block_id)
        if student is not None and block is not None:
            before = completed_block_ids(db, student, submission.lesson_id)
            _record_completion(db, student, block, submission.lesson_id,
                               COMPLETION_SOURCE, before, commit=False)
            completed = True
    audit(db, request.app.state.settings, "scratch_submission_review", "success",
          client_ip(request), admin.id, resource_type="scratch_submission",
          resource_id=submission.id,
          summary={"verdict": payload.verdict, "completed": completed,
                   "manual_score": submission.manual_score})
    create_notification(
        db, kind="homework_graded", title="作品批改完成",
        body="你的 Scratch 作品已完成批改，请查看结果。",
        target_type="scratch_submission", target_id=submission.id,
        source_type="scratch_submission", source_id=submission.id,
        link_url=lesson_homework_link(submission.lesson_id, submission.lesson_block_id),
        created_by=admin.id,
        idempotency_key=f"scratch-review:{submission.id}:{submission.review_revision}:{submission.user_id}",
        recipients=[{"user_id": submission.user_id, "admin_user_id": None}],
    )
    db.commit()
    return {"submission": _submission_row(db, submission, detail=True),
            "completed": completed}


@router.post("/submissions/{submission_id}/return")
def return_submission(submission_id: int, payload: ReturnPayload, request: Request,
                      idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
                      db: Session = Depends(db_session)):
    """退回重做：明确告诉学生"改完再交一次"，**不是终态**。

    与 `/review` 的差别只在两点：`comment` 必填（不说要改什么，学生只会原样再交一遍，
    队列里就多一条垃圾）、`status` 写成 `returned`（老行保持 returned 作为历史，学生
    重交产生新行 attempt_no + 1）。

    **不写完成记录，也不撤销已有完成记录**（沿用 `/review` 未通过那条裁定）：
    `passed → returned` 时学生的课时进度已经涨过，按回去会造成进度反向抖动、解锁链
    烂账。界面照实说"进度已经记上了，但老师希望你再改一版"。

    幂等：对已是 `returned` 的行再调一次，覆盖评语和时间，不报错。
    """
    require_csrf(request)
    admin = _require_submission_reader(request, db)
    student_ids = visible_student_ids(admin, db)
    submission = _load_visible_submission(db, admin, submission_id, student_ids)
    if _review_idempotency(submission, action="return", payload=payload,
                           idempotency_key=idempotency_key):
        return {"submission": _submission_row(db, submission, detail=True),
                "idempotent": True}
    challenge = db.get(ScratchChallenge, submission.challenge_id)

    rubric_result = _apply_rubric(challenge, payload.rubric) if challenge else None
    if rubric_result is not None:
        scores_dict, manual_score, manual_score_max = rubric_result
        submission.rubric_snapshot = challenge.rubric_json
        submission.rubric_scores_json = json.dumps(scores_dict, ensure_ascii=False)
        submission.manual_score = manual_score
        submission.manual_score_max = manual_score_max

    submission.status = "returned"
    submission.passed = False
    submission.review_comment = payload.comment
    submission.reviewed_by = admin.id
    submission.reviewed_at = utcnow()
    submission.review_revision += 1

    audit(db, request.app.state.settings, "scratch_submission_return", "success",
          client_ip(request), admin.id, resource_type="scratch_submission",
          resource_id=submission.id, summary={"manual_score": submission.manual_score})
    create_notification(
        db, kind="homework_returned", title="作品需要修改后重新提交",
        body="教师已退回你的 Scratch 作品，请查看反馈后重新提交。",
        target_type="scratch_submission", target_id=submission.id,
        source_type="scratch_submission", source_id=submission.id,
        link_url=lesson_homework_link(submission.lesson_id, submission.lesson_block_id),
        created_by=admin.id,
        idempotency_key=f"scratch-return:{submission.id}:{submission.review_revision}:{submission.user_id}",
        recipients=[{"user_id": submission.user_id, "admin_user_id": None}],
    )
    db.commit()
    return {"submission": _submission_row(db, submission, detail=True)}
