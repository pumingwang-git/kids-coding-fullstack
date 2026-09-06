"""视频转码：源文件 → 多码率 HLS（VOD）→ videos-play 桶。

流程：
1. 从 videos-source 下载源文件到本地临时工作目录
2. ffprobe 探测分辨率/时长，按源分辨率过滤出目标档位（480p/720p/1080p）
   源低于 480p 时兜底转一个不缩放的 source 档
3. 每个档位 ffmpeg 转 HLS（hls_time=6, VOD），产物目录 video-{id}/{档位}/
4. 手写多码率 master.m3u8 到 video-{id}/master.m3u8
5. 全部产物上传 videos-play；video_variants 每档一行；video.status=ready，
   primary_variant_id 指向最高档；失败置 failed 并重试

播放侧约定（video_play.py）：variant.object_key 是 master.m3u8 的 key，
其目录前缀 = 整条 HLS 路径前缀。master 在 video-{id}/ 根，子档在子目录，
两者都落在同一个前缀下，一个播放令牌覆盖全部。
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import time
import uuid
from pathlib import Path

from sqlalchemy import select

from ..celery_app import celery_app
from ..config import get_settings
from ..database import build_database
from ..logging_config import log_business_event
from ..models import Video, VideoUpload, VideoVariant
from ..s3_multipart import get_minio_client

# (档位名, 最大高, 视频码率, 音频码率)
RENDITIONS = [
    ("480p", 480, "800k", "96k"),
    ("720p", 720, "2000k", "128k"),
    ("1080p", 1080, "4000k", "128k"),
]
HLS_TIME = 6
logger = logging.getLogger("auth_service.transcode")

_TIMEOUT = 60 * 60  # 单档转码超时 1 小时（2GB 源文件足够）

# 项目根（auth_service/），用于把相对配置解析成绝对路径——subprocess 的工作目录
# 不保证在项目根，相对路径的 ffmpeg 会 FileNotFoundError。
# transcode.py 位于 app/tasks/ 下：parents[0]=tasks, parents[1]=app, parents[2]=auth_service
BASE_DIR = Path(__file__).resolve().parents[2]


def _abs(path: str | Path) -> Path:
    p = Path(path)
    return p if p.is_absolute() else BASE_DIR / p


def _bin(name: str) -> str:
    settings = get_settings()
    exe = f"{name}.exe" if os.name == "nt" else name
    return str(_abs(settings.ffmpeg_bin_dir) / exe)


def _run(cmd: list[str], cwd: Path | None = None) -> None:
    """执行 ffmpeg/ffprobe；失败抛错并把 stderr 末尾带上，便于排查。"""
    proc = subprocess.run(
        cmd, capture_output=True, text=True, timeout=_TIMEOUT, cwd=cwd, encoding="utf-8", errors="replace"
    )
    if proc.returncode != 0:
        tail = "\n".join((proc.stderr or "").strip().splitlines()[-20:])
        raise RuntimeError(f"命令失败: {' '.join(cmd[:6])}...\n{tail}")


def _probe(src: Path) -> dict:
    cmd = [
        _bin("ffprobe"), "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height",
        "-show_entries", "format=duration",
        "-of", "json",
        str(src),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        raise RuntimeError(f"ffprobe 失败: {proc.stderr[-300:]}")
    data = json.loads(proc.stdout)
    stream = (data.get("streams") or [{}])[0]
    width = int(stream.get("width") or 0)
    height = int(stream.get("height") or 0)
    duration = float((data.get("format") or {}).get("duration") or 0)
    return {"width": width, "height": height, "duration": duration}


def _upload_dir(client, bucket: str, prefix: str, local_dir: Path) -> int:
    """把本地目录递归上传到 bucket/prefix（保留相对路径）。返回文件数。

    注意 boto3 的 upload_file 签名是 (Filename, Bucket, Key)——与
    download_file 的 (Bucket, Key, Filename) 顺序不同，别写反。
    """
    count = 0
    for root, _dirs, files in os.walk(local_dir):
        for fname in files:
            local = Path(root) / fname
            rel = local.relative_to(local_dir).as_posix()
            client.upload_file(str(local), bucket, f"{prefix}{rel}")
            count += 1
    return count


def _kb(vbr: str) -> int:
    return int(vbr.rstrip("k"))


@celery_app.task(bind=True, max_retries=2, default_retry_delay=30)
def transcode_video(self, video_id: int) -> None:
    task_id = getattr(self.request, "id", None) or f"video:{video_id}"
    started = time.perf_counter()
    log_business_event(logger, "video_transcode", "started", task_id=task_id, resource_type="video", resource_id=video_id)
    settings = get_settings()
    _, session_factory = build_database(settings.database_url)
    work = _abs(settings.transcode_work_root) / f"v{video_id}-{uuid.uuid4().hex[:8]}"
    db = session_factory()
    try:
        video = db.get(Video, video_id)
        if video is None:
            log_business_event(logger, "video_transcode", "not_found", task_id=task_id, resource_type="video", resource_id=video_id)
            return
        source = db.scalar(
            select(VideoUpload)
            .where(VideoUpload.video_id == video_id, VideoUpload.status == "completed")
            .order_by(VideoUpload.id.desc())
            .limit(1)
        )
        if source is None:
            video.status = "failed"
            db.commit()
            log_business_event(logger, "video_transcode", "missing_source", task_id=task_id, resource_type="video", resource_id=video_id)
            return

        video.status = "transcoding"
        # 该视频旧档位全部删除（重新转码场景：直接重建，不保留失效行）。
        # 先解除 primary_variant_id 指向，否则 DELETE 违反 fk_videos_primary_variant_id。
        video.primary_variant_id = None
        db.flush()
        for old in db.scalars(select(VideoVariant).where(VideoVariant.video_id == video_id)):
            db.delete(old)
        db.commit()

        client = get_minio_client(settings)
        work.mkdir(parents=True, exist_ok=True)
        src_local = work / ("source" + Path(source.object_key).suffix)
        client.download_file(settings.minio_source_bucket, source.object_key, str(src_local))

        info = _probe(src_local)
        src_h = info["height"]
        duration = info["duration"]

        # 目标档位：只保留低于源分辨率的降档；源 <480p 时兜底不缩放 source 档
        targets = [r for r in RENDITIONS if src_h and r[1] < src_h]
        if not targets:
            targets = [("source", src_h, "", "96k")]

        variants = []  # (name, vbr_kbps, height)
        for name, max_h, vbr, abr in targets:
            out_dir = work / name
            out_dir.mkdir(parents=True, exist_ok=True)
            cmd = [_bin("ffmpeg"), "-y", "-i", str(src_local)]
            if vbr:  # 降档才缩放；source 档保持原始分辨率
                cmd += ["-vf", f"scale=-2:{max_h}"]
            cmd += [
                "-c:v", "libx264", "-preset", "veryfast",
                "-b:v", vbr or "0",
                "-c:a", "aac", "-b:a", abr,
                "-hls_time", str(HLS_TIME),
                "-hls_playlist_type", "vod",
                "-hls_segment_filename", str(out_dir / "seg_%05d.ts"),
                "-force_key_frames", "expr:gte(t,n_forced*6)",
                str(out_dir / "index.m3u8"),
            ]
            _run(cmd)
            _upload_dir(client, settings.minio_play_bucket, f"video-{video_id}/{name}/", out_dir)
            variants.append((name, _kb(vbr) if vbr else 0, max_h))
            logger.info("transcode rendition completed", extra={"task_id": task_id, "resource_id": video_id})

        # 多码率 master.m3u8。RESOLUTION 按源宽高比推算实际输出尺寸（scale 保持宽高比，
        # 宽取偶：ffmpeg scale=-2 的行为）；write_text 用 newline="\n" 避免 Windows 把
        # 换行写成 \r\n 污染 m3u8。
        src_w = info.get("width") or 0
        master_lines = ["#EXTM3U"]
        for name, vbr_kbps, height in variants:
            bw = max(vbr_kbps * 1024, 800 * 1024) + 128 * 1024
            if height and src_w and src_h:
                out_w = round(src_w / src_h * height / 2) * 2
                res = f",RESOLUTION={out_w}x{height}"
            else:
                res = ""
            master_lines.append(f"#EXT-X-STREAM-INF:BANDWIDTH={bw}{res}")
            master_lines.append(f"{name}/index.m3u8")
        master_local = work / "master.m3u8"
        master_local.write_text("\n".join(master_lines) + "\n", encoding="utf-8", newline="\n")
        client.upload_file(str(master_local), settings.minio_play_bucket, f"video-{video_id}/master.m3u8")

        # 回写：每档一行 variant，primary 指向最高档
        primary = None
        primary_h = -1
        for name, vbr_kbps, height in variants:
            v = VideoVariant(
                video_id=video_id,
                bucket=settings.minio_play_bucket,
                # 普通档：object_key 指向本档 index.m3u8（信息完整）。
                object_key=f"video-{video_id}/{name}/index.m3u8",
                resolution=name,
                bitrate_kbps=vbr_kbps or None,
                duration_seconds=duration or None,
                status="ready",
            )
            db.add(v)
            db.flush()
            if (height or 0) > primary_h:
                primary, primary_h = v, height or 0
        if primary is not None:
            # ⚠️ primary 档的 object_key 必须是 master.m3u8 的 key——播放代理
            # (video_play.stream) 从它推「整条 HLS 路径前缀」：master 在 video-{id}/ 根，
            # 子档/切片在子目录，一个令牌覆盖全部。
            primary.object_key = f"video-{video_id}/master.m3u8"
            video.primary_variant_id = primary.id
        video.status = "ready"
        db.commit()
        log_business_event(logger, "video_transcode", "success", task_id=task_id, resource_type="video", resource_id=video_id)
    except Exception as exc:
        logger.exception("video transcode failed", extra={"task_id": task_id, "resource_id": video_id, "duration_ms": round((time.perf_counter() - started) * 1000, 2)})
        db.rollback()
        try:
            v = db.get(Video, video_id)
            if v is not None and v.status != "failed":
                v.status = "failed"
                db.commit()
        except Exception:
            db.rollback()
        # eager 模式（本地无 Redis）没有 worker 消费 retry 计划，直接抛最终错误；
        # 生产 worker 模式下才重试。
        if celery_app.conf.task_always_eager:
            raise
        raise self.retry(exc=exc) from exc
    finally:
        shutil.rmtree(work, ignore_errors=True)
        db.close()
