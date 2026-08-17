"""Windows 文件夹迁移：会话 / 清单分批 / 分片续传 / 服务端校验建档。

对接交接文档《12、资料管理与Windows文件夹迁移》§5/§7：
- POST /api/admin/material-imports                          创建迁移会话
- POST /api/admin/material-imports/{id}/manifest-batches    分批提交目录清单（≤1000/批，幂等）
- POST /api/admin/material-imports/{id}/upload-parts        初始化/恢复条目上传
- POST /api/admin/material-imports/{id}/items/{item_id}/complete  逐文件服务端核对
- GET  /api/admin/material-imports/{id}                    恢复进度与失败项
- POST /api/admin/material-imports/{id}/finalize            触发服务端校验与建档
- POST /api/admin/material-imports/{id}/cancel              取消会话

关键口径：
- 目录清单不允许一次超大 JSON：每批 500～1000 条，client_id 是稳定锚点（幂等 upsert）；
- 冲突策略三选一（§5）：skip 跳过同名 / rename 自动重命名 / version 仅哈希不同建新版本；
  禁止默认静默覆盖；
- SHA-256 由 finalize 阶段服务端下载对象计算（§5：不以文件名/大小/浏览器自报值为准）；
- finalize 是异步任务（可能上万条目），立即返回 finalizing，前端轮询 GET 拿结果摘要；
- 会话记录操作人、来源根目录名、冲突策略与结果摘要（§8）。
"""
from __future__ import annotations

import json

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..material_helpers import (
    MULTIPART_MIN_BYTES,
    compute_object_sha256,
    find_or_create_folder,
    import_object_key,
    infer_mime,
    safe_relative_path,
    sanitize_display_name,
    validate_client_id,
)
from ..models import (
    MaterialAsset,
    MaterialFolder,
    MaterialImportItem,
    MaterialImportSession,
)
from ..permissions import is_editor
from .admin_auth import audit, client_ip, current_admin, db_session, require_csrf

router = APIRouter(prefix="/api/admin", tags=["admin-material-imports"])

CONFLICT_POLICIES = {"skip", "rename", "version"}
BATCH_MAX = 1000
ITEM_UPLOAD_MAX = 100

# finalize 结果统计的键
SUMMARY_KEYS = ("total", "success", "skipped", "conflicted", "failed", "pending")


# ---------- 请求模型 ----------


class CreateImportSessionPayload(BaseModel):
    source_root_name: str = Field(min_length=1, max_length=255)
    target_folder_id: int | None = None
    preserve_structure: bool = True
    conflict_policy: str = "skip"

    @field_validator("conflict_policy")
    @classmethod
    def _check_policy(cls, v: str) -> str:
        if v not in CONFLICT_POLICIES:
            raise ValueError("conflict_policy 只允许 skip / rename / version")
        return v


class ManifestItemPayload(BaseModel):
    client_id: str = Field(min_length=1, max_length=64)
    relative_path: str = Field(min_length=1, max_length=1024)
    file_name: str = Field(min_length=1, max_length=255)
    size_bytes: int = Field(ge=1)
    mime_type: str | None = Field(default=None, max_length=128)
    last_modified: str | None = Field(default=None, max_length=64)  # 前端清单信息，本期不落库


class ManifestBatchPayload(BaseModel):
    items: list[ManifestItemPayload] = Field(min_length=1, max_length=BATCH_MAX)


class UploadPartsPayload(BaseModel):
    item_ids: list[int] = Field(min_length=1, max_length=ITEM_UPLOAD_MAX)


class CompletePart(BaseModel):
    part_number: int = Field(ge=1, le=10_000)
    etag: str = Field(min_length=1, max_length=128)


class CompleteItemPayload(BaseModel):
    parts: list[CompletePart] = Field(default_factory=list, max_length=10_000)


# ---------- 会话辅助 ----------


def _load_session(db: Session, session_id: int) -> MaterialImportSession:
    session = db.get(MaterialImportSession, session_id)
    if session is None:
        raise HTTPException(404, "迁移会话不存在。")
    return session


def _require_owner(session: MaterialImportSession, admin) -> None:
    """迁移会话是私有操作资源：只有创建者能读清单、签发分片、完成上传（评审 P0-3）。"""
    if session.created_by != admin.id:
        raise HTTPException(403, "只能由会话创建者操作该迁移会话。")


def _load_item(db: Session, session_id: int, item_id: int) -> MaterialImportItem:
    item = db.get(MaterialImportItem, item_id)
    if item is None or item.session_id != session_id:
        raise HTTPException(404, "清单条目不存在。")
    return item


def _item_stats(db: Session, session_id: int) -> dict:
    rows = db.execute(
        select(MaterialImportItem.status, func.count())
        .where(MaterialImportItem.session_id == session_id)
        .group_by(MaterialImportItem.status)
    ).all()
    stats = {"pending": 0, "uploading": 0, "uploaded": 0, "imported": 0,
             "failed": 0, "skipped": 0, "conflicted": 0}
    for status, count in rows:
        stats[status] = count
    return stats


def _serialize_item(db: Session, item: MaterialImportItem, settings, parts: bool = False) -> dict:
    uploaded_parts = None
    if parts and item.status == "uploading" and item.upload_mode == "multipart" and item.upload_id:
        from ..s3_multipart import get_minio_client

        try:
            resp = get_minio_client(settings).list_parts(
                Bucket=item.bucket, Key=item.object_key, UploadId=item.upload_id
            )
            uploaded_parts = [p["PartNumber"] for p in resp.get("Parts", [])]
        except Exception:
            uploaded_parts = None
    return {
        "id": item.id,
        "client_id": item.client_id,
        "relative_path": item.relative_path,
        "file_name": item.file_name,
        "size_bytes": item.size_bytes,
        "status": item.status,
        "error": item.error,
        "mode": item.upload_mode,
        "upload_id": item.upload_id,
        "part_count": item.part_count,
        "uploaded_parts": uploaded_parts,
        "asset_id": item.asset_id,
        "sha256": item.sha256,
    }


# ---------- 创建与清单 ----------


@router.post("/material-imports", status_code=201)
def create_import_session(payload: CreateImportSessionPayload, request: Request,
                          db: Session = Depends(db_session)):
    require_csrf(request)
    admin = current_admin(request, db)
    if not is_editor(admin):
        raise HTTPException(403, "没有迁移资料的权限。")
    source_root = payload.source_root_name.strip()
    if not source_root:
        raise HTTPException(400, "来源目录名称不能为空。")
    if payload.target_folder_id is not None and db.get(MaterialFolder, payload.target_folder_id) is None:
        raise HTTPException(404, "目标文件夹不存在。")
    session = MaterialImportSession(
        source_root_name=source_root,
        target_folder_id=payload.target_folder_id,
        preserve_structure=payload.preserve_structure,
        conflict_policy=payload.conflict_policy,
        status="collecting",
        created_by=admin.id,
    )
    db.add(session)
    audit(db, request.app.state.settings, "material_import_create", "success",
          client_ip(request), admin.id, resource_type="material_import_session",
          summary={"source_root_name": source_root, "target_folder_id": payload.target_folder_id,
                   "preserve_structure": payload.preserve_structure,
                   "conflict_policy": payload.conflict_policy})
    db.commit()
    return {
        "id": session.id,
        "source_root_name": session.source_root_name,
        "target_folder_id": session.target_folder_id,
        "preserve_structure": session.preserve_structure,
        "conflict_policy": session.conflict_policy,
        "status": session.status,
    }


@router.post("/material-imports/{session_id}/manifest-batches")
def submit_manifest_batch(session_id: int, payload: ManifestBatchPayload, request: Request,
                          db: Session = Depends(db_session)):
    """分批提交目录清单（§5：每批 500～1000 条）。幂等：同 client_id 覆盖更新。

    单个条目非法不阻断整批：返回 accepted / rejected 明细，前端可精确重试。
    """
    require_csrf(request)
    admin = current_admin(request, db)
    if not is_editor(admin):
        raise HTTPException(403, "没有迁移资料的权限。")
    session = _load_session(db, session_id)
    if session.created_by != admin.id:
        raise HTTPException(403, "只能由会话创建者提交清单。")
    if session.status not in ("collecting", "uploading"):
        raise HTTPException(409, "会话已结束，不能继续提交清单。")
    settings = request.app.state.settings

    accepted = 0
    rejected: list[dict] = []
    seen_client_ids: set[str] = set()
    for entry in payload.items:
        if entry.client_id in seen_client_ids:
            rejected.append({"client_id": entry.client_id, "reason": "同一批次内条目 ID 重复。"})
            continue
        seen_client_ids.add(entry.client_id)
        try:
            validate_client_id(entry.client_id)
            relative_path = safe_relative_path(entry.relative_path)
            file_name = sanitize_display_name(entry.file_name)
            if entry.size_bytes > settings.material_source_max_bytes:
                raise ValueError(f"单个文件不能超过 {settings.material_source_max_bytes // (1024 * 1024)} MB。")
        except ValueError as exc:
            rejected.append({"client_id": entry.client_id, "reason": str(exc)})
            continue
        item = db.scalar(
            select(MaterialImportItem).where(
                MaterialImportItem.session_id == session_id,
                MaterialImportItem.client_id == entry.client_id,
            )
        )
        mime = entry.mime_type or infer_mime(file_name)[0]
        if item is None:
            item = MaterialImportItem(
                session_id=session_id, client_id=entry.client_id, relative_path=relative_path,
                file_name=file_name, size_bytes=entry.size_bytes, mime_type=mime,
            )
            db.add(item)
        else:
            if item.status not in ("pending", "failed"):
                # 已进入上传流程的条目不允许改元数据（断点续传的锚点不能漂移）
                rejected.append({"client_id": entry.client_id, "reason": "条目已开始上传，不能修改。"})
                continue
            item.relative_path = relative_path
            item.file_name = file_name
            item.size_bytes = entry.size_bytes
            item.mime_type = mime
        accepted += 1

    session.total_items = db.scalar(
        select(func.count()).select_from(MaterialImportItem).where(
            MaterialImportItem.session_id == session_id
        )
    ) or 0
    session.total_bytes = db.scalar(
        select(func.coalesce(func.sum(MaterialImportItem.size_bytes), 0)).where(
            MaterialImportItem.session_id == session_id
        )
    ) or 0
    if session.total_bytes > settings.material_import_session_max_bytes:
        raise HTTPException(413, "迁移会话总大小超出配额。")
    audit(db, settings, "material_import_manifest", "success", client_ip(request), admin.id,
          resource_type="material_import_session", resource_id=session_id,
          summary={"accepted": accepted, "rejected": len(rejected)})
    db.commit()
    return {"accepted": accepted, "rejected": rejected, "total_items": session.total_items}


# ---------- 上传 ----------


@router.post("/material-imports/{session_id}/upload-parts")
def init_item_uploads(session_id: int, payload: UploadPartsPayload, request: Request,
                      db: Session = Depends(db_session)):
    """为清单条目初始化上传（大文件 multipart / 小文件 presigned PUT）。

    幂等续传：已 uploading 的条目复用现有 upload_id，不重复创建 multipart；
    刷新后前端用 GET /material-imports/{id} 恢复已传分片，再调本接口补齐参数。
    """
    require_csrf(request)
    admin = current_admin(request, db)
    if not is_editor(admin):
        raise HTTPException(403, "没有迁移资料的权限。")
    session = _load_session(db, session_id)
    if session.created_by != admin.id:
        raise HTTPException(403, "只能由会话创建者上传。")
    if session.status not in ("collecting", "uploading"):
        raise HTTPException(409, "会话已结束，不能继续上传。")
    settings = request.app.state.settings
    items = [db.get(MaterialImportItem, iid) for iid in payload.item_ids]
    if any(item is None or item.session_id != session_id for item in items):
        raise HTTPException(400, "部分清单条目不存在。")

    from ..s3_multipart import create_multipart_upload, get_minio_client

    client = get_minio_client(settings)
    results: list[dict] = []
    for item in items:
        if item.status == "uploading":
            if item.upload_mode == "presigned_put":
                # 续传：小文件重新签发 PUT URL（旧 URL 可能已过期或被使用）
                try:
                    presigned = client.generate_presigned_url(
                        "put_object",
                        Params={"Bucket": item.bucket, "Key": item.object_key, "ContentType": item.mime_type},
                        ExpiresIn=3600,
                    )
                except Exception as exc:
                    raise HTTPException(502, "对象存储暂不可用，请稍后重试。") from exc
                results.append(_upload_params(item, presigned, settings.material_part_size))
            else:
                # multipart 续传：复用现有 upload_id，前端用 GET 恢复已传分片后补齐
                results.append(_upload_params(item, None, settings.material_part_size))
            continue
        if item.status != "pending":
            raise HTTPException(409, f"条目 {item.client_id} 当前状态不允许上传。")
        key = import_object_key(session_id, item.client_id, item.file_name)
        small = item.size_bytes < MULTIPART_MIN_BYTES
        item.bucket = settings.minio_materials_bucket
        item.object_key = key
        if small:
            try:
                presigned = client.generate_presigned_url(
                    "put_object",
                    Params={"Bucket": item.bucket, "Key": key, "ContentType": item.mime_type},
                    ExpiresIn=3600,
                )
            except Exception as exc:
                raise HTTPException(502, "对象存储暂不可用，请稍后重试。") from exc
            item.upload_mode = "presigned_put"
            item.status = "uploading"
            results.append(_upload_params(item, presigned, settings.material_part_size))
        else:
            part_count = max(1, (item.size_bytes + settings.material_part_size - 1) // settings.material_part_size)
            try:
                s3_upload_id = create_multipart_upload(
                    client, item.bucket, key, item.mime_type
                )
            except Exception as exc:
                raise HTTPException(502, "对象存储暂不可用，请稍后重试。") from exc
            item.upload_mode = "multipart"
            item.upload_id = s3_upload_id
            item.part_count = part_count
            item.status = "uploading"
            results.append(_upload_params(item, None, settings.material_part_size))
    if session.status == "collecting":
        session.status = "uploading"
    audit(db, settings, "material_import_upload_init", "success", client_ip(request), admin.id,
          resource_type="material_import_session", resource_id=session_id,
          summary={"items": [r["item_id"] for r in results]})
    db.commit()
    return {"items": results}


def _upload_params(item: MaterialImportItem, presigned: str | None, part_size: int) -> dict:
    return {
        "item_id": item.id,
        "client_id": item.client_id,
        "mode": item.upload_mode,
        "presigned_url": presigned,
        "upload_id": item.upload_id,
        "part_size": None if item.upload_mode == "presigned_put" else part_size,
        "part_count": item.part_count,
    }


@router.get("/material-imports/{session_id}/items/{item_id}/part-url")
def presign_item_part(session_id: int, item_id: int, part_number: int, request: Request,
                      db: Session = Depends(db_session)):
    """分片预签名 URL（GET 无副作用，不要求 CSRF）。续传时前端逐片取。"""
    admin = current_admin(request, db)
    _require_owner(_load_session(db, session_id), admin)
    item = _load_item(db, session_id, item_id)
    if item.status != "uploading" or item.upload_mode != "multipart" or not item.upload_id:
        raise HTTPException(409, "该条目当前不可上传分片。")
    if part_number < 1 or part_number > (item.part_count or 10_000):
        raise HTTPException(400, "分片序号越界。")
    settings = request.app.state.settings
    from ..s3_multipart import get_minio_client, presign_upload_part

    try:
        url = presign_upload_part(
            get_minio_client(settings), item.bucket, item.object_key, item.upload_id, part_number
        )
    except Exception as exc:
        raise HTTPException(502, "对象存储暂不可用，请稍后重试。") from exc
    return {"item_id": item_id, "part_number": part_number, "url": url}


@router.post("/material-imports/{session_id}/items/{item_id}/complete")
def complete_item_upload(session_id: int, item_id: int, payload: CompleteItemPayload,
                         request: Request, db: Session = Depends(db_session)):
    """完成单文件上传：服务端向 MinIO 核对（不信任前端自报），置 uploaded。

    哈希与建档在 finalize 阶段统一做（一个清单可能上万条目，逐条同步算会卡死请求）。
    """
    require_csrf(request)
    admin = current_admin(request, db)
    if not is_editor(admin):
        raise HTTPException(403, "没有迁移资料的权限。")
    _require_owner(_load_session(db, session_id), admin)
    item = _load_item(db, session_id, item_id)
    if item.status != "uploading":
        raise HTTPException(409, "条目当前状态不允许完成上传。")
    settings = request.app.state.settings
    from ..s3_multipart import complete_multipart_upload, get_minio_client, list_uploaded_parts

    client = get_minio_client(settings)
    try:
        if item.upload_mode == "multipart":
            stored = {
                p["PartNumber"]: p["ETag"]
                for p in list_uploaded_parts(client, item.bucket, item.object_key, item.upload_id)
            }
            provided = {p.part_number: p.etag for p in payload.parts}
            if set(provided) != set(stored):
                raise HTTPException(409, "已传分片与服务端记录不一致，请检查后重试。")
            for pn, etag in provided.items():
                if etag.strip('"') != stored[pn].strip('"'):
                    raise HTTPException(409, f"分片 {pn} 的校验值不匹配。")
            complete_multipart_upload(
                client, item.bucket, item.object_key, item.upload_id,
                [{"PartNumber": p.part_number, "ETag": p.etag} for p in payload.parts],
            )
        else:  # presigned_put：head_object 核对大小
            head = client.head_object(Bucket=item.bucket, Key=item.object_key)
            if head.get("ContentLength") != item.size_bytes:
                raise HTTPException(409, "上传文件大小与服务端记录不一致。")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(502, "对象存储暂不可用，请稍后重试。") from exc
    item.status = "uploaded"
    audit(db, settings, "material_import_item_complete", "success", client_ip(request), admin.id,
          resource_type="material_import_session", resource_id=session_id,
          summary={"item_id": item_id, "client_id": item.client_id, "key": item.object_key})
    db.commit()
    return {"item_id": item_id, "status": "uploaded"}


# ---------- 恢复 / 最终化 / 取消 ----------


@router.get("/material-imports/{session_id}")
def get_import_session(
    session_id: int, request: Request, page: int = 1, page_size: int = 50,
    status: str = "", include_parts: int = 0, db: Session = Depends(db_session),
):
    """恢复进度与失败项（§5 第 7 条：刷新后可恢复；§9 第 10 步对账用）。"""
    admin = current_admin(request, db)
    session = _load_session(db, session_id)
    _require_owner(session, admin)
    settings = request.app.state.settings
    page = max(1, page)
    page_size = min(max(1, page_size), 200)
    conds = [MaterialImportItem.session_id == session_id]
    if status:
        conds.append(MaterialImportItem.status == status)
    total = db.scalar(select(func.count()).select_from(MaterialImportItem).where(*conds)) or 0
    items = db.scalars(
        select(MaterialImportItem).where(*conds)
        .order_by(MaterialImportItem.id)
        .offset((page - 1) * page_size).limit(page_size)
    ).all()
    summary = {}
    if session.summary_json:
        try:
            summary = json.loads(session.summary_json)
        except ValueError:
            summary = {}
    return {
        "id": session.id,
        "source_root_name": session.source_root_name,
        "target_folder_id": session.target_folder_id,
        "preserve_structure": session.preserve_structure,
        "conflict_policy": session.conflict_policy,
        "status": session.status,
        "total_items": session.total_items,
        "total_bytes": session.total_bytes,
        "summary": summary,
        "stats": _item_stats(db, session_id),
        "items": [_serialize_item(db, i, settings, parts=bool(include_parts)) for i in items],
        "page": page,
        "page_size": page_size,
        "total": total,
    }


@router.post("/material-imports/{session_id}/finalize")
def finalize_import(session_id: int, request: Request, background: BackgroundTasks,
                    db: Session = Depends(db_session)):
    """触发最终化：服务端逐文件校验哈希、建目录、按冲突策略建档（异步执行）。"""
    require_csrf(request)
    admin = current_admin(request, db)
    if not is_editor(admin):
        raise HTTPException(403, "没有迁移资料的权限。")
    session = _load_session(db, session_id)
    if session.created_by != admin.id:
        raise HTTPException(403, "只能由会话创建者触发最终化。")
    if session.status not in ("collecting", "uploading"):
        raise HTTPException(409, "会话当前状态不能触发最终化。")
    session.status = "finalizing"
    audit(db, request.app.state.settings, "material_import_finalize_start", "success",
          client_ip(request), admin.id, resource_type="material_import_session", resource_id=session_id)
    db.commit()
    background.add_task(
        finalize_import_background, request.app.state.settings,
        request.app.state.session_factory, session_id,
    )
    return {"status": "finalizing"}


@router.post("/material-imports/{session_id}/cancel")
def cancel_import(session_id: int, request: Request, db: Session = Depends(db_session)):
    """取消会话：中止所有进行中的 multipart，会话状态置 cancelled（未传对象留待清理脚本）。"""
    require_csrf(request)
    admin = current_admin(request, db)
    if not is_editor(admin):
        raise HTTPException(403, "没有迁移资料的权限。")
    session = _load_session(db, session_id)
    if session.created_by != admin.id:
        raise HTTPException(403, "只能由会话创建者取消。")
    if session.status in ("completed", "cancelled", "failed"):
        raise HTTPException(409, "会话已结束，不能取消。")
    settings = request.app.state.settings
    if session.status == "uploading":
        from ..s3_multipart import abort_multipart_upload, get_minio_client

        client = get_minio_client(settings)
        for item in db.scalars(
            select(MaterialImportItem).where(
                MaterialImportItem.session_id == session_id,
                MaterialImportItem.status == "uploading",
                MaterialImportItem.upload_mode == "multipart",
                MaterialImportItem.upload_id.is_not(None),
            )
        ).all():
            try:
                abort_multipart_upload(client, item.bucket, item.object_key, item.upload_id)
            except Exception:
                pass
    session.status = "cancelled"
    audit(db, settings, "material_import_cancel", "success", client_ip(request), admin.id,
          resource_type="material_import_session", resource_id=session_id)
    db.commit()
    return {"status": "cancelled"}


# ---------- 后台最终化 ----------


def _resolve_target_folder(db: Session, session: MaterialImportSession, relative_path: str) -> int | None:
    """按保留目录结构解析条目的目标文件夹：relative_path 的父目录在 target 下逐级建。

    preserve_structure=False 时全部落到 target_folder_id（可为 None = 根）。
    """
    if not session.preserve_structure:
        return session.target_folder_id
    parent_dir = relative_path.rsplit("/", 1)[0] if "/" in relative_path else ""
    if not parent_dir:
        return session.target_folder_id
    current_id = session.target_folder_id
    for segment in parent_dir.split("/"):
        current_id = find_or_create_folder(db, current_id, segment).id
    return current_id


def _folder_cond(folder_id: int | None):
    """folder_id 可能为 None（根目录）也可能为数字：PG 不认 `col IS 1`，需分情况。"""
    return MaterialAsset.folder_id.is_(None) if folder_id is None else MaterialAsset.folder_id == folder_id


def _unique_display_name(db: Session, folder_id: int | None, file_name: str) -> str:
    """同名冲突（rename 策略）：找 "name (2).ext" 这类可用名。"""
    stem, dot, ext = file_name.rpartition(".")
    n = 2
    base = f"{stem} ({n}){dot}{ext}" if dot else f"{file_name} ({n})"
    while db.scalar(
        select(MaterialAsset.id).where(
            _folder_cond(folder_id),
            MaterialAsset.display_name == base,
        )
    ) is not None:
        n += 1
        base = f"{stem} ({n}){dot}{ext}" if dot else f"{file_name} ({n})"
    return base


def _existing_asset_in_folder(db: Session, folder_id: int | None, display_name: str) -> MaterialAsset | None:
    return db.scalar(
        select(MaterialAsset).where(
            _folder_cond(folder_id),
            MaterialAsset.display_name == display_name,
            MaterialAsset.status == "ready",
        )
    )


def finalize_import_background(settings, session_factory, session_id: int) -> None:
    """最终化：逐 uploaded 条目下载算 sha256 → 建目录 → 冲突策略建档 → 汇总摘要。

    冲突语义（§5）：
    - skip    目标目录已有同名 → 跳过（不建档，记 skipped）
    - rename  自动重命名保留两份（记 conflicted）
    - version 同名且同哈希 → 跳过（内容重复，记 skipped）；同名不同哈希 → 新建版本（记 conflicted）
    成功建档的条目 status 置 imported（区别于已上传未建档的 uploaded）。
    """
    db = session_factory()
    try:
        session = db.get(MaterialImportSession, session_id)
        if session is None or session.status != "finalizing":
            return
        from ..s3_multipart import get_minio_client

        client = get_minio_client(settings)
        items = db.scalars(
            select(MaterialImportItem)
            .where(MaterialImportItem.session_id == session_id)
            .order_by(MaterialImportItem.id)
        ).all()
        summary = {"total": len(items), "success": 0, "skipped": 0,
                   "conflicted": 0, "failed": 0, "pending": 0}
        for item in items:
            if item.status != "uploaded":
                if item.status == "pending":
                    summary["pending"] += 1
                elif item.status == "failed":
                    summary["failed"] += 1
                continue
            try:
                digest, actual = compute_object_sha256(client, item.bucket, item.object_key)
                if actual != item.size_bytes:
                    raise ValueError("上传对象大小与清单不一致。")
                item.sha256 = digest
                folder_id = _resolve_target_folder(db, session, item.relative_path)
                existing = _existing_asset_in_folder(db, folder_id, item.file_name)
                if existing is not None:
                    if session.conflict_policy == "skip":
                        item.status = "skipped"
                        summary["skipped"] += 1
                        continue
                    if session.conflict_policy == "version" and existing.sha256 == digest:
                        # 同名同哈希：内容重复，跳过并复用已有资产
                        item.status = "skipped"
                        item.asset_id = existing.id
                        item.target_folder_id = folder_id
                        summary["skipped"] += 1
                        continue
                    if session.conflict_policy == "rename":
                        display_name = _unique_display_name(db, folder_id, item.file_name)
                    else:  # version：同名不同哈希 → 多版本共存，同名建档
                        display_name = item.file_name
                else:
                    display_name = item.file_name
                asset = MaterialAsset(
                    folder_id=folder_id, display_name=display_name,
                    object_key=item.object_key, mime_type=item.mime_type,
                    asset_type=infer_mime(item.file_name)[1],
                    size_bytes=item.size_bytes, sha256=digest, status="ready",
                    created_by=session.created_by,
                )
                db.add(asset)
                db.flush()
                item.asset_id = asset.id
                item.target_folder_id = folder_id
                item.status = "imported"
                item.error = None
                if session.conflict_policy == "rename" or (
                    session.conflict_policy == "version" and existing is not None
                ):
                    summary["conflicted"] += 1
                else:
                    summary["success"] += 1
            except Exception as exc:
                item.status = "failed"
                item.error = str(exc)[:255]
                summary["failed"] += 1
        session.status = "completed"
        session.summary_json = json.dumps(summary, ensure_ascii=False)
        db.commit()
    except Exception:
        db.rollback()
        session = db.get(MaterialImportSession, session_id)
        if session is not None and session.status == "finalizing":
            session.status = "failed"
            db.commit()
    finally:
        db.close()


def sweep_material_imports(settings, session_factory) -> int:
    """服务重启后重新触发卡在 finalizing 的迁移会话（BackgroundTasks 不跨进程）。

    finalize 是幂等的：只处理 status=uploaded 的条目，重新跑不会重复建档；
    失败条目保持 failed，pending 保持 pending，前端可继续补传后再 finalize。
    """
    db = session_factory()
    count = 0
    try:
        session_ids = db.scalars(
            select(MaterialImportSession.id).where(MaterialImportSession.status == "finalizing")
        ).all()
        for session_id in session_ids:
            try:
                finalize_import_background(settings, session_factory, session_id)
                count += 1
            except Exception:
                db.rollback()
    finally:
        db.close()
    return count
