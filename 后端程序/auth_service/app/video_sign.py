"""视频播放的「稳定 URL + query 签名」（P2-5，三代：边缘鉴权）。

## 为什么换掉路径里的令牌

旧方案把令牌放在路径里：``/v/{token}/{video_id}/master.m3u8``。两个后果：

1. **字节全过应用**——令牌只有 FastAPI 认得，nginx 无法在边缘校验，每一片 .ts 都要
   经 uvicorn 转发一遍，线程和带宽双倍消耗（交接文档 17 §3.1 的「一代」）。
2. **缓存永远不命中**——每次进课时重签一次，token 一变整条路径全变，浏览器按完整
   URL 匹配缓存，master.m3u8 和每个切片都成了新地址。

改成 B 站 / 腾讯视频那套：**路径稳定，签名放 query，校验下沉到边缘**。

    /v/12/720p/seg_00001.ts?e=1786000000&u=37&s=Xk3q...

- 路径 ``/v/{video_id}/{相对路径}`` 与对象键 ``video-{video_id}/{相对路径}`` 一一对应，
  nginx 一条 rewrite 就能直连 MinIO，不需要查库；
- ``e`` 过期时间、``u`` 用户 id、``s`` 签名。三者少一个都不放行。

## 签名格式：nginx secure_link 原生格式

    s = base64url( md5( "{e}{uri}{u} {secret}" ) )        # 去掉 '=' 填充

对应 nginx（``ngx_http_secure_link_module``，见 部署配置/nginx-cache.conf）：

    secure_link      $arg_s,$arg_e;
    secure_link_md5  "$secure_link_expires$uri$arg_u {secret}";

用 nginx 原生格式而不是阿里云 A 类 / 腾讯云 typeA 的十六进制 ``auth_key``，是因为边缘
就是自建 nginx：原生格式零模块零脚本即可校验。协议形状（稳定路径 + query 签名 +
边缘校验）与各家 CDN 完全一致，将来真上 CDN 只需把 :func:`sign` 换成厂商的拼接口径
（阿里云 A 类：``auth_key={t}-{rand}-{uid}-{md5hex}``；腾讯云 typeA 同构），
**校验位置和播放器都不用动**。

## deadline 量化：让浏览器缓存真的命中

签名在 query 有个人所共知的代价：浏览器缓存键包含 query，``e`` 每次不同 → URL 每次
不同 → 跨刷新照样重下。B 站靠 CDN 侧「缓存键忽略签名参数」拿边缘命中率，但用户侧
省不掉。

这里多做一步：**把 e 对齐到固定时间片**（:data:`BUCKET_SECONDS`）。同一个用户、同一个
视频，在同一个时间片内算出的 ``e`` 完全相同 → 整条 URL 逐字节相同 → F5 之后浏览器
磁盘缓存直接命中，切片不再重下。代价是有效期最多比申请的 TTL 多出一个时间片，
上限可控（见 :func:`quantized_deadline`）。
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import time

# 时间片长度。同一时间片内签出的 URL 逐字节相同（浏览器缓存据此命中）。
# 取 30 分钟：太短则缓存窗口太窄，太长则过期时间被放宽得多。
BUCKET_SECONDS = 1800


def quantized_deadline(ttl_seconds: int, now: float | None = None) -> int:
    """把过期时刻对齐到时间片边界，返回 epoch 秒。

    保证两件事：

    - **有效期不短于 ttl_seconds**——绝不会因为量化让令牌比申请的更早失效；
    - **同一时间片内取值恒定**——``now`` 落在同一个 BUCKET 内算出的结果相同，
      这正是 URL 能稳定、浏览器缓存能命中的原因。

    实际有效期落在 ``[ttl, ttl + 2 * BUCKET)``，即最多比申请的多给一小时。
    这是拿「多给不超过一个时间片的宽限」换「跨刷新缓存命中」，是本方案的核心取舍。
    """
    now = int(now if now is not None else time.time())
    slices = -(-max(ttl_seconds, 0) // BUCKET_SECONDS)  # 向上取整
    return (now // BUCKET_SECONDS + slices + 1) * BUCKET_SECONDS


def _digest(secret: str, expires: int, uri: str, uid: str) -> str:
    """nginx secure_link_md5 的等价实现。

    待签串必须与 nginx 里 ``secure_link_md5`` 的拼接**逐字符一致**：
    ``{expires}{uri}{uid} {secret}``（uid 与 secret 之间有一个空格，抄 nginx 官方示例的
    习惯写法）。``uri`` 用 nginx 的 ``$uri``——已解码、已规范化，不含 query。
    我们的对象路径全是 ASCII（video-12/720p/seg_00001.ts），不存在编码歧义。
    """
    raw = f"{expires}{uri}{uid} {secret}".encode()
    digest = hashlib.md5(raw).digest()  # noqa: S324 - 与 nginx secure_link 对齐，非口令哈希
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


def sign(secret: str, uri: str, uid: str | int, expires: int) -> str:
    """算出 ``s`` 参数的值。``uri`` 是不含 query 的绝对路径（以 / 开头）。"""
    return _digest(secret, expires, uri, str(uid))


def signed_query(secret: str, uri: str, uid: str | int, expires: int) -> str:
    """拼出完整 query 串（不含前导 ``?``），顺序固定便于比对与缓存键配置。"""
    return f"e={expires}&u={uid}&s={sign(secret, uri, uid, expires)}"


def signed_url(secret: str, uri: str, uid: str | int, expires: int) -> str:
    return f"{uri}?{signed_query(secret, uri, uid, expires)}"


def stream_uri(video_id: int | str, path: str) -> str:
    """播放路径的唯一构造口径：``/v/{video_id}/{path}``。

    与对象键 ``video-{video_id}/{path}``（桶 = settings.minio_play_bucket）一一对应——
    这是 nginx 能不查库直连 MinIO 的前提，见 部署配置/nginx-cache.conf 的 rewrite。
    转码产物布局由 tasks/transcode.py 保证：master 在 ``video-{id}/`` 根，
    各档 ``video-{id}/{档}/index.m3u8``，切片 ``video-{id}/{档}/seg_%05d.ts``。
    """
    return f"/v/{video_id}/{path.lstrip('/')}"


def playback_urls(secret: str, video_id: int, uid: str | int, resolutions: list[str],
                  ttl_seconds: int, now: float | None = None) -> dict:
    """签发一次播放会话的全部入口 URL（学生端与后台预览共用一份口径）。

    只签 master 与各档 playlist：**切片 URL 不在这里签**——它们由
    routers/video_play 在改写 m3u8 时逐条签，沿用同一个 ``e``/``u``，
    这样整条会话的地址在一个时间片内保持稳定。
    """
    expires = quantized_deadline(ttl_seconds, now=now)
    master = stream_uri(video_id, "master.m3u8")
    return {
        "master_playlist": signed_url(secret, master, uid, expires),
        "expires_in_seconds": max(0, expires - int(now if now is not None else time.time())),
        "variants_urls": {
            r: signed_url(secret, stream_uri(video_id, f"{r}/index.m3u8"), uid, expires)
            for r in resolutions
        },
    }


def verify(secret: str, uri: str, uid: str | None, expires: str | int | None,
           signature: str | None, now: float | None = None) -> bool:
    """校验签名 + 过期。三者任一不满足即 False。

    应用内也要校验（不能只靠 nginx）：开发环境没有 nginx，且生产上 ``.m3u8`` 是由应用
    出的——边缘校验过一遍、应用再校验一遍，是纵深防御，不是重复劳动。
    """
    if not signature or expires is None or uid is None:
        return False
    try:
        expires_i = int(expires)
    except (TypeError, ValueError):
        return False
    expected = _digest(secret, expires_i, uri, str(uid))
    # 先比签名再看过期：顺序不影响安全性，但保证签名比较始终是常量时间的。
    if not hmac.compare_digest(expected, signature):
        return False
    return expires_i >= int(now if now is not None else time.time())
