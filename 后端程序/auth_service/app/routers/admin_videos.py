"""后台视频上传：Uppy + S3 Multipart 直传 MinIO。

流程（方案 A）：
1. 管理员 POST /api/admin/videos/uploads —— 建 Video(draft) + VideoUpload(initiated)，
   并在 MinIO 起一个 multipart upload，返回 video_id / upload_id / object_key / 建议分片大小。
2. 前端 Uppy 对每个 part 调 GET /api/admin/videos/uploads/{upload_id}/parts/{n}
   拿预签名 URL，浏览器**直传** MinIO（服务端不碰字节）。
3. 全部传完，前端 POST /api/admin/videos/uploads/{upload_id}/complete，body 带
   [{part_number, etag}]。服务端**不信前端**：用 upload_id 向 MinIO 列 parts 核对 ETag，
   再 complete_multipart_upload，回写 Video.status=uploaded（等待转码）。
4. 失败可 POST .../abort 取消，MinIO 清理已传 part。

复用 admin_auth 的 current_admin / require_csrf / limit / audit / client_ip / db_session。
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import AdminUser, CourseLesson, CourseLessonBlock, LessonVideoBlock, Problem, ScratchChallenge, Video, VideoUpload, VideoVariant
from ..s3_multipart import (
    abort_multipart_upload,
    complete_multipart_upload,
    create_multipart_upload,
    delete_object,
    list_uploaded_parts,
    play_token_minutes,
    presign_upload_part,
)
from .admin_auth import audit, client_ip, current_admin, db_session, limit, require_csrf
from .video_play import build_play_response

router = APIRouter(prefix="/api/admin", tags=["admin-videos"])

# 角色常量单源在 app/permissions.py。原先各 router 各抄一份，抄到第 5 份时
# 收口——跨 router 耦合是想避免的，但常量本来就不属于任何一个 router。
from ..permissions import is_editor as _is_editor  # noqa: E402  (紧邻使用处，便于溯源)


class CreateUploadRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    filename: str = Field(min_length=1, max_length=255)
    content_type: str = Field(default="video/mp4", max_length=128)
    file_size: int = Field(ge=1)
    # 不收 lesson_id：上传时课时通常还不存在，绑定统一在后台「节点管理」里做，
    # 权威列是 course_lessons.video_id（0028 迁移已删掉本表的 lesson_id）。


class CompletePart(BaseModel):
    part_number: int = Field(ge=1, le=10000)
    etag: str = Field(min_length=1, max_length=128)


class CompleteUploadRequest(BaseModel):
    parts: list[CompletePart] = Field(min_length=1, max_length=10000)


def _object_key(admin_id: int, filename: str) -> str:
    """源桶里的 key：按 管理员/年/月 分目录，文件名用 uuid 防枚举与覆盖。

    原始文件名不进 key（隐私 + 防路径冲突）；扩展名保留用于内容类型推断。
    """
    now = datetime.now(UTC)
    stem = uuid.uuid4().hex
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "mp4"
    return f"admin-{admin_id}/{now:%Y/%m}/{stem}.{ext}"


@router.get("/videos")
def list_videos(request: Request, db: Session = Depends(db_session)):
    """最近上传列表（供后台视频管理页）。每条的 file_size 取最近一次上传会话。"""
    current_admin(request, db)  # 仅校验登录态，不需要读取该对象
    videos = db.scalars(
        select(Video).order_by(Video.id.desc()).limit(20)
    ).all()
    result = []
    for v in videos:
        latest = db.scalar(
            select(VideoUpload.file_size)
            .where(VideoUpload.video_id == v.id)
            .order_by(VideoUpload.id.desc())
            .limit(1)
        )
        primary = db.get(VideoVariant, v.primary_variant_id) if v.primary_variant_id else None
        # 只有 primary 档是 HLS 产物（master.m3u8）才算可播；source 直出（.bin 等）
        # 或未转码完成的都不给「播放」按钮。
        playable = bool(
            primary and primary.status == "ready" and primary.object_key.endswith(".m3u8")
        )
        result.append(
            {
                "id": v.id,
                "title": v.title,
                "status": v.status,
                "file_size": latest,
                "created_at": v.created_at.isoformat() if v.created_at else None,
                "playable": playable,
            }
        )
    return result


@router.post("/videos/{video_id}/play")
def admin_play_url(request: Request, video_id: int, db: Session = Depends(db_session)):
    """后台预览：管理员签发播放令牌（不走课时权限，仅需编辑权限 + 视频 ready）。"""
    require_csrf(request)
    admin = current_admin(request, db)
    if not _is_editor(admin):
        raise HTTPException(403, "没有播放预览权限。")
    settings = request.app.state.settings

    video = db.get(Video, video_id)
    if video is None or video.status != "ready":
        raise HTTPException(404, "该视频暂不可播放，或仍在转码中。")
    variant: VideoVariant | None = (
        db.get(VideoVariant, video.primary_variant_id) if video.primary_variant_id else None
    )
    # primary 档必须是 HLS 产物（master.m3u8）。source 直出（.bin 等非 HLS）没有
    # master 播放列表，发了令牌前端也会 404——这里直接拒，返回一致的可播判断。
    if (
        variant is None
        or variant.status != "ready"
        or not variant.object_key.endswith("master.m3u8")
    ):
        raise HTTPException(404, "该视频暂不可播放，或仍在转码中。")

    ttl_minutes = play_token_minutes(video.duration_seconds, settings.video_token_minutes)
    # 所有 ready 档位列表，给前端构造画质切换菜单。地址口径与学生端同一份
    # （build_play_response）：稳定路径 /v/{video_id}/... + query 签名，生产由 nginx
    # 在边缘校验，见 app/video_sign.py。
    variant_rows = db.scalars(
        select(VideoVariant)
        .where(VideoVariant.video_id == video_id, VideoVariant.status == "ready")
        .order_by(VideoVariant.bitrate_kbps.asc())
    ).all()
    # uid 前缀 "a"：管理员与学生的自增 id 会撞号，签名串里必须区分开，
    # 否则出问题时从访问日志的 u= 反查不出到底是谁在拉流。
    return build_play_response(settings, video.id, f"a{admin.id}", variant_rows, ttl_minutes)


@router.post("/videos/uploads", status_code=201)
def create_upload(request: Request, payload: CreateUploadRequest, db: Session = Depends(db_session)):
    require_csrf(request)
    admin = current_admin(request, db)
    if not _is_editor(admin):
        raise HTTPException(403, "没有上传视频的权限。")
    settings = request.app.state.settings
    limit(request, "admin-video-upload", client_ip(request), 30, 3600)
    if payload.file_size > settings.video_source_max_bytes:
        raise HTTPException(
            413, f"源文件不能超过 {settings.video_source_max_bytes // (1024 * 1024 * 1024)} GB。"
        )

    key = _object_key(admin.id, payload.filename)
    from ..s3_multipart import get_minio_client

    client = get_minio_client(settings)
    try:
        upload_id = create_multipart_upload(client, settings.minio_source_bucket, key, payload.content_type)
    except Exception as exc:  # MinIO 不可达 / 凭据错
        raise HTTPException(502, "对象存储暂不可用，请稍后重试。") from exc

    video = Video(title=payload.title, owner_id=admin.id, status="draft")
    db.add(video)
    db.flush()  # 先拿到 video.id 再建 upload 关联
    part_count = max(1, (payload.file_size + settings.video_part_size - 1) // settings.video_part_size)
    upload = VideoUpload(
        video_id=video.id,
        uploader_id=admin.id,
        bucket=settings.minio_source_bucket,
        object_key=key,
        upload_id=upload_id,
        content_type=payload.content_type,
        file_size=payload.file_size,
        part_count=part_count,
        status="initiated",
    )
    db.add(upload)
    audit(
        db, settings, "video_upload_create", "success", client_ip(request), admin.id,
        resource_type="video", resource_id=video.id,
        summary={"upload_id": upload_id, "bucket": settings.minio_source_bucket, "key": key, "file_size": payload.file_size},
    )
    db.commit()
    return {
        "video_id": video.id,
        "upload_id": upload_id,
        "object_key": key,
        "bucket": settings.minio_source_bucket,
        "part_size": settings.video_part_size,
        "part_count": part_count,
        "content_type": payload.content_type,
    }


def _load_upload(db: Session, upload_id: str, admin: AdminUser) -> VideoUpload:
    upload = db.scalar(select(VideoUpload).where(VideoUpload.upload_id == upload_id))
    if upload is None or upload.status != "initiated":
        raise HTTPException(404, "上传会话不存在或已结束。")
    # 仅发起者可继续操作，避免 A 起的上传被 B 完成 / abort。
    if upload.uploader_id != admin.id:
        raise HTTPException(403, "无权操作该上传会话。")
    return upload


@router.get("/videos/uploads/{upload_id}/parts/{part_number}")
def presign_part(request: Request, upload_id: str, part_number: int, db: Session = Depends(db_session)):
    # 刻意不要求 CSRF：GET 无副作用（仅返回一个预签名 URL），响应受同源策略/CORS
    # 保护，跨站攻击者读不到内容；与 /api/admin/me 等只读接口同口径。
    # 前端 adminRequest 也只对 mutation 附加 X-CSRF-Token，GET 若要求 CSRF 会 403。
    admin = current_admin(request, db)
    upload = _load_upload(db, upload_id, admin)
    settings = request.app.state.settings
    if part_number < 1 or part_number > (upload.part_count or 10000):
        raise HTTPException(400, "分片序号越界。")
    from ..s3_multipart import get_minio_client

    client = get_minio_client(settings)
    try:
        url = presign_upload_part(client, upload.bucket, upload.object_key, upload.upload_id, part_number)
    except Exception as exc:
        raise HTTPException(502, "对象存储暂不可用，请稍后重试。") from exc
    return {"upload_id": upload_id, "part_number": part_number, "url": url}


@router.post("/videos/uploads/{upload_id}/complete")
def complete_upload(
    request: Request,
    upload_id: str,
    payload: CompleteUploadRequest,
    background: BackgroundTasks,
    db: Session = Depends(db_session),
):
    require_csrf(request)
    admin = current_admin(request, db)
    upload = _load_upload(db, upload_id, admin)
    settings = request.app.state.settings
    from ..s3_multipart import get_minio_client

    client = get_minio_client(settings)

    # 不信前端自报的 ETag：用 upload_id 向 MinIO 列已传 parts，逐一核对。
    try:
        stored = {
            p["PartNumber"]: p["ETag"]
            for p in list_uploaded_parts(client, upload.bucket, upload.object_key, upload.upload_id)
        }
    except Exception as exc:
        raise HTTPException(502, "对象存储暂不可用，请稍后重试。") from exc
    provided = {p.part_number: p.etag for p in payload.parts}
    if set(provided) != set(stored):
        raise HTTPException(409, "已传分片与服务端记录不一致，请检查后重试。")
    for pn, etag in provided.items():
        if etag.strip('"') != stored[pn].strip('"'):
            raise HTTPException(409, f"分片 {pn} 的校验值不匹配。")

    try:
        complete_multipart_upload(
            client, upload.bucket, upload.object_key, upload.upload_id,
            [{"PartNumber": p.part_number, "ETag": p.etag} for p in payload.parts],
        )
    except Exception as exc:
        raise HTTPException(502, "合并分片失败，请稍后重试。") from exc

    upload.status = "completed"
    video = db.get(Video, upload.video_id)
    if video is not None:
        video.status = "uploaded"
    audit(
        db, settings, "video_upload_complete", "success", client_ip(request), admin.id,
        resource_type="video", resource_id=upload.video_id,
        summary={"upload_id": upload_id, "key": upload.object_key, "parts": len(payload.parts)},
    )
    db.commit()
    # 提交转码。eager 模式（本地无 Redis）在响应发送后同步执行；生产由 worker 异步消费。
    from ..tasks.transcode import transcode_video

    background.add_task(transcode_video.delay, upload.video_id)
    return {"video_id": upload.video_id, "status": "uploaded"}


@router.post("/videos/uploads/{upload_id}/abort", status_code=200)
def abort_upload(request: Request, upload_id: str, db: Session = Depends(db_session)):
    require_csrf(request)
    admin = current_admin(request, db)
    upload = _load_upload(db, upload_id, admin)
    settings = request.app.state.settings
    from ..s3_multipart import get_minio_client

    client = get_minio_client(settings)
    try:
        abort_multipart_upload(client, upload.bucket, upload.object_key, upload.upload_id)
    except Exception:
        # 即使 MinIO 清理失败也要把本地会话标记 abort，避免悬挂的 multipart 占桶。
        pass
    upload.status = "aborted"
    audit(
        db, settings, "video_upload_abort", "success", client_ip(request), admin.id,
        resource_type="video", resource_id=upload.video_id, summary={"upload_id": upload_id},
    )
    db.commit()
    return {"video_id": upload.video_id, "status": "aborted"}


@router.delete("/videos/{video_id}", status_code=204)
def delete_video(video_id: int, request: Request, db: Session = Depends(db_session)):
    """彻底删除一个视频（解析视频「删除」按钮走这里）。

    两条闸门，顺序就是顺序：
    1. 引用检查先行——凡被题目解析、Scratch 挑战解析、课时主视频、课时内容块视频
       引用的视频一律 409 并列出引用方；删除侧不依赖发布状态兜底（同
       `admin_papers._paper_delete_blocker` 的范式）。
    2. 只有未引用的视频能删，删除时先清 MinIO 对象（源桶 + 各播放桶产物）再删行——
       `video_uploads` / `video_variants` 带 ondelete=CASCADE，库删由外键级联。
       对象删除失败不阻塞（`delete_object` 吞异常）：库里删干净即对用户不可见。
    """
    require_csrf(request)
    admin = current_admin(request, db)
    if not _is_editor(admin):
        raise HTTPException(403, "没有删除视频的权限。")
    video = db.get(Video, video_id)
    if video is None:
        raise HTTPException(404, "视频不存在。")

    # 引用检查：题目解析视频 / Scratch 挑战解析视频 / 课时主视频 / 内容块视频。
    blockers: list[str] = []
    problem_refs = db.scalar(
        select(func.count()).select_from(Problem)
        .where(Problem.analysis_video_id == video_id)
    ) or 0
    if problem_refs:
        blockers.append(f"被 {problem_refs} 道题的解析视频引用")
    scratch_refs = db.scalar(
        select(func.count()).select_from(ScratchChallenge)
        .where(ScratchChallenge.analysis_video_id == video_id)
    ) or 0
    if scratch_refs:
        blockers.append(f"被 {scratch_refs} 个 Scratch 挑战的解析视频引用")
    lesson_refs = db.scalar(
        select(func.count()).select_from(CourseLesson)
        .where(CourseLesson.video_id == video_id)
    ) or 0
    if lesson_refs:
        blockers.append(f"被 {lesson_refs} 个课时引用")
    block_refs = db.scalar(
        select(func.count()).select_from(LessonVideoBlock)
        .where(LessonVideoBlock.video_id == video_id)
    ) or 0
    if block_refs:
        blockers.append(f"被 {block_refs} 个内容块引用")
    if blockers:
        raise HTTPException(409, "该视频正在被使用，不能删除：" + "、".join(blockers))

    settings = request.app.state.settings
    from ..s3_multipart import get_minio_client

    client = get_minio_client(settings)
    # 源文件（源桶）+ 各档 HLS 产物（播放桶）。HLS 产物按目录存放，
    # master.m3u8 的 key 所在目录即整条流的根——这里删 master 即可，切片是孤儿。
    upload = db.scalar(
        select(VideoUpload).where(VideoUpload.video_id == video_id)
        .order_by(VideoUpload.id.desc())
    )
    if upload and upload.bucket and upload.object_key:
        delete_object(client, upload.bucket, upload.object_key)
    variants = db.scalars(
        select(VideoVariant).where(VideoVariant.video_id == video_id)
    ).all()
    for variant in variants:
        if variant.bucket and variant.object_key:
            delete_object(client, variant.bucket, variant.object_key)

    audit(
        db, settings, "video_delete", "success", client_ip(request), admin.id,
        resource_type="video", resource_id=video_id,
        summary={"status": video.status, "variants": len(variants)},
    )
    db.delete(video)
    db.commit()
    return Response(status_code=204)
