"""后台课包-课程管理：课包 / 分类 / 章节 / 课时。

阶段 1（课包最小闭环）范围：
- 课包 CRUD + 分类 + 发布状态机（draft → published → off_shelf）。
- 章节、课时 CRUD + 拖拽排序（有序 id 数组重写 sort_order）。
- 课时内容：图文(markdown) / 绑定视频(videos 表) / 外链视频，三选一或组合。
- 发布前完整性校验：基本信息、至少一个章节、至少一个已配置内容的课时。

学习进度 / 课时作业 / 开通资格（enrollments）为后续阶段，本文件不涉及。
权限与 admin_videos 同口径：editor/super_admin 可写，reviewer 只读。
"""
from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..attempt_source import SOURCE_LESSON_HOMEWORK, attempt_count_for
from ..course_access import OPEN_POLICIES, enrollment_predicates
from ..notification_links import course_link
from ..models import (
    Course,
    CourseCategory,
    CourseLesson,
    CourseLessonBlock,
    CourseSection,
    CourseTag,
    CourseTagLink,
    CourseType,
    Enrollment,
    LearningArea,
    LessonBlockMaterial,
    LessonMarkdownBlock,
    LessonPaperBlock,
    LessonProblemBlock,
    LessonScratchBlock,
    LessonVideoBlock,
    MaterialAsset,
    Paper,
    Problem,
    ScratchChallenge,
    Video,
    VideoVariant,
)
from ..notification_service import create_notification, request_hash
from ..permissions import is_editor
from .admin_auth import audit, client_ip, current_admin, db_session, require_csrf

router = APIRouter(prefix="/api/admin", tags=["admin-courses"])

COURSE_STATUSES = {"draft", "published", "off_shelf"}
DIFFICULTIES = {"beginner", "intermediate", "advanced"}
# 发布检查中「提示不拦截」的 code（实现计划 v2 §4.2）：只提醒不改判定，
# 发布端点据此区分 422 拦截与 200 放行 + hints 回传。
NON_BLOCKING_HINTS = {"problem_type_stale", "problem_score_zero", "scratch_starter_missing"}


# ---------- 请求模型 ----------


class CategoryPayload(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    sort_order: int = Field(default=0)


def _only_http_url(v: str | None) -> str | None:
    """外链地址只收 http/https——`javascript:` 之类的伪协议会变成 XSS 载体。"""
    if v is None:
        return v
    if not (v.startswith("http://") or v.startswith("https://")):
        raise ValueError("仅支持 http/https 外链地址")
    return v


def _cover_url(v: str | None) -> str | None:
    """封面来源有两个：应用内上传（/course-covers/…，独立存储区域）与历史外链。

    上传接口只会产生 /course-covers/ 开头的相对路径（admin_media.py 的
    course_cover_relative_path），伪造协议（javascript: 等）两个来源都不放行。
    """
    if v is None:
        return v
    if v.startswith("/course-covers/"):
        return v
    return _only_http_url(v)


class CoursePayload(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    subtitle: str | None = Field(default=None, max_length=300)
    description: str | None = None
    cover_url: str | None = Field(default=None, max_length=512)
    category_id: int | None = None
    area_key: str = Field(default="kids", max_length=32)
    course_kind: str = Field(default="systematic", max_length=16)
    tag_ids: list[int] = Field(default_factory=list, max_length=30)
    difficulty: str = Field(default="beginner", max_length=16)
    price_cents: int = Field(default=0, ge=0)
    sort_order: int = Field(default=0)

    @field_validator("cover_url")
    @classmethod
    def _check_cover_url(cls, v: str | None) -> str | None:
        return _cover_url(v)


class SectionPayload(BaseModel):
    title: str = Field(min_length=1, max_length=200)


class LessonPayload(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    summary: str | None = Field(default=None, max_length=500)
    content_md: str | None = None
    video_id: int | None = None
    video_url: str | None = Field(default=None, max_length=512)
    duration_minutes: int = Field(default=0, ge=0)
    # 学习开放策略（2026-08-10 定稿）：is_trial 复选框退役，改策略 + 参数。
    # open_policy=whole 时 is_trial 由服务端同步为 True，兼容旧口径读取方。
    open_policy: str = Field(default="closed", max_length=16)
    trial_block_count: int = Field(default=0, ge=0)  # first_n：前 N 块可学
    trial_minutes: int = Field(default=0, ge=0)  # video_minutes：视频试听 N 分钟（二期）
    # 旧客户端/测试兼容：显式传 is_trial 时覆盖 open_policy（True→whole，False→closed）。
    # 新前端只发 open_policy，不再发本字段。
    is_trial: bool | None = None

    @field_validator("video_url")
    @classmethod
    def _check_video_url(cls, v: str | None) -> str | None:
        return _only_http_url(v)

    @field_validator("open_policy")
    @classmethod
    def _check_open_policy(cls, v: str) -> str:
        if v not in OPEN_POLICIES:
            raise ValueError("open_policy 只允许 closed / whole / first_n / video_minutes")
        return v


class ReorderPayload(BaseModel):
    ids: list[int] = Field(min_length=1)


class LessonMovePayload(BaseModel):
    """跨章节移动：目标章节 + 该章节移动后的完整课时顺序（含被移进来的这一节）。"""

    target_section_id: int
    ordered_ids: list[int] = Field(min_length=1)


# ---------- 分类 ----------


@router.get("/course-categories")
def list_categories(request: Request, db: Session = Depends(db_session)):
    current_admin(request, db)
    rows = db.scalars(select(CourseCategory).order_by(
        CourseCategory.area_key, CourseCategory.sort_order, CourseCategory.id
    )).all()
    return [
        {"id": c.id, "name": c.name, "sort_order": c.sort_order, "area_key": c.area_key,
         "parent_id": c.parent_id, "key": c.key, "is_active": c.is_active}
        for c in rows
    ]


@router.post("/course-categories", status_code=201)
def create_category(request: Request, payload: CategoryPayload, db: Session = Depends(db_session)):
    require_csrf(request)
    admin = current_admin(request, db)
    if not is_editor(admin):
        raise HTTPException(403, "没有管理分类的权限。")
    if db.scalar(select(CourseCategory).where(CourseCategory.name == payload.name)):
        raise HTTPException(409, "分类名称已存在。")
    cat = CourseCategory(
        area_key="kids", parent_id=None, key=f"legacy-{uuid4().hex[:12]}",
        name=payload.name, sort_order=payload.sort_order,
    )
    db.add(cat)
    audit(db, request.app.state.settings, "course_category_create", "success",
          client_ip(request), admin.id, resource_type="course_category", summary={"name": payload.name})
    db.commit()
    return {"id": cat.id, "name": cat.name, "sort_order": cat.sort_order}


@router.put("/course-categories/{category_id}")
def update_category(category_id: int, payload: CategoryPayload, request: Request, db: Session = Depends(db_session)):
    require_csrf(request)
    admin = current_admin(request, db)
    if not is_editor(admin):
        raise HTTPException(403, "没有管理分类的权限。")
    cat = db.get(CourseCategory, category_id)
    if cat is None:
        raise HTTPException(404, "分类不存在。")
    dup = db.scalar(select(CourseCategory).where(
        CourseCategory.name == payload.name, CourseCategory.id != category_id))
    if dup:
        raise HTTPException(409, "分类名称已存在。")
    cat.name = payload.name
    cat.sort_order = payload.sort_order
    audit(db, request.app.state.settings, "course_category_update", "success",
          client_ip(request), admin.id, resource_type="course_category", resource_id=category_id)
    db.commit()
    return {"id": cat.id, "name": cat.name, "sort_order": cat.sort_order}


@router.delete("/course-categories/{category_id}")
def delete_category(category_id: int, request: Request, db: Session = Depends(db_session)):
    require_csrf(request)
    admin = current_admin(request, db)
    if not is_editor(admin):
        raise HTTPException(403, "没有管理分类的权限。")
    cat = db.get(CourseCategory, category_id)
    if cat is None:
        raise HTTPException(404, "分类不存在。")
    used = db.scalar(select(func.count()).select_from(Course).where(Course.category_id == category_id))
    if used:
        raise HTTPException(409, f"仍有 {used} 个课包使用该分类，请先调整课包分类。")
    audit(db, request.app.state.settings, "course_category_delete", "success",
          client_ip(request), admin.id, resource_type="course_category", resource_id=category_id)
    db.delete(cat)
    db.commit()
    return {"ok": True}


# ---------- 课包 ----------


def _require_editable(course: Course | None) -> Course:
    """阶段 1 口径：已发布课包必须先下架才能编辑（属性/目录/课时/排序/跨章移动）。

    发布校验只在 publish 时跑一次，发布后把内容清空/删空会把 published 课包改坏，
    学生端会看到不完整课程——这里在**每一个**结构修改入口拦截。
    """
    if course is None:
        raise HTTPException(404, "课包不存在。")
    if course.status == "published":
        raise HTTPException(409, "已发布课包请先下架再编辑。")
    return course


def _course_counts(db: Session, course_ids: list[int]) -> dict[int, dict]:
    """一次查出每个课包的章节数 / 课时数，避免列表页 N+1。"""
    out: dict[int, dict] = {}
    if not course_ids:
        return out
    for cid in course_ids:
        out[cid] = {"section_count": 0, "lesson_count": 0}
    sec_rows = db.execute(
        select(CourseSection.course_id, func.count())
        .where(CourseSection.course_id.in_(course_ids))
        .group_by(CourseSection.course_id)
    ).all()
    for cid, n in sec_rows:
        out[cid]["section_count"] = n
    les_rows = db.execute(
        select(CourseLesson.course_id, func.count())
        .where(CourseLesson.course_id.in_(course_ids))
        .group_by(CourseLesson.course_id)
    ).all()
    for cid, n in les_rows:
        out[cid]["lesson_count"] = n
    return out


def _validate_course_catalog(db: Session, payload: CoursePayload) -> None:
    area = db.get(LearningArea, payload.area_key)
    if area is None or area.status == "hidden":
        raise HTTPException(400, "学习专区不存在或已停用。")
    course_type = db.scalar(select(CourseType).where(
        CourseType.area_key == payload.area_key,
        CourseType.key == payload.course_kind,
        CourseType.is_active.is_(True),
    ))
    if course_type is None:
        raise HTTPException(400, "课程类型不属于所选专区或已停用。")
    if payload.category_id is not None:
        category = db.get(CourseCategory, payload.category_id)
        if category is None or category.area_key != payload.area_key or not category.is_active:
            raise HTTPException(400, "主分类不属于所选专区或已停用。")
    if len(payload.tag_ids) != len(set(payload.tag_ids)):
        raise HTTPException(400, "课程标签不能重复。")
    if payload.tag_ids:
        tags = db.scalars(select(CourseTag).where(CourseTag.id.in_(payload.tag_ids))).all()
        if len(tags) != len(payload.tag_ids) or any(
            tag.area_key != payload.area_key or not tag.is_active for tag in tags
        ):
            raise HTTPException(400, "课程标签不属于所选专区或已停用。")


def _replace_course_tags(db: Session, course: Course, tag_ids: list[int]) -> None:
    old = db.scalars(select(CourseTagLink).where(CourseTagLink.course_id == course.id)).all()
    for row in old:
        db.delete(row)
    db.flush()
    for tag_id in tag_ids:
        db.add(CourseTagLink(course_id=course.id, tag_id=tag_id))


def _serialize_course(db: Session, c: Course) -> dict:
    counts = _course_counts(db, [c.id])[c.id]
    cat_name = None
    if c.category_id:
        cat = db.get(CourseCategory, c.category_id)
        cat_name = cat.name if cat else None
    tags = db.scalars(
        select(CourseTag).join(CourseTagLink, CourseTagLink.tag_id == CourseTag.id)
        .where(CourseTagLink.course_id == c.id)
        .order_by(CourseTag.sort_order, CourseTag.id)
    ).all()
    return {
        "id": c.id,
        "title": c.title,
        "subtitle": c.subtitle,
        "description": c.description,
        "cover_url": c.cover_url,
        "category_id": c.category_id,
        "category_name": cat_name,
        "area_key": c.area_key,
        "course_kind": c.course_kind,
        "tags": [{"id": tag.id, "key": tag.key, "name": tag.name} for tag in tags],
        "tag_ids": [tag.id for tag in tags],
        "difficulty": c.difficulty,
        "price_cents": c.price_cents,
        "status": c.status,
        "sort_order": c.sort_order,
        "section_count": counts["section_count"],
        "lesson_count": counts["lesson_count"],
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
    }


@router.get("/courses")
def list_courses(
    request: Request,
    keyword: str = "",
    category_id: int | None = None,
    status: str = "",
    area_key: str = "",
    course_kind: str = "",
    page: int = 1,
    page_size: int = 10,
    db: Session = Depends(db_session),
):
    current_admin(request, db)
    if area_key and db.get(LearningArea, area_key) is None:
        raise HTTPException(400, "专区参数不合法。")
    if course_kind and db.scalar(select(CourseType.id).where(
        CourseType.key == course_kind,
        *([CourseType.area_key == area_key] if area_key else []),
    ).limit(1)) is None:
        raise HTTPException(400, "课程类型参数不合法。")
    if status and status not in COURSE_STATUSES:
        raise HTTPException(400, "状态参数不合法。")
    # 分页上下限：负数/超大 page_size 会变成大查询或数据库错误
    page = max(1, page)
    page_size = min(max(1, page_size), 100)
    conds = []
    if keyword.strip():
        like = f"%{keyword.strip()}%"
        conds.append(Course.title.ilike(like))
    if category_id is not None:
        conds.append(Course.category_id == category_id)
    if status:
        conds.append(Course.status == status)
    if area_key:
        conds.append(Course.area_key == area_key)
    if course_kind:
        conds.append(Course.course_kind == course_kind)

    total = db.scalar(select(func.count()).select_from(Course).where(*conds)) or 0
    rows = db.scalars(
        select(Course).where(*conds)
        .order_by(Course.sort_order, Course.id.desc())
        .offset((page - 1) * page_size).limit(page_size)
    ).all()
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [_serialize_course(db, c) for c in rows],
    }


@router.post("/courses", status_code=201)
def create_course(request: Request, payload: CoursePayload, db: Session = Depends(db_session)):
    require_csrf(request)
    admin = current_admin(request, db)
    if not is_editor(admin):
        raise HTTPException(403, "没有创建课包的权限。")
    if payload.difficulty not in DIFFICULTIES:
        raise HTTPException(400, "难度取值不合法。")
    _validate_course_catalog(db, payload)
    course = Course(
        title=payload.title, subtitle=payload.subtitle, description=payload.description,
        cover_url=payload.cover_url, category_id=payload.category_id,
        area_key=payload.area_key, course_kind=payload.course_kind,
        difficulty=payload.difficulty, price_cents=payload.price_cents,
        sort_order=payload.sort_order, owner_id=admin.id, status="draft",
    )
    db.add(course)
    db.flush()
    _replace_course_tags(db, course, payload.tag_ids)
    audit(db, request.app.state.settings, "course_create", "success",
          client_ip(request), admin.id, resource_type="course", summary={"title": payload.title})
    db.commit()
    return _serialize_course(db, course)


@router.get("/courses/{course_id}")
def get_course(course_id: int, request: Request, db: Session = Depends(db_session)):
    current_admin(request, db)
    course = db.get(Course, course_id)
    if course is None:
        raise HTTPException(404, "课包不存在。")
    return _serialize_course(db, course)


@router.put("/courses/{course_id}")
def update_course(course_id: int, payload: CoursePayload, request: Request, db: Session = Depends(db_session)):
    require_csrf(request)
    admin = current_admin(request, db)
    if not is_editor(admin):
        raise HTTPException(403, "没有编辑课包的权限。")
    course = db.get(Course, course_id)
    if course is None:
        raise HTTPException(404, "课包不存在。")
    _require_editable(course)
    if payload.difficulty not in DIFFICULTIES:
        raise HTTPException(400, "难度取值不合法。")
    _validate_course_catalog(db, payload)
    # 编辑不改变发布状态：发布/下架走专门接口。
    course.title = payload.title
    course.subtitle = payload.subtitle
    course.description = payload.description
    course.cover_url = payload.cover_url
    course.category_id = payload.category_id
    course.area_key = payload.area_key
    course.course_kind = payload.course_kind
    course.difficulty = payload.difficulty
    course.price_cents = payload.price_cents
    course.sort_order = payload.sort_order
    _replace_course_tags(db, course, payload.tag_ids)
    audit(db, request.app.state.settings, "course_update", "success",
          client_ip(request), admin.id, resource_type="course", resource_id=course_id)
    db.commit()
    return _serialize_course(db, course)


def _lesson_block_problems(db: Session, lesson: CourseLesson) -> list[dict]:
    """单个课时的块级发布问题（交接文档 §6.7）。

    旧字段兜底（§5.3）：课时无块但旧字段（content_md / video_id / video_url）仍有内容时
    视为有效——迁移回填后不应出现，但保护直接写旧字段的中间态客户端。
    """
    problems: list[dict] = []

    def add(code: str, message: str, block_id: int | None = None) -> None:
        problems.append({
            "stage": "lesson_content",
            "lesson_id": lesson.id,
            "block_id": block_id,
            "code": code,
            "message": message,
        })

    blocks = db.scalars(
        select(CourseLessonBlock).where(CourseLessonBlock.lesson_id == lesson.id)
        .order_by(CourseLessonBlock.sort_order, CourseLessonBlock.id)
    ).all()
    if not blocks:
        if not (lesson.content_md or lesson.video_id or lesson.video_url):
            add("no_content", f"《{lesson.title}》未配置任何内容。")
        return problems

    for block in blocks:
        display = block.title or lesson.title
        if block.block_type == "markdown":
            md = db.get(LessonMarkdownBlock, block.id)
            if md is None or not md.content_md.strip():
                add("markdown_empty", f"《{display}》图文正文为空。", block.id)
        elif block.block_type == "video":
            vd = db.get(LessonVideoBlock, block.id)
            if vd is None:
                add("video_missing_detail", f"《{display}》视频块缺少绑定信息。", block.id)
            elif vd.source_type == "platform":
                if vd.video_id is None:
                    add("video_not_bound", f"《{display}》平台视频块未绑定视频。", block.id)
                else:
                    v = db.get(Video, vd.video_id)
                    if v is None:
                        add("video_missing", f"《{display}》绑定的视频已不存在。", block.id)
                    elif not _video_playable(db, v):
                        add("video_not_ready", f"《{display}》视频尚未转码完成，暂不可播放。", block.id)
            else:
                if not (vd.video_url or "").startswith(("http://", "https://")):
                    add("video_url_invalid", f"《{display}》外链地址必须是 http/https。", block.id)
        elif block.block_type == "materials":
            # 阅读资料块：至少绑定一份 ready 资料才算有内容（交接文档 12 §4.3）。
            bound = db.scalar(
                select(func.count())
                .select_from(LessonBlockMaterial)
                .join(MaterialAsset, MaterialAsset.id == LessonBlockMaterial.material_id)
                .where(
                    LessonBlockMaterial.block_id == block.id,
                    MaterialAsset.status == "ready",
                )
            ) or 0
            if bound == 0:
                add("materials_empty", f"《{display}》阅读资料块尚未绑定任何资料。", block.id)
        elif block.block_type == "scratch":
            # Scratch 块发布检查（任务书 21b）。没有这一段的话，scratch 块会掉进
            # 下面的 else（绑卷分支）被报成 paper_missing_detail——一条谁也看不懂的
            # 错误，且课包永远发不出去。
            sc_ = db.get(LessonScratchBlock, block.id)
            if sc_ is None:
                add("scratch_missing_detail", f"《{display}》Scratch 块未绑定挑战。", block.id)
                continue
            challenge = db.get(ScratchChallenge, sc_.challenge_id)
            if challenge is None:
                add("scratch_challenge_missing", f"《{display}》绑定的挑战已不存在。", block.id)
            elif challenge.status != "published":
                # 拦截：未发布的挑战对学生等同不存在，课包上架了学生点进去也是 404。
                add("scratch_challenge_not_published",
                    f"《{display}》绑定的挑战《{challenge.title}》尚未发布。", block.id)
            elif not challenge.starter_sb3_key:
                # 提示不拦截：允许"从空白项目开始"的关卡，但发布的人应当知情。
                add("scratch_starter_missing",
                    f"《{display}》挑战《{challenge.title}》未上传初始项目，学生将从空白项目开始。",
                    block.id)
        elif block.block_type == "practice":
            # v2 单题化发布检查（实现计划 v2 §4.2）：
            # - problem_missing_detail / problem_missing：拦截（缺绑定 / 题目不存在或未审核）；
            # - problem_type_stale / problem_score_zero：不拦截提示（快照纪律 / score=0 口径）。
            pb_ = db.get(LessonProblemBlock, block.id)
            if pb_ is None:
                add("problem_missing_detail", f"《{display}》课中练习块缺少题目绑定。", block.id)
                continue
            problem = db.scalar(
                select(Problem).where(
                    Problem.problem_id_no == pb_.problem_id_no,
                    Problem.status == "approved",
                )
            )
            if problem is None:
                add("problem_missing",
                    f"《{display}》绑定的题目不存在或未审核通过（{pb_.problem_id_no}）。", block.id)
            else:
                # 提示不拦截：快照只用于管理端展示/筛选，作答判分以题库实际题型为准；
                # score 默认 0（Q5 已定），满分 0 分题进统计时得分率分母为 0。
                if pb_.problem_type != problem.type:
                    add("problem_type_stale",
                        f"《{display}》题目快照题型（{pb_.problem_type}）与题库实际题型（{problem.type}）不一致，作答判分以题库实际题型为准。", block.id)
                if pb_.score == 0:
                    add("problem_score_zero",
                        f"《{display}》题分值为 0，进入成绩统计时得分率分母为 0，请确认。", block.id)
        else:  # homework —— 保持现状（绑卷分支）
            pd_ = db.get(LessonPaperBlock, block.id)
            if pd_ is None:
                add("paper_missing_detail", f"《{display}》课后练习块缺少试卷绑定。", block.id)
                continue
            if pd_.mode != block.block_type:
                add("block_type_mismatch",
                    f"《{display}》块类型与试卷模式不一致（{block.block_type} vs {pd_.mode}）。", block.id)
            paper = db.get(Paper, pd_.paper_id)
            if paper is None:
                add("paper_missing", f"《{display}》绑定的试卷已不存在。", block.id)
            elif paper.status != "published":
                add("paper_not_published", f"《{display}》绑定的试卷《{paper.title}》未发布。", block.id)
            if pd_.due_at is not None:
                due = pd_.due_at
                # SQLite 存不出时区（naive），PostgreSQL 是 aware；统一按 UTC 比较。
                if due.tzinfo is None:
                    due = due.replace(tzinfo=UTC)
                if due <= datetime.now(UTC):
                    add("homework_due_past", f"《{display}》作业截止时间已过。", block.id)
    return problems


def _publish_checks(db: Session, course: Course) -> list[dict]:
    """发布前完整性校验，返回结构化问题列表（空 = 可发布）。

    每个问题带 stage / lesson_id / block_id / code / message，前端可跳转到具体课时块。
    """
    problems: list[dict] = []
    if not course.title.strip():
        problems.append({"stage": "basic_info", "lesson_id": None, "block_id": None,
                         "code": "missing_title", "message": "课包名称不能为空。"})
    if course.category_id is None:
        problems.append({"stage": "basic_info", "lesson_id": None, "block_id": None,
                         "code": "missing_category", "message": "请先选择课包分类。"})
    else:
        category = db.get(CourseCategory, course.category_id)
        if category is None or category.area_key != course.area_key or not category.is_active:
            problems.append({"stage": "basic_info", "lesson_id": None, "block_id": None,
                             "code": "invalid_category", "message": "课包分类与学习专区不一致或已停用。"})
    area = db.get(LearningArea, course.area_key)
    if area is None or area.status == "hidden":
        problems.append({"stage": "basic_info", "lesson_id": None, "block_id": None,
                         "code": "invalid_area", "message": "学习专区不存在或已停用。"})
    course_type = db.scalar(select(CourseType).where(
        CourseType.area_key == course.area_key, CourseType.key == course.course_kind,
        CourseType.is_active.is_(True),
    ))
    if course_type is None:
        problems.append({"stage": "basic_info", "lesson_id": None, "block_id": None,
                         "code": "invalid_course_type", "message": "课程类型不属于当前专区或已停用。"})
    section_count = db.scalar(
        select(func.count()).select_from(CourseSection).where(CourseSection.course_id == course.id)
    ) or 0
    if section_count == 0:
        problems.append({"stage": "structure", "lesson_id": None, "block_id": None,
                         "code": "no_section", "message": "至少需要添加一个章节。"})
        return problems  # 无章节时课时校验无从谈起，提前返回
    lessons = db.scalars(
        select(CourseLesson).where(CourseLesson.course_id == course.id).order_by(CourseLesson.id)
    ).all()
    if not lessons:
        problems.append({"stage": "structure", "lesson_id": None, "block_id": None,
                         "code": "no_lesson", "message": "至少需要一个已配置内容的课时。"})
        return problems
    for lesson in lessons:
        problems.extend(_lesson_block_problems(db, lesson))
    return problems


@router.post("/courses/{course_id}/publish")
def publish_course(course_id: int, request: Request,
                   idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
                   db: Session = Depends(db_session)):
    require_csrf(request)
    admin = current_admin(request, db)
    if not is_editor(admin):
        raise HTTPException(403, "没有发布课包的权限。")
    course = db.get(Course, course_id)
    if course is None:
        raise HTTPException(404, "课包不存在。")
    # Existing admin clients predate E6.  They retain the former one-click
    # publish behavior; upgraded clients provide the header for retry safety.
    idempotency_key = idempotency_key or f"legacy-course-publish:{course_id}:{uuid4()}"
    key_hash = hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()
    input_hash = request_hash({"course_id": course_id})
    if course.status == "published":
        if course.last_publish_idempotency_key_hash == key_hash:
            if course.last_publish_request_hash != input_hash:
                raise HTTPException(409, "Idempotency-Key 已用于不同请求。")
            return {"id": course.id, "status": course.status, "idempotent": True,
                    "publish_generation": course.publish_generation, "hints": []}
        raise HTTPException(409, "课包已经发布，请勿重复发布。")
    if course.status not in {"draft", "off_shelf"}:
        raise HTTPException(409, "课包当前状态不可发布。")
    problems = _publish_checks(db, course)
    blocking = [p for p in problems if p["code"] not in NON_BLOCKING_HINTS]
    if blocking:
        # 用 JSONResponse 而不是 HTTPException(detail=dict)：后者会被 FastAPI
        # 再包一层 {"detail": ...}，破坏交接文档 §6.7 的响应契约
        # {detail, problems}——前端按 problems 逐条定位跳转。
        # 提示项（problem_type_stale / problem_score_zero）也一并输出，供前端展示。
        return JSONResponse(status_code=422, content={"detail": "课包暂不能发布。", "problems": problems})
    course.status = "published"
    course.publish_generation += 1
    course.last_publish_idempotency_key_hash = key_hash
    course.last_publish_request_hash = input_hash
    recipients = list(db.scalars(select(Enrollment.student_id).where(
        Enrollment.course_id == course.id,
        *enrollment_predicates(datetime.now(UTC)),
    ).distinct()))
    # Persist the broadcast even with an empty current roster.  The cron task
    # can then attach a receipt when a future Enrollment.opened_at becomes valid.
    create_notification(
        db, kind="homework_published", title="课程已发布", body=f"《{course.title}》现已开放学习。",
        target_type="course", target_id=course.id, source_type="course", source_id=course.id,
        link_url=course_link(course.id), created_by=admin.id,
        idempotency_key=f"course-published:{course.id}:{course.publish_generation}",
        recipients=[{"user_id": user_id, "admin_user_id": None} for user_id in recipients],
    )
    audit(db, request.app.state.settings, "course_publish", "success",
          client_ip(request), admin.id, resource_type="course", resource_id=course_id)
    db.commit()
    # 仅提示项不拦截发布：随 200 响应回传 hints，管理员可看到但不阻塞。
    return {
        "id": course.id,
        "status": "published",
        "publish_generation": course.publish_generation,
        "hints": [p for p in problems if p["code"] in NON_BLOCKING_HINTS],
    }


@router.post("/courses/{course_id}/off-shelf")
def off_shelf_course(course_id: int, request: Request, db: Session = Depends(db_session)):
    require_csrf(request)
    admin = current_admin(request, db)
    if not is_editor(admin):
        raise HTTPException(403, "没有下架课包的权限。")
    course = db.get(Course, course_id)
    if course is None:
        raise HTTPException(404, "课包不存在。")
    if course.status != "published":
        raise HTTPException(409, "只有已发布的课包可以下架。")
    course.status = "off_shelf"
    audit(db, request.app.state.settings, "course_off_shelf", "success",
          client_ip(request), admin.id, resource_type="course", resource_id=course_id)
    db.commit()
    return {"id": course.id, "status": "off_shelf"}


@router.delete("/courses/{course_id}")
def delete_course(course_id: int, request: Request, db: Session = Depends(db_session)):
    require_csrf(request)
    admin = current_admin(request, db)
    if not is_editor(admin):
        raise HTTPException(403, "没有删除课包的权限。")
    course = db.get(Course, course_id)
    if course is None:
        raise HTTPException(404, "课包不存在。")
    if course.status == "published":
        raise HTTPException(409, "已发布的课包不能删除，请先下架。")
    homework_ids = db.scalars(
        select(CourseLessonBlock.id).join(CourseLesson).join(CourseSection)
        .where(CourseSection.course_id == course_id, CourseLessonBlock.block_type == "homework")
    ).all()
    if sum(attempt_count_for(db, SOURCE_LESSON_HOMEWORK, bid) for bid in homework_ids):
        raise HTTPException(409, "课包下的作业已有作答记录，不能删除；请下架课包。")
    audit(db, request.app.state.settings, "course_delete", "success",
          client_ip(request), admin.id, resource_type="course", resource_id=course_id,
          summary={"title": course.title})
    db.delete(course)  # 级联删章节、课时；视频记录本身不受影响
    db.commit()
    return {"ok": True}


# ---------- 章节 ----------


def _video_playable(db: Session, video: Video | None) -> bool:
    """视频是否已转出可播主档（primary_variant ready 且为 .m3u8）。

    与 admin_course_content._video_playable 同口径；发布检查与课时序列化共用。
    """
    if video is None or not video.primary_variant_id:
        return False
    variant = db.get(VideoVariant, video.primary_variant_id)
    return bool(variant and variant.status == "ready" and variant.object_key.endswith(".m3u8"))


def _serialize_lesson(db: Session, lesson: CourseLesson) -> dict:
    video = None
    if lesson.video_id:
        v = db.get(Video, lesson.video_id)
        if v is not None:
            video = {
                "id": v.id, "title": v.title, "status": v.status,
                "duration_seconds": v.duration_seconds, "playable": _video_playable(db, v),
            }
    return {
        "id": lesson.id,
        "section_id": lesson.section_id,
        "title": lesson.title,
        "summary": lesson.summary,
        "content_md": lesson.content_md,
        "video_id": lesson.video_id,
        "video": video,
        "video_url": lesson.video_url,
        "duration_minutes": lesson.duration_minutes,
        "is_trial": lesson.is_trial,
        "open_policy": lesson.open_policy,
        "trial_block_count": lesson.trial_block_count,
        "trial_minutes": lesson.trial_minutes,
        "sort_order": lesson.sort_order,
        "created_at": lesson.created_at.isoformat() if lesson.created_at else None,
    }


def _serialize_section(db: Session, section: CourseSection) -> dict:
    lessons = db.scalars(
        select(CourseLesson).where(CourseLesson.section_id == section.id)
        .order_by(CourseLesson.sort_order, CourseLesson.id)
    ).all()
    return {
        "id": section.id,
        "course_id": section.course_id,
        "title": section.title,
        "sort_order": section.sort_order,
        "lesson_count": len(lessons),
        "lessons": [_serialize_lesson(db, lesson) for lesson in lessons],
    }


@router.get("/courses/{course_id}/sections")
def list_sections(course_id: int, request: Request, db: Session = Depends(db_session)):
    """章节树：章节按 sort_order，课时按 sort_order，含视频绑定信息。"""
    current_admin(request, db)
    course = db.get(Course, course_id)
    if course is None:
        raise HTTPException(404, "课包不存在。")
    sections = db.scalars(
        select(CourseSection).where(CourseSection.course_id == course_id)
        .order_by(CourseSection.sort_order, CourseSection.id)
    ).all()
    return {
        "course": _serialize_course(db, course),
        "sections": [_serialize_section(db, s) for s in sections],
    }


@router.post("/courses/{course_id}/sections", status_code=201)
def create_section(course_id: int, payload: SectionPayload, request: Request, db: Session = Depends(db_session)):
    require_csrf(request)
    admin = current_admin(request, db)
    if not is_editor(admin):
        raise HTTPException(403, "没有编辑课程内容的权限。")
    _require_editable(db.get(Course, course_id))
    next_order = db.scalar(
        select(func.max(CourseSection.sort_order)).where(CourseSection.course_id == course_id)
    ) or -1
    section = CourseSection(course_id=course_id, title=payload.title, sort_order=next_order + 1)
    db.add(section)
    audit(db, request.app.state.settings, "course_section_create", "success",
          client_ip(request), admin.id, resource_type="course_section", summary={"title": payload.title})
    db.commit()
    return _serialize_section(db, section)


@router.put("/sections/{section_id}")
def update_section(section_id: int, payload: SectionPayload, request: Request, db: Session = Depends(db_session)):
    require_csrf(request)
    admin = current_admin(request, db)
    if not is_editor(admin):
        raise HTTPException(403, "没有编辑课程内容的权限。")
    section = db.get(CourseSection, section_id)
    if section is None:
        raise HTTPException(404, "章节不存在。")
    _require_editable(db.get(Course, section.course_id))
    homework_ids = db.scalars(
        select(CourseLessonBlock.id).join(CourseLesson)
        .where(CourseLesson.section_id == section_id, CourseLessonBlock.block_type == "homework")
    ).all()
    if sum(attempt_count_for(db, SOURCE_LESSON_HOMEWORK, bid) for bid in homework_ids):
        raise HTTPException(409, "章节下的作业已有作答记录，不能删除；请下架课程。")
    section.title = payload.title
    audit(db, request.app.state.settings, "course_section_update", "success",
          client_ip(request), admin.id, resource_type="course_section", resource_id=section_id)
    db.commit()
    return _serialize_section(db, section)


@router.delete("/sections/{section_id}")
def delete_section(section_id: int, request: Request, db: Session = Depends(db_session)):
    require_csrf(request)
    admin = current_admin(request, db)
    if not is_editor(admin):
        raise HTTPException(403, "没有编辑课程内容的权限。")
    section = db.get(CourseSection, section_id)
    if section is None:
        raise HTTPException(404, "章节不存在。")
    _require_editable(db.get(Course, section.course_id))
    # 级联删除课时；视频记录保留在 videos 表，仅失去课时绑定。
    audit(db, request.app.state.settings, "course_section_delete", "success",
          client_ip(request), admin.id, resource_type="course_section", resource_id=section_id,
          summary={"title": section.title})
    db.delete(section)
    db.commit()
    return {"ok": True}


@router.post("/courses/{course_id}/sections/reorder")
def reorder_sections(course_id: int, payload: ReorderPayload, request: Request, db: Session = Depends(db_session)):
    require_csrf(request)
    admin = current_admin(request, db)
    if not is_editor(admin):
        raise HTTPException(403, "没有编辑课程内容的权限。")
    _require_editable(db.get(Course, course_id))
    sections = db.scalars(
        select(CourseSection).where(CourseSection.course_id == course_id)
    ).all()
    by_id = {s.id: s for s in sections}
    if len(payload.ids) != len(sections) or any(i not in by_id for i in payload.ids):
        raise HTTPException(400, "排序列表与当前章节不一致，请刷新后重试。")
    if len(payload.ids) != len(set(payload.ids)):
        raise HTTPException(400, "排序列表存在重复 ID。")
    for order, sid in enumerate(payload.ids):
        by_id[sid].sort_order = order
    audit(db, request.app.state.settings, "course_section_reorder", "success",
          client_ip(request), admin.id, resource_type="course", resource_id=course_id)
    db.commit()
    return {"ok": True}


# ---------- 课时 ----------


def _resolve_open_policy(payload: LessonPayload) -> str:
    """旧字段兼容：显式传 is_trial 时以它为准（True→whole / False→closed），否则用 open_policy。"""
    if payload.is_trial is not None:
        return "whole" if payload.is_trial else "closed"
    return payload.open_policy


@router.post("/sections/{section_id}/lessons", status_code=201)
def create_lesson(section_id: int, payload: LessonPayload, request: Request, db: Session = Depends(db_session)):
    require_csrf(request)
    admin = current_admin(request, db)
    if not is_editor(admin):
        raise HTTPException(403, "没有编辑课程内容的权限。")
    section = db.get(CourseSection, section_id)
    if section is None:
        raise HTTPException(404, "章节不存在。")
    _require_editable(db.get(Course, section.course_id))
    if payload.video_id is not None and db.get(Video, payload.video_id) is None:
        raise HTTPException(400, "绑定的视频不存在。")
    next_order = db.scalar(
        select(func.max(CourseLesson.sort_order)).where(CourseLesson.section_id == section_id)
    ) or -1
    open_policy = _resolve_open_policy(payload)
    lesson = CourseLesson(
        course_id=section.course_id, section_id=section_id, title=payload.title,
        summary=payload.summary, content_md=payload.content_md,
        video_id=payload.video_id, video_url=payload.video_url,
        duration_minutes=payload.duration_minutes,
        open_policy=open_policy,
        trial_block_count=payload.trial_block_count,
        trial_minutes=payload.trial_minutes,
        is_trial=(open_policy == "whole"),
        sort_order=next_order + 1,
    )
    db.add(lesson)
    audit(db, request.app.state.settings, "course_lesson_create", "success",
          client_ip(request), admin.id, resource_type="course_lesson",
          summary={"title": payload.title})
    db.commit()
    return _serialize_lesson(db, lesson)


@router.put("/lessons/{lesson_id}")
def update_lesson(lesson_id: int, payload: LessonPayload, request: Request, db: Session = Depends(db_session)):
    require_csrf(request)
    admin = current_admin(request, db)
    if not is_editor(admin):
        raise HTTPException(403, "没有编辑课程内容的权限。")
    lesson = db.get(CourseLesson, lesson_id)
    if lesson is None:
        raise HTTPException(404, "课时不存在。")
    _require_editable(db.get(Course, lesson.course_id))
    homework_ids = db.scalars(
        select(CourseLessonBlock.id).where(
            CourseLessonBlock.lesson_id == lesson_id, CourseLessonBlock.block_type == "homework"
        )
    ).all()
    if sum(attempt_count_for(db, SOURCE_LESSON_HOMEWORK, bid) for bid in homework_ids):
        raise HTTPException(409, "课时下的作业已有作答记录，不能删除；请下架课程。")
    if payload.video_id is not None and db.get(Video, payload.video_id) is None:
        raise HTTPException(400, "绑定的视频不存在。")
    lesson.title = payload.title
    lesson.summary = payload.summary
    lesson.content_md = payload.content_md
    lesson.video_id = payload.video_id
    lesson.video_url = payload.video_url
    lesson.duration_minutes = payload.duration_minutes
    open_policy = _resolve_open_policy(payload)
    lesson.open_policy = open_policy
    lesson.trial_block_count = payload.trial_block_count
    lesson.trial_minutes = payload.trial_minutes
    lesson.is_trial = open_policy == "whole"
    audit(db, request.app.state.settings, "course_lesson_update", "success",
          client_ip(request), admin.id, resource_type="course_lesson", resource_id=lesson_id)
    db.commit()
    return _serialize_lesson(db, lesson)


@router.delete("/lessons/{lesson_id}")
def delete_lesson(lesson_id: int, request: Request, db: Session = Depends(db_session)):
    require_csrf(request)
    admin = current_admin(request, db)
    if not is_editor(admin):
        raise HTTPException(403, "没有编辑课程内容的权限。")
    lesson = db.get(CourseLesson, lesson_id)
    if lesson is None:
        raise HTTPException(404, "课时不存在。")
    _require_editable(db.get(Course, lesson.course_id))
    audit(db, request.app.state.settings, "course_lesson_delete", "success",
          client_ip(request), admin.id, resource_type="course_lesson", resource_id=lesson_id,
          summary={"title": lesson.title})
    db.delete(lesson)
    db.commit()
    return {"ok": True}


@router.post("/sections/{section_id}/lessons/reorder")
def reorder_lessons(section_id: int, payload: ReorderPayload, request: Request, db: Session = Depends(db_session)):
    require_csrf(request)
    admin = current_admin(request, db)
    if not is_editor(admin):
        raise HTTPException(403, "没有编辑课程内容的权限。")
    section = db.get(CourseSection, section_id)
    if section is None:
        raise HTTPException(404, "章节不存在。")
    _require_editable(db.get(Course, section.course_id))
    lessons = db.scalars(
        select(CourseLesson).where(CourseLesson.section_id == section_id)
    ).all()
    by_id = {lesson.id: lesson for lesson in lessons}
    if len(payload.ids) != len(lessons) or any(i not in by_id for i in payload.ids):
        raise HTTPException(400, "排序列表与当前课时不一致，请刷新后重试。")
    if len(payload.ids) != len(set(payload.ids)):
        raise HTTPException(400, "排序列表存在重复 ID。")
    for order, lid in enumerate(payload.ids):
        by_id[lid].sort_order = order
    audit(db, request.app.state.settings, "course_lesson_reorder", "success",
          client_ip(request), admin.id, resource_type="course_lesson", resource_id=section_id)
    db.commit()
    return {"ok": True}


@router.post("/lessons/{lesson_id}/move")
def move_lesson(lesson_id: int, payload: LessonMovePayload, request: Request,
                db: Session = Depends(db_session)):
    """课时跨章节移动 + 落点章节整段重排，单事务完成。

    为什么不复用 reorder_lessons：它要求 ids 与本章节当前集合**完全一致**（上面那个 400），
    而跨章节移动必然经过「课时已经不在原章节、又还没算进新章节」的中间态，
    两次请求拆着做只要中间崩一次就会留下 sort_order 撞车的脏数据。
    """
    require_csrf(request)
    admin = current_admin(request, db)
    if not is_editor(admin):
        raise HTTPException(403, "没有编辑课程内容的权限。")
    lesson = db.get(CourseLesson, lesson_id)
    if lesson is None:
        raise HTTPException(404, "课时不存在。")
    _require_editable(db.get(Course, lesson.course_id))
    target = db.get(CourseSection, payload.target_section_id)
    if target is None:
        raise HTTPException(404, "目标章节不存在。")
    if target.course_id != lesson.course_id:
        raise HTTPException(400, "只能在同一课包内移动课时。")

    source_section_id = lesson.section_id
    lesson.section_id = target.id
    db.flush()  # 让下面这次查询看得到刚改的归属

    lessons = db.scalars(
        select(CourseLesson).where(CourseLesson.section_id == target.id)
    ).all()
    by_id = {lesson.id: lesson for lesson in lessons}
    if len(payload.ordered_ids) != len(lessons) or any(i not in by_id for i in payload.ordered_ids):
        # 校验没过就整体回滚——flush 过的 section_id 不能留在会话里，
        # 否则同一请求后续（或同连接的下一次读）会看到半截状态。
        db.rollback()
        raise HTTPException(400, "排序列表与目标章节不一致，请刷新后重试。")
    if len(payload.ordered_ids) != len(set(payload.ordered_ids)):
        db.rollback()
        raise HTTPException(400, "排序列表存在重复 ID。")
    for order, lid in enumerate(payload.ordered_ids):
        by_id[lid].sort_order = order

    # 源章节留下的空档：剩余课时重新压实成 0..n-1，避免长期使用后 sort_order 稀疏到看不懂。
    if source_section_id != target.id:
        rest = db.scalars(
            select(CourseLesson).where(CourseLesson.section_id == source_section_id)
            .order_by(CourseLesson.sort_order, CourseLesson.id)
        ).all()
        for order, row in enumerate(rest):
            row.sort_order = order

    audit(db, request.app.state.settings, "course_lesson_move", "success",
          client_ip(request), admin.id, resource_type="course_lesson", resource_id=lesson_id,
          summary={"from_section": source_section_id, "to_section": target.id})
    db.commit()
    return {"ok": True}


# ---------- 课时可绑定的视频选项 ----------


@router.get("/videos/options")
def video_options(request: Request, keyword: str = "", db: Session = Depends(db_session)):
    """课时绑定用：列出视频及其转码状态，供管理员选择。

    与列表页不同，这里不限制状态——转码中的视频也可以先绑定课时，
    前端在卡片上标注「转码中」即可。keyword 用于找回老视频
    （列表只回最新 100 条，按标题搜不受数量限制）。
    """
    current_admin(request, db)
    conds = []
    if keyword.strip():
        conds.append(Video.title.ilike(f"%{keyword.strip()}%"))
    rows = db.scalars(
        select(Video).where(*conds).order_by(Video.id.desc()).limit(100)
    ).all()
    result = []
    for v in rows:
        playable = False
        if v.primary_variant_id:
            variant = db.get(VideoVariant, v.primary_variant_id)
            playable = bool(
                variant and variant.status == "ready" and variant.object_key.endswith(".m3u8")
            )
        result.append({
            "id": v.id,
            "title": v.title,
            "status": v.status,
            "duration_seconds": v.duration_seconds,
            "playable": playable,
        })
    return result
