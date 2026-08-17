"""题干配图上传。内容寻址落盘，URL 由 nginx 直发。

单独成一个 router 而不是并进 admin_questions.py：配图不是题库独有的，解析、选项现在
就在用，将来课程节点/公告一样要用。另外那个文件已经 800 行，再塞一套图片处理会更难读。

**存储与访问的取舍（决定了这个模块的形状，改之前先读）**：
图片走磁盘 + 内容寻址 + 静态服务，URL 无鉴权，靠 sha256 不可枚举。
代价写明：解析里的配图，只要 URL 泄露就能被直接访问，即使那条考试链接配的是
`show_analysis = never`。接受它，因为堵这个口子要一整套签名 URL 基建，
而泄露路径只有"看得见解析的人主动把地址发出去"这一条。

红线：判分资产（参考代码、标准答案）不许以图片形式存在。这条拦不住，只在界面上提示。
"""

from __future__ import annotations

import hashlib
from io import BytesIO
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy.orm import Session

from ..models import AdminUser, CourseCover, MediaAsset
from .admin_auth import audit, client_ip, current_admin, db_session, limit, require_csrf

router = APIRouter(prefix="/api/admin", tags=["admin-media"])

# 与 admin_questions.py 保持同一套角色常量。故意复制而不是 import：那个文件正在被
# 频繁改动，为一个三元组建立跨路由依赖不划算；不一致会被 test_admin_media 里的用例逮到。
EDITOR_ROLES = {"editor", "admin"}
REVIEWER_ROLES = {"reviewer"}
SUPER_ROLE = "super_admin"

# 输出格式白名单。键是 Pillow 解出来的 format，值是（落盘扩展名, 保存用的 format）。
# 不在表里的一律转 PNG——包括 BMP、TIFF 这些能解但不该出现在网页上的格式。
_OUTPUT_FORMATS = {
    "PNG": ("png", "PNG"),
    "JPEG": ("jpg", "JPEG"),
    "GIF": ("gif", "GIF"),
    "WEBP": ("webp", "WEBP"),
}
# 动图的帧数上限。一张 500 帧的 GIF 解出来是几百 MB 的像素，且题干里没有用途。
_MAX_GIF_FRAMES = 200


def _is_editor(admin: AdminUser) -> bool:
    # 审核员也放行：审核时补一张说明图是合理的，为此把图存不进去只会逼人绕路。
    return admin.role in EDITOR_ROLES | REVIEWER_ROLES or admin.role == SUPER_ROLE


def _decode(raw: bytes) -> tuple[Image.Image, str]:
    """把上传的字节解成 Pillow 图像，并返回它真实的格式。

    **只信解码结果，不信 Content-Type 也不信扩展名**：改个后缀就能把任意文件塞进来，
    而这个目录是要被浏览器当图片加载的。
    """
    try:
        probe = Image.open(BytesIO(raw))
        probe.verify()          # verify() 之后对象不可再用，必须重新 open
        image = Image.open(BytesIO(raw))
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise HTTPException(400, "无法识别的图片格式，请上传 PNG / JPG / GIF / WebP。") from exc
    fmt = (image.format or "").upper()
    # SVG 走不到这里（Pillow 不认），但把话说清楚：它是可执行 XML，能带 <script>，
    # 而 DOMPurify 管的是我们渲染的 HTML，管不到 <img src> 指向的那个文件本身。
    if fmt not in _OUTPUT_FORMATS:
        raise HTTPException(400, "只支持 PNG / JPG / GIF / WebP 格式的图片。")
    if getattr(image, "n_frames", 1) > _MAX_GIF_FRAMES:
        raise HTTPException(400, f"动图帧数不能超过 {_MAX_GIF_FRAMES} 帧。")
    return image, fmt


def _normalize(image: Image.Image, fmt: str, max_dimension: int) -> tuple[bytes, str, str, int, int]:
    """缩放 + 重编码，返回（字节, 扩展名, 格式, 宽, 高）。

    重编码一次性解决三件事：剥掉 EXIF（手机拍的题目照片带 GPS，会一路进学员端）、
    剥掉附加在图片尾部的伪装数据、把"20MB 单反原图"压到题干用得起的大小。

    动图不缩放也不重编码内容——逐帧处理会把动图拍扁成第一帧，那是把图弄坏而不是优化。
    """
    ext, save_format = _OUTPUT_FORMATS[fmt]
    if save_format == "GIF" and getattr(image, "n_frames", 1) > 1:
        buffer = BytesIO()
        image.save(buffer, format="GIF", save_all=True)
        return buffer.getvalue(), ext, save_format, image.width, image.height

    # exif_transpose：手机竖拍的照片靠 EXIF 方向标记才显示得正，而我们下一步就把
    # EXIF 剥了——不先转正，图会横过来。slider_captcha.py 里是同一个理由。
    flat = ImageOps.exif_transpose(image)
    if max(flat.width, flat.height) > max_dimension:
        flat.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)
    buffer = BytesIO()
    if save_format == "JPEG":
        # JPEG 不支持透明通道，带 alpha 的图存进去会报错或变成黑块
        flat = flat.convert("RGB")
        flat.save(buffer, format="JPEG", quality=88, optimize=True)
    else:
        flat.save(buffer, format=save_format)
    return buffer.getvalue(), ext, save_format, flat.width, flat.height


def media_relative_path(sha256: str, ext: str) -> str:
    """URL 与磁盘共用的相对路径。两级分桶避免单目录堆几万个文件——ext4 撑得住，
    但 `ls` 一次要等半分钟，运维的时候会骂人。"""
    return f"{sha256[:2]}/{sha256}.{ext}"


def course_cover_relative_path(sha256: str, ext: str) -> str:
    """课包封面的相对路径。与 media_relative_path() 同构，但根目录 / URL 前缀
    各用各的（course_cover_upload_root / /course-covers/）——用户要求封面与题干
    配图**存储位置新开一个区域**，两个清理口径不能互相扫到对方的文件。"""
    return f"{sha256[:2]}/{sha256}.{ext}"


@router.post("/media/images", status_code=201)
async def upload_image(request: Request, file: UploadFile = File(...), db: Session = Depends(db_session)):
    require_csrf(request)
    admin = current_admin(request, db)
    if not _is_editor(admin):
        raise HTTPException(403, "没有上传图片的权限。")
    # 5 分钟 60 张。比 ZIP 的 12/300 松：录一道题贴三四张图是正常的。
    limit(request, "admin-media-upload", client_ip(request), 60, 300)

    settings = request.app.state.settings
    # 多读一个字节才能区分"正好等于上限"和"超了"，与 ZIP 上传同一套写法
    raw = await file.read(settings.media_max_bytes + 1)
    if len(raw) > settings.media_max_bytes:
        raise HTTPException(413, f"图片不能超过 {settings.media_max_bytes // (1024 * 1024)} MB。")
    if not raw:
        raise HTTPException(400, "上传内容为空。")

    image, fmt = _decode(raw)
    try:
        data, ext, _save_format, width, height = _normalize(image, fmt, settings.media_max_dimension)
    except OSError as exc:
        raise HTTPException(400, "图片处理失败，请换一张或另存为 PNG 后重试。") from exc
    finally:
        image.close()

    # 哈希算的是**重编码之后**的字节。对原始字节算的话，同一张图从不同设备传来
    # EXIF 不同、哈希就不同，去重直接废掉。
    digest = hashlib.sha256(data).hexdigest()
    relative = media_relative_path(digest, ext)

    existing = db.get(MediaAsset, digest)
    if existing is not None:
        # 命中去重：一套模板图被 50 道题引用，磁盘上只有一份。
        # 不写审计——这既不是新内容进入系统，也不是一次外泄。
        return _payload(existing)

    root = Path(settings.media_upload_root).resolve()
    target = (root / relative).resolve()
    if root not in target.parents:
        raise HTTPException(500, "图片存储目录配置无效。")
    target.parent.mkdir(parents=True, exist_ok=True)
    # 先写临时文件再 replace：直接写目标路径的话，写到一半进程挂了会留下一个
    # 大小对不上的半张图，而它的文件名是哈希——看起来完全正常，永远不会被重传覆盖。
    temporary = target.with_suffix(f"{target.suffix}.part")
    try:
        temporary.write_bytes(data)
        temporary.replace(target)
    except OSError as exc:
        temporary.unlink(missing_ok=True)
        raise HTTPException(500, "图片写入失败。") from exc

    asset = MediaAsset(sha256=digest, ext=ext, byte_size=len(data), width=width, height=height,
                       uploaded_by=admin.id)
    db.add(asset)
    audit(db, settings, "problem_media_upload", "success", client_ip(request), admin.id,
          resource_type="media", resource_id=None,
          summary={"sha256": digest, "ext": ext, "byte_size": len(data), "width": width, "height": height})
    try:
        db.commit()
    except Exception:
        # 库写失败就把刚落的文件收走，别留孤儿。反过来（先库后文件）不能接受：
        # 那会得到"库里有行但文件不存在"，题干直接图裂。
        db.rollback()
        target.unlink(missing_ok=True)
        raise
    return _payload(asset)


def _payload(asset: MediaAsset) -> dict:
    return {
        "url": f"/media/{media_relative_path(asset.sha256, asset.ext)}",
        "sha256": asset.sha256, "width": asset.width, "height": asset.height,
        "byte_size": asset.byte_size,
    }


# ---------- 课包封面上传（独立存储区域） ----------


def _store_course_cover(db, settings, request, admin, raw: bytes) -> dict:
    """封面上传的公共步骤：解码 → 重编码 → 内容寻址落盘 → 登记 CourseCover。

    与题干配图共用 _decode / _normalize（封面同样要剥 EXIF、压尺寸），只是
    落盘根目录与登记表不同——两者必须一致地使用 course_cover_upload_root，
    绝不能混进 data/media。
    """
    image, fmt = _decode(raw)
    try:
        data, ext, _save_format, width, height = _normalize(image, fmt, settings.media_max_dimension)
    except OSError as exc:
        raise HTTPException(400, "图片处理失败，请换一张或另存为 PNG 后重试。") from exc
    finally:
        image.close()

    digest = hashlib.sha256(data).hexdigest()
    relative = course_cover_relative_path(digest, ext)

    existing = db.get(CourseCover, digest)
    if existing is not None:
        # 命中去重：同一张封面被多个课包引用，磁盘上只有一份。不写审计。
        return _course_cover_payload(existing)

    root = Path(settings.course_cover_upload_root).resolve()
    target = (root / relative).resolve()
    if root not in target.parents:
        raise HTTPException(500, "封面存储目录配置无效。")
    target.parent.mkdir(parents=True, exist_ok=True)
    # 先写临时文件再 replace：与题干配图同一套写法，防止进程中断留下"看起来正常"的半张图。
    temporary = target.with_suffix(f"{target.suffix}.part")
    try:
        temporary.write_bytes(data)
        temporary.replace(target)
    except OSError as exc:
        temporary.unlink(missing_ok=True)
        raise HTTPException(500, "封面写入失败。") from exc

    asset = CourseCover(sha256=digest, ext=ext, byte_size=len(data), width=width, height=height,
                        uploaded_by=admin.id)
    db.add(asset)
    audit(db, settings, "course_cover_upload", "success", client_ip(request), admin.id,
          resource_type="course_cover", resource_id=None,
          summary={"sha256": digest, "ext": ext, "byte_size": len(data), "width": width, "height": height})
    try:
        db.commit()
    except Exception:
        db.rollback()
        target.unlink(missing_ok=True)
        raise
    return _course_cover_payload(asset)


def _course_cover_payload(asset: CourseCover) -> dict:
    return {
        "url": f"/course-covers/{course_cover_relative_path(asset.sha256, asset.ext)}",
        "sha256": asset.sha256, "width": asset.width, "height": asset.height,
        "byte_size": asset.byte_size,
    }


@router.post("/course-covers", status_code=201)
async def upload_course_cover(request: Request, file: UploadFile = File(...),
                              db: Session = Depends(db_session)):
    require_csrf(request)
    admin = current_admin(request, db)
    if not _is_editor(admin):
        raise HTTPException(403, "没有上传封面的权限。")
    # 封面是低频操作（一个课包一张），比题干配图收紧：12 次 / 5 分钟。
    limit(request, "admin-course-cover-upload", client_ip(request), 12, 300)

    settings = request.app.state.settings
    raw = await file.read(settings.media_max_bytes + 1)
    if len(raw) > settings.media_max_bytes:
        raise HTTPException(413, f"封面不能超过 {settings.media_max_bytes // (1024 * 1024)} MB。")
    if not raw:
        raise HTTPException(400, "上传内容为空。")
    return _store_course_cover(db, settings, request, admin, raw)
