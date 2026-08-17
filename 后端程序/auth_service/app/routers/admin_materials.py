"""后台资料管理：文件夹树 / 资料检索 / 上传 / 标签 / 统计 / 课时绑定。

对接交接文档《12、资料管理与Windows文件夹迁移》§7 API 契约：
- GET/POST/PATCH/DELETE /api/admin/material-folders          文件夹（按需展开 + 面包屑）
- GET  /api/admin/materials                                   服务端检索与分页
- GET  /api/admin/materials/{id}                              详情、引用摘要和处理状态
- GET  /api/admin/materials/{id}/download                     管理员代理流式下载
- POST /api/admin/materials/uploads/init                      初始化上传（小文件 PUT / 大文件分片）
- GET  /api/admin/materials/uploads/{sid}/parts/{n}           分片预签名
- POST /api/admin/materials/uploads/{sid}/complete            服务端核对并校验（后台算 sha256）
- POST /api/admin/materials/uploads/{sid}/abort               取消上传
- GET/POST /api/admin/material-tags                           标签选择器与新建
- POST /api/admin/materials/{id}/tags                         设置标签（全量替换）
- GET/POST/DELETE /api/admin/lesson-blocks/{bid}/materials    课时块绑定 / 解绑

安全口径（§7/§8）：
- 所有列表接口验证管理员权限并限制 page_size（20/50/100）；
- 写操作 require_csrf + is_editor；读操作 current_admin（reviewer 可检索/预览）；
- 上传完成前不标 ready：sha256 由后台任务从对象存储下载计算，uploading→ready/failed；
- 删除被课时引用的资料返回 409 + 引用清单；文件夹非空拒绝删除；
- 下载不暴露永久对象地址：服务端从 MinIO 流式转发。
"""
from __future__ import annotations

from datetime import UTC, datetime
from urllib.parse import quote

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..material_helpers import (
    MULTIPART_MIN_BYTES,
    asset_object_key,
    compute_object_sha256,
    infer_mime,
    sanitize_display_name,
)
from ..models import (
    AdminUser,
    CourseLesson,
    CourseLessonBlock,
    LessonBlockMaterial,
    MaterialAsset,
    MaterialAssetTag,
    MaterialFolder,
    MaterialTag,
    MaterialUpload,
)
from ..permissions import is_editor
from .admin_auth import audit, client_ip, current_admin, db_session, limit, require_csrf

router = APIRouter(prefix="/api/admin", tags=["admin-materials"])

PAGE_SIZES = {20, 50, 100}
DEFAULT_PAGE_SIZE = 50
VALID_ASSET_TYPES = {"document", "image", "video", "audio", "archive", "other"}


# ---------- 请求模型 ----------


class CreateFolderPayload(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    parent_id: int | None = None
    sort_order: int = 0


class UpdateFolderPayload(BaseModel):
    """PATCH 载荷：用 exclude_unset 区分「未传」与「显式传 null」（移到根目录）。"""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    parent_id: int | None = None
    sort_order: int | None = None


class CreateMaterialTagPayload(BaseModel):
    name: str = Field(min_length=1, max_length=64)


class SetMaterialTagsPayload(BaseModel):
    tag_ids: list[int] = Field(default_factory=list, max_length=50)


class InitUploadPayload(BaseModel):
    display_name: str = Field(min_length=1, max_length=255)
    folder_id: int | None = None
    mime_type: str | None = Field(default=None, max_length=128)  # 仅供参考，服务端重新判断
    file_size: int = Field(ge=1)


class CompletePart(BaseModel):
    part_number: int = Field(ge=1, le=10_000)
    etag: str = Field(min_length=1, max_length=128)


class CompleteUploadPayload(BaseModel):
    parts: list[CompletePart] = Field(default_factory=list, max_length=10_000)


class BindMaterialsPayload(BaseModel):
    material_ids: list[int] = Field(min_length=1, max_length=200)


# ---------- 序列化 ----------


def _serialize_folder(db: Session, folder: MaterialFolder) -> dict:
    child_count = db.scalar(
        select(func.count()).select_from(MaterialFolder).where(MaterialFolder.parent_id == folder.id)
    ) or 0
    asset_count = db.scalar(
        select(func.count()).select_from(MaterialAsset).where(
            MaterialAsset.folder_id == folder.id, MaterialAsset.status != "failed"
        )
    ) or 0
    return {
        "id": folder.id,
        "name": folder.name,
        "parent_id": folder.parent_id,
        "sort_order": folder.sort_order,
        "child_count": child_count,
        "asset_count": asset_count,
        "created_at": folder.created_at.isoformat() if folder.created_at else None,
    }


def _folder_path(db: Session, folder_id: int | None) -> list[dict]:
    """从根到自身的祖先链（含自身），面包屑渲染用。"""
    path: list[dict] = []
    current_id = folder_id
    seen: set[int] = set()
    while current_id is not None:
        if current_id in seen:  # 兜底防脏数据循环
            break
        seen.add(current_id)
        folder = db.get(MaterialFolder, current_id)
        if folder is None:
            break
        path.append({"id": folder.id, "name": folder.name})
        current_id = folder.parent_id
    return list(reversed(path))


def _serialize_material(db: Session, asset: MaterialAsset, owners: dict | None = None) -> dict:
    """单条资料序列化（详情/下载等按需场景用；列表走 _serialize_materials_batch）。"""
    tags = [
        name
        for (name,) in db.execute(
            select(MaterialTag.name)
            .join(MaterialAssetTag, MaterialAssetTag.tag_id == MaterialTag.id)
            .where(MaterialAssetTag.asset_id == asset.id)
            .order_by(MaterialTag.name)
        ).all()
    ]
    folder_name = None
    if asset.folder_id is not None:
        folder = db.get(MaterialFolder, asset.folder_id)
        folder_name = folder.name if folder else None
    owner_name = None
    if owners is not None:
        owner_name = owners.get(asset.created_by)
    else:
        owner = db.get(AdminUser, asset.created_by) if asset.created_by else None
        owner_name = owner.display_name if owner else None
    duplicate_of = None
    if asset.sha256:
        duplicate_of = db.scalar(
            select(MaterialAsset.id)
            .where(
                MaterialAsset.sha256 == asset.sha256,
                MaterialAsset.id != asset.id,
                MaterialAsset.status == "ready",
            )
            .order_by(MaterialAsset.id)
            .limit(1)
        )
    return {
        "id": asset.id,
        "display_name": asset.display_name,
        "asset_type": asset.asset_type,
        "mime_type": asset.mime_type,
        "size_bytes": asset.size_bytes,
        "status": asset.status,
        "sha256": asset.sha256,
        "duplicate_of": duplicate_of,
        "folder_id": asset.folder_id,
        "folder_name": folder_name,
        "tags": tags,
        "created_by_name": owner_name,
        "created_at": asset.created_at.isoformat() if asset.created_at else None,
    }


def _serialize_materials_batch(db: Session, assets: list[MaterialAsset], owners: dict) -> list[dict]:
    """列表批量序列化：标签/文件夹/去重提示各一条聚合查询，避免逐条 N+1（评审 P2）。

    上万条资料的搜索管理场景，100 条/页 必须固定 ~4 次查询而不是 ~400 次。
    """
    if not assets:
        return []
    ids = [a.id for a in assets]

    # 标签：一次查齐 → {asset_id: [name]}
    tag_map: dict[int, list[str]] = {aid: [] for aid in ids}
    for asset_id, name in db.execute(
        select(MaterialAssetTag.asset_id, MaterialTag.name)
        .join(MaterialTag, MaterialTag.id == MaterialAssetTag.tag_id)
        .where(MaterialAssetTag.asset_id.in_(ids))
        .order_by(MaterialTag.name)
    ).all():
        tag_map.setdefault(asset_id, []).append(name)

    # 文件夹：一次查齐 → {id: name}
    folder_ids = {a.folder_id for a in assets if a.folder_id is not None}
    folder_map = {
        f.id: f.name
        for f in db.scalars(select(MaterialFolder).where(MaterialFolder.id.in_(folder_ids))).all()
    } if folder_ids else {}

    # 去重提示：同 sha256 的其他 ready 资产的最小 id → {sha256: min_id}
    hashes = {a.sha256 for a in assets if a.sha256}
    duplicate_map: dict[str, int] = {}
    if hashes:
        rows = db.execute(
            select(MaterialAsset.sha256, MaterialAsset.id)
            .where(MaterialAsset.sha256.in_(hashes), MaterialAsset.status == "ready")
        ).all()
        by_hash: dict[str, list[int]] = {}
        for sha, aid in rows:
            by_hash.setdefault(sha, []).append(aid)
        for sha, aid_list in by_hash.items():
            if len(aid_list) > 1:
                duplicate_map[sha] = min(aid_list)

    out = []
    for asset in assets:
        peers = duplicate_map.get(asset.sha256) if asset.sha256 else None
        out.append({
            "id": asset.id,
            "display_name": asset.display_name,
            "asset_type": asset.asset_type,
            "mime_type": asset.mime_type,
            "size_bytes": asset.size_bytes,
            "status": asset.status,
            "sha256": asset.sha256,
            # duplicate_of = 同哈希的**其他** ready 资产最小 id；只有一个时不提示
            "duplicate_of": peers if (peers is not None and peers != asset.id) else None,
            "folder_id": asset.folder_id,
            "folder_name": folder_map.get(asset.folder_id),
            "tags": tag_map.get(asset.id, []),
            "created_by_name": owners.get(asset.created_by),
            "created_at": asset.created_at.isoformat() if asset.created_at else None,
        })
    return out


def _material_references(db: Session, asset_id: int) -> list[dict]:
    """资料被哪些课时块引用（删除保护用）。"""
    return [
        {
            "block_id": block_id,
            "block_type": block_type,
            "lesson_id": lesson_id,
            "lesson_title": lesson_title,
        }
        for block_id, block_type, lesson_id, lesson_title in db.execute(
            select(
                CourseLessonBlock.id,
                CourseLessonBlock.block_type,
                CourseLesson.id,
                CourseLesson.title,
            )
            .select_from(LessonBlockMaterial)
            .join(CourseLessonBlock, CourseLessonBlock.id == LessonBlockMaterial.block_id)
            .join(CourseLesson, CourseLesson.id == CourseLessonBlock.lesson_id)
            .where(LessonBlockMaterial.material_id == asset_id)
        ).all()
    ]


def _require_folder(db: Session, folder_id: int | None) -> None:
    if folder_id is not None and db.get(MaterialFolder, folder_id) is None:
        raise HTTPException(404, "目标文件夹不存在。")


def _sibling_name_taken(db: Session, parent_id: int | None, name: str, exclude_id: int | None = None) -> bool:
    # PostgreSQL 不认 `col IS 1`（IS 只能跟 NULL/TRUE/FALSE/UNKNOWN），非空父目录必须用 ==
    parent_cond = MaterialFolder.parent_id.is_(None) if parent_id is None else MaterialFolder.parent_id == parent_id
    stmt = select(MaterialFolder).where(parent_cond, MaterialFolder.name == name)
    if exclude_id is not None:
        stmt = stmt.where(MaterialFolder.id != exclude_id)
    return db.scalar(stmt) is not None


def _is_descendant(db: Session, folder_id: int, maybe_descendant: int) -> bool:
    """maybe_descendant 是否在 folder_id 的子树内（循环防护用，沿 parent 链向上走）。"""
    current = db.get(MaterialFolder, maybe_descendant)
    seen: set[int] = set()
    while current is not None and current.parent_id is not None:
        if current.parent_id in seen:
            return True  # 脏数据循环兜底
        seen.add(current.parent_id)
        if current.parent_id == folder_id:
            return True
        current = db.get(MaterialFolder, current.parent_id)
    return False


def _load_upload(db: Session, session_id: int, admin: AdminUser) -> MaterialUpload:
    upload = db.get(MaterialUpload, session_id)
    if upload is None or upload.status != "initiated":
        raise HTTPException(404, "上传会话不存在或已结束。")
    if upload.uploader_id != admin.id:
        raise HTTPException(403, "无权操作该上传会话。")
    return upload


# ---------- 文件夹 ----------


@router.get("/material-folders")
def list_folders(request: Request, parent_id: str = "", db: Session = Depends(db_session)):
    """按需读取直接子目录（交接文档 §4.1：首次只取根与一级，展开时再取直接子项）。"""
    current_admin(request, db)
    parent: int | None = None
    if parent_id not in ("", "null"):
        parent = int(parent_id)
    parent_cond = MaterialFolder.parent_id.is_(None) if parent is None else MaterialFolder.parent_id == parent
    folders = db.scalars(
        select(MaterialFolder)
        .where(parent_cond)
        .order_by(MaterialFolder.sort_order, MaterialFolder.name)
    ).all()
    return {
        "parent_id": parent,
        "path": _folder_path(db, parent),
        "items": [_serialize_folder(db, f) for f in folders],
    }


@router.post("/material-folders", status_code=201)
def create_folder(payload: CreateFolderPayload, request: Request, db: Session = Depends(db_session)):
    require_csrf(request)
    admin = current_admin(request, db)
    if not is_editor(admin):
        raise HTTPException(403, "没有编辑资料的权限。")
    name = payload.name.strip()
    if not name:
        raise HTTPException(400, "文件夹名称不能为空。")
    _require_folder(db, payload.parent_id)
    if _sibling_name_taken(db, payload.parent_id, name):
        raise HTTPException(409, "同级目录下已存在同名文件夹。")
    folder = MaterialFolder(
        parent_id=payload.parent_id, name=name, sort_order=payload.sort_order, created_by=admin.id
    )
    db.add(folder)
    audit(db, request.app.state.settings, "material_folder_create", "success",
          client_ip(request), admin.id, resource_type="material_folder",
          summary={"name": name, "parent_id": payload.parent_id})
    try:
        db.commit()
    except IntegrityError:
        # 预查与插入之间的并发竞态由数据库唯一约束兜底（评审 P2）
        db.rollback()
        raise HTTPException(409, "同级目录下已存在同名文件夹。")
    return _serialize_folder(db, folder)


@router.patch("/material-folders/{folder_id}")
def update_folder(folder_id: int, payload: UpdateFolderPayload, request: Request,
                  db: Session = Depends(db_session)):
    require_csrf(request)
    admin = current_admin(request, db)
    if not is_editor(admin):
        raise HTTPException(403, "没有编辑资料的权限。")
    folder = db.get(MaterialFolder, folder_id)
    if folder is None:
        raise HTTPException(404, "文件夹不存在。")
    fields = payload.model_dump(exclude_unset=True)
    if "name" in fields:
        name = (payload.name or "").strip()
        if not name:
            raise HTTPException(400, "文件夹名称不能为空。")
        if _sibling_name_taken(db, folder.parent_id, name, exclude_id=folder_id):
            raise HTTPException(409, "同级目录下已存在同名文件夹。")
        folder.name = name
    if "parent_id" in fields:
        new_parent = payload.parent_id
        _require_folder(db, new_parent)
        if new_parent == folder.id:
            raise HTTPException(400, "不能把文件夹移动到自身。")
        if new_parent is not None and _is_descendant(db, folder.id, new_parent):
            raise HTTPException(400, "不能把文件夹移动到自己的子目录下。")
        if new_parent is not None and _sibling_name_taken(db, new_parent, folder.name, exclude_id=folder_id):
            raise HTTPException(409, "目标目录下已存在同名文件夹。")
        folder.parent_id = new_parent
    if "sort_order" in fields and payload.sort_order is not None:
        folder.sort_order = payload.sort_order
    audit(db, request.app.state.settings, "material_folder_update", "success",
          client_ip(request), admin.id, resource_type="material_folder", resource_id=folder_id,
          summary={k: fields.get(k) for k in ("name", "parent_id", "sort_order") if k in fields})
    db.commit()
    return _serialize_folder(db, folder)


@router.delete("/material-folders/{folder_id}")
def delete_folder(folder_id: int, request: Request, db: Session = Depends(db_session)):
    require_csrf(request)
    admin = current_admin(request, db)
    if not is_editor(admin):
        raise HTTPException(403, "没有编辑资料的权限。")
    folder = db.get(MaterialFolder, folder_id)
    if folder is None:
        raise HTTPException(404, "文件夹不存在。")
    child_count = db.scalar(
        select(func.count()).select_from(MaterialFolder).where(MaterialFolder.parent_id == folder_id)
    ) or 0
    asset_count = db.scalar(
        select(func.count()).select_from(MaterialAsset).where(MaterialAsset.folder_id == folder_id)
    ) or 0
    if child_count or asset_count:
        # 结构化 detail：引用/子项计数放 body（HTTP header 不能承载中文消息）
        raise HTTPException(
            409, detail={
                "message": f"文件夹非空（{child_count} 个子目录、{asset_count} 份资料），不能删除。",
                "child_count": child_count,
                "asset_count": asset_count,
            },
        )
    audit(db, request.app.state.settings, "material_folder_delete", "success",
          client_ip(request), admin.id, resource_type="material_folder", resource_id=folder_id,
          summary={"name": folder.name})
    db.delete(folder)
    db.commit()
    return {"ok": True}


@router.get("/material-folders/{folder_id}")
def get_folder(folder_id: int, request: Request, db: Session = Depends(db_session)):
    """文件夹详情 + 祖先链（面包屑，交接文档 §4.1：深层目录不依赖无限横向缩进）。"""
    current_admin(request, db)
    folder = db.get(MaterialFolder, folder_id)
    if folder is None:
        raise HTTPException(404, "文件夹不存在。")
    data = _serialize_folder(db, folder)
    data["path"] = _folder_path(db, folder.id)
    return data


# ---------- 标签 ----------


@router.get("/material-tags")
def list_material_tags(request: Request, keyword: str = "", db: Session = Depends(db_session)):
    current_admin(request, db)
    conds = []
    if keyword.strip():
        conds.append(MaterialTag.name.ilike(f"%{keyword.strip()}%"))
    tags = db.scalars(select(MaterialTag).where(*conds).order_by(MaterialTag.name)).all()
    counts = dict(
        db.execute(
            select(MaterialAssetTag.tag_id, func.count())
            .where(MaterialAssetTag.tag_id.in_([t.id for t in tags]))
            .group_by(MaterialAssetTag.tag_id)
        ).all()
    ) if tags else {}
    return {
        "items": [
            {"id": t.id, "name": t.name, "asset_count": counts.get(t.id, 0)} for t in tags
        ]
    }


@router.post("/material-tags", status_code=201)
def create_material_tag(payload: CreateMaterialTagPayload, request: Request,
                        db: Session = Depends(db_session)):
    require_csrf(request)
    admin = current_admin(request, db)
    if not is_editor(admin):
        raise HTTPException(403, "没有编辑资料的权限。")
    name = payload.name.strip()
    if not name:
        raise HTTPException(400, "标签名称不能为空。")
    existing = db.scalar(select(MaterialTag).where(MaterialTag.name == name))
    if existing is not None:  # 幂等：重名返回已有
        return {"id": existing.id, "name": existing.name, "asset_count": 0, "created": False}
    tag = MaterialTag(name=name, created_by=admin.id)
    db.add(tag)
    audit(db, request.app.state.settings, "material_tag_create", "success",
          client_ip(request), admin.id, resource_type="material_tag", summary={"name": name})
    db.commit()
    return {"id": tag.id, "name": tag.name, "asset_count": 0, "created": True}


# ---------- 资料检索 ----------


def _parse_optional_int(value: str, field: str) -> int | None:
    if value in ("", "null"):
        return None
    try:
        return int(value)
    except ValueError:
        raise HTTPException(400, f"{field} 参数不合法。")


@router.get("/materials")
def list_materials(
    request: Request,
    folder_id: str = "",
    keyword: str = "",
    type: str = "",
    tag: str = "",
    uploader_id: str = "",
    date_from: str = "",
    date_to: str = "",
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
    db: Session = Depends(db_session),
):
    """服务端检索与分页：搜索、类型、标签、目录、上传人和日期全部传服务端（§4.2）。"""
    current_admin(request, db)
    page = max(1, page)
    page_size = page_size if page_size in PAGE_SIZES else DEFAULT_PAGE_SIZE
    if type and type not in VALID_ASSET_TYPES:
        raise HTTPException(400, "type 参数不合法。")
    folder = _parse_optional_int(folder_id, "folder_id")
    uploader = _parse_optional_int(uploader_id, "uploader_id")
    tag_id = _parse_optional_int(tag, "tag")

    conds = []
    if folder is not None:
        # folder_id 省略/空 = 全部；"null" = 不筛选（与 parent_id 同语义）；
        # -1 = 未分类（folder_id IS NULL），与 folders 列表的 parent_id=null 口径区分开。
        conds.append(MaterialAsset.folder_id.is_(None) if folder == -1 else MaterialAsset.folder_id == folder)
    if keyword.strip():
        conds.append(MaterialAsset.display_name.ilike(f"%{keyword.strip()}%"))
    if type:
        conds.append(MaterialAsset.asset_type == type)
    if uploader is not None:
        conds.append(MaterialAsset.created_by == uploader)
    if date_from:
        try:
            conds.append(MaterialAsset.created_at >= datetime.fromisoformat(date_from))
        except ValueError:
            raise HTTPException(400, "date_from 参数不合法。")
    if date_to:
        try:
            conds.append(MaterialAsset.created_at <= datetime.fromisoformat(date_to))
        except ValueError:
            raise HTTPException(400, "date_to 参数不合法。")
    if tag_id is not None:
        # 标签是附加检索维度：只筛"打过该标签的资产"，与其他条件可组合（§4.2）。
        conds.append(
            MaterialAsset.id.in_(
                select(MaterialAssetTag.asset_id).where(MaterialAssetTag.tag_id == tag_id)
            )
        )

    total = db.scalar(select(func.count()).select_from(MaterialAsset).where(*conds)) or 0
    rows = db.scalars(
        select(MaterialAsset)
        .where(*conds)
        .order_by(MaterialAsset.id.desc())
        .offset((page - 1) * page_size).limit(page_size)
    ).all()
    owner_ids = {a.created_by for a in rows if a.created_by}
    owners = {
        a.id: a.display_name
        for a in db.scalars(select(AdminUser).where(AdminUser.id.in_(owner_ids))).all()
    } if owner_ids else {}
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": _serialize_materials_batch(db, list(rows), owners),
    }


@router.get("/materials/{material_id}")
def get_material(material_id: int, request: Request, db: Session = Depends(db_session)):
    """详情 + 引用摘要 + 上传会话状态（交接文档 §7 / §8：删除前返回引用清单）。"""
    current_admin(request, db)
    asset = db.get(MaterialAsset, material_id)
    if asset is None:
        raise HTTPException(404, "资料不存在。")
    data = _serialize_material(db, asset)
    upload = db.scalar(
        select(MaterialUpload).where(MaterialUpload.asset_id == material_id).order_by(MaterialUpload.id.desc()).limit(1)
    )
    data["references"] = _material_references(db, material_id)
    data["upload"] = {
        "mode": upload.upload_mode if upload else None,
        "status": upload.status if upload else None,
        "created_at": upload.created_at.isoformat() if upload and upload.created_at else None,
    } if upload else None
    return data


@router.get("/materials/{material_id}/download")
def download_material(material_id: int, request: Request, db: Session = Depends(db_session)):
    """管理员代理流式下载：不暴露永久对象地址（§8），从 MinIO 流式转发。

    reviewer 也允许预览/下载（审核内容需要看原始材料）。
    """
    current_admin(request, db)
    asset = db.get(MaterialAsset, material_id)
    if asset is None:
        raise HTTPException(404, "资料不存在。")
    if asset.status != "ready":
        raise HTTPException(409, "资料尚未就绪或已被移除。")
    settings = request.app.state.settings
    from ..s3_multipart import get_minio_client

    client = get_minio_client(settings)
    try:
        resp = client.get_object(Bucket=settings.minio_materials_bucket, Key=asset.object_key)
    except Exception as exc:
        raise HTTPException(502, "对象存储暂不可用，请稍后重试。") from exc
    from fastapi.responses import StreamingResponse

    body = resp["Body"]

    def _chunks():
        while True:
            chunk = body.read(1024 * 1024)
            if not chunk:
                break
            yield chunk

    fallback = asset.display_name.encode("ascii", "ignore").decode() or "download"
    disposition = f"attachment; filename=\"{fallback}\"; filename*=UTF-8''{quote(asset.display_name)}"
    return StreamingResponse(
        _chunks(),
        media_type=asset.mime_type,
        headers={"Content-Disposition": disposition},
    )


@router.delete("/materials/{material_id}")
def delete_material(material_id: int, request: Request, db: Session = Depends(db_session)):
    """删除资料：被课时引用时拒绝并列出引用（§8）；无引用则删行，对象按引用计数回收。"""
    require_csrf(request)
    admin = current_admin(request, db)
    if not is_editor(admin):
        raise HTTPException(403, "没有编辑资料的权限。")
    asset = db.get(MaterialAsset, material_id)
    if asset is None:
        raise HTTPException(404, "资料不存在。")
    references = _material_references(db, material_id)
    if references:
        raise HTTPException(
            409, detail={
                "message": f"该资料已被 {len(references)} 个课时内容引用，请先解除绑定。",
                "references": references,
            },
        )
    settings = request.app.state.settings
    # 引用计数：同 object_key 的其他非 failed 资产行仍在引用该对象 → 只删行不删对象。
    ref_count = db.scalar(
        select(func.count()).select_from(MaterialAsset).where(
            MaterialAsset.object_key == asset.object_key,
            MaterialAsset.id != material_id,
            MaterialAsset.status != "failed",
        )
    ) or 0
    audit(db, settings, "material_delete", "success", client_ip(request), admin.id,
          resource_type="material_asset", resource_id=material_id,
          summary={"display_name": asset.display_name, "object_key": asset.object_key,
                   "object_removed": ref_count == 0})
    db.delete(asset)
    db.flush()
    if ref_count == 0:
        from ..s3_multipart import get_minio_client

        try:
            get_minio_client(settings).delete_object(
                Bucket=settings.minio_materials_bucket, Key=asset.object_key
            )
        except Exception:
            pass  # 对象删除失败不阻断行删除，孤儿对象留给离线清理脚本回收
    db.commit()
    return {"ok": True}


@router.post("/materials/{material_id}/tags")
def set_material_tags(material_id: int, payload: SetMaterialTagsPayload, request: Request,
                      db: Session = Depends(db_session)):
    """设置资料标签（全量替换）。标签是额外检索维度，与文件夹互不干扰（§6）。"""
    require_csrf(request)
    admin = current_admin(request, db)
    if not is_editor(admin):
        raise HTTPException(403, "没有编辑资料的权限。")
    asset = db.get(MaterialAsset, material_id)
    if asset is None:
        raise HTTPException(404, "资料不存在。")
    tag_ids = set(payload.tag_ids)
    if tag_ids:
        found = set(db.scalars(select(MaterialTag.id).where(MaterialTag.id.in_(tag_ids))).all())
        missing = tag_ids - found
        if missing:
            raise HTTPException(400, f"标签不存在：{sorted(missing)}")
    db.execute(delete(MaterialAssetTag).where(MaterialAssetTag.asset_id == material_id))
    for tag_id in tag_ids:
        db.add(MaterialAssetTag(asset_id=material_id, tag_id=tag_id))
    audit(db, request.app.state.settings, "material_set_tags", "success",
          client_ip(request), admin.id, resource_type="material_asset", resource_id=material_id,
          summary={"tag_ids": sorted(tag_ids)})
    db.commit()
    return {"ok": True, "tag_ids": sorted(tag_ids)}


# ---------- 普通上传 ----------


@router.post("/materials/uploads/init", status_code=201)
def init_material_upload(payload: InitUploadPayload, request: Request,
                         db: Session = Depends(db_session)):
    """初始化普通上传：小文件 presigned PUT，大文件 S3 Multipart（§7 / §8 大文件分片）。"""
    require_csrf(request)
    admin = current_admin(request, db)
    if not is_editor(admin):
        raise HTTPException(403, "没有上传资料的权限。")
    settings = request.app.state.settings
    limit(request, "material-upload-ip", client_ip(request), 120, 3600)
    if payload.file_size > settings.material_source_max_bytes:
        raise HTTPException(413, f"文件不能超过 {settings.material_source_max_bytes // (1024 * 1024)} MB。")
    display_name = sanitize_display_name(payload.display_name)
    _require_folder(db, payload.folder_id)
    mime_type, asset_type = infer_mime(display_name)

    key = asset_object_key(admin.id, display_name)
    asset = MaterialAsset(
        folder_id=payload.folder_id, display_name=display_name, object_key=key,
        mime_type=mime_type, asset_type=asset_type, size_bytes=payload.file_size,
        status="uploading", created_by=admin.id,
    )
    db.add(asset)
    db.flush()

    from ..s3_multipart import create_multipart_upload, get_minio_client

    client = get_minio_client(settings)
    small = payload.file_size < MULTIPART_MIN_BYTES
    upload: MaterialUpload | None = None
    s3_upload_id: str | None = None
    if small:
        try:
            presigned = client.generate_presigned_url(
                "put_object",
                Params={"Bucket": settings.minio_materials_bucket, "Key": key, "ContentType": mime_type},
                ExpiresIn=3600,
            )
        except Exception as exc:
            raise HTTPException(502, "对象存储暂不可用，请稍后重试。") from exc
        upload = MaterialUpload(
            asset_id=asset.id, uploader_id=admin.id, bucket=settings.minio_materials_bucket,
            object_key=key, upload_mode="presigned_put", content_type=mime_type,
            file_size=payload.file_size, status="initiated",
        )
    else:
        part_size = settings.material_part_size
        part_count = max(1, (payload.file_size + part_size - 1) // part_size)
        try:
            s3_upload_id = create_multipart_upload(
                client, settings.minio_materials_bucket, key, mime_type
            )
        except Exception as exc:
            raise HTTPException(502, "对象存储暂不可用，请稍后重试。") from exc
        upload = MaterialUpload(
            asset_id=asset.id, uploader_id=admin.id, bucket=settings.minio_materials_bucket,
            object_key=key, upload_mode="multipart", upload_id=s3_upload_id,
            content_type=mime_type, file_size=payload.file_size, part_count=part_count,
            status="initiated",
        )
    db.add(upload)
    audit(db, settings, "material_upload_init", "success", client_ip(request), admin.id,
          resource_type="material_asset", resource_id=asset.id,
          summary={"bucket": settings.minio_materials_bucket, "key": key,
                   "file_size": payload.file_size, "mode": upload.upload_mode})
    db.commit()
    return {
        "asset_id": asset.id,
        "upload_session_id": upload.id,
        "mode": upload.upload_mode,
        "presigned_url": presigned if small else None,
        "part_size": settings.material_part_size if not small else None,
        "part_count": upload.part_count if not small else None,
        "asset_type": asset_type,
    }


@router.get("/materials/uploads/{upload_session_id}/parts/{part_number}")
def presign_material_part(upload_session_id: int, part_number: int, request: Request,
                          db: Session = Depends(db_session)):
    """分片预签名 URL（GET 无副作用，不要求 CSRF，同 admin_videos 口径）。"""
    admin = current_admin(request, db)
    upload = _load_upload(db, upload_session_id, admin)
    if upload.upload_mode != "multipart":
        raise HTTPException(400, "该上传会话不是分片上传。")
    if part_number < 1 or part_number > (upload.part_count or 10_000):
        raise HTTPException(400, "分片序号越界。")
    settings = request.app.state.settings
    from ..s3_multipart import get_minio_client, presign_upload_part

    try:
        url = presign_upload_part(
            get_minio_client(settings), upload.bucket, upload.object_key,
            upload.upload_id, part_number,
        )
    except Exception as exc:
        raise HTTPException(502, "对象存储暂不可用，请稍后重试。") from exc
    return {"part_number": part_number, "url": url}


def verify_material_asset(settings, session_factory, asset_id: int) -> None:
    """上传完成后的后台校验：下载对象算 SHA-256，比对大小，置 ready/failed。

    内容寻址去重：同 sha256 的 ready 资产行共享同一 object_key（复用对象），
    duplicate_of 提示由序列化时按 sha256 查询生成。
    """
    db = session_factory()
    try:
        asset = db.get(MaterialAsset, asset_id)
        if asset is None or asset.status != "uploading":
            return
        from ..s3_multipart import get_minio_client

        try:
            digest, actual = compute_object_sha256(
                get_minio_client(settings), settings.minio_materials_bucket, asset.object_key
            )
        except Exception:
            asset.status = "failed"
            db.commit()
            return
        if actual != asset.size_bytes:
            asset.status = "failed"
            db.commit()
            return
        asset.sha256 = digest
        asset.status = "ready"
        db.commit()
    finally:
        db.close()


@router.post("/materials/uploads/{upload_session_id}/complete")
def complete_material_upload(upload_session_id: int, payload: CompleteUploadPayload,
                             request: Request, background: BackgroundTasks,
                             db: Session = Depends(db_session)):
    """完成上传：服务端向 MinIO 核对（不信任前端自报），后台算 sha256 后置 ready。"""
    require_csrf(request)
    admin = current_admin(request, db)
    upload = _load_upload(db, upload_session_id, admin)
    settings = request.app.state.settings
    from ..s3_multipart import complete_multipart_upload, get_minio_client, list_uploaded_parts

    client = get_minio_client(settings)
    try:
        if upload.upload_mode == "multipart":
            stored = {
                p["PartNumber"]: p["ETag"]
                for p in list_uploaded_parts(client, upload.bucket, upload.object_key, upload.upload_id)
            }
            provided = {p.part_number: p.etag for p in payload.parts}
            if set(provided) != set(stored):
                raise HTTPException(409, "已传分片与服务端记录不一致，请检查后重试。")
            for pn, etag in provided.items():
                if etag.strip('"') != stored[pn].strip('"'):
                    raise HTTPException(409, f"分片 {pn} 的校验值不匹配。")
            complete_multipart_upload(
                client, upload.bucket, upload.object_key, upload.upload_id,
                [{"PartNumber": p.part_number, "ETag": p.etag} for p in payload.parts],
            )
        else:  # presigned_put：head_object 核对大小
            head = client.head_object(Bucket=upload.bucket, Key=upload.object_key)
            if head.get("ContentLength") != upload.file_size:
                raise HTTPException(409, "上传文件大小与服务端记录不一致。")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(502, "对象存储暂不可用，请稍后重试。") from exc

    upload.status = "completed"
    audit(db, settings, "material_upload_complete", "success", client_ip(request), admin.id,
          resource_type="material_asset", resource_id=upload.asset_id,
          summary={"key": upload.object_key, "mode": upload.upload_mode})
    db.commit()
    background.add_task(verify_material_asset, settings, request.app.state.session_factory, upload.asset_id)
    return {"asset_id": upload.asset_id, "status": "uploading"}


@router.post("/materials/uploads/{upload_session_id}/abort")
def abort_material_upload(upload_session_id: int, request: Request,
                          db: Session = Depends(db_session)):
    require_csrf(request)
    admin = current_admin(request, db)
    upload = _load_upload(db, upload_session_id, admin)
    settings = request.app.state.settings
    if upload.upload_mode == "multipart" and upload.upload_id:
        from ..s3_multipart import abort_multipart_upload, get_minio_client

        try:
            abort_multipart_upload(
                get_minio_client(settings), upload.bucket, upload.object_key, upload.upload_id
            )
        except Exception:
            pass  # MinIO 清理失败也要标记本地 aborted，避免悬挂会话（同 admin_videos）
    upload.status = "aborted"
    asset = db.get(MaterialAsset, upload.asset_id)
    if asset is not None and asset.status == "uploading":
        asset.status = "failed"
    audit(db, settings, "material_upload_abort", "success", client_ip(request), admin.id,
          resource_type="material_asset", resource_id=upload.asset_id)
    db.commit()
    return {"asset_id": upload.asset_id, "status": "failed"}


# ---------- 统计 ----------


@router.get("/material-stats")
def material_stats(request: Request, db: Session = Depends(db_session)):
    """资料管理页顶部统计：总量、文件夹数、存储量、本月新增（DEMO 界面需要）。"""
    current_admin(request, db)
    now = datetime.now(UTC)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    total_assets = db.scalar(
        select(func.count()).select_from(MaterialAsset).where(MaterialAsset.status == "ready")
    ) or 0
    total_folders = db.scalar(select(func.count()).select_from(MaterialFolder)) or 0
    total_bytes = db.scalar(
        select(func.coalesce(func.sum(MaterialAsset.size_bytes), 0)).where(
            MaterialAsset.status == "ready"
        )
    ) or 0
    month_new = db.scalar(
        select(func.count()).select_from(MaterialAsset).where(
            MaterialAsset.status == "ready", MaterialAsset.created_at >= month_start
        )
    ) or 0
    return {
        "total_assets": total_assets,
        "total_folders": total_folders,
        "total_bytes": int(total_bytes),
        "month_new": month_new,
    }


# ---------- 课时块绑定（阅读资料） ----------


def _require_materials_block(db: Session, block_id: int) -> CourseLessonBlock:
    block = db.get(CourseLessonBlock, block_id)
    if block is None:
        raise HTTPException(404, "内容块不存在。")
    if block.block_type != "materials":
        raise HTTPException(400, "只有阅读资料块可以绑定资料。")
    return block


@router.get("/lesson-blocks/{block_id}/materials")
def list_block_materials(block_id: int, request: Request, db: Session = Depends(db_session)):
    """已绑定资料列表（§4.3：已选项独立保留，删除块/解绑不删源文件）。"""
    current_admin(request, db)
    _require_materials_block(db, block_id)
    rows = db.execute(
        select(LessonBlockMaterial, MaterialAsset)
        .join(MaterialAsset, MaterialAsset.id == LessonBlockMaterial.material_id)
        .where(LessonBlockMaterial.block_id == block_id)
        .order_by(LessonBlockMaterial.sort_order, LessonBlockMaterial.id)
    ).all()
    return {
        "items": [
            {
                "id": link.id,
                "material_id": asset.id,
                "sort_order": link.sort_order,
                "material": _serialize_material(db, asset),
            }
            for link, asset in rows
        ]
    }


@router.post("/lesson-blocks/{block_id}/materials", status_code=201)
def bind_block_materials(block_id: int, payload: BindMaterialsPayload, request: Request,
                         db: Session = Depends(db_session)):
    """批量绑定资料 ID（不复制文件对象，§4.3）；已绑定跳过，幂等。"""
    require_csrf(request)
    admin = current_admin(request, db)
    if not is_editor(admin):
        raise HTTPException(403, "没有编辑课程内容的权限。")
    _require_materials_block(db, block_id)
    ids = list(dict.fromkeys(payload.material_ids))  # 去重保序
    assets = db.scalars(select(MaterialAsset).where(MaterialAsset.id.in_(ids))).all()
    by_id = {a.id: a for a in assets}
    if len(by_id) != len(ids):
        raise HTTPException(400, "部分资料不存在。")
    not_ready = [aid for aid in ids if by_id[aid].status != "ready"]
    if not_ready:
        raise HTTPException(400, f"资料尚未就绪，不能绑定：{sorted(not_ready)}")
    existing = set(
        db.scalars(
            select(LessonBlockMaterial.material_id).where(LessonBlockMaterial.block_id == block_id)
        ).all()
    )
    max_order = db.scalar(
        select(func.max(LessonBlockMaterial.sort_order)).where(LessonBlockMaterial.block_id == block_id)
    ) or -1
    added = 0
    for material_id in ids:
        if material_id in existing:
            continue
        max_order += 1
        db.add(LessonBlockMaterial(block_id=block_id, material_id=material_id, sort_order=max_order))
        added += 1
    audit(db, request.app.state.settings, "lesson_block_bind_materials", "success",
          client_ip(request), admin.id, resource_type="course_lesson_block", resource_id=block_id,
          summary={"added": added, "material_ids": ids})
    db.commit()
    return {"ok": True, "added": added}


@router.delete("/lesson-blocks/{block_id}/materials/{material_id}")
def unbind_block_material(block_id: int, material_id: int, request: Request,
                          db: Session = Depends(db_session)):
    """解除绑定：只删关联行，资料库源文件保留（§4.3 验收点）。"""
    require_csrf(request)
    admin = current_admin(request, db)
    if not is_editor(admin):
        raise HTTPException(403, "没有编辑课程内容的权限。")
    _require_materials_block(db, block_id)
    link = db.scalar(
        select(LessonBlockMaterial).where(
            LessonBlockMaterial.block_id == block_id,
            LessonBlockMaterial.material_id == material_id,
        )
    )
    if link is None:
        raise HTTPException(404, "该资料未绑定到此内容块。")
    audit(db, request.app.state.settings, "lesson_block_unbind_material", "success",
          client_ip(request), admin.id, resource_type="course_lesson_block", resource_id=block_id,
          summary={"material_id": material_id})
    db.delete(link)
    db.commit()
    return {"ok": True}


# ---------- 启动扫尾（后台任务持久化，评审 P1） ----------


def sweep_material_uploads(settings, session_factory) -> int:
    """服务重启后补跑遗留的 sha256 校验（BackgroundTasks 不跨进程）。

    只处理「上传会话已 completed、资产仍 uploading」的行——complete 请求已成功、
    但进程在后台校验任务前退出。上传中（upload.status == initiated）的资产不动，
    避免把用户正在进行的上传误判为失败。
    """
    db = session_factory()
    count = 0
    try:
        rows = db.execute(
            select(MaterialUpload.asset_id)
            .join(MaterialAsset, MaterialAsset.id == MaterialUpload.asset_id)
            .where(
                MaterialUpload.status == "completed",
                MaterialAsset.status == "uploading",
            )
            .distinct()
        ).all()
        for (asset_id,) in rows:
            try:
                verify_material_asset(settings, session_factory, asset_id)
                count += 1
            except Exception:
                db.rollback()
    finally:
        db.close()
    return count
