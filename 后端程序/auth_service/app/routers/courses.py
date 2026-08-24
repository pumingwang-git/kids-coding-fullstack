"""学生端课包浏览：已发布课包列表 / 详情目录 / 单节课时正文。

阶段 1 最小闭环的消费端入口。门控口径**不在本文件实现**——一律调
`app.course_access.lesson_access`，与 video_play 共用同一份规则（见该模块文档）。

两条硬约束：
1. **目录树不带正文**：`/courses/{id}` 只回标题、时长、试看标记与 unlocked 布尔值。
   正文（content_md / video_url）只在 `/lessons/{id}` 里、且只在 GRANTED 时下发。
   把正文塞进目录树，等于把「未开通看不到」降级成一个前端隐藏问题。
2. **永不下发 video_id**：播放走 `POST /api/lessons/{id}/play`，学生端全程只需要
   lesson_id。给出 video_id 就等于给出一个绕过课时鉴权的坐标。
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import video_watch
from ..course_access import (
    Access,
    block_gate,
    block_lock_reason,
    completed_block_ids,
    course_enrolled,
    course_visible,
    lesson_access,
    lesson_block_open,
    lesson_policy,
    lesson_progress,
    lesson_unlocked,
)
from ..learning_activity import last_activity_at
from ..models import (
    Course,
    CourseCategory,
    CourseLesson,
    CourseLessonBlock,
    CourseSection,
    CourseTag,
    CourseTagLink,
    CourseType,
    LessonBlockCompletion,
    LessonBlockMaterial,
    LessonMarkdownBlock,
    LessonPaperBlock,
    LessonProblemBlock,
    LessonScratchBlock,
    LessonVideoBlock,
    LessonVideoWatch,
    PaperQuestion,
    MaterialAsset,
    ScratchChallenge,
    ScratchSubmission,
    Video,
)

# 判定词表取自规则层：scratch.py 依赖本文件的完成流程，反向 import 会成环。
from ..scratch_rules import TERMINAL_STATUSES as TERMINAL_SUBMISSION_STATUSES
from ..security import as_utc, utcnow
from .auth_secure import current_user, db_session, limit, require_csrf
from .learning_catalog import category_breadcrumb, category_descendant_ids, serialize_tags

router = APIRouter(prefix="/api", tags=["student-courses"])


def _area_exists(db: Session, area_key: str) -> bool:
    from ..models import LearningArea
    area = db.get(LearningArea, area_key)
    return area is not None and area.status != "hidden"


def _course_type_exists(db: Session, area_key: str | None, course_kind: str) -> bool:
    conds = [CourseType.key == course_kind, CourseType.is_active.is_(True)]
    if area_key:
        conds.append(CourseType.area_key == area_key)
    return db.scalar(select(CourseType.id).where(*conds).limit(1)) is not None


def _content_kind(lesson: CourseLesson, block_types: list[str]) -> str:
    """给前端画图标用：video | url | article | mixed | empty。

    内容块优先：有块时按块类型汇总；无块时回退旧字段（§5.3 过渡口径）。
    """
    kinds = list(block_types)
    if not kinds:
        if lesson.video_id:
            kinds.append("video")
        if lesson.video_url:
            kinds.append("url")
        if lesson.content_md:
            kinds.append("article")
    if not kinds:
        return "empty"
    return kinds[0] if len(kinds) == 1 else "mixed"


def _block_types_by_lesson(db: Session, lesson_ids: list[int]) -> dict[int, list[str]]:
    """批量取课时块类型，供目录树画图标，避免逐课时 N+1 查询。"""
    out: dict[int, list[str]] = {lid: [] for lid in lesson_ids}
    if not lesson_ids:
        return out
    for lesson_id, block_type in db.execute(
        select(CourseLessonBlock.lesson_id, CourseLessonBlock.block_type)
        .where(CourseLessonBlock.lesson_id.in_(lesson_ids))
    ).all():
        out.setdefault(lesson_id, []).append(block_type)
    return out


def _course_public(db: Session, course: Course, category: CourseCategory | None, stats: dict) -> dict:
    """课包公开字段。

    不下发 price_cents（B2B 开通制，前台不谈价）、不下发 owner_id / status
    （能查到就说明是 published）。
    """
    return {
        "id": course.id,
        "title": course.title,
        "subtitle": course.subtitle,
        "description": course.description,
        "cover_url": course.cover_url,
        "category_id": course.category_id,
        "category_name": category.name if category else None,
        "category_breadcrumb": category_breadcrumb(db, category),
        "tags": serialize_tags(db, course.id),
        "area_key": course.area_key,
        "course_kind": course.course_kind,
        "difficulty": course.difficulty,
        "section_count": stats.get("section_count", 0),
        "lesson_count": stats.get("lesson_count", 0),
        "total_minutes": stats.get("total_minutes", 0),
    }


def _course_stats(db: Session, course_ids: list[int]) -> dict[int, dict]:
    """一次查全部课包的章节数/课时数/总时长，避免列表页 N+1。"""
    out = {cid: {"section_count": 0, "lesson_count": 0, "total_minutes": 0} for cid in course_ids}
    if not course_ids:
        return out
    for cid, n in db.execute(
        select(CourseSection.course_id, func.count())
        .where(CourseSection.course_id.in_(course_ids))
        .group_by(CourseSection.course_id)
    ).all():
        out[cid]["section_count"] = n
    for cid, n, minutes in db.execute(
        select(CourseLesson.course_id, func.count(), func.coalesce(func.sum(CourseLesson.duration_minutes), 0))
        .where(CourseLesson.course_id.in_(course_ids))
        .group_by(CourseLesson.course_id)
    ).all():
        out[cid]["lesson_count"] = n
        out[cid]["total_minutes"] = int(minutes or 0)
    return out


@router.get("/course-categories")
def list_course_categories(
    request: Request,
    area_key: str | None = None,
    course_kind: str | None = None,
    db: Session = Depends(db_session),
):
    """学生端分类筛选：只返回关联了**已发布课包**的分类，带 course_count。

    草稿/下架课包不参与计数；没有已发布课包的分类不下发（避免空筛选项）。
    分类本身是后台维护的（course_categories 表），这里只做聚合视图。
    """
    current_user(request, db)
    if area_key is not None and not _area_exists(db, area_key):
        raise HTTPException(400, "专区参数不合法。")
    if course_kind is not None and not _course_type_exists(db, area_key, course_kind):
        raise HTTPException(400, "课程类型参数不合法。")
    conds = [Course.status == "published"]
    if area_key is not None:
        conds.append(Course.area_key == area_key)
    if course_kind is not None:
        conds.append(Course.course_kind == course_kind)
    rows = db.execute(
        select(CourseCategory.id, CourseCategory.name, func.count(Course.id))
        .join(Course, Course.category_id == CourseCategory.id)
        .where(*conds)
        .group_by(CourseCategory.id, CourseCategory.name)
        .order_by(CourseCategory.sort_order, CourseCategory.id)
    ).all()
    return {
        "items": [
            {"id": cid, "name": name, "course_count": count}
            for cid, name, count in rows
        ]
    }


@router.get("/courses")
def list_courses(
    request: Request,
    keyword: str = "",
    category_id: int | None = None,
    area_key: str | None = None,
    course_kind: str | None = None,
    tag_id: int | None = None,
    page: int = 1,
    page_size: int = 12,
    db: Session = Depends(db_session),
):
    """已发布课包列表。目录与内容的可见性由课时级门控决定，这里只管橱窗。"""
    current_user(request, db)
    if area_key is not None and not _area_exists(db, area_key):
        raise HTTPException(400, "专区参数不合法。")
    if course_kind is not None and not _course_type_exists(db, area_key, course_kind):
        raise HTTPException(400, "课程类型参数不合法。")
    page = max(1, page)
    page_size = min(max(1, page_size), 48)

    conds = [Course.status == "published"]
    if keyword.strip():
        conds.append(Course.title.ilike(f"%{keyword.strip()}%"))
    if category_id is not None:
        category = db.get(CourseCategory, category_id)
        if category is None or (area_key and category.area_key != area_key):
            raise HTTPException(400, "课程分类参数不合法。")
        conds.append(Course.category_id.in_(category_descendant_ids(db, category_id)))
    if area_key is not None:
        conds.append(Course.area_key == area_key)
    if course_kind is not None:
        conds.append(Course.course_kind == course_kind)
    if tag_id is not None:
        tag = db.get(CourseTag, tag_id)
        if tag is None or (area_key and tag.area_key != area_key):
            raise HTTPException(400, "课程标签参数不合法。")
        conds.append(Course.id.in_(select(CourseTagLink.course_id).where(
            CourseTagLink.tag_id == tag_id
        )))

    total = db.scalar(select(func.count()).select_from(Course).where(*conds)) or 0
    rows = db.scalars(
        select(Course).where(*conds)
        .order_by(Course.sort_order, Course.id.desc())
        .offset((page - 1) * page_size).limit(page_size)
    ).all()

    stats = _course_stats(db, [c.id for c in rows])
    cat_ids = {c.category_id for c in rows if c.category_id}
    cats = {
        c.id: c
        for c in db.scalars(select(CourseCategory).where(CourseCategory.id.in_(cat_ids))).all()
    } if cat_ids else {}

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [_course_public(db, c, cats.get(c.category_id), stats.get(c.id, {})) for c in rows],
    }


@router.get("/courses/continue-learning")
def continue_learning(request: Request, db: Session = Depends(db_session),
                      limit_count: int = Query(5, ge=1, le=20)):
    """学习端首页「继续学习」：最近有学习活动的课时（含续播断点）。

    学习活动四张账本，按「最近活动时间」聚合到课时：
      lesson_video_watch          视频心跳（updated_at）→ 兼作续播断点来源
      lesson_block_completions    块完成（completed_at）
      lesson_problem_attempts     课中练习作答（updated_at）
      lesson_code_runs            编程题试跑（created_at）

    每条目给出 continue_lesson_id（可直接跳转的课时）：本课时未学完就是它自己；
    已学完则指向课程内下一节未完成的课时；整门课学完为 None。无必修块的旧课时
    以「有无视频续播断点」判定是否学完（没断点视为看完，去下一节）。
    已下架课程的记录不返回。放在 /courses/{course_id} 之前注册，避免被 int 路径吞掉。
    """
    user = current_user(request, db)

    # —— 1. 聚合学习活动 → (lesson_id → 最近活动时间) + 视频续播断点 ——
    last_learned = last_activity_at(db, {user.id}, group_by_lesson=True)
    resume_position: dict[int, int] = {}
    resume_beat_at: dict[int, datetime] = {}

    # 视频心跳：同课时多个视频块并行，续播断点取「最近一次心跳」那块的最远位置
    for row in db.scalars(
        select(LessonVideoWatch).where(LessonVideoWatch.user_id == user.id)
    ).all():
        at = row.updated_at or row.last_beat_at
        if at is None:
            continue
        if resume_beat_at.get(row.lesson_id) is None or at > resume_beat_at[row.lesson_id]:
            resume_beat_at[row.lesson_id] = at
            resume_position[row.lesson_id] = row.max_position_seconds

    if not last_learned:
        return {"items": []}

    # —— 2. 组装课时/课程/章节，过滤已删除课时与下架课程 ——
    lesson_ids = sorted(last_learned, key=lambda lid: last_learned[lid], reverse=True)
    lessons = {
        lesson.id: lesson for lesson in db.scalars(
            select(CourseLesson).where(CourseLesson.id.in_(lesson_ids))
        ).all()
    }
    course_ids = sorted({lesson.course_id for lesson in lessons.values()})
    courses = {course.id: course for course in db.scalars(
        select(Course).where(Course.id.in_(course_ids))
    ).all()}
    section_ids = sorted({lesson.section_id for lesson in lessons.values()})
    sections = {section.id: section for section in db.scalars(
        select(CourseSection).where(CourseSection.id.in_(section_ids))
    ).all()}

    # —— 3. 涉及课程的全部课时（含不在最近列表里的，供「下一节」查找）+ 进度数据 ——
    ordered_by_course: dict[int, list[CourseLesson]] = {}
    for lesson in db.scalars(
        select(CourseLesson)
        .join(CourseSection, CourseSection.id == CourseLesson.section_id)
        .where(CourseLesson.course_id.in_(course_ids))
        .order_by(CourseSection.sort_order, CourseSection.id,
                  CourseLesson.sort_order, CourseLesson.id)
    ).all():
        ordered_by_course.setdefault(lesson.course_id, []).append(lesson)

    all_lesson_ids = [lesson.id for lst in ordered_by_course.values() for lesson in lst]
    blocks_by_lesson: dict[int, list[CourseLessonBlock]] = {lid: [] for lid in all_lesson_ids}
    for b in db.scalars(
        select(CourseLessonBlock)
        .where(CourseLessonBlock.lesson_id.in_(all_lesson_ids))
        .order_by(CourseLessonBlock.sort_order, CourseLessonBlock.id)
    ).all():
        blocks_by_lesson.setdefault(b.lesson_id, []).append(b)

    completed_by_lesson: dict[int, set[int]] = {}
    for lesson_id, block_id in db.execute(
        select(LessonBlockCompletion.lesson_id, LessonBlockCompletion.block_id)
        .where(
            LessonBlockCompletion.user_id == user.id,
            LessonBlockCompletion.lesson_id.in_(all_lesson_ids),
        )
    ).all():
        completed_by_lesson.setdefault(lesson_id, set()).add(block_id)

    def _lesson_done(lesson: CourseLesson) -> bool:
        """课时是否学完。有必修块按完成度；无必修块的旧课时以完成记录/续播断点为准。"""
        required = [b for b in blocks_by_lesson.get(lesson.id, []) if b.required]
        if required:
            done = completed_by_lesson.get(lesson.id, set())
            return all(b.id in done for b in required)
        # 无必修块的旧课时：有任何块完成记录（视频看满记账 / 手动确认）即视为学完——
        # 否则已看完的课时 max_position 永远 > 0，会永远卡在「未学完」，
        # 连环效应是 _next_lesson 也跳不过它，「下一节」和「整门学完」都到不了。
        if completed_by_lesson.get(lesson.id):
            return True
        return not resume_position.get(lesson.id)

    def _next_lesson(lesson: CourseLesson) -> CourseLesson | None:
        """课程内下一节未学完的课时（含被跳过时），没有则 None。"""
        seq = ordered_by_course.get(lesson.course_id, [])
        pos = next((i for i, item in enumerate(seq) if item.id == lesson.id), -1)
        if pos < 0:
            return None
        for nxt in seq[pos + 1:]:
            if not _lesson_done(nxt):
                return nxt
        return None

    # —— 4. 组装响应 ——
    items: list[dict] = []
    for lesson_id in lesson_ids:
        lesson = lessons.get(lesson_id)
        course = courses.get(lesson.course_id) if lesson is not None else None
        if lesson is None or not course_visible(course):
            continue
        section = sections.get(lesson.section_id)
        done = completed_by_lesson.get(lesson_id, set())
        progress = lesson_progress(blocks_by_lesson.get(lesson_id, []), done)
        completed = _lesson_done(lesson)
        # 未学完 → 继续本课时；已学完 → 课程内下一节未学完的课时（整门学完为 None）
        continue_lesson = lesson if not completed else _next_lesson(lesson)
        items.append({
            "course_id": course.id,
            "course_title": course.title,
            "course_kind": course.course_kind,
            "area_key": course.area_key,
            "cover_url": course.cover_url,
            "lesson_id": lesson.id,
            "lesson_title": lesson.title,
            "section_title": section.title if section is not None else "",
            "duration_minutes": lesson.duration_minutes,
            "progress": progress,
            "completed": completed,
            "resume_position_seconds": resume_position.get(lesson_id, 0),
            "continue_lesson_id": None if continue_lesson is None else continue_lesson.id,
            "continue_lesson_title": None if continue_lesson is None else continue_lesson.title,
            # 统一过 as_utc：SQLite 读出的是 naive 值，直接 isoformat 会丢时区，
            # 前端 new Date() 会把无时区字符串当本地时间解析，「几分钟前」差出一个时区偏移。
            "last_learned_at": as_utc(last_learned[lesson_id]).isoformat(),
        })
        if len(items) >= limit_count:
            break
    return {"items": items}


@router.get("/courses/{course_id}")
def course_detail(course_id: int, request: Request, page: int = Query(1, ge=1),
                  page_size: int = Query(8, ge=1, le=24), db: Session = Depends(db_session)):
    """课包详情 + 章节课时目录。**目录不含正文**，见模块文档约束 1。"""
    user = current_user(request, db)
    course = db.get(Course, course_id)
    if not course_visible(course):
        raise HTTPException(404, "课包不存在或未发布。")

    category = None
    if course.category_id:
        category = db.get(CourseCategory, course.category_id)

    section_filters = (CourseSection.course_id == course_id,)
    total_sections = db.scalar(select(func.count()).select_from(CourseSection).where(*section_filters)) or 0
    sections = db.scalars(
        select(CourseSection).where(CourseSection.course_id == course_id)
        .order_by(CourseSection.sort_order, CourseSection.id)
        .offset((page - 1) * page_size).limit(page_size)
    ).all()
    section_ids = [section.id for section in sections]
    all_lessons = db.scalars(
        select(CourseLesson).where(CourseLesson.course_id == course_id, CourseLesson.section_id.in_(section_ids))
        .order_by(CourseLesson.sort_order, CourseLesson.id)
    ).all()
    lessons_by_section: dict[int, list[CourseLesson]] = {}
    for lesson in all_lessons:
        lessons_by_section.setdefault(lesson.section_id, []).append(lesson)
    block_types = _block_types_by_lesson(db, [lesson.id for lesson in all_lessons])

    stats = _course_stats(db, [course_id]).get(course_id, {})
    return {
        "course": _course_public(db, course, category, stats),
        "enrolled": course_enrolled(db, user, course),
        "total_sections": total_sections, "page": page, "page_size": page_size,
        "sections": [
            {
                "id": sec.id,
                "title": sec.title,
                "sort_order": sec.sort_order,
                "lessons": [
                    {
                        "id": lesson.id,
                        "section_id": lesson.section_id,
                        "title": lesson.title,
                        "summary": lesson.summary,
                        "duration_minutes": lesson.duration_minutes,
                        "is_trial": lesson.is_trial,
                        "open_policy": lesson_policy(lesson),
                        "trial_block_count": lesson.trial_block_count or 0,
                        "trial_minutes": lesson.trial_minutes or 0,
                        "content_kind": _content_kind(lesson, block_types.get(lesson.id, [])),
                        "unlocked": lesson_unlocked(db, user, lesson),
                    }
                    for lesson in lessons_by_section.get(sec.id, [])
                ],
            }
            for sec in sections
        ],
    }


def _legacy_virtual_blocks(db: Session, lesson: CourseLesson) -> list[dict]:
    """旧字段合成内容块（过渡口径，与 0030 迁移回填顺序一致：图文→平台视频→外链视频）。

    老课时只有 content_md / video_id / video_url、没有 blocks 时，按同一顺序合成
    虚拟块交给学生端渲染——前端只写一套 blocks 逻辑，不需要针对旧字段再写分支。
    返回的 dict 无 DB id（虚拟块），sort_order 为 0..n-1。
    """
    items: list[dict] = []
    order = 0
    if lesson.content_md:
        items.append({"block_type": "markdown", "title": lesson.title, "sort_order": order})
        order += 1
    if lesson.video_id:
        items.append({
            "block_type": "video", "title": lesson.title, "sort_order": order,
            "video": {"source_type": "platform", "video_id": lesson.video_id},
        })
        order += 1
    if lesson.video_url:
        items.append({
            "block_type": "video", "title": lesson.title, "sort_order": order,
            "video": {"source_type": "embed", "video_url": lesson.video_url},
        })
    return items


def _scratch_note(submission) -> str | None:
    """Scratch 提交的一句话总评（入口卡片用）。逐条反馈在 /api/scratch/… 详情里。"""
    if submission is None:
        return None
    if submission.review_comment:
        return submission.review_comment
    try:
        return json.loads(submission.evaluation_json or "{}").get("note") or None
    except (TypeError, ValueError):
        return None


def _student_block_dto(db: Session, lesson: CourseLesson, item, can_access: bool,
                       gate: dict | None = None, user=None) -> dict | None:
    """单个内容块的学生端 DTO（按 sort_order 顺序）。

    保密红线（交接文档 §11.2，2026-08-10 起改为逐块口径）：
    - 锁定块（lock_reason 非空）只给骨架：id/类型/标题/序号 + 闸门字段，不给任何内容。
      注意内容闸看的是 **lock_reason 而不是 can_access**：顺序锁（Gate B）的块虽然
      can_access=true，但学生还没轮到学，同样不能把正文/题目提前读走（交接文档 §4）；
    - 平台视频不下发 video_id（播放走课时级授权接口，学生端只有 block_id）；
    - 练习/作业块不下发 paper_id 与卷内容（作答链路 PR 3 接入），只给投放规则；
    - 课中练习块（v2 单题化 §4.4）只下发 problem 投放规则，**绝不下发 problem_id_no**；
    - 阅读资料不下发 object_key（对象存储位置是内部细节），只给摘要供渲染。

    item 是真实 CourseLessonBlock 行或旧字段合成的虚拟 dict。已解锁但明细缺失
    （视频块没绑定、资料块无关联等）对学生端等同不存在，返回 None 由调用方跳过。
    """
    real = isinstance(item, CourseLessonBlock)
    if real:
        block_id, block_type, title, sort_order = item.id, item.block_type, item.title, item.sort_order
    else:
        block_id, block_type, title, sort_order = None, item["block_type"], item["title"], item["sort_order"]

    base = {
        "id": block_id,
        "block_type": block_type,
        "title": title,
        "sort_order": sort_order,
        "can_access": can_access,
    }
    # 闸门字段（0034 起）。旧字段合成的虚拟块没有 unlock_rule/完成记录，按「自由学习、
    # 未完成」兜底——它们本来就是过渡期产物，不参与闯关。
    base.update(gate or {
        "unlock_rule": "free",
        "is_unlocked": True,
        "completed": False,
        "lock_reason": None if can_access else "not_enrolled",
    })
    if base["lock_reason"] is not None:
        return base

    if block_type == "markdown":
        content = ""
        if real:
            md = db.get(LessonMarkdownBlock, item.id)
            content = md.content_md if md else ""
        else:
            content = lesson.content_md or ""
        if not content:
            return None
        base["content_md"] = content
    elif block_type == "video":
        vd = None
        if real:
            vd = db.get(LessonVideoBlock, item.id)
            if vd is None:
                return None
            source_type, video_id, video_url, completion = (
                vd.source_type, vd.video_id, vd.video_url, vd.completion_percent
            )
        else:
            video = item["video"]
            source_type = video.get("source_type", "platform")
            video_id = video.get("video_id")
            video_url = video.get("video_url")
            completion = 100
        base["source_type"] = source_type
        base["completion_percent"] = completion
        platform_video = None
        if source_type == "platform":
            platform_video = db.get(Video, video_id) if video_id else None
            if platform_video is None:
                return None
            base["ready"] = platform_video.status == "ready"
            base["duration_seconds"] = platform_video.duration_seconds
            # 续播断点：账本行的 max_position_seconds（到达过的最远位置）。
            # 只对真实块有账本；未登录/无记录一律 0。播放器 loadedmetadata 后 seek 到这里。
            base["resume_position_seconds"] = 0
            if user is not None and real:
                watch = db.scalar(
                    select(LessonVideoWatch).where(
                        LessonVideoWatch.user_id == user.id,
                        LessonVideoWatch.block_id == block_id,
                    )
                )
                if watch is not None:
                    base["resume_position_seconds"] = watch.max_position_seconds
        else:  # embed / direct：外链地址，学生端按类型选 iframe 或 Video.js
            if not video_url:
                return None
            base["video_url"] = video_url
        # 完成度由谁裁决，**服务端说了算，前端只认这个字段**（同 lock_reason 的处理方式）。
        # 让前端自己按 source_type 推的话，direct（播放器报得出位置、服务端却没有时长）
        # 这类边界必然推错，而推错的后果是学生卡在一个永远完不成的块上。
        # 旧字段合成的虚拟块不参与记账，一律 MANUAL。
        base["completion_mode"] = (
            video_watch.completion_mode(vd, platform_video) if real else video_watch.MANUAL
        )
    elif block_type == "materials":
        if not real:
            return None  # 旧字段没有资料
        base["materials"] = [
            {
                "material_id": material_id,
                "display_name": display_name,
                "asset_type": asset_type,
                "mime_type": mime_type,
                "size_bytes": size_bytes,
                "sha256": sha256,
            }
            for material_id, display_name, asset_type, mime_type, size_bytes, sha256 in db.execute(
                select(
                    MaterialAsset.id,
                    MaterialAsset.display_name,
                    MaterialAsset.asset_type,
                    MaterialAsset.mime_type,
                    MaterialAsset.size_bytes,
                    MaterialAsset.sha256,
                )
                .select_from(LessonBlockMaterial)
                .join(MaterialAsset, MaterialAsset.id == LessonBlockMaterial.material_id)
                .where(
                    LessonBlockMaterial.block_id == block_id,
                    MaterialAsset.status == "ready",
                )
                .order_by(LessonBlockMaterial.sort_order, LessonBlockMaterial.id)
            ).all()
        ]
    elif block_type == "practice":
        # v2 单题化：课中练习块只给「渲染骨架 + 投放规则」，绝不下发 problem_id_no
        # （延续保密红线 courses.py:270-273：练习/作业块不下发 paper_id 与卷内容；
        #  题目内容由 X2 作答链路服务端按 block 取题下发，见实现计划 v2 §4.4）。
        if not real:
            return None
        pb_ = db.get(LessonProblemBlock, item.id)
        if pb_ is None:
            return None
        base["problem"] = {
            "problem_type": pb_.problem_type,
            "display_no": pb_.display_no,  # NULL = 前端回退该课时内 practice 块之间序号
            "score": pb_.score,
            "attempt_limit": pb_.attempt_limit,
            "shuffle_options": pb_.shuffle_options,
            "show_analysis": pb_.show_analysis,
        }
    elif block_type == "scratch":
        # Scratch 块只给"入口卡片"要用的东西：关卡名、一句话摘要、我上次交得怎么样。
        # 完整题面、判定清单、作品版本与逐条反馈一律走
        # /api/scratch/lesson-blocks/{id}——那条路径会重跑一次门控，而课时详情是
        # 一次性下发整节课的响应，把题面塞进来等于绕过逐块鉴权多发一份。
        if not real:
            return None
        sc_ = db.get(LessonScratchBlock, item.id)
        challenge = db.get(ScratchChallenge, sc_.challenge_id) if sc_ else None
        # 未绑定 / 挑战被删 / 挑战未发布：与"视频块没绑定"同一口径，对学生端等同不存在。
        # 否则学生看到一个点进去必然 404 的入口。
        if challenge is None or challenge.status != "published":
            return None
        summary = " ".join((challenge.instructions_md or "").split())
        # 摘要要去掉 Markdown 标题号：卡片上是一行纯文本，"# 任务"里的井号只是噪声。
        summary = summary.lstrip("# ").strip()
        last, attempts = None, 0
        if user is not None:
            last = db.scalar(
                select(ScratchSubmission)
                .where(ScratchSubmission.user_id == user.id,
                       ScratchSubmission.lesson_block_id == item.id)
                .order_by(ScratchSubmission.attempt_no.desc()).limit(1)
            )
            attempts = last.attempt_no if last is not None else 0
        base["scratch"] = {
            "challenge_id": challenge.id,
            "challenge_title": challenge.title,
            "has_starter": bool(challenge.starter_sb3_key),
            "instructions_summary": summary[:80],
            # 入口卡片的三态文案（未开始 / 已通过 / 待人工 / 未通过）由它决定。
            "submission_status": last.status if last is not None else None,
            "attempt_count": attempts,
            # 只给一句总评，逐条反馈在 Scratch 详情接口里——卡片放不下，也没必要在
            # 课时详情里把每个块的判定明细都发一遍。
            "feedback": _scratch_note(last),
            # 解析视频会透露实现思路，因此必须先有一次终态提交；最终签发时还会
            # 在 /api/scratch/.../analysis-play 重跑同一套课时门控。
            "has_analysis_video": bool(challenge.analysis_video_id),
            "analysis_available": bool(
                challenge.analysis_video_id
                and last is not None
                and last.status in TERMINAL_SUBMISSION_STATUSES
            ),
            # 示范项目同理，而且更严：它就是答案。这两个布尔值是入口按钮显示/隐藏的
            # 唯一数据来源，**一个 URL 都不下发**——课时详情一次性发整节课所有块，
            # 一个越权字段会连着几十个块一起漏。
            "has_demo": bool(challenge.demo_sb3_key),
            "demo_available": bool(
                challenge.demo_sb3_key
                and last is not None
                and last.status in TERMINAL_SUBMISSION_STATUSES
            ),
        }
    else:  # homework —— 保持现状（绑卷投放规则，不下发 paper_id）
        if not real:
            return None
        pd_ = db.get(LessonPaperBlock, item.id)
        if pd_ is None:
            return None
        base["mode"] = pd_.mode
        base["attempt_limit"] = pd_.attempt_limit
        base["shuffle_questions"] = pd_.shuffle_questions
        base["shuffle_options"] = pd_.shuffle_options
        base["show_score"] = pd_.show_score
        base["show_analysis"] = pd_.show_analysis
        base["due_at"] = as_utc(pd_.due_at).isoformat() if pd_.due_at else None
        # 入口卡片要显示「共 N 题」。只下发数量这一个数字，不下发 paper_id 与题目，
        # 与上面投放规则同一保密口径；进了作答流程后候考接口本来就公开题数。
        base["question_count"] = db.scalar(
            select(func.count()).select_from(PaperQuestion)
            .where(PaperQuestion.paper_id == pd_.paper_id)
        ) or 0
    return base


def _serialize_lesson_blocks(db: Session, user, lesson: CourseLesson,
                             granted: bool) -> tuple[list[dict], dict]:
    """课时内容块的学生端 DTO 列表 + 课时进度。

    两道闸门都在这里合成（判定实现全在 course_access.py，本文件不复刻规则）：
      Gate A 权限闸  granted 或 open_policy 逐块判定 → can_access
      Gate B 路径闸  unlock_rule + 前置块完成情况   → is_unlocked
    二者合成 lock_reason，前端只认这一个字段。

    返回 (blocks, progress)。进度分母只数 required=True 的块。
    """
    rows = list(db.scalars(
        select(CourseLessonBlock).where(CourseLessonBlock.lesson_id == lesson.id)
        .order_by(CourseLessonBlock.sort_order, CourseLessonBlock.id)
    ).all())
    completed_ids = completed_block_ids(db, user, lesson.id)
    progress = lesson_progress(rows, completed_ids)

    items: list = rows if rows else _legacy_virtual_blocks(db, lesson)
    out: list[dict] = []
    for item in items:
        real = isinstance(item, CourseLessonBlock)
        if real:
            g = block_gate(db, user, lesson, item, rows, completed_ids, granted)
            can_access = g["can_access"]
            gate = {
                "unlock_rule": item.unlock_rule,
                "is_unlocked": g["is_unlocked"],
                "completed": item.id in completed_ids,
                "lock_reason": g["lock_reason"],
            }
        else:
            # 旧字段虚拟块：不参与闯关，只走权限闸；gate 由 _student_block_dto 内部兜底
            can_access = granted or lesson_block_open(db, user, lesson, item["sort_order"])
            gate = None
        dto = _student_block_dto(db, lesson, item, can_access, gate, user)
        if dto is None:
            continue  # 已解锁但明细缺失的块对学生端等同不存在
        out.append(dto)
    return out, progress


@router.get("/lessons/{lesson_id}")
def lesson_detail(lesson_id: int, request: Request, db: Session = Depends(db_session)):
    """单节课时：标题摘要 + 开放策略 + 逐块内容（含 can_access）+ 上下节导航。

    上下节按整个课包展平后取相邻（section.sort_order, lesson.sort_order），
    放后端算是因为前端拿不到完整目录时也要能跳，且展平规则只该有一份实现。

    2026-08-10 起不再「未解锁整页锁死」：正文以内容块为单位下发，锁定块只给
    骨架（标题可见 + can_access=false），由前端渲染锁遮罩与开通引导。
    """
    user = current_user(request, db)
    lesson = db.get(CourseLesson, lesson_id)
    if lesson is None:
        raise HTTPException(404, "课时不存在。")
    course = db.get(Course, lesson.course_id)
    if not course_visible(course):
        raise HTTPException(404, "课时不存在。")  # 课包未发布：对学生等同不存在

    access = lesson_access(db, user, lesson)
    granted = access is Access.GRANTED

    # 展平整包课时，算上下节。用 join 保证按章节顺序、再按章节内顺序。
    ordered = db.scalars(
        select(CourseLesson)
        .join(CourseSection, CourseSection.id == CourseLesson.section_id)
        .where(CourseLesson.course_id == lesson.course_id)
        .order_by(CourseSection.sort_order, CourseSection.id,
                  CourseLesson.sort_order, CourseLesson.id)
    ).all()
    ids = [lesson.id for lesson in ordered]
    pos = ids.index(lesson.id) if lesson.id in ids else -1

    payload = {
        "id": lesson.id,
        "course_id": lesson.course_id,
        "course_title": course.title,
        "area_key": course.area_key,
        "course_kind": course.course_kind,
        "section_id": lesson.section_id,
        "title": lesson.title,
        "summary": lesson.summary,
        "duration_minutes": lesson.duration_minutes,
        "is_trial": lesson.is_trial,
        "open_policy": lesson_policy(lesson),
        "trial_block_count": lesson.trial_block_count or 0,
        "trial_minutes": lesson.trial_minutes or 0,
        "unlocked": granted,
        "content_kind": _content_kind(lesson, _block_types_by_lesson(db, [lesson.id]).get(lesson.id, [])),
        "prev_lesson_id": ids[pos - 1] if pos > 0 else None,
        "next_lesson_id": ids[pos + 1] if 0 <= pos < len(ids) - 1 else None,
        # 旧字段兼容：完整开放才下发（内容以 blocks 为准，这里兜底旧播放器）
        "content_md": None,
        "video_url": None,
        "has_video": False,
        "video_ready": False,
    }
    payload["blocks"], payload["progress"] = _serialize_lesson_blocks(db, user, lesson, granted)
    if granted:
        video = db.get(Video, lesson.video_id) if lesson.video_id else None
        payload.update({
            "content_md": lesson.content_md,
            "video_url": lesson.video_url,
            "has_video": video is not None,
            "video_ready": bool(video is not None and video.status == "ready"),
        })
    return payload


COMPLETE_SOURCES = {"manual", "video", "practice", "homework"}


class BlockCompletePayload(BaseModel):
    """完成上报。

    progress_percent 只有视频块用得上：播放器每 15s 节流上报一次，达不到块配置的
    completion_percent 就只是个中间态，不写记录。

    默认值是 None 而不是 100：视频块上"没报进度"必须按 0 处理（fail closed）。
    默认 100 的后果是一个空 body 的 POST 就能把任何视频块刷成看完——门槛形同虚设。
    非视频块不看这个字段，缺省与否都一样。
    """

    source: str = Field(default="manual")
    progress_percent: int | None = Field(default=None, ge=0, le=100)


def _gated_block(db: Session, request: Request, lesson_id: int, block_id: int):
    """解析课时/块并过两道闸门，返回 (user, lesson, block, ordered, before_ids, granted)。

    `complete` 与 `watch` 共用。**两个端点的门控必须一字不差**——记账端点若漏了这道闸，
    学生就能隔着锁把观看时长刷满，等块一解锁当场达标，闯关闸等于没有。
    """
    user = current_user(request, db)
    lesson = db.get(CourseLesson, lesson_id)
    if lesson is None:
        raise HTTPException(404, "课时不存在。")
    if not course_visible(db.get(Course, lesson.course_id)):
        raise HTTPException(404, "课时不存在。")
    block = db.get(CourseLessonBlock, block_id)
    if block is None or block.lesson_id != lesson_id:
        raise HTTPException(404, "该课时没有这个内容块。")

    granted = lesson_access(db, user, lesson) is Access.GRANTED
    ordered = list(db.scalars(
        select(CourseLessonBlock).where(CourseLessonBlock.lesson_id == lesson_id)
        .order_by(CourseLessonBlock.sort_order, CourseLessonBlock.id)
    ).all())
    before_ids = completed_block_ids(db, user, lesson_id)

    # 越权保护：两种锁都不允许上报，且**不写入任何记录**。
    # 否则学生可以直接 POST 把没权限的块刷成已完成，把闯关闸门整条绕过去。
    reason = block_lock_reason(db, user, lesson, block, ordered, before_ids, granted)
    if reason == "not_enrolled":
        raise HTTPException(403, "该内容尚未对你开放。")
    if reason == "sequential":
        raise HTTPException(403, "请先完成前面的内容块。")
    return user, lesson, block, ordered, before_ids, granted


def _record_completion(db: Session, user, block, lesson_id: int, source: str,
                       before_ids: set[int], *, commit: bool = True) -> None:
    """写一条完成记录（幂等）。已完成就什么都不做。"""
    if block.id in before_ids:
        return
    completion = LessonBlockCompletion(
        user_id=user.id, block_id=block.id, lesson_id=lesson_id, source=source,
    )
    try:
        with db.begin_nested():
            db.add(completion)
            db.flush()
    except IntegrityError:
        # 并发双击：唯一约束挡下，当作已完成处理（幂等，§5.3）
        pass
    if commit:
        db.commit()


def _newly_unlocked(db: Session, user, lesson, ordered, before_ids: set[int],
                    after_ids: set[int], granted: bool, skip_block_id: int) -> list[int]:
    """本次上报后新解锁的块：上报前锁着、上报后开了的那些。

    抽成函数是因为 complete 与 watch 都要回这个字段，而它们**必须给出同一个答案**：
    前端拿它刷新抽屉的锁图标，两处算法一旦分叉，就会出现「用心跳完成的块不刷新锁、
    用手动完成的块刷新」这种没人查得出来的差异。
    """
    unlocked: list[int] = []
    for other in ordered:
        if other.id == skip_block_id:
            continue
        was = block_lock_reason(db, user, lesson, other, ordered, before_ids, granted)
        now = block_lock_reason(db, user, lesson, other, ordered, after_ids, granted)
        if was == "sequential" and now is None:
            unlocked.append(other.id)
    return unlocked


def _video_rows(db: Session, block: CourseLessonBlock):
    """(视频块明细, 平台视频行)。非视频块或未绑定时相应位置为 None。"""
    if block.block_type != "video":
        return None, None
    vd = db.get(LessonVideoBlock, block.id)
    video = db.get(Video, vd.video_id) if vd is not None and vd.video_id else None
    return vd, video


@router.post("/lessons/{lesson_id}/blocks/{block_id}/complete")
def complete_block(lesson_id: int, block_id: int, request: Request,
                   payload: BlockCompletePayload | None = None,
                   db: Session = Depends(db_session)):
    """标记一个内容块完成（交接文档 14 §5 / P5）。

    幂等：重复上报返回 200，不报错、不改 completed_at。完成记录只增不减。

    返回 unlocked_block_ids = **本次上报后新解锁的块**。有了它，前端刷新抽屉的
    锁图标不需要重拉整个课时详情——那个响应带着全部图文正文，为了一个锁图标
    重拉一遍太浪费。

    **视频块见下方注释**：账本裁决模式下本端点对它不再有写入能力。
    """
    require_csrf(request)
    user, lesson, block, ordered, before_ids, granted = _gated_block(
        db, request, lesson_id, block_id)

    data = payload or BlockCompletePayload()
    source = data.source if data.source in COMPLETE_SOURCES else "manual"

    if block.block_type == "scratch":
        # ============ Scratch 块：本端点**永远只读** ============
        # 完成只能由 POST /api/scratch/lesson-blocks/{id}/submit 在服务端判定通过后写入
        # （任务书 21b：客户端不能传 passed / score / 完成状态作为可信结果）。
        # 少了这一段，学生对任意 scratch 块打一个空 body 的 /complete 就能标记完成，
        # 判定、进度和 sequential 闯关闸一起被绕过——比视频块那条口子更彻底，
        # 因为 Scratch 块本来就没有"客户端能自证"的完成条件。
        #
        # 与视频块同样是**静默只读**而不是 403：老前端（未接 Scratch 之前）对所有块
        # 一视同仁地上报，报错只会在学生屏幕上刷出一片无意义的失败提示。
        return {
            "completed": block.id in before_ids,
            "progress": lesson_progress(ordered, before_ids),
            "unlocked_block_ids": [],
        }

    if block.block_type == "video":
        settings = request.app.state.settings
        vd, video = _video_rows(db, block)
        mode = video_watch.completion_mode(vd, video)
        # ============ 裁决权移交（《20、…设计》批次 B3）============
        # 账本模式下，视频块的完成**只能由 /watch 的服务端记账写入**，本端点对它
        # 一律只读。理由：客户端报什么进度都是它自己说的，服务端手里有账本这个
        # 独立事实，就没有理由再采信前者。
        #
        # 注意是「静默只读」不是 403：老前端（B2 前）还在打这个端点，报错只会在
        # 学生屏幕上刷出一片失败提示，而它本来就不该有效果。
        if mode == video_watch.LEDGER and settings.video_watch_authoritative:
            return _watch_state_payload(db, user, lesson, block, ordered, before_ids,
                                        granted, vd, video, settings)
        # 降级块（embed / direct / 时长未知）与灰度期：沿用阈值判定。
        # 判定依据是 **block.block_type**，不是客户端自报的 source——按 source 判的话，
        # 把 source 换成 "manual" 就整段跳过了检查，completion_percent 连同依赖它的
        # sequential 闯关闸一起被绕过。客户端能决定的只是"报什么进度"，
        # 不该由它决定"要不要过这道闸"。
        threshold = vd.completion_percent if vd is not None else 100
        # 没报进度按 0 算：视频块的完成必须由播放进度驱动，不能靠一个空 body 蒙混。
        if (data.progress_percent or 0) < threshold:
            return {
                "completed": block.id in before_ids,
                "progress": lesson_progress(ordered, before_ids),
                "unlocked_block_ids": [],
            }
        source = "video"  # 完成来源如实记成 video，别让审计里留下 manual

    _record_completion(db, user, block, lesson_id, source, before_ids)
    after_ids = completed_block_ids(db, user, lesson_id)
    return {
        "completed": True,
        "progress": lesson_progress(ordered, after_ids),
        "unlocked_block_ids": _newly_unlocked(
            db, user, lesson, ordered, before_ids, after_ids, granted, block.id),
    }


class WatchBeatPayload(BaseModel):
    """播放心跳。**只报位置，不报时长、不报百分比**。

    时长由服务端从 videos.duration_seconds 取——让客户端报时长等于把分母交出去，
    报一个 duration=1 就能让阈值变成 1 秒。百分比同理由服务端换算。
    """

    position_seconds: int = Field(ge=0, le=24 * 3600)


def _watch_state_payload(db: Session, user, lesson, block, ordered, before_ids: set[int],
                         granted: bool, vd, video, settings,
                         unlocked: list[int] | None = None) -> dict:
    """账本状态的对外形状。心跳响应与「只读地看一眼」共用。"""
    row = db.scalar(
        select(LessonVideoWatch).where(
            LessonVideoWatch.user_id == user.id, LessonVideoWatch.block_id == block.id)
    )
    duration = video.duration_seconds if video is not None else None
    required = video_watch.required_seconds(
        duration, vd.completion_percent if vd is not None else 100)
    watched = row.watched_seconds if row is not None else 0
    return {
        "completed": block.id in (before_ids if unlocked is None else completed_block_ids(
            db, user, lesson.id)),
        "watched_seconds": watched,
        "required_seconds": required,
        "duration_seconds": duration,
        # 时长未知时前端不画百分比进度条，改提示「看完后请手动确认」（设计文档 §9.4）
        "percent": None if not required else min(100, int(watched * 100 / required)),
        "resume_position_seconds": row.max_position_seconds if row is not None else 0,
        "completion_mode": video_watch.completion_mode(vd, video),
        "heartbeat_seconds": settings.video_watch_heartbeat_seconds,
        "progress": lesson_progress(ordered, before_ids if unlocked is None
                                    else completed_block_ids(db, user, lesson.id)),
        "unlocked_block_ids": unlocked or [],
    }


@router.post("/lessons/{lesson_id}/blocks/{block_id}/watch")
def watch_beat(lesson_id: int, block_id: int, payload: WatchBeatPayload, request: Request,
               db: Session = Depends(db_session)):
    """播放心跳：把「看了多久」记进服务端账本，达标即写完成度。

    算法在 app/video_watch.py（纯函数，可单测），本端点只负责取行、上锁、落库。
    改动前请读那个模块的文档字符串与《20、视频观看时长服务端记账-设计》§4。
    """
    require_csrf(request)
    settings = request.app.state.settings
    user, lesson, block, ordered, before_ids, granted = _gated_block(
        db, request, lesson_id, block_id)
    if block.block_type != "video":
        raise HTTPException(400, "该内容块不是视频。")
    # 心跳 15 秒一拍、可能多块并行，闸门开在正常量的十几倍上——它挡的是打洪水，
    # 不是记账正确性（正确性由 video_watch.credit 的三个夹子保证）。
    limit(request, "lesson-watch", str(user.id), 60, 60)

    vd, video = _video_rows(db, block)
    mode = video_watch.completion_mode(vd, video)
    if mode != video_watch.LEDGER:
        # 降级块没有账本可记（embed 拿不到位置、direct 与异常 platform 没有时长）。
        # 回 200 而不是 4xx：前端据 completion_mode 本就不该发心跳，发了也只是白发一次，
        # 不值得在学生屏幕上刷一条错误。
        return _watch_state_payload(db, user, lesson, block, ordered, before_ids,
                                    granted, vd, video, settings)

    now = utcnow()
    row = db.scalar(
        select(LessonVideoWatch).where(
            LessonVideoWatch.user_id == user.id,
            LessonVideoWatch.block_id == block.id,
        ).with_for_update()
    )
    if row is None:
        row = LessonVideoWatch(
            user_id=user.id, block_id=block.id, lesson_id=lesson_id, video_id=vd.video_id,
        )
        db.add(row)
        try:
            db.flush()
        except IntegrityError:
            # 并发首拍：唯一约束挡下抢输的那个，回滚重读而不是抛 500。
            db.rollback()
            row = db.scalar(
                select(LessonVideoWatch).where(
                    LessonVideoWatch.user_id == user.id,
                    LessonVideoWatch.block_id == block.id,
                ).with_for_update()
            )
            if row is None:
                raise HTTPException(409, "观看记录正在并发写入，请重试。") from None
    elif row.video_id != vd.video_id:
        # 换绑视频：旧账对新视频没有意义，整行归零重开（设计文档 §9.6）。
        # 不归零的话，学生能拿旧视频攒的时长兑现新视频的完成度。
        row.video_id = vd.video_id
        row.watched_seconds = 0
        row.max_position_seconds = 0
        row.last_position_seconds = 0
        row.last_beat_at = None
        row.completed_at = None

    result = video_watch.credit(
        position_seconds=payload.position_seconds,
        duration_seconds=video.duration_seconds,
        prev_position=row.last_position_seconds,
        prev_watched=row.watched_seconds,
        prev_max_position=row.max_position_seconds,
        last_beat_at=row.last_beat_at,
        now=now,
        beat_cap_seconds=settings.video_watch_beat_cap_seconds,
        tolerance=settings.video_watch_tolerance,
    )
    row.watched_seconds = result.watched_seconds
    row.max_position_seconds = result.max_position
    row.last_position_seconds = min(payload.position_seconds, video.duration_seconds)
    row.last_beat_at = now
    row.beat_count += 1

    required = video_watch.required_seconds(video.duration_seconds, vd.completion_percent)
    reached = video_watch.completed(result.watched_seconds, result.max_position, required)
    if reached and row.completed_at is None:
        row.completed_at = now
    db.commit()

    unlocked: list[int] = []
    if reached:
        _record_completion(db, user, block, lesson_id, "video", before_ids)
        after_ids = completed_block_ids(db, user, lesson_id)
        unlocked = _newly_unlocked(
            db, user, lesson, ordered, before_ids, after_ids, granted, block.id)

    return _watch_state_payload(db, user, lesson, block, ordered, before_ids,
                                granted, vd, video, settings,
                                unlocked=unlocked if reached else None)


# ---------------------------------------------------------------------------
# 学生端资料下载/预览（交接文档 15 §7.3，S1）
#
# 红线：路径必须带 lesson_id + block_id，不能做成 /api/materials/{id}/download。
# 资料是跨课包共享的素材库（MaterialAsset 与课时是多对多，经 LessonBlockMaterial
# 关联）。按 material_id 单独开放 = 任何登录学生递增 id 就能拖走全站所有课包的
# 资料，两道闸门形同虚设。带上下文才能校验：
#   1. 课时存在、块属于该课时、资料确实绑在该块上（LessonBlockMaterial）；
#   2. 该块对当前用户 lock_reason is None（复用 course_access.block_gate，
#      不在路由体里另写判定——文档 14 §4.4 同一条红线）；
#   3. MaterialAsset.status == "ready"。
# 实现照抄 admin_materials.download_material 的 StreamingResponse 代理范式
# （含 ASCII fallback 文件名），响应不下发 object_key——对象存储位置是内部细节。
# ---------------------------------------------------------------------------


def _resolve_student_material(db, user, lesson_id: int, block_id: int, material_id: int):
    """学生端资料三条校验，返回 (lesson, block, asset)。任何一条不满足抛 404/403。"""
    lesson = db.get(CourseLesson, lesson_id)
    if lesson is None:
        raise HTTPException(404, "课时不存在。")
    course = db.get(Course, lesson.course_id)
    if not course_visible(course):
        raise HTTPException(404, "课时不存在。")  # 未发布课包对学生等同不存在
    block = db.get(CourseLessonBlock, block_id)
    if block is None or block.lesson_id != lesson_id:
        raise HTTPException(404, "该课时没有这个内容块。")
    binding = db.scalar(
        select(LessonBlockMaterial).where(
            LessonBlockMaterial.block_id == block_id,
            LessonBlockMaterial.material_id == material_id,
        )
    )
    if binding is None:
        raise HTTPException(404, "该块没有绑定这份资料。")
    granted = lesson_access(db, user, lesson) is Access.GRANTED
    ordered = list(db.scalars(
        select(CourseLessonBlock).where(CourseLessonBlock.lesson_id == lesson_id)
        .order_by(CourseLessonBlock.sort_order, CourseLessonBlock.id)
    ).all())
    completed_ids = completed_block_ids(db, user, lesson_id)
    reason = block_gate(db, user, lesson, block, ordered, completed_ids, granted)["lock_reason"]
    if reason == "not_enrolled":
        raise HTTPException(403, "该内容尚未对你开放。")
    if reason == "sequential":
        raise HTTPException(403, "请先完成前面的内容块。")
    asset = db.get(MaterialAsset, material_id)
    if asset is None or asset.status != "ready":
        raise HTTPException(404, "资料不存在或尚未就绪。")
    return lesson, block, asset


def _parse_material_range(range_header: str | None):
    """解析 Range: bytes=start-end。抄自 video_play._parse_range（交接文档 17 批次1 S1-2），
    资料代理与视频流式代理行为对齐——支持 Range 后浏览器 PDF 阅读器才能按页取。"""
    if not range_header:
        return None
    match = re.match(r"bytes=(\d*)-(\d*)$", range_header.strip())
    if not match:
        return None
    start_s, end_s = match.groups()
    start = int(start_s) if start_s else 0
    end = int(end_s) if end_s else None
    return start, end


def _proxy_material_stream(request: Request, asset: MaterialAsset, disposition: str):
    """从 MinIO 流式转发资料对象，不暴露 object_key。

    兜底路径（交接文档 17 批次1 S1-2）：当 ?proxy=1 或未配 minio_public_endpoint 时走这里。
    在原 StreamingResponse 基础上补齐 Content-Length / Accept-Ranges / Range 206 / ETag /
    Cache-Control——Range 支持是 PDF 阅读器秒开的关键（抄 video_play.stream 的实现），
    Cache-Control 让「切走再切回」走浏览器缓存而不是重下一遍。块从 1MB 调到 256KB，
    首字节更快、内存更稳。
    """
    settings = request.app.state.settings
    from fastapi.responses import StreamingResponse

    from ..s3_multipart import get_minio_client

    client = get_minio_client(settings)
    rng = _parse_material_range(request.headers.get("range"))
    get_kwargs = {}
    if rng is not None:
        start, end = rng
        get_kwargs["Range"] = f"bytes={start}-{end if end is not None else ''}"
    try:
        resp = client.get_object(
            Bucket=settings.minio_materials_bucket, Key=asset.object_key, **get_kwargs
        )
    except Exception as exc:
        raise HTTPException(502, "对象存储暂不可用，请稍后重试。") from exc
    body = resp["Body"]

    # 透传对象存储给的元信息：ETag 让浏览器做条件请求（304），Cache-Control 让切走再
    # 切回走磁盘缓存。private = 只在此用户浏览器缓存（资料是私有内容）。
    headers = {
        "Cache-Control": "private, max-age=600",
        "Accept-Ranges": "bytes",
    }
    etag = resp.get("ETag")
    if etag:
        headers["ETag"] = etag
    content_length = resp.get("ContentLength")
    if content_length is not None:
        headers["Content-Length"] = str(content_length)
    fallback = asset.display_name.encode("ascii", "ignore").decode() or "download"
    headers["Content-Disposition"] = (
        f"{disposition}; filename=\"{fallback}\"; filename*=UTF-8''{quote(asset.display_name)}"
    )

    status_code = 200
    if rng is not None:
        # 与 video_play.stream 同一修复（P0-1）：透传 S3 ContentRange（bytes start-end/
        # total）——end 是 S3 实际返回的最后字节、total 是完整对象长度。旧实现用
        # rng[0] + total - 1 在 open-ended Range（bytes=start-）下算出越界的结束值，
        # PDF 阅读器据此拼下一段 Range 会 416 或反复重试。
        content_range = resp.get("ContentRange")
        if content_range and re.match(r"^bytes \d+-\d+/\d+$", content_range):
            status_code = 206
            headers["Content-Range"] = content_range
        else:
            # 兜底（正常走不到：S3 对合法 Range 必回 ContentRange）：
            # ContentLength 是本次分片的字节数，end 由 start + 本段长度算得，一定准；
            # **总长这里是真不知道**，按 RFC 7233 §4.2 写 "*"——猜一个 total 更糟：
            # PDF.js 拿 bytes=0-262143 预热时会以为整份文件只有 256KB，后面不再取。
            length = resp.get("ContentLength")
            if length:
                status_code = 206
                end = rng[0] + int(length) - 1
                headers["Content-Range"] = f"bytes {rng[0]}-{end}/*"

    def _chunks():
        while True:
            chunk = body.read(256 * 1024)  # 256KB：首字节更快、内存更稳
            if not chunk:
                break
            yield chunk

    return StreamingResponse(
        _chunks(),
        status_code=status_code,
        media_type=asset.mime_type,
        headers=headers,
    )


# inline 预览留宽一点（PDF.js 可能要边看边按页取）；下载点一下就走，短一点。
# TTL 是预签名 URL 的有效期——安全性靠短 TTL，不靠保密：学生把 URL 转给同学，
# 过期后就失效了（交接文档 17 §3.1 二代做法的安全边界）。
INLINE_TTL = 300
DOWNLOAD_TTL = 60


@router.get("/lessons/{lesson_id}/blocks/{block_id}/materials/{material_id}/download")
def download_lesson_material(lesson_id: int, block_id: int, material_id: int,
                             request: Request, db: Session = Depends(db_session),
                             proxy: int = 0):
    """学生端资料下载（attachment）。

    鉴权后优先 302 到预签名 URL（交接文档 17 批次1 S1-1）：字节直接从对象存储走，
    Range / ETag / 断点续传白送，应用不当中转。?proxy=1 或未配 public_endpoint 时
    退回 _proxy_material_stream 兜底。**_resolve_student_material 一行不改**，
    三条校验 + 两道闸门 + 路径带 lesson_id/block_id 的红线全部保留。
    """
    user = current_user(request, db)
    _, _, asset = _resolve_student_material(db, user, lesson_id, block_id, material_id)
    settings = request.app.state.settings
    if not proxy and settings.minio_public_endpoint:
        from ..s3_multipart import presign_material_get
        url = presign_material_get(
            settings, settings.minio_materials_bucket, asset.object_key,
            filename=asset.display_name, disposition="attachment", expires=DOWNLOAD_TTL,
        )
        if url:
            # 302 而非 307：302 语义即「资源临时在别处」，iframe/img/PDF.js 都跟得动，
            # 且不带请求体、不会把 cookie 转发到对象存储域名。
            return RedirectResponse(url, status_code=302)
    return _proxy_material_stream(request, asset, "attachment")


@router.get("/lessons/{lesson_id}/blocks/{block_id}/materials/{material_id}/inline")
def inline_lesson_material(lesson_id: int, block_id: int, material_id: int,
                           request: Request, db: Session = Depends(db_session),
                           proxy: int = 0):
    """学生端资料内嵌预览（inline）：PDF/图片 iframe/img 用，否则浏览器直接触发下载。"""
    user = current_user(request, db)
    _, _, asset = _resolve_student_material(db, user, lesson_id, block_id, material_id)
    settings = request.app.state.settings
    if not proxy and settings.minio_public_endpoint:
        from ..s3_multipart import presign_material_get
        url = presign_material_get(
            settings, settings.minio_materials_bucket, asset.object_key,
            filename=asset.display_name, disposition="inline", expires=INLINE_TTL,
        )
        if url:
            return RedirectResponse(url, status_code=302)
    return _proxy_material_stream(request, asset, "inline")
