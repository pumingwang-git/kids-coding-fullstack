"""学生端视频播放：课时权限校验 + 稳定 URL + query 签名（P2-5，三代边缘鉴权）。

设计（B 站 / 腾讯视频同款形状，见 app/video_sign.py 的完整推导）：
- 学生 POST /api/lessons/{lesson_id}/play 过权限校验后，服务端不再签「路径令牌」，
  而是签一组**稳定地址 + query 签名**：``/v/{video_id}/master.m3u8?e=..&u=..&s=..``。
- 路径 ``/v/{video_id}/{相对路径}`` 与对象键 ``video-{video_id}/{相对路径}`` 一一对应，
  **生产环境由 nginx 用 secure_link 在边缘校验后直连 MinIO 发字节**，切片不进 FastAPI
  （部署配置/nginx-cache.conf）。开发环境没有 nginx，本文件的 stream 兜底发字节，
  行为一致、可单测。
- HLS 的坑：播放器不会把 master 的 query 继承到子列表和切片上。所以 ``.m3u8``
  **必须由应用改写**——把每条子 URI 补上签名（沿用同一个 e/u）。播放列表很小、
  一次会话只有两三个，交给应用完全划得来；真正的字节（.ts）全部走边缘。

说明：
- 课时视频的**权威绑定**是 course_lessons.video_id（后台课时编辑器写这一列），
  不读 Video.lesson_id（旧逻辑引用，历史数据，不建 FK）。见 models.CourseLesson 注释。
- 门控规则统一在 `app/course_access.py`（课包已发布 → 试看或已开通；开通资格尚未落地，
  非试看课时 deny by default）。本文件只做 lesson_id → 对象的解析，不复制规则。
- 旧的 ``/v/{token}/{video_id}/{path}`` 路径令牌已**整体下线**：两种形状在同一前缀下
  无法无歧义共存（``/v/12/720p/index.m3u8`` 既像新式也像旧式）。发版瞬间正在播的会话
  会收到一次 403，播放器的 error → renew 分支会重签换源，代价是一次重新缓冲。
"""
from __future__ import annotations

import mimetypes
import posixpath
import re
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import video_sign
from ..course_access import Access, course_visible, lesson_access, lesson_block_open
from ..models import Course, CourseLesson, CourseLessonBlock, LessonVideoBlock, Video, VideoVariant
from ..s3_multipart import get_minio_client, play_token_minutes
from .auth_secure import current_user, db_session, require_csrf

router = APIRouter(prefix="/api", tags=["video-play"])
# 播放流走独立的 /v 前缀：生产上这一整段由 nginx 接管，只有 .m3u8 回源到这里。
play_router = APIRouter(prefix="/v", tags=["video-play-stream"])


class PlayPayload(BaseModel):
    """课时内视频块的播放指定（可选）。

    内容块模型下，一节课时可以有多个视频块。不传 block_id 时保持旧行为：
    播放 course_lessons.video_id 绑定的单视频（旧字段兜底，见交接文档 §5.3）。
    """

    block_id: int | None = None


@router.post("/lessons/{lesson_id}/play")
def mint_play_url(request: Request, lesson_id: int, db: Session = Depends(db_session),
                  payload: PlayPayload | None = None):
    require_csrf(request)
    user = current_user(request, db)
    lesson = db.get(CourseLesson, lesson_id)
    if lesson is None:
        raise HTTPException(404, "课时不存在。")
    if not course_visible(db.get(Course, lesson.course_id)):
        raise HTTPException(404, "课时不存在。")
    settings = request.app.state.settings

    # 门控规则只在 app/course_access.py 一份：课时级（整节开放）+ 块级（前 N 块试看）。
    # 不要把规则抄回这里：它将来会被 enrollments / 学习有效期 / 解锁规则改写。
    lesson_granted = lesson_access(db, user, lesson) is Access.GRANTED

    # 权威视频解析：优先内容块（block_id 指定），旧字段兜底 lesson.video_id。
    # 学生端 DTO 不下发 video_id，这里必须校验 block 属于该课时、且是平台视频块，
    # 不给「用任意 video_id 换令牌」的坐标。
    if payload is not None and payload.block_id is not None:
        block = db.get(CourseLessonBlock, payload.block_id)
        if block is None or block.lesson_id != lesson_id or block.block_type != "video":
            raise HTTPException(404, "该课时没有指定的视频块。")
        vd = db.get(LessonVideoBlock, block.id)
        if vd is None or vd.source_type != "platform" or vd.video_id is None:
            raise HTTPException(404, "该视频块未绑定平台视频。")
        # 逐块门控：整节开放，或「试看前 N 块」策略命中该块，才能拿播放令牌
        if not (lesson_granted or lesson_block_open(db, user, lesson, block.sort_order)):
            raise HTTPException(403, "你还没有该课时的播放权限。")
        video_id = vd.video_id
    else:
        if not lesson_granted:
            raise HTTPException(403, "你还没有该课时的播放权限。")
        video_id = lesson.video_id
        if video_id is None:
            raise HTTPException(404, "该课时未绑定视频。")
    video = db.get(Video, video_id)
    if video is None or video.status != "ready":
        raise HTTPException(404, "该课时暂无可播放视频，或仍在转码中。")
    variant: VideoVariant | None = (
        db.get(VideoVariant, video.primary_variant_id) if video.primary_variant_id else None
    )
    # primary 档必须是 HLS 产物（master.m3u8），与后台预览同一判断口径。
    if (
        variant is None
        or variant.status != "ready"
        or not variant.object_key.endswith("master.m3u8")
    ):
        raise HTTPException(404, "该课时暂无可播放视频，或仍在转码中。")

    ttl_minutes = play_token_minutes(video.duration_seconds, settings.video_token_minutes)
    variant_rows = db.scalars(
        select(VideoVariant)
        .where(VideoVariant.video_id == video.id, VideoVariant.status == "ready")
        .order_by(VideoVariant.bitrate_kbps.asc())
    ).all()
    return build_play_response(settings, video.id, user.id, variant_rows, ttl_minutes)


def build_play_response(settings, video_id: int, uid: int, variant_rows, ttl_minutes: int) -> dict:
    """学生端与后台预览共用的播放响应构造（口径只此一份）。

    ``expires_in_seconds`` 是**量化后**的真实剩余寿命，不是 ttl_minutes * 60——
    播放器靠它决定何时续签，必须如实告知（见 video_sign.quantized_deadline）。
    """
    signed = video_sign.playback_urls(
        settings.minio_play_secret,
        video_id,
        uid,
        [v.resolution for v in variant_rows],
        ttl_minutes * 60,
    )
    return {
        "master_playlist": signed["master_playlist"],
        "expires_in_seconds": signed["expires_in_seconds"],
        "variants": [
            {
                "resolution": v.resolution,
                "bitrate_kbps": v.bitrate_kbps,
                "playlist_url": signed["variants_urls"][v.resolution],
            }
            for v in variant_rows
        ],
    }


def _content_type(path: str, fallback: str) -> str:
    # 先按扩展名定类型：Windows mimetypes 会把 .ts 映射成 video/vnd.dlna.mpeg-tts
    # （DLNA 私有类型），HLS 切片必须用标准 video/mp2t。
    if path.endswith(".m3u8"):
        return "application/vnd.apple.mpegurl"
    if path.endswith(".ts"):
        return "video/mp2t"
    guessed, _ = mimetypes.guess_type(path)
    if guessed:
        return guessed
    return fallback or "application/octet-stream"


# Range: bytes=start-end 解析。HLS 客户端有时会发 Range（seek/部分拉取）；
# 后端流式代理支持后返回 206，行为与静态文件服务器一致。
def _parse_range(range_header: str | None):
    if not range_header:
        return None
    match = re.match(r"bytes=(\d*)-(\d*)$", range_header.strip())
    if not match:
        return None
    start_s, end_s = match.groups()
    start = int(start_s) if start_s else 0
    end = int(end_s) if end_s else None
    return start, end


# m3u8 里除了裸的 URI 行，还有 #EXT-X-KEY / #EXT-X-MAP 这类带 URI="..." 属性的标签。
# 当前转码产物（tasks/transcode.py，未开加密、TS 切片）两者都不会出现，但加密一旦启用
# 就会多出 #EXT-X-KEY，漏签会让整条流解不出来——一并处理，成本只有一个正则。
_M3U8_URI_ATTR = re.compile(r'(URI=")([^"]+)(")')


def _rewrite_playlist(text: str, base_uri: str, secret: str, uid: str, expires: int) -> str:
    """给播放列表里每条子 URI 补上签名。

    播放器**不会**把 master 上的 query 继承给子列表和切片（HLS 里 URI 是按 RFC 3986
    相对解析的，query 不参与继承），所以必须在这里逐条改写。沿用调用方带进来的
    ``e``/``u``——整条会话共用一个过期时刻，配合 video_sign 的时间片量化，
    同一时间片内刷新页面拿到的地址逐字节相同，浏览器缓存才能命中。

    绝对 URL（http:// 开头，比如将来外链的备用源）原样放过：签名只覆盖自家路径。
    """
    base_dir = posixpath.dirname(base_uri)

    def sign_child(ref: str) -> str:
        if ref.startswith(("http://", "https://", "//")):
            return ref
        child = posixpath.normpath(posixpath.join(base_dir, ref))
        return video_sign.signed_url(secret, child, uid, expires)

    out = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            out.append(line)
        elif stripped.startswith("#"):
            out.append(_M3U8_URI_ATTR.sub(lambda m: m.group(1) + sign_child(m.group(2)) + m.group(3),
                                          line))
        else:
            out.append(sign_child(stripped))
    return "\n".join(out) + "\n"


def _segment_cache_control(expires: int) -> str:
    """切片的缓存指令：缓存到签名过期为止，封顶一天。

    - ``immutable``：切片是转码产物，生成后永不变更。告诉浏览器别发条件请求，
      省掉每片一次 304 往返——一节课几百片，这个往返数很可观。
    - max-age 取「签名剩余寿命」而不是一个固定大数：签名一过期，播放器就会重签并换到
      新一批地址，旧地址的缓存条目再也不会被查到，留着只是白占磁盘配额（浏览器缓存
      是有总量上限的，撑爆了会把**还有用的**条目挤出去）。
    - ``private``：地址按 uid 签，内容虽与用户无关，但不能进任何共享缓存。

    生产上这条头由 nginx 发（见 部署配置/nginx-cache.conf 5b-②，那里给的是固定
    86400——nginx 算不了剩余寿命，且边缘那层本就有独立的淘汰策略）。这里是开发环境
    与无 secure_link 兜底时的口径。
    """
    remaining = max(0, expires - int(time.time()))
    return f"private, max-age={min(remaining, 86400)}, immutable"


def _playlist_response(client, settings, key: str, uri: str, uid: str, expires: int) -> Response:
    """取回 m3u8 并把子 URI 逐条签名后返回。

    整读进内存是安全的：播放列表是文本，一档几十 KB 封顶（VOD 切片 6 秒一片，
    两小时的课也就一千多行）。真正大的是 .ts，那些走流式（或者根本不进这个进程）。
    """
    try:
        obj = client.get_object(Bucket=settings.minio_play_bucket, Key=key)
    except Exception:
        raise HTTPException(404, "对象不存在或存储暂不可用。")
    body = obj["Body"]
    raw = body.read() if hasattr(body, "read") else b"".join(body)
    text = _rewrite_playlist(
        raw.decode("utf-8"), uri, settings.minio_play_secret, uid, expires,
    )
    return Response(
        content=text,
        media_type="application/vnd.apple.mpegurl",
        # 播放列表本身也是「同一时间片内内容相同」，但它比切片廉价得多，
        # 给个短缓存即可；真正要省的是切片那几百 MB。
        headers={"Cache-Control": "private, max-age=300"},
    )


@play_router.get("/{video_id}/{path:path}")
def stream(request: Request, video_id: int, path: str):
    """按签名发字节。**生产上切片不会走到这里**——nginx 在边缘校验完直连 MinIO。

    这里不查库、不建会话：签名本身就是凭证（和 CDN 的语义一致），
    每片 .ts 少一次 DB 往返。能签出 URL 的前提是签发时已经过了完整的课时门控。
    """
    settings = request.app.state.settings
    uri = video_sign.stream_uri(video_id, path)
    if not video_sign.verify(
        settings.minio_play_secret,
        uri,
        request.query_params.get("u"),
        request.query_params.get("e"),
        request.query_params.get("s"),
    ):
        raise HTTPException(403, "播放地址无效或已过期。")
    # 路径穿越兜底：签名保证了 URI 没被篡改，但绝不能让「签发方写错」升级成越权读桶。
    if ".." in path.split("/") or path.startswith("/"):
        raise HTTPException(400, "非法的播放路径。")

    full_key = f"video-{video_id}/{path}"
    expires = int(request.query_params["e"])
    uid = request.query_params["u"]

    client = get_minio_client(settings)
    if path.endswith(".m3u8"):
        return _playlist_response(client, settings, full_key, uri, uid, expires)
    rng = _parse_range(request.headers.get("range"))
    get_kwargs = {}
    if rng is not None:
        start, end = rng
        get_kwargs["Range"] = f"bytes={start}-{end if end is not None else ''}"
    try:
        obj = client.get_object(Bucket=settings.minio_play_bucket, Key=full_key, **get_kwargs)
    except Exception:
        raise HTTPException(404, "对象不存在或存储暂不可用。")
    # 切片是**不可变内容**（转码产物一旦生成不会再变），URL 在一个时间片内又完全稳定，
    # 所以可以放心缓存到签名过期为止：这正是「F5 之后不再重下」靠的那一条。
    # private = 只许最终用户的浏览器缓存，反代/CDN 不得共享（URL 是按 uid 签的）。
    headers = {"Cache-Control": _segment_cache_control(expires)}
    status_code = 200
    if rng is not None:
        # S3 Range 响应带 ContentRange（bytes start-end/total）：end 是 S3 实际返回的
        # 最后字节、total 是对象完整长度——**直接透传最可靠**（P0-1 修复）。
        # 旧实现 end = rng[0] + total - 1：open-ended Range（bytes=start-）下 S3 返回的
        # end 已是 total-1，再叠加 start 必然越界（start>0 时超出文件尾），播放器 /
        # PDF 阅读器据此拼下一段 Range 会 416 或反复重试。
        content_range = obj.get("ContentRange")
        if content_range and re.match(r"^bytes \d+-\d+/\d+$", content_range):
            status_code = 206
            headers["Content-Range"] = content_range
        else:
            # 兜底（正常走不到：S3 对合法 Range 必回 ContentRange）：
            # ContentLength 是本次分片的字节数，end 由 start + 本段长度算得，一定准；
            # **总长这里是真不知道**（没有 ContentRange 就没有对象完整长度），按
            # RFC 7233 §4.2 写 "*" —— 硬编一个猜出来的 total 才是害人：bytes=0-9
            # 会被写成 /10，客户端以为文件只有 10 字节，直接停在第一段不再往下取。
            length = obj.get("ContentLength")
            if length:
                status_code = 206
                end = rng[0] + int(length) - 1
                headers["Content-Range"] = f"bytes {rng[0]}-{end}/*"
    # 流式转发，避免把整片 .ts 读进内存。MinIO 不可达会抛异常，由上面的 except 兜底。
    return StreamingResponse(
        obj["Body"],
        status_code=status_code,
        media_type=_content_type(path, obj.get("ContentType")),
        headers=headers,
    )
