"""数据驱动的学习专区、分类树、课程类型与标签接口。"""
from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..learning_catalog import AREA_STATUSES, MODULE_KEYS, MODULE_STATUSES
from ..models import (
    Course,
    CourseCategory,
    CourseTag,
    CourseTagLink,
    CourseType,
    LearningArea,
    LearningAreaModule,
)
from ..permissions import is_editor
from .admin_auth import audit, client_ip, current_admin, db_session, require_csrf

router = APIRouter(prefix="/api", tags=["learning-catalog"])
admin_router = APIRouter(prefix="/api/admin/learning-catalog", tags=["admin-learning-catalog"])

KEY_RE = re.compile(r"^[a-z][a-z0-9-]{1,62}$")


def _valid_key(value: str, label: str = "标识") -> str:
    value = value.strip().lower()
    if not KEY_RE.fullmatch(value):
        raise HTTPException(400, f"{label}只能使用小写字母、数字和连字符，且必须以字母开头。")
    return value


def _area_or_404(db: Session, area_key: str, include_hidden: bool = False) -> LearningArea:
    area = db.get(LearningArea, area_key)
    if area is None or (not include_hidden and area.status == "hidden"):
        raise HTTPException(404, "学习专区不存在。")
    return area


def _active_course_type_exists(db: Session, area_key: str, course_kind: str) -> bool:
    return db.scalar(select(CourseType.id).where(
        CourseType.area_key == area_key,
        CourseType.key == course_kind,
        CourseType.is_active.is_(True),
    ).limit(1)) is not None


def _serialize_module(row: LearningAreaModule) -> dict:
    return {
        "id": row.id, "module_key": row.module_key, "label": row.label,
        "status": row.status, "sort_order": row.sort_order,
    }


def serialize_area(db: Session, area: LearningArea) -> dict:
    modules = db.scalars(select(LearningAreaModule).where(
        LearningAreaModule.area_key == area.key,
        LearningAreaModule.status != "hidden",
    ).order_by(LearningAreaModule.sort_order, LearningAreaModule.id)).all()
    return {
        "key": area.key, "name": area.name, "description": area.description,
        "audience": area.audience, "theme_key": area.theme_key,
        "status": area.status, "sort_order": area.sort_order,
        "modules": [_serialize_module(row) for row in modules],
    }


def category_descendant_ids(db: Session, root_id: int) -> list[int]:
    """数据库无关的分类后代遍历；分类规模是运营目录，不会成为大数据查询。"""
    rows = db.execute(select(CourseCategory.id, CourseCategory.parent_id)).all()
    children: dict[int | None, list[int]] = {}
    for category_id, parent_id in rows:
        children.setdefault(parent_id, []).append(category_id)
    found, stack = [], [root_id]
    while stack:
        current = stack.pop()
        if current in found:
            continue
        found.append(current)
        stack.extend(children.get(current, []))
    return found


def category_breadcrumb(db: Session, category: CourseCategory | None) -> list[dict]:
    chain: list[CourseCategory] = []
    seen: set[int] = set()
    current = category
    while current is not None and current.id not in seen:
        seen.add(current.id)
        chain.append(current)
        current = db.get(CourseCategory, current.parent_id) if current.parent_id else None
    return [{"id": item.id, "key": item.key, "name": item.name} for item in reversed(chain)]


def serialize_tags(db: Session, course_id: int) -> list[dict]:
    rows = db.scalars(
        select(CourseTag).join(CourseTagLink, CourseTagLink.tag_id == CourseTag.id)
        .where(CourseTagLink.course_id == course_id)
        .order_by(CourseTag.sort_order, CourseTag.id)
    ).all()
    return [{"id": row.id, "key": row.key, "name": row.name} for row in rows]


@router.get("/learning-areas")
def list_learning_areas(db: Session = Depends(db_session)):
    rows = db.scalars(select(LearningArea).where(
        LearningArea.status != "hidden"
    ).order_by(LearningArea.sort_order, LearningArea.key)).all()
    return {"items": [serialize_area(db, row) for row in rows]}


@router.get("/learning-areas/{area_key}")
def get_learning_area(area_key: str, db: Session = Depends(db_session)):
    return serialize_area(db, _area_or_404(db, area_key))


def _taxonomy_items(db: Session, area_key: str, include_inactive: bool) -> list[dict]:
    conds = [CourseCategory.area_key == area_key]
    if not include_inactive:
        conds.append(CourseCategory.is_active.is_(True))
    rows = db.scalars(select(CourseCategory).where(*conds).order_by(
        CourseCategory.sort_order, CourseCategory.id
    )).all()
    counts = dict(db.execute(
        select(Course.category_id, func.count(Course.id)).where(
            Course.status == "published", Course.area_key == area_key,
            Course.category_id.is_not(None),
        ).group_by(Course.category_id)
    ).all())
    by_parent: dict[int | None, list[CourseCategory]] = {}
    for row in rows:
        by_parent.setdefault(row.parent_id, []).append(row)

    def build(row: CourseCategory) -> dict:
        children = [build(child) for child in by_parent.get(row.id, [])]
        course_count = int(counts.get(row.id, 0)) + sum(child["course_count"] for child in children)
        return {
            "id": row.id, "area_key": row.area_key, "parent_id": row.parent_id,
            "key": row.key, "name": row.name, "description": row.description,
            "is_active": row.is_active, "sort_order": row.sort_order,
            "course_count": course_count, "children": children,
        }
    return [build(row) for row in by_parent.get(None, [])]


@router.get("/course-taxonomy")
def get_course_taxonomy(area_key: str, db: Session = Depends(db_session)):
    _area_or_404(db, area_key)
    return {"area_key": area_key, "items": _taxonomy_items(db, area_key, False)}


@router.get("/course-types")
def list_course_types(area_key: str, db: Session = Depends(db_session)):
    _area_or_404(db, area_key)
    rows = db.scalars(select(CourseType).where(
        CourseType.area_key == area_key, CourseType.is_active.is_(True)
    ).order_by(CourseType.sort_order, CourseType.id)).all()
    return {"items": [
        {"id": row.id, "key": row.key, "name": row.name,
         "description": row.description, "sort_order": row.sort_order}
        for row in rows
    ]}


@router.get("/course-tags")
def list_course_tags(
    area_key: str,
    course_kind: str | None = None,
    category_id: int | None = None,
    db: Session = Depends(db_session),
):
    """课程特色筛选项：只返回当前列表范围内实际可用的标签。"""
    _area_or_404(db, area_key)
    course_conds = [Course.status == "published", Course.area_key == area_key]
    if course_kind is not None:
        if not _active_course_type_exists(db, area_key, course_kind):
            raise HTTPException(400, "课程类型参数不合法。")
        course_conds.append(Course.course_kind == course_kind)
    if category_id is not None:
        category = db.get(CourseCategory, category_id)
        if category is None or category.area_key != area_key:
            raise HTTPException(400, "课程分类参数不合法。")
        course_conds.append(Course.category_id.in_(category_descendant_ids(db, category_id)))

    rows = db.execute(
        select(CourseTag, func.count(Course.id).label("course_count"))
        .join(CourseTagLink, CourseTagLink.tag_id == CourseTag.id)
        .join(Course, Course.id == CourseTagLink.course_id)
        .where(CourseTag.area_key == area_key, CourseTag.is_active.is_(True), *course_conds)
        .group_by(CourseTag.id)
        .order_by(CourseTag.sort_order, CourseTag.id)
    ).all()
    return {"items": [
        {
            "id": row.id,
            "key": row.key,
            "name": row.name,
            "sort_order": row.sort_order,
            "course_count": int(course_count),
        }
        for row, course_count in rows
    ]}


class AreaPayload(BaseModel):
    key: str = Field(min_length=2, max_length=32)
    name: str = Field(min_length=1, max_length=50)
    description: str | None = Field(default=None, max_length=500)
    audience: str | None = Field(default=None, max_length=200)
    theme_key: str = Field(default="default", max_length=32)
    status: str = Field(default="planning", max_length=16)
    sort_order: int = 0


class ModulePayload(BaseModel):
    module_key: str = Field(min_length=2, max_length=32)
    label: str = Field(min_length=1, max_length=50)
    status: str = Field(default="planning", max_length=16)
    sort_order: int = 0


class CategoryPayload(BaseModel):
    area_key: str = Field(min_length=2, max_length=32)
    parent_id: int | None = None
    key: str = Field(min_length=2, max_length=64)
    name: str = Field(min_length=1, max_length=50)
    description: str | None = Field(default=None, max_length=300)
    is_active: bool = True
    sort_order: int = 0


class TypePayload(BaseModel):
    area_key: str = Field(min_length=2, max_length=32)
    key: str = Field(min_length=2, max_length=32)
    name: str = Field(min_length=1, max_length=50)
    description: str | None = Field(default=None, max_length=200)
    is_active: bool = True
    sort_order: int = 0


class TagPayload(BaseModel):
    area_key: str = Field(min_length=2, max_length=32)
    key: str = Field(min_length=2, max_length=64)
    name: str = Field(min_length=1, max_length=50)
    is_active: bool = True
    sort_order: int = 0


def _editor(request: Request, db: Session):
    require_csrf(request)
    admin = current_admin(request, db)
    if not is_editor(admin):
        raise HTTPException(403, "没有维护学习目录的权限。")
    return admin


@admin_router.get("/areas")
def admin_list_areas(request: Request, db: Session = Depends(db_session)):
    current_admin(request, db)
    rows = db.scalars(select(LearningArea).order_by(LearningArea.sort_order, LearningArea.key)).all()
    return [serialize_area(db, row) for row in rows]


@admin_router.post("/areas", status_code=201)
def admin_create_area(payload: AreaPayload, request: Request, db: Session = Depends(db_session)):
    admin = _editor(request, db)
    key = _valid_key(payload.key, "专区标识")
    if payload.status not in AREA_STATUSES:
        raise HTTPException(400, "专区状态不合法。")
    if db.get(LearningArea, key):
        raise HTTPException(409, "专区标识已存在。")
    area = LearningArea(**payload.model_dump(exclude={"key"}), key=key)
    db.add(area)
    audit(db, request.app.state.settings, "learning_area_create", "success", client_ip(request), admin.id,
          resource_type="learning_area", summary={"key": key})
    db.commit()
    return serialize_area(db, area)


@admin_router.put("/areas/{area_key}")
def admin_update_area(area_key: str, payload: AreaPayload, request: Request, db: Session = Depends(db_session)):
    admin = _editor(request, db)
    area = _area_or_404(db, area_key, True)
    if _valid_key(payload.key, "专区标识") != area_key:
        raise HTTPException(409, "专区标识创建后不可修改。")
    if payload.status not in AREA_STATUSES:
        raise HTTPException(400, "专区状态不合法。")
    for field, value in payload.model_dump(exclude={"key"}).items():
        setattr(area, field, value)
    audit(db, request.app.state.settings, "learning_area_update", "success", client_ip(request), admin.id,
          resource_type="learning_area", summary={"key": area_key})
    db.commit()
    return serialize_area(db, area)


@admin_router.delete("/areas/{area_key}")
def admin_delete_area(area_key: str, request: Request, db: Session = Depends(db_session)):
    admin = _editor(request, db)
    area = _area_or_404(db, area_key, True)
    used = db.scalar(select(func.count()).select_from(Course).where(Course.area_key == area_key)) or 0
    configured = sum([
        db.scalar(select(func.count()).select_from(CourseCategory).where(CourseCategory.area_key == area_key)) or 0,
        db.scalar(select(func.count()).select_from(CourseType).where(CourseType.area_key == area_key)) or 0,
        db.scalar(select(func.count()).select_from(CourseTag).where(CourseTag.area_key == area_key)) or 0,
    ])
    if used or configured:
        raise HTTPException(409, f"专区仍有关联课包或目录配置，只能停用专区。")
    db.delete(area)
    audit(db, request.app.state.settings, "learning_area_delete", "success", client_ip(request), admin.id,
          resource_type="learning_area", summary={"key": area_key})
    db.commit()
    return {"ok": True}


@admin_router.put("/areas/{area_key}/modules")
def admin_replace_modules(area_key: str, payload: list[ModulePayload], request: Request,
                          db: Session = Depends(db_session)):
    admin = _editor(request, db)
    _area_or_404(db, area_key, True)
    keys = [item.module_key for item in payload]
    if len(keys) != len(set(keys)):
        raise HTTPException(400, "同一个能力模块不能重复配置。")
    for item in payload:
        if item.module_key not in MODULE_KEYS:
            raise HTTPException(400, f"能力模块 {item.module_key} 尚未在应用中注册。")
        if item.status not in MODULE_STATUSES:
            raise HTTPException(400, "模块状态不合法。")
    old = db.scalars(select(LearningAreaModule).where(LearningAreaModule.area_key == area_key)).all()
    for row in old:
        db.delete(row)
    db.flush()
    for item in payload:
        db.add(LearningAreaModule(area_key=area_key, **item.model_dump()))
    audit(db, request.app.state.settings, "learning_area_modules_update", "success", client_ip(request), admin.id,
          resource_type="learning_area", summary={"key": area_key})
    db.commit()
    return serialize_area(db, db.get(LearningArea, area_key))


@admin_router.get("/categories")
def admin_list_categories(request: Request, area_key: str = "", db: Session = Depends(db_session)):
    current_admin(request, db)
    conds = [CourseCategory.area_key == area_key] if area_key else []
    rows = db.scalars(select(CourseCategory).where(*conds).order_by(
        CourseCategory.area_key, CourseCategory.sort_order, CourseCategory.id
    )).all()
    return [{
        "id": row.id, "area_key": row.area_key, "parent_id": row.parent_id,
        "key": row.key, "name": row.name, "description": row.description,
        "is_active": row.is_active, "sort_order": row.sort_order,
    } for row in rows]


def _validate_category(db: Session, payload: CategoryPayload, category_id: int | None = None):
    _area_or_404(db, payload.area_key, True)
    key = _valid_key(payload.key, "分类标识")
    parent = db.get(CourseCategory, payload.parent_id) if payload.parent_id else None
    if payload.parent_id and parent is None:
        raise HTTPException(400, "上级分类不存在。")
    if parent and parent.area_key != payload.area_key:
        raise HTTPException(400, "上级分类必须属于同一个专区。")
    if category_id and payload.parent_id in category_descendant_ids(db, category_id):
        raise HTTPException(400, "不能把分类移动到自身或其下级。")
    duplicate = db.scalar(select(CourseCategory).where(
        CourseCategory.area_key == payload.area_key,
        CourseCategory.parent_id == payload.parent_id,
        CourseCategory.key == key,
        *([CourseCategory.id != category_id] if category_id else []),
    ))
    if duplicate:
        raise HTTPException(409, "同级分类标识已存在。")
    return key


@admin_router.post("/categories", status_code=201)
def admin_create_category(payload: CategoryPayload, request: Request, db: Session = Depends(db_session)):
    admin = _editor(request, db)
    key = _validate_category(db, payload)
    row = CourseCategory(**payload.model_dump(exclude={"key"}), key=key)
    db.add(row)
    audit(db, request.app.state.settings, "course_category_create", "success", client_ip(request), admin.id,
          resource_type="course_category", summary={"name": row.name})
    db.commit()
    return {"id": row.id, **payload.model_dump(), "key": row.key}


@admin_router.put("/categories/{category_id}")
def admin_update_category(category_id: int, payload: CategoryPayload, request: Request,
                          db: Session = Depends(db_session)):
    admin = _editor(request, db)
    row = db.get(CourseCategory, category_id)
    if row is None:
        raise HTTPException(404, "分类不存在。")
    # area_key 和 key 会被课程响应、路由和统计长期引用。名称、排序、启停和树内位置仍可维护。
    if payload.area_key != row.area_key or _valid_key(payload.key, "分类标识") != row.key:
        raise HTTPException(409, "已创建分类的专区和稳定标识不可修改；如需新标识，请新建分类并迁移课程。")
    key = _validate_category(db, payload, category_id)
    for field, value in payload.model_dump(exclude={"area_key", "key"}).items():
        setattr(row, field, value)
    row.key = key
    audit(db, request.app.state.settings, "course_category_update", "success", client_ip(request), admin.id,
          resource_type="course_category", resource_id=category_id)
    db.commit()
    return {"id": row.id, **payload.model_dump(), "key": row.key}


@admin_router.delete("/categories/{category_id}")
def admin_delete_category(category_id: int, request: Request, db: Session = Depends(db_session)):
    admin = _editor(request, db)
    row = db.get(CourseCategory, category_id)
    if row is None:
        raise HTTPException(404, "分类不存在。")
    used = db.scalar(select(func.count()).select_from(Course).where(Course.category_id == category_id)) or 0
    children = db.scalar(select(func.count()).select_from(CourseCategory).where(
        CourseCategory.parent_id == category_id
    )) or 0
    if used or children:
        raise HTTPException(409, "分类仍有下级或关联课包，请先调整内容；也可以直接停用。")
    db.delete(row)
    audit(db, request.app.state.settings, "course_category_delete", "success", client_ip(request), admin.id,
          resource_type="course_category", resource_id=category_id)
    db.commit()
    return {"ok": True}


def _list_simple(db: Session, model, area_key: str):
    conds = [model.area_key == area_key] if area_key else []
    return db.scalars(select(model).where(*conds).order_by(model.area_key, model.sort_order, model.id)).all()


@admin_router.get("/types")
def admin_list_types(request: Request, area_key: str = "", db: Session = Depends(db_session)):
    current_admin(request, db)
    return [{"id": r.id, "area_key": r.area_key, "key": r.key, "name": r.name,
             "description": r.description, "is_active": r.is_active, "sort_order": r.sort_order}
            for r in _list_simple(db, CourseType, area_key)]


def _validate_type_or_tag(db: Session, payload, model, item_id: int | None = None):
    _area_or_404(db, payload.area_key, True)
    key = _valid_key(payload.key)
    conds = [model.area_key == payload.area_key, model.key == key]
    if item_id:
        conds.append(model.id != item_id)
    if db.scalar(select(model).where(*conds)):
        raise HTTPException(409, "同专区标识已存在。")
    return key


@admin_router.post("/types", status_code=201)
def admin_create_type(payload: TypePayload, request: Request, db: Session = Depends(db_session)):
    admin = _editor(request, db)
    row = CourseType(**payload.model_dump(exclude={"key"}), key=_validate_type_or_tag(db, payload, CourseType))
    db.add(row); db.commit()
    return {"id": row.id, **payload.model_dump(), "key": row.key}


@admin_router.put("/types/{item_id}")
def admin_update_type(item_id: int, payload: TypePayload, request: Request, db: Session = Depends(db_session)):
    _editor(request, db)
    row = db.get(CourseType, item_id)
    if row is None: raise HTTPException(404, "课程类型不存在。")
    if payload.area_key != row.area_key or _valid_key(payload.key) != row.key:
        raise HTTPException(409, "已创建课程类型的专区和稳定标识不可修改；如需新标识，请新建类型并迁移课程。")
    for field, value in payload.model_dump(exclude={"area_key", "key"}).items(): setattr(row, field, value)
    row.key = _validate_type_or_tag(db, payload, CourseType, item_id)
    db.commit(); return {"id": row.id, **payload.model_dump(), "key": row.key}


@admin_router.delete("/types/{item_id}")
def admin_delete_type(item_id: int, request: Request, db: Session = Depends(db_session)):
    _editor(request, db)
    row = db.get(CourseType, item_id)
    if row is None: raise HTTPException(404, "课程类型不存在。")
    used = db.scalar(select(func.count()).select_from(Course).where(
        Course.area_key == row.area_key, Course.course_kind == row.key
    )) or 0
    if used: raise HTTPException(409, f"仍有 {used} 个课包使用该类型，只能停用。")
    db.delete(row); db.commit(); return {"ok": True}


@admin_router.get("/tags")
def admin_list_tags(request: Request, area_key: str = "", db: Session = Depends(db_session)):
    current_admin(request, db)
    return [{"id": r.id, "area_key": r.area_key, "key": r.key, "name": r.name,
             "is_active": r.is_active, "sort_order": r.sort_order}
            for r in _list_simple(db, CourseTag, area_key)]


@admin_router.post("/tags", status_code=201)
def admin_create_tag(payload: TagPayload, request: Request, db: Session = Depends(db_session)):
    _editor(request, db)
    row = CourseTag(**payload.model_dump(exclude={"key"}), key=_validate_type_or_tag(db, payload, CourseTag))
    db.add(row); db.commit(); return {"id": row.id, **payload.model_dump(), "key": row.key}


@admin_router.put("/tags/{item_id}")
def admin_update_tag(item_id: int, payload: TagPayload, request: Request, db: Session = Depends(db_session)):
    _editor(request, db)
    row = db.get(CourseTag, item_id)
    if row is None: raise HTTPException(404, "标签不存在。")
    if payload.area_key != row.area_key or _valid_key(payload.key) != row.key:
        raise HTTPException(409, "已创建标签的专区和稳定标识不可修改；如需新标识，请新建标签并迁移课程关联。")
    for field, value in payload.model_dump(exclude={"area_key", "key"}).items(): setattr(row, field, value)
    row.key = _validate_type_or_tag(db, payload, CourseTag, item_id)
    db.commit(); return {"id": row.id, **payload.model_dump(), "key": row.key}


@admin_router.delete("/tags/{item_id}")
def admin_delete_tag(item_id: int, request: Request, db: Session = Depends(db_session)):
    _editor(request, db)
    row = db.get(CourseTag, item_id)
    if row is None: raise HTTPException(404, "标签不存在。")
    used = db.scalar(select(func.count()).select_from(CourseTagLink).where(
        CourseTagLink.tag_id == item_id
    )) or 0
    if used: raise HTTPException(409, f"仍有 {used} 个课包使用该标签，只能停用。")
    db.delete(row); db.commit(); return {"ok": True}
