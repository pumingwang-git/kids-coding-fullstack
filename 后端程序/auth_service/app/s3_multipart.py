"""MinIO / S3 直传与预签名。

职责：
1. 分片上传（S3 Multipart）：create / presign-part / complete / abort。
   服务端只用专用账号（app_uploader）签发每片预签名 URL，文件字节由浏览器直传 MinIO，
   应用不下载、不缓存源文件。complete 时由服务端用 upload_id 向 MinIO 列 parts 核对，
   不信任前端自报的 ETag。
2. 资料的短期预签名 GET URL（presign_material_get）。
3. 播放授权时长（play_token_minutes）。**播放地址的签名不在这里**——见
   app/video_sign.py（P2-5：稳定 URL + query 签名，由 nginx 在边缘校验）。

boto3 延迟导入：时长计算不依赖 MinIO，即使未装 boto3 应用也能正常加载（便于渐进接入）。
"""
from __future__ import annotations

import math
import time

from .config import Settings


def get_minio_client(settings: Settings):
    """用应用专用账号建一个 boto3 S3 客户端（指向 MinIO 的 S3 兼容 API）。"""
    import boto3
    from botocore.client import Config

    return boto3.client(
        "s3",
        endpoint_url=settings.minio_endpoint,
        aws_access_key_id=settings.minio_access_key,
        aws_secret_access_key=settings.minio_secret_key,
        use_ssl=settings.minio_use_ssl,
        config=Config(
            signature_version="s3v4",
            retries={"max_attempts": 3},
            s3={"addressing_style": "path"},
        ),
    )


def get_public_minio_client(settings: Settings):
    """用 minio_public_endpoint 建一个 boto3 S3 client（交接文档 17 批次1 S1-1b）。

    给学生端签预签名 GET URL 必须用这个，**不能用 get_minio_client**——S3v4 签名把
    Host 签进去了，用内网 endpoint 签出来的 URL 浏览器换个域名访问会直接 403。

    未配 minio_public_endpoint 时返回 None，调用方据此退回应用代理模式。
    use_ssl 按 public_endpoint 的 scheme 推导，不复用 minio_use_ssl——两者常常不同
    （应用走内网 http、浏览器走 nginx 反代的 https 是生产常态）。
    """
    if not settings.minio_public_endpoint:
        return None
    import boto3
    from botocore.client import Config

    endpoint = settings.minio_public_endpoint
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=settings.minio_access_key,
        aws_secret_access_key=settings.minio_secret_key,
        use_ssl=endpoint.startswith("https"),
        config=Config(
            signature_version="s3v4",
            retries={"max_attempts": 3},
            s3={"addressing_style": "path"},
        ),
    )


def presign_material_get(settings, bucket: str, key: str, *,
                         filename: str, disposition: str, expires: int) -> str:
    """给学生端签一个短期 GET URL（交接文档 17 批次1 S1-1）。

    disposition: "inline"（预览）或 "attachment"（下载）。
    文件名走 ResponseContentDisposition 参数，中文名用 RFC 5987 双写法不丢（和
    _proxy_material_stream 里的 header 写法逐字一致）。
    ⚠️ 必须用 public 端点的 client 签名，理由见 get_public_minio_client。
    未配 public_endpoint 时返回 None，调用方退回代理模式。

    URL 复用（2026-08-12）：同一 (bucket, key, disposition, expires) 在签名有效期的
    80% 内返回同一个 URL。boto3 每次签名都带当前时间（X-Amz-Date），直接签的话同
    一 PDF 每次 inline 请求 URL 都不同，浏览器 HTTP 缓存永远 miss、重复下载大文件。
    复用后 URL 稳定 → 浏览器 memory/disk 缓存或 304 命中。安全边界不变：URL 有效期
    仍由 expires（短 TTL）控制，泄露了也只是在 TTL 内可访问。
    """
    from urllib.parse import quote

    client = get_public_minio_client(settings)
    if client is None:
        return None
    fallback = filename.encode("ascii", "ignore").decode() or "download"
    cd = f"{disposition}; filename=\"{fallback}\"; filename*=UTF-8''{quote(filename)}"

    ck = _presign_cache_key(bucket, key, cd, expires)
    now = time.time()
    hit = _presign_cache.get(ck)
    # 缓存窗口 = expires * 0.8：URL 快过期就重签，避免浏览器缓存里还活着、签名已失效
    if hit and now - hit[1] < hit[2] * _PRESIGN_TTL_RATIO:
        return hit[0]

    url = client.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": key, "ResponseContentDisposition": cd},
        ExpiresIn=expires,
    )
    _presign_cache[ck] = (url, now, expires)
    if len(_presign_cache) > 128:  # 防御性清理：只删已过缓存窗口的条目
        for k, (_, t, e) in list(_presign_cache.items()):
            if now - t >= e * _PRESIGN_TTL_RATIO:
                _presign_cache.pop(k, None)
    return url


# 预签名 URL 复用缓存：key -> (url, signed_at, expires)。
# 进程内模块级缓存即可——多 worker 各自缓存只会多签一次，不影响正确性；
# 条目是 URL 字符串，占用极小，超 128 条才清理。
_presign_cache: dict[str, tuple[str, float, int]] = {}
_PRESIGN_TTL_RATIO = 0.8


def _presign_cache_key(bucket: str, key: str, cd: str, expires: int) -> str:
    # \x1f 是 ASCII 单元分隔符，避免 bucket/key/cd/expires 拼接歧义
    return f"{bucket}\x1f{key}\x1f{cd}\x1f{expires}"


# ----------------------------- 分片上传 -----------------------------

def create_multipart_upload(client, bucket: str, key: str, content_type: str) -> str:
    resp = client.create_multipart_upload(Bucket=bucket, Key=key, ContentType=content_type)
    return resp["UploadId"]


def presign_upload_part(client, bucket: str, key: str, upload_id: str, part_number: int, expires: int = 3600) -> str:
    return client.generate_presigned_url(
        "upload_part",
        Params={"Bucket": bucket, "Key": key, "UploadId": upload_id, "PartNumber": part_number},
        ExpiresIn=expires,
    )


def list_uploaded_parts(client, bucket: str, key: str, upload_id: str) -> list[dict]:
    """向 MinIO 列已传 parts（自动翻页），返回 [{PartNumber, ETag}, ...]。

    complete 时用它核对前端自报的 ETag，避免「前端说传完了但其实没传全」就完成合并。
    """
    parts: list[dict] = []
    marker = 0
    while True:
        resp = client.list_parts(Bucket=bucket, Key=key, UploadId=upload_id, PartNumberMarker=marker)
        parts.extend(
            {"PartNumber": p["PartNumber"], "ETag": p["ETag"]}
            for p in resp.get("Parts", [])
        )
        if not resp.get("IsTruncated"):
            break
        marker = resp["NextPartNumberMarker"]
    return parts


def complete_multipart_upload(client, bucket: str, key: str, upload_id: str, parts: list[dict]) -> None:
    ordered = sorted(parts, key=lambda p: p["PartNumber"])
    client.complete_multipart_upload(
        Bucket=bucket,
        Key=key,
        UploadId=upload_id,
        MultipartUpload={
            "Parts": [{"PartNumber": p["PartNumber"], "ETag": p["ETag"]} for p in ordered]
        },
    )


def abort_multipart_upload(client, bucket: str, key: str, upload_id: str) -> None:
    client.abort_multipart_upload(Bucket=bucket, Key=key, UploadId=upload_id)


def delete_object(client, bucket: str, key: str) -> None:
    """删除单个对象（解析视频/资料「彻底删除」时回收源桶与播放桶的产物）。

    删除失败**不抛异常**：对象存储不可达时，宁可留下孤儿对象（由运维定期清理），
    也不能让「删一条记录」变成 500——库里删干净了，学生端/管理端立刻不可见，
    孤儿对象不泄露任何权限（桶是私有的，访问仍要过应用签名）。
    """
    try:
        client.delete_object(Bucket=bucket, Key=key)
    except Exception:
        pass


# ----------------------- 播放授权时长 -----------------------
# 签名本身搬到 app/video_sign.py（P2-5：稳定 URL + query 签名，nginx 边缘校验）。
# 原先的「路径前缀令牌」mint_play_token / verify_play_token 已随之删除——
# 留着一套并行的、没人调用的鉴权原语，只会等着被误用。


def play_token_minutes(duration_seconds: int | None, default_minutes: int) -> int:
    """播放授权时长（分钟）：视频时长 + 10 分钟，clamp 到 [60, 240]。

    口径（2026-08-09 拍板）：短期授权，下架只阻止**新签发**、已签发的自然过期。
    TTL 按视频时长伸缩——时长未知（转码中/未填）回落默认值，
    短视频至少 1 小时，超长视频封顶 4 小时（避免一次播放中途失效）。
    实际过期时刻还会被 video_sign.quantized_deadline 对齐到时间片，只会更长不会更短。
    """
    if not duration_seconds or duration_seconds <= 0:
        return max(60, min(240, default_minutes or 60))
    minutes = math.ceil(duration_seconds / 60) + 10
    return max(60, min(240, minutes))
