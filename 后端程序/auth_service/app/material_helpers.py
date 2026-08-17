"""资料模块共享工具：MIME/类型推断、路径安全校验、对象哈希、目录工具。

供 admin_materials（普通上传）与 admin_material_imports（文件夹迁移）复用，
避免两处各自抄一份推断与校验逻辑。S3 客户端一律由调用方延迟导入
（``from ..s3_multipart import get_minio_client``），本文件不直接依赖 boto3。
"""
from __future__ import annotations

import hashlib
import re
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import MaterialFolder

# S3 Multipart 协议要求除最后一片外每片 ≥ 5MB，因此小于该阈值的文件不能走
# multipart，必须整文件 presigned PUT。这是协议硬限制，不是可配置项。
MULTIPART_MIN_BYTES = 5 * 1024 * 1024

_CLIENT_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")

# 扩展名 → (mime, asset_type)。未知扩展名回落 application/octet-stream / other。
# MIME 由服务端重新判断（交接文档 §8：不信任浏览器上报），asset_type 供类型筛选。
_EXT_MAP: dict[str, tuple[str, str]] = {
    # 图片
    "png": ("image/png", "image"), "jpg": ("image/jpeg", "image"), "jpeg": ("image/jpeg", "image"),
    "gif": ("image/gif", "image"), "webp": ("image/webp", "image"), "bmp": ("image/bmp", "image"),
    "svg": ("image/svg+xml", "image"), "ico": ("image/x-icon", "image"), "avif": ("image/avif", "image"),
    # 视频
    "mp4": ("video/mp4", "video"), "webm": ("video/webm", "video"), "mov": ("video/quicktime", "video"),
    "mkv": ("video/x-matroska", "video"), "avi": ("video/x-msvideo", "video"),
    # 音频
    "mp3": ("audio/mpeg", "audio"), "wav": ("audio/wav", "audio"), "ogg": ("audio/ogg", "audio"),
    "m4a": ("audio/mp4", "audio"), "flac": ("audio/flac", "audio"), "aac": ("audio/aac", "audio"),
    # 文档
    "pdf": ("application/pdf", "document"), "doc": ("application/msword", "document"),
    "docx": ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", "document"),
    "xls": ("application/vnd.ms-excel", "document"),
    "xlsx": ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "document"),
    "ppt": ("application/vnd.ms-powerpoint", "document"),
    "pptx": ("application/vnd.openxmlformats-officedocument.presentationml.presentation", "document"),
    "txt": ("text/plain", "document"), "md": ("text/markdown", "document"),
    "csv": ("text/csv", "document"),
    # 压缩包
    "zip": ("application/zip", "archive"), "rar": ("application/vnd.rar", "archive"),
    "7z": ("application/x-7z-compressed", "archive"), "tar": ("application/x-tar", "archive"),
    "gz": ("application/gzip", "archive"),
}


def infer_mime(filename: str) -> tuple[str, str]:
    """按扩展名推断 (mime, asset_type)。服务端权威口径，不信任前端上报。"""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return _EXT_MAP.get(ext, ("application/octet-stream", "other"))


def sanitize_display_name(name: str) -> str:
    """清洗用户可见文件名：去路径分隔符与控制字符，限制长度。"""
    cleaned = _CONTROL_RE.sub("", name.replace("\\", "/").rsplit("/", 1)[-1]).strip()
    if not cleaned:
        raise ValueError("文件名不能为空。")
    if len(cleaned) > 255:
        raise ValueError("文件名过长。")
    return cleaned


def safe_relative_path(path: str) -> str:
    """校验并规范化迁移清单里的相对路径（Windows webkitRelativePath）。

    规则：只接受正斜杠相对路径；任一段不能是空、`.`、`..`；不能含控制字符。
    反斜杠统一转正斜杠（Windows 浏览器给的是反斜杠分隔的相对路径）。
    返回规范化后的正斜杠路径，非法时抛 ValueError（附中文原因）。
    """
    if not path or len(path) > 1024:
        raise ValueError("路径为空或过长。")
    normalized = path.replace("\\", "/")
    if _CONTROL_RE.search(normalized):
        raise ValueError("路径包含控制字符。")
    segments = normalized.split("/")
    if segments[0] == "" or segments[-1] == "":
        raise ValueError("路径不能以斜杠开头或结尾。")
    for segment in segments:
        if segment in ("", ".", ".."):
            raise ValueError("路径包含非法段。")
    return normalized


def validate_client_id(client_id: str) -> None:
    if not _CLIENT_ID_RE.match(client_id):
        raise ValueError("条目 ID 只能包含字母、数字、下划线或连字符。")


def asset_object_key(admin_id: int, filename: str) -> str:
    """普通上传的对象 key：按 管理员/年/月 分目录，uuid 防枚举与覆盖。

    原始文件名不进 key（隐私 + 防路径冲突）；扩展名保留用于类型推断。
    """
    now = datetime.now(UTC)
    stem = uuid.uuid4().hex
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
    return f"materials/admin-{admin_id}/{now:%Y/%m}/{stem}.{ext}"


def import_object_key(session_id: int, client_id: str, filename: str) -> str:
    """迁移导入的对象 key：按会话 + 客户端稳定 ID 组织，断点续传可回溯。"""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
    return f"materials/import-{session_id}/{client_id}.{ext}"


def compute_object_sha256(client, bucket: str, key: str) -> tuple[str, int]:
    """从对象存储下载对象，流式计算 SHA-256（不落盘），返回 (hex, 实际字节数)。

    这是资料去重的唯一可信依据（交接文档 §5：不以文件名、大小或浏览器自报值为准）。
    用 read() 而非 iter_chunks()：boto3 StreamingBody 与测试用的 BytesIO 都支持，
    避免实现被测试替身的接口形状绑架。
    """
    resp = client.get_object(Bucket=bucket, Key=key)
    body = resp["Body"]
    digest = hashlib.sha256()
    size = 0
    try:
        while True:
            chunk = body.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
            size += len(chunk)
    finally:
        body.close()
    return digest.hexdigest(), size


def find_or_create_folder(db: Session, parent_id: int | None, name: str) -> MaterialFolder:
    """在指定父目录下按名查找目录，不存在则创建（迁移建目录层级用，幂等）。

    注意 PostgreSQL 不认 `col IS 1`：非空 parent_id 必须用 == 而非 is_。
    """
    parent_cond = MaterialFolder.parent_id.is_(None) if parent_id is None else MaterialFolder.parent_id == parent_id
    existing = db.scalar(
        select(MaterialFolder).where(parent_cond, MaterialFolder.name == name)
    )
    if existing is not None:
        return existing
    folder = MaterialFolder(parent_id=parent_id, name=name)
    db.add(folder)
    db.flush()
    return folder
