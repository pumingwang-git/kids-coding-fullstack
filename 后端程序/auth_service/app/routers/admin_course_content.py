"""后台课时内容块（积木化编排）：块 CRUD / 排序 / 素材选项 / 结构化校验。

对接交文档《11、课包内容积木化编排-开发交接》§6：
- `GET  /api/admin/lessons/{lesson_id}/blocks`      查询课时块
- `POST /api/admin/lessons/{lesson_id}/blocks`      新增块（追加到课时末尾）
- `PUT  /api/admin/lesson-blocks/{block_id}`        全量更新块（含类型明细，整块提交）
- `DELETE /api/admin/lesson-blocks/{block_id}`      删除块（解除引用，素材本体保留）
- `POST /api/admin/lessons/{lesson_id}/blocks/reorder` 排序（完整有序 id 数组）
- `GET  /api/admin/papers/options`                  试卷素材选择器（服务端分页搜索）

口径说明：
- 块类型是块的骨架，**更新不允许改类型**（要换类型请删后重建），避免明细表错位；
- 更新采用全量覆盖：前端提交完整块（含全部明细字段），缺省字段按默认值重置；
- **v2 单题化双分支**（《课中练习重构-实现计划-v2》§4.1）：practice 块只绑单题
  （lesson_problem_blocks，`detail.problem`），homework 块保持绑卷（lesson_paper_blocks，
  `detail.paper`）；practice 传 paper / homework 传 problem 一律 400；
- `attempt_limit` 入库前统一处理「0 → NULL」（0 表示不限次数，不保留两种含义）；
- 删除块/课时后在同一事务压实剩余 sort_order 为 0..n-1；
- 权限与 admin_videos 同口径：editor/super_admin 可写，reviewer 只读。
"""
from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from ..attempt_source import SOURCE_LESSON_HOMEWORK, attempt_count_for
from ..course_access import UNLOCK_RULES  # 解锁规则枚举只有一份，不在本文件另立
from ..models import (
    AdminUser,
    Course,
    CourseLesson,
    CourseLessonBlock,
    LessonBlockMaterial,
    LessonMarkdownBlock,
    LessonPaperBlock,
    LessonProblemBlock,
    LessonScratchBlock,
    LessonVideoBlock,
    MaterialAsset,
    Paper,
    PaperAttempt,
    PaperQuestion,
    Problem,
    ScratchChallenge,
    ScratchSubmission,
    Video,
    VideoVariant,
)
from ..permissions import is_editor, visible_student_ids
from .admin_auth import audit, client_ip, current_admin, db_session, require_csrf

router = APIRouter(prefix="/api/admin", tags=["admin-course-content"])

BLOCK_TYPES = {"markdown", "video", "practice", "homework", "materials", "scratch"}
PAPER_MODES = {"practice", "homework"}
# 视频来源三态（2026-08-10 定稿，替代 platform/external 二态）：
#   platform = 平台自建视频（走 /play 令牌 HLS）
#   embed    = 外链 iframe 嵌入播放器地址（B 站/腾讯等官方嵌入页）
#   direct   = 外链 MP4/HLS 直链（交给 Video.js 播放，不再进 iframe）
VIDEO_SOURCE_TYPES = {"platform", "embed", "direct"}


# ---------- 请求模型 ----------


def _only_http_url(v: str | None) -> str | None:
    if v is None:
        return v
    if not (v.startswith("http://") or v.startswith("https://")):
        raise ValueError("仅支持 http/https 外链地址")
    return v


class MarkdownDetailPayload(BaseModel):
    content_md: str = ""


class VideoDetailPayload(BaseModel):
    source_type: str = "platform"  # platform/embed/direct
    video_id: int | None = None
    video_url: str | None = Field(default=None, max_length=512)
    completion_percent: int = Field(default=100, ge=0, le=100)

    @field_validator("video_url")
    @classmethod
    def _check_video_url(cls, v: str | None) -> str | None:
        return _only_http_url(v)

    @field_validator("source_type")
    @classmethod
    def _check_source_type(cls, v: str) -> str:
        if v not in VIDEO_SOURCE_TYPES:
            raise ValueError("source_type 只允许 platform / embed / direct")
        return v


class PaperDetailPayload(BaseModel):
    """课后练习（homework）块明细：绑定一张试卷 + 投放规则（v2 起仅服务 homework）。"""

    paper_id: int
    mode: str = "homework"  # practice/homework（迁移后恒为 homework，校验见 _apply_detail）
    attempt_limit: int | None = Field(default=None, ge=0)  # 0 = 不限次数（入库转 NULL）
    shuffle_questions: bool = True
    shuffle_options: bool = True
    show_score: bool = True
    show_analysis: bool = True
    due_at: datetime | None = None

    @field_validator("mode")
    @classmethod
    def _check_mode(cls, v: str) -> str:
        if v not in PAPER_MODES:
            raise ValueError("mode 只允许 practice / homework")
        return v


class HomeworkDeadlineExtensionPayload(BaseModel):
    due_at: datetime


class ProblemDetailPayload(BaseModel):
    """课中练习（practice）块明细：绑定题库单题 + 投放规则（v2 单题化，§3.1）。

    `problem_type` 不接收前端传值：由服务端从 `problems.type` 回填冗余快照
    （快照只用于管理端列表展示/筛选，作答判分以题库实际值为准，见实现计划 v2 §3.1 说明 4）。
    """

    problem_id_no: str = Field(min_length=1, max_length=64)
    display_no: str | None = Field(default=None, max_length=32)  # NULL = 回退该课时内 practice 块间序号
    score: int = Field(default=0, ge=0)  # 默认 0（Q5 已定），发布检查输出不拦截的 problem_score_zero 提示
    attempt_limit: int | None = Field(default=None, ge=0)  # 0 = 不限次数（入库转 NULL）
    shuffle_options: bool = True
    show_analysis: bool = True


class ScratchDetailPayload(BaseModel):
    """Scratch 块明细：**只有一个 challenge_id**（任务书 21b 强制约束第 1 条）。

    题面、初始项目、允许扩展、判定规则全部住在 `scratch_challenges`，由
    `/api/admin/scratch/challenges` 维护。把这些配置塞进内容块的话，两节课复用
    同一关卡就得复制一份，改题面要改 N 处。
    """

    challenge_id: int


class BlockDetailPayload(BaseModel):
    """任意块类型的可选明细；由 create/update 按 block_type 挑对应的那个。"""

    markdown: MarkdownDetailPayload | None = None
    video: VideoDetailPayload | None = None
    paper: PaperDetailPayload | None = None
    problem: ProblemDetailPayload | None = None
    scratch: ScratchDetailPayload | None = None


class BlockPayload(BaseModel):
    block_type: str = Field(min_length=1, max_length=16)
    title: str = Field(default="", max_length=200)
    required: bool = True
    # Gate B 路径闸（0034 起）：free=任意顺序学 / sequential=前面「必修且有权限」的块完成才开
    unlock_rule: str = Field(default="free", max_length=16)
    detail: BlockDetailPayload | None = None

    @field_validator("block_type")
    @classmethod
    def _check_block_type(cls, v: str) -> str:
        if v not in BLOCK_TYPES:
            raise ValueError(
                "block_type 只允许 markdown / video / practice / homework / materials / scratch")
        return v

    @field_validator("unlock_rule")
    @classmethod
    def _check_unlock_rule(cls, v: str) -> str:
        if v not in UNLOCK_RULES:
            raise ValueError("unlock_rule 只允许 free / sequential")
        return v


class ReorderBlocksPayload(BaseModel):
    ids: list[int] = Field(min_length=1)


# ---------- 序列化 ----------


def _video_playable(db: Session, video_id: int | None) -> tuple[str | None, bool]:
    """视频块的转码状态 + 可播判定，与 admin_courses 的 _serialize_lesson 同口径。"""
    if video_id is None:
        return None, False
    v = db.get(Video, video_id)
    if v is None:
        return None, False
    playable = False
    if v.primary_variant_id:
        variant = db.get(VideoVariant, v.primary_variant_id)
        playable = bool(
            variant and variant.status == "ready" and variant.object_key.endswith(".m3u8")
        )
    return v.status, playable


def _serialize_block(db: Session, block: CourseLessonBlock) -> dict:
    payload: dict = {
        "id": block.id,
        "block_type": block.block_type,
        "title": block.title,
        "sort_order": block.sort_order,
        "required": block.required,
        "unlock_rule": block.unlock_rule,
        "created_at": block.created_at.isoformat() if block.created_at else None,
    }
    if block.block_type == "markdown":
        md = db.get(LessonMarkdownBlock, block.id)
        payload["markdown"] = {"content_md": md.content_md if md else ""}
    elif block.block_type == "video":
        vd = db.get(LessonVideoBlock, block.id)
        if vd is None:
            payload["video"] = {"source_type": "platform", "video_id": None, "video_url": None,
                                "status": None, "playable": False, "completion_percent": 100}
        else:
            status, playable = _video_playable(db, vd.video_id)
            payload["video"] = {
                "source_type": vd.source_type,
                "video_id": vd.video_id,
                "video_url": vd.video_url,
                "status": status,
                "playable": playable,
                "completion_percent": vd.completion_percent,
            }
    elif block.block_type == "practice":
        # v2 单题化：practice 块挂 lesson_problem_blocks（单题明细），不再绑卷。
        pb_ = db.get(LessonProblemBlock, block.id)
        if pb_ is None:
            payload["problem"] = {"problem_id_no": None, "problem_type": None, "display_no": None,
                                  "score": 0, "attempt_limit": None,
                                  "shuffle_options": True, "show_analysis": True}
        else:
            payload["problem"] = {
                "problem_id_no": pb_.problem_id_no,
                "problem_type": pb_.problem_type,
                "display_no": pb_.display_no,
                "score": pb_.score,
                "attempt_limit": pb_.attempt_limit,
                "shuffle_options": pb_.shuffle_options,
                "show_analysis": pb_.show_analysis,
            }
    elif block.block_type == "homework":
        # 课后练习保持绑卷现状（lesson_paper_blocks 收窄为只服务 homework）。
        pd_ = db.get(LessonPaperBlock, block.id)
        if pd_ is None:
            payload["paper"] = {"paper_id": None, "mode": block.block_type, "attempt_limit": None,
                                "shuffle_questions": True, "shuffle_options": True,
                                "show_score": True, "show_analysis": True, "due_at": None}
        else:
            payload["paper"] = {
                "paper_id": pd_.paper_id,
                "mode": pd_.mode,
                "attempt_limit": pd_.attempt_limit,
                "shuffle_questions": pd_.shuffle_questions,
                "shuffle_options": pd_.shuffle_options,
                "show_score": pd_.show_score,
                "show_analysis": pd_.show_analysis,
                "due_at": pd_.due_at.isoformat() if pd_.due_at else None,
            }
    elif block.block_type == "scratch":
        sc_ = db.get(LessonScratchBlock, block.id)
        challenge = db.get(ScratchChallenge, sc_.challenge_id) if sc_ else None
        payload["scratch"] = {
            "challenge_id": sc_.challenge_id if sc_ else None,
            # 挑战标题/状态是**快照式展示**，不是绑定的一部分：管理端块卡片要一眼看出
            # "绑的哪一关、发布了没有"，否则未发布挑战的块看起来完全正常，
            # 学生点进去却是 404。
            "challenge_title": challenge.title if challenge else None,
            "challenge_status": challenge.status if challenge else None,
            "challenge_version": challenge.version if challenge else None,
            "has_starter": bool(challenge and challenge.starter_sb3_key),
        }
    elif block.block_type == "materials":
        # 阅读资料块：无明细表，绑定关系在 lesson_block_materials 关联表（交接文档 §6）。
        # 只回列表所需字段；完整摘要走 /lesson-blocks/{id}/materials。
        payload["materials"] = [
            {
                "material_id": material_id,
                "display_name": display_name,
                "asset_type": asset_type,
                "size_bytes": size_bytes,
                "status": status,
                "sha256": sha256,
            }
            for material_id, display_name, asset_type, size_bytes, status, sha256 in db.execute(
                select(
                    MaterialAsset.id,
                    MaterialAsset.display_name,
                    MaterialAsset.asset_type,
                    MaterialAsset.size_bytes,
                    MaterialAsset.status,
                    MaterialAsset.sha256,
                )
                .join(LessonBlockMaterial, LessonBlockMaterial.material_id == MaterialAsset.id)
                .where(LessonBlockMaterial.block_id == block.id)
                .order_by(LessonBlockMaterial.sort_order, LessonBlockMaterial.id)
            ).all()
        ]
    return payload


def _serialize_lesson_meta(lesson: CourseLesson) -> dict:
    return {
        "id": lesson.id,
        "title": lesson.title,
        "summary": lesson.summary,
        "is_trial": lesson.is_trial,
        "open_policy": lesson.open_policy,
        "trial_block_count": lesson.trial_block_count,
        "trial_minutes": lesson.trial_minutes,
        "duration_minutes": lesson.duration_minutes,
    }


# ---------- 校验辅助 ----------


def _get_lesson_or_404(db: Session, lesson_id: int) -> CourseLesson:
    lesson = db.get(CourseLesson, lesson_id)
    if lesson is None:
        raise HTTPException(404, "课时不存在。")
    return lesson


def _require_editable(db: Session, lesson: CourseLesson) -> None:
    course = db.get(Course, lesson.course_id)
    if course is None:
        raise HTTPException(404, "课包不存在。")
    if course.status == "published":
        raise HTTPException(409, "已发布课包请先下架再编辑。")
    return None


def _next_sort_order(db: Session, lesson_id: int) -> int:
    max_order = db.scalar(
        select(func.max(CourseLessonBlock.sort_order)).where(CourseLessonBlock.lesson_id == lesson_id)
    )
    # 注意不能用 `max_order or -1`：max=0 时 0 是 falsy，会把 0 误判成空表。
    return 0 if max_order is None else max_order + 1


def _apply_detail(
    db: Session,
    block: CourseLessonBlock,
    detail: BlockDetailPayload | None,
    admin, request,
) -> None:
    """按 block_type 创建/替换类型明细行。块类型不可改（调用方保证）。"""
    if block.block_type == "markdown":
        md = detail.markdown if detail and detail.markdown else MarkdownDetailPayload()
        if not md.content_md.strip():
            raise HTTPException(400, "图文块正文不能为空。")
        db.add(LessonMarkdownBlock(block_id=block.id, content_md=md.content_md))
    elif block.block_type == "video":
        vd = detail.video if detail and detail.video else VideoDetailPayload()
        if vd.source_type == "platform":
            if vd.video_id is None:
                raise HTTPException(400, "平台视频块必须绑定一个视频。")
            if db.get(Video, vd.video_id) is None:
                raise HTTPException(400, "绑定的视频不存在。")
            db.add(LessonVideoBlock(block_id=block.id, source_type="platform", video_id=vd.video_id,
                                    video_url=None, completion_percent=vd.completion_percent))
        else:  # embed / direct：都是外链地址，只是学生端渲染方式不同（iframe / Video.js）
            if not vd.video_url:
                raise HTTPException(400, "外链视频块必须填写外链地址。")
            db.add(LessonVideoBlock(block_id=block.id, source_type=vd.source_type, video_id=None,
                                    video_url=vd.video_url, completion_percent=vd.completion_percent))
    elif block.block_type == "scratch":
        sc_ = detail.scratch if detail and detail.scratch else None
        if sc_ is None:
            raise HTTPException(400, "Scratch 块必须绑定一个挑战。")
        challenge = db.get(ScratchChallenge, sc_.challenge_id)
        if challenge is None:
            raise HTTPException(400, "绑定的挑战不存在。")
        # 允许绑草稿挑战：教研的顺序常常是"先建块占位、再把关卡做完发布"。
        # 未发布的后果由发布检查（admin_courses._lesson_block_problems）拦在上架前，
        # 学生端也会 404，不会读到半成品题面。
        db.add(LessonScratchBlock(block_id=block.id, challenge_id=sc_.challenge_id))
    elif block.block_type == "practice":
        # v2 单题化：practice 块只能绑单题（problem_id_no）；绑卷在老前端/脏数据场景
        # 已不合法，直接 400 比静默写错表安全（实现计划 v2 §4.1.2 / §6.5）。
        if detail and detail.paper is not None:
            raise HTTPException(400, "课中练习块请绑定题目（课后练习才绑定试卷）。")
        pb_ = detail.problem if detail and detail.problem else None
        if pb_ is None:
            raise HTTPException(400, "课中练习块必须绑定一道题目。")
        problem = db.scalar(
            select(Problem).where(
                Problem.problem_id_no == pb_.problem_id_no,
                Problem.status == "approved",
            )
        )
        if problem is None:
            raise HTTPException(400, "绑定的题目不存在或未审核通过。")
        db.add(LessonProblemBlock(
            block_id=block.id,
            problem_id_no=pb_.problem_id_no,
            problem_type=problem.type,          # 冗余快照，服务端回填（不信任前端传值）
            display_no=pb_.display_no,
            score=pb_.score,
            attempt_limit=None if pb_.attempt_limit == 0 else pb_.attempt_limit,
            shuffle_options=pb_.shuffle_options,
            show_analysis=pb_.show_analysis,
        ))
    else:  # homework —— 保持现状（绑卷分支，含 mode 强校验）
        if detail and detail.problem is not None:
            raise HTTPException(400, "课后练习块请绑定试卷（课中练习才绑定题目）。")
        pd_ = detail.paper if detail and detail.paper else None
        if pd_ is None:
            raise HTTPException(400, "课后练习块必须绑定一张试卷。")
        if pd_.mode != block.block_type:
            raise HTTPException(400, "块类型与试卷模式不一致。")
        if db.get(Paper, pd_.paper_id) is None:
            raise HTTPException(400, "绑定的试卷不存在。")
        db.add(LessonPaperBlock(
            block_id=block.id,
            paper_id=pd_.paper_id,
            mode=pd_.mode,
            attempt_limit=None if pd_.attempt_limit == 0 else pd_.attempt_limit,
            shuffle_questions=pd_.shuffle_questions,
            shuffle_options=pd_.shuffle_options,
            show_score=pd_.show_score,
            show_analysis=pd_.show_analysis,
            due_at=pd_.due_at,
        ))


def _apply_materials_block(db: Session, block: CourseLessonBlock, detail: BlockDetailPayload | None) -> None:
    """阅读资料块的创建/更新处理：无类型明细表，仅占位（绑定走独立关联接口）。"""
    if detail and (detail.markdown or detail.video or detail.paper or detail.problem
                   or detail.scratch):
        raise HTTPException(400, "阅读资料块不支持内容明细，请通过资料绑定接口添加资料。")


def _deadline_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


# ---------- 查询 ----------


@router.get("/lessons/{lesson_id}/blocks")
def list_lesson_blocks(lesson_id: int, request: Request, db: Session = Depends(db_session)):
    """课时内容块列表：课时元数据 + 有序块（含各自类型明细与管理端状态）。"""
    current_admin(request, db)
    lesson = _get_lesson_or_404(db, lesson_id)
    blocks = db.scalars(
        select(CourseLessonBlock).where(CourseLessonBlock.lesson_id == lesson_id)
        .order_by(CourseLessonBlock.sort_order, CourseLessonBlock.id)
    ).all()
    return {
        "lesson": _serialize_lesson_meta(lesson),
        "blocks": [_serialize_block(db, b) for b in blocks],
    }


# ---------- 新增 ----------


@router.post("/lessons/{lesson_id}/blocks", status_code=201)
def create_block(lesson_id: int, payload: BlockPayload, request: Request, db: Session = Depends(db_session)):
    require_csrf(request)
    admin = current_admin(request, db)
    if not is_editor(admin):
        raise HTTPException(403, "没有编辑课程内容的权限。")
    lesson = _get_lesson_or_404(db, lesson_id)
    _require_editable(db, lesson)
    block = CourseLessonBlock(
        lesson_id=lesson_id,
        block_type=payload.block_type,
        title=payload.title,
        sort_order=_next_sort_order(db, lesson_id),
        required=payload.required,
        unlock_rule=payload.unlock_rule,
    )
    db.add(block)
    db.flush()  # 拿到 block.id 才能写明细
    if block.block_type == "materials":
        _apply_materials_block(db, block, payload.detail)
    else:
        _apply_detail(db, block, payload.detail, admin, request)
    audit(db, request.app.state.settings, "course_block_create", "success",
          client_ip(request), admin.id, resource_type="course_lesson_block",
          summary={"lesson_id": lesson_id, "block_type": payload.block_type})
    db.commit()
    return _serialize_block(db, block)


# ---------- 更新（全量覆盖） ----------


@router.put("/lesson-blocks/{block_id}")
def update_block(block_id: int, payload: BlockPayload, request: Request, db: Session = Depends(db_session)):
    require_csrf(request)
    admin = current_admin(request, db)
    if not is_editor(admin):
        raise HTTPException(403, "没有编辑课程内容的权限。")
    block = db.get(CourseLessonBlock, block_id)
    if block is None:
        raise HTTPException(404, "内容块不存在。")
    _require_editable(db, db.get(CourseLesson, block.lesson_id))
    if payload.block_type != block.block_type:
        raise HTTPException(400, "内容块类型不可变更，请删除后重建。")
    block.title = payload.title
    block.required = payload.required
    block.unlock_rule = payload.unlock_rule
    if block.block_type == "homework":
        old_detail = db.get(LessonPaperBlock, block.id)
        new_paper = payload.detail.paper if payload.detail and payload.detail.paper else None
        new_paper_id = new_paper.paper_id if new_paper else None
        if old_detail is not None:
            attempt_count = attempt_count_for(db, SOURCE_LESSON_HOMEWORK, block.id)
            if attempt_count and old_detail.paper_id != new_paper_id:
                audit(db, request.app.state.settings, "course_block_update", "failure",
                      client_ip(request), admin.id, resource_type="course_lesson_block",
                      resource_id=block.id,
                      summary={"attempt_count": attempt_count, "reason": "paper_changed",
                               "old_paper_id": old_detail.paper_id, "new_paper_id": new_paper_id})
                db.commit()
                raise HTTPException(409, "该作业已有作答记录，不能更换试卷；请新建作业块。")
            new_due_at = new_paper.due_at if new_paper else None
            if attempt_count and _deadline_utc(old_detail.due_at) != _deadline_utc(new_due_at):
                audit(db, request.app.state.settings, "course_block_update", "failure",
                      client_ip(request), admin.id, resource_type="course_lesson_block",
                      resource_id=block.id,
                      summary={"attempt_count": attempt_count, "reason": "deadline_changed",
                               "old_due_at": _deadline_utc(old_detail.due_at).isoformat() if old_detail.due_at else None,
                               "new_due_at": _deadline_utc(new_due_at).isoformat() if new_due_at else None})
                db.commit()
                raise HTTPException(409, "该作业已有作答记录，普通编辑不能修改作业截止时间；请使用“延长截止时间”。")
    if block.block_type == "materials":
        # 阅读资料块：无明细表，不重建；资料绑定走独立关联接口，全量覆盖不影响已绑定关系。
        _apply_materials_block(db, block, payload.detail)
    else:
        # 全量覆盖：先删旧明细再按新载荷重建，避免残留下一次编辑的旧字段。
        if block.block_type == "markdown":
            db.execute(delete(LessonMarkdownBlock).where(LessonMarkdownBlock.block_id == block_id))
        elif block.block_type == "video":
            db.execute(delete(LessonVideoBlock).where(LessonVideoBlock.block_id == block_id))
        elif block.block_type == "practice":
            db.execute(delete(LessonProblemBlock).where(LessonProblemBlock.block_id == block_id))
        elif block.block_type == "scratch":
            db.execute(delete(LessonScratchBlock).where(LessonScratchBlock.block_id == block_id))
        else:  # homework
            db.execute(delete(LessonPaperBlock).where(LessonPaperBlock.block_id == block_id))
        _apply_detail(db, block, payload.detail, admin, request)
    audit(db, request.app.state.settings, "course_block_update", "success",
          client_ip(request), admin.id, resource_type="course_lesson_block", resource_id=block_id)
    db.commit()
    return _serialize_block(db, block)


@router.post("/lesson-blocks/{block_id}/extend-deadline")
def extend_homework_deadline(block_id: int, payload: HomeworkDeadlineExtensionPayload,
                             request: Request, db: Session = Depends(db_session)):
    """显式延长课时作业截止时间，并同步尚未提交的作答。"""
    require_csrf(request)
    admin = current_admin(request, db)
    if not is_editor(admin):
        raise HTTPException(403, "没有编辑课程内容的权限。")
    student_ids = visible_student_ids(admin, db)
    if student_ids is not None and not student_ids:
        raise HTTPException(403, "当前没有可管理的学生范围。")
    block = db.get(CourseLessonBlock, block_id)
    if block is None or block.block_type != "homework":
        raise HTTPException(404, "课时作业块不存在。")
    # 延期是已发布课包运行期间的管理动作，是“发布后禁止改内容”的唯一例外。
    lesson = db.get(CourseLesson, block.lesson_id)
    if lesson is None or db.get(Course, lesson.course_id) is None:
        raise HTTPException(404, "课时或课包不存在。")
    detail = db.get(LessonPaperBlock, block_id)
    if detail is None:
        raise HTTPException(404, "课时作业配置不存在。")

    old_due_at = _deadline_utc(detail.due_at)
    new_due_at = _deadline_utc(payload.due_at)
    now = datetime.now(UTC)
    if old_due_at is None:
        raise HTTPException(409, "该作业当前为长期有效，无需延长截止时间。")
    if new_due_at is None or new_due_at <= old_due_at:
        raise HTTPException(400, "新的作业截止时间必须晚于当前截止时间。")
    if new_due_at <= now:
        raise HTTPException(400, "新的作业截止时间必须晚于当前时间。")

    detail.due_at = new_due_at
    ongoing_query = select(PaperAttempt).where(
        PaperAttempt.source_type == SOURCE_LESSON_HOMEWORK,
        PaperAttempt.source_id == block_id,
        PaperAttempt.status == "ongoing",
    )
    if student_ids is not None:
        ongoing_query = ongoing_query.where(PaperAttempt.user_id.in_(student_ids))
    ongoing = db.scalars(ongoing_query).all()
    for attempt in ongoing:
        attempt.deadline_at = new_due_at
    audit(db, request.app.state.settings, "course_homework_deadline_extend", "success",
          client_ip(request), admin.id, resource_type="course_lesson_block",
          resource_id=block_id,
          summary={"old_due_at": old_due_at.isoformat(), "new_due_at": new_due_at.isoformat(),
                   "updated_ongoing_attempts": len(ongoing)})
    db.commit()
    return {"block": _serialize_block(db, block),
            "updated_ongoing_attempts": len(ongoing)}


# ---------- 删除 ----------


@router.delete("/lesson-blocks/{block_id}")
def delete_block(block_id: int, request: Request, db: Session = Depends(db_session)):
    require_csrf(request)
    admin = current_admin(request, db)
    if not is_editor(admin):
        raise HTTPException(403, "没有编辑课程内容的权限。")
    block = db.get(CourseLessonBlock, block_id)
    if block is None:
        raise HTTPException(404, "内容块不存在。")
    _require_editable(db, db.get(CourseLesson, block.lesson_id))
    lesson_id = block.lesson_id
    # source_id 是多态列，数据库无法替我们做 FK/CASCADE。已有作答的 homework
    # 块只能停用/下架，不能删除，否则历史记录会留下但解析来源会变成 404。
    if block.block_type == "scratch":
        # 与 homework 同一条纪律：已有学生提交的块只能停用/下架，不能删。
        # scratch_submissions.lesson_block_id 是 CASCADE，删块会把学生的作品判定记录
        # 一起静默带走——历史成绩凭空消失比"删不掉"严重得多。
        submitted = db.scalar(
            select(func.count()).select_from(ScratchSubmission)
            .where(ScratchSubmission.lesson_block_id == block_id)
        ) or 0
        if submitted:
            audit(db, request.app.state.settings, "course_block_delete", "failure",
                  client_ip(request), admin.id, resource_type="course_lesson_block",
                  resource_id=block_id,
                  summary={"lesson_id": lesson_id, "block_type": block.block_type,
                           "submission_count": submitted, "reason": "has_submissions"})
            db.commit()
            raise HTTPException(409, "该 Scratch 块已有学生提交，不能删除；请停用或下架课时。")
    if block.block_type == "homework":
        attempt_count = attempt_count_for(db, SOURCE_LESSON_HOMEWORK, block_id)
        if attempt_count:
            audit(db, request.app.state.settings, "course_block_delete", "failure",
                  client_ip(request), admin.id, resource_type="course_lesson_block",
                  resource_id=block_id,
                  summary={"lesson_id": lesson_id, "block_type": block.block_type,
                           "attempt_count": attempt_count, "reason": "has_attempts"})
            db.commit()
            raise HTTPException(409, "该作业已有作答记录，不能删除；请停用或下架课时。")
    # 明细表 FK 带 ondelete=CASCADE，删主表行即带走明细；视频/试卷素材本体不受影响。
    audit(db, request.app.state.settings, "course_block_delete", "success",
          client_ip(request), admin.id, resource_type="course_lesson_block", resource_id=block_id,
          summary={"lesson_id": lesson_id, "block_type": block.block_type})
    db.delete(block)
    db.flush()  # db_session 是 autoflush=False：不显式 flush，下面的查询仍会看到被删的行
    # 同一事务压实剩余 sort_order 为 0..n-1（交接文档 §5.2）。
    # 与 reorder 相同的两阶段写法，避免中间态撞 uq_lesson_blocks_order。
    rest = db.scalars(
        select(CourseLessonBlock).where(CourseLessonBlock.lesson_id == lesson_id)
        .order_by(CourseLessonBlock.sort_order, CourseLessonBlock.id)
    ).all()
    for i, row in enumerate(rest):
        row.sort_order = -(i + 1)
    db.flush()
    for order, row in enumerate(rest):
        row.sort_order = order
    db.commit()
    return {"ok": True}


# ---------- 排序 ----------


@router.post("/lessons/{lesson_id}/blocks/reorder")
def reorder_blocks(lesson_id: int, payload: ReorderBlocksPayload, request: Request,
                   db: Session = Depends(db_session)):
    """块排序：完整有序 id 数组，集合必须与当前课时块完全一致（防丢行/跨课时偷块）。"""
    require_csrf(request)
    admin = current_admin(request, db)
    if not is_editor(admin):
        raise HTTPException(403, "没有编辑课程内容的权限。")
    lesson = _get_lesson_or_404(db, lesson_id)
    _require_editable(db, lesson)
    blocks = db.scalars(
        select(CourseLessonBlock).where(CourseLessonBlock.lesson_id == lesson_id)
    ).all()
    by_id = {b.id: b for b in blocks}
    if len(payload.ids) != len(blocks) or any(i not in by_id for i in payload.ids):
        raise HTTPException(400, "排序列表与当前内容块不一致，请刷新后重试。")
    if len(payload.ids) != len(set(payload.ids)):
        raise HTTPException(400, "排序列表存在重复 ID。")
    # 两阶段重写：先整体移出 0..n-1 区间再写入目标顺序。
    # 逐条 UPDATE 会让中间态出现两个块同 sort_order（唯一约束），
    # 先都写成负数再覆盖，任何时刻都不违反 uq_lesson_blocks_order。
    for i, bid in enumerate(payload.ids):
        by_id[bid].sort_order = -(i + 1)
    db.flush()
    for order, bid in enumerate(payload.ids):
        by_id[bid].sort_order = order
    audit(db, request.app.state.settings, "course_block_reorder", "success",
          client_ip(request), admin.id, resource_type="course_lesson_block",
          summary={"lesson_id": lesson_id, "count": len(blocks)})
    db.commit()
    return {"ok": True}


# ---------- 试卷素材选择器 ----------


@router.get("/papers/options")
def paper_options(
    request: Request,
    keyword: str = "",
    page: int = 1,
    page_size: int = 20,
    status: str = "published",
    db: Session = Depends(db_session),
):
    """课时练习 / 作业块的试卷选择器：服务端搜索分页，不一次拉全部。

    默认只给已发布卷（published），草稿/归档卷在发布检查阶段会被拦，这里不展示。
    used_by_lessons 是「该卷当前被哪些课时块引用」的轻量提示，供前端标注复用情况。
    """
    current_admin(request, db)
    page = max(1, page)
    page_size = min(max(1, page_size), 100)
    if status not in {"", "draft", "published", "archived"}:
        raise HTTPException(400, "状态参数不合法。")
    conds = []
    if status:
        conds.append(Paper.status == status)
    if keyword.strip():
        term = keyword.strip()
        # 课程配置既要支持标题检索，也要支持运营人员手里的数据库 ID / 对外卷号。
        # 先按精确 ID 命中，不把 100+ 张试卷一次性下发给浏览器。
        exact = []
        if term.isdigit():
            exact.append(Paper.id == int(term))
        exact.append(Paper.paper_id_no.ilike(f"%{term}%"))
        exact.append(Paper.title.ilike(f"%{term}%"))
        conds.append(or_(*exact))
    total = db.scalar(select(func.count()).select_from(Paper).where(*conds)) or 0
    rows = db.scalars(
        select(Paper).where(*conds)
        .order_by(Paper.id.desc())
        .offset((page - 1) * page_size).limit(page_size)
    ).all()
    paper_ids = [p.id for p in rows]
    # 引用统计一次查齐，避免 N+1
    used: dict[int, list[str]] = {pid: [] for pid in paper_ids}
    if paper_ids:
        for pid, mode, lesson_id in db.execute(
            select(LessonPaperBlock.paper_id, LessonPaperBlock.mode, CourseLessonBlock.lesson_id)
            .join(CourseLessonBlock, CourseLessonBlock.id == LessonPaperBlock.block_id)
            .where(LessonPaperBlock.paper_id.in_(paper_ids))
        ).all():
            # v2 命名对齐（实现计划 §2.2 #6）：迁移后存量 mode 恒为 homework，文案统一
            # 「课后练习」；三元保留为防御（downgrade 场景/历史脏数据仍可识别）。
            used[pid].append(f"{'课中练习' if mode == 'practice' else '课后练习'}@课时{lesson_id}")
    owner_ids = {p.owner_id for p in rows if p.owner_id}
    owners = {
        a.id: a.display_name
        for a in db.scalars(select(AdminUser).where(AdminUser.id.in_(owner_ids))).all()
    } if owner_ids else {}
    qcounts = dict(db.execute(
        select(PaperQuestion.paper_id, func.count())
        .where(PaperQuestion.paper_id.in_(paper_ids))
        .group_by(PaperQuestion.paper_id)
    ).all())
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [
            {
                "id": p.id,
                "paper_id_no": p.paper_id_no,
                "title": p.title,
                "paper_type": p.paper_type,
                "status": p.status,
                "question_count": qcounts.get(p.id, 0),
                "owner_name": owners.get(p.owner_id),
                "used_by_lessons": used.get(p.id, []),
            }
            for p in rows
        ],
    }
