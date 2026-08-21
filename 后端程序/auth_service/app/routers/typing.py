"""打字星球：学生档案（年龄段分流）+ 章节完成记录上报 + 发音代理。

与 `focus.py`（专注星球）同口径的三条红线：

1. **写请求一律学生端 CSRF**（`csrf_token` Cookie + `require_csrf`）。
2. **章节记录是 append-only 事件流**：靠 `client_uuid` 幂等，已存在的直接跳过，
   重复提交不产生脏数据（断网补送、双设备并发的安全网）。
3. **档案是当前状态**：`age_group` 三段（'3-6'/'7-12'/'13+'）与 `settings`
   整体 JSON 后写覆盖，服务端不做任何业务判定。

端点：

    GET  /api/typing/bootstrap   档案 + 最近统计（子应用启动只发这一个）
    POST /api/typing/profile     保存/更新档案（首次进字母乐园/单词打字前调用）
    POST /api/typing/sessions    批量上报章节完成记录（幂等，≤50 条/批）
    GET  /api/typing/audio       发音代理（25 号文档 §3.2，有道 dictvoice + 磁盘缓存）
"""
from __future__ import annotations

import hashlib
import os
import secrets
import threading
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import TypingProfile, TypingSession, User
from .auth_secure import client_ip, current_user, db_session, limit, require_csrf
from .focus import _day_start_shanghai

router = APIRouter(prefix="/api/typing", tags=["student-typing"])

AGE_GROUPS = {"3-6", "7-12", "13+"}
SESSIONS_BATCH_MAX = 50
SETTINGS_MAX_BYTES = 32 * 1024

# 前端 PronunciationType → 有道参数（usePronunciation.ts generateWordSoundSrc 的镜像）
YOUDAO_LE = {
    "us": "type=2",
    "uk": "type=1",
    "zh": "le=zh",
    "ja": "le=jap",
    "de": "le=de",
    "ru": "le=ru",  # 哈萨克语暂时用俄语兜底（前端同口径）
    "id": "le=id",
    "romaji": "le=jap",
}

_AUDIO_KEY_LOCKS_GUARD = threading.Lock()
_AUDIO_KEY_LOCKS: dict[str, tuple[threading.Lock, int]] = {}
_AUDIO_CACHE_GUARD = threading.Lock()
_AUDIO_LOCK_WAIT_SECONDS = 12
_AUDIO_LOCK_STALE_SECONDS = 60


# ---------- 请求模型 ----------


class TypingProfileIn(BaseModel):
    age_group: str = Field(min_length=3, max_length=8)
    settings: dict = Field(default_factory=dict)


class TypingSessionIn(BaseModel):
    client_uuid: str = Field(min_length=8, max_length=36)
    dict_id: str = Field(min_length=1, max_length=64)
    chapter: int = Field(default=0, ge=0, le=10_000)
    duration_sec: int = Field(default=0, ge=0, le=24 * 3600)
    count_input: int = Field(default=0, ge=0, le=1_000_000)
    count_correct: int = Field(default=0, ge=0, le=1_000_000)
    count_typo: int = Field(default=0, ge=0, le=1_000_000)
    mode_dictation: bool = False


# ---------- 工具 ----------


def _profile_payload(row: TypingProfile | None) -> dict | None:
    if row is None:
        return None
    return {
        "age_group": row.age_group,
        "settings": row.settings or {},
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _json_bytes(obj: dict) -> bytes:
    import json

    return json.dumps(obj, ensure_ascii=False).encode("utf-8")


@contextmanager
def _audio_key_lock(key: str):
    """同一进程内同词只回源一次，并在请求结束后回收锁表条目。"""
    with _AUDIO_KEY_LOCKS_GUARD:
        lock, users = _AUDIO_KEY_LOCKS.get(key, (threading.Lock(), 0))
        _AUDIO_KEY_LOCKS[key] = (lock, users + 1)
    lock.acquire()
    try:
        yield
    finally:
        lock.release()
        with _AUDIO_KEY_LOCKS_GUARD:
            current_lock, users = _AUDIO_KEY_LOCKS[key]
            if users <= 1:
                _AUDIO_KEY_LOCKS.pop(key, None)
            else:
                _AUDIO_KEY_LOCKS[key] = (current_lock, users - 1)


@contextmanager
def _audio_file_lock(cache_dir: Path, key: str):
    """跨进程回源锁；崩溃遗留的锁文件会在 60 秒后被接管。"""
    lock_path = cache_dir / f".{key}.lock"
    owner_token = secrets.token_urlsafe(24)
    deadline = time.monotonic() + _AUDIO_LOCK_WAIT_SECONDS
    while True:
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            try:
                if time.time() - lock_path.stat().st_mtime > _AUDIO_LOCK_STALE_SECONDS:
                    lock_path.unlink(missing_ok=True)
                    continue
            except OSError:
                continue
            if time.monotonic() >= deadline:
                raise HTTPException(status_code=503, detail="发音正在生成，请稍后重试")
            time.sleep(0.05)
            continue
        os.write(fd, owner_token.encode("ascii"))
        os.close(fd)
        break
    try:
        yield
    finally:
        try:
            if lock_path.read_text(encoding="ascii") == owner_token:
                lock_path.unlink(missing_ok=True)
        except (OSError, UnicodeDecodeError):
            pass


def _prune_audio_cache(cache_dir: Path, *, max_bytes: int, max_files: int,
                       incoming_bytes: int = 0) -> None:
    """按最近访问时间淘汰旧 MP3，为即将写入的文件腾出配额。"""
    entries: list[tuple[Path, os.stat_result]] = []
    for path in cache_dir.glob("*.mp3"):
        try:
            entries.append((path, path.stat()))
        except OSError:
            continue
    total = sum(stat.st_size for _, stat in entries)
    count = len(entries)
    entries.sort(key=lambda item: item[1].st_mtime)
    for path, stat in entries:
        if total + incoming_bytes <= max_bytes and count + 1 <= max_files:
            break
        try:
            path.unlink()
        except OSError:
            continue
        total -= stat.st_size
        count -= 1


def _fetch_audio(url: str, destination: Path, *, max_bytes: int) -> int:
    """流式下载并限制实际字节数，绝不把不受控响应整体读入内存。"""
    written = 0
    completed = False
    try:
        with httpx.Client(timeout=8, follow_redirects=True) as client:
            with client.stream("GET", url) as resp:
                if resp.status_code != 200:
                    raise HTTPException(status_code=502, detail="发音服务暂不可用")
                declared = resp.headers.get("content-length")
                if declared:
                    try:
                        if int(declared) > max_bytes:
                            raise HTTPException(status_code=502, detail="发音服务响应过大")
                    except ValueError:
                        pass
                with destination.open("xb") as output:
                    for chunk in resp.iter_bytes():
                        written += len(chunk)
                        if written > max_bytes:
                            raise HTTPException(status_code=502, detail="发音服务响应过大")
                        output.write(chunk)
        if written == 0:
            raise HTTPException(status_code=502, detail="发音服务暂不可用")
        completed = True
        return written
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="发音服务暂不可用") from exc
    except Exception:
        raise
    finally:
        if not completed:
            destination.unlink(missing_ok=True)


def _valid_audio_cache(path: Path, *, max_bytes: int) -> bool:
    try:
        size = path.stat().st_size
        return 0 < size <= max_bytes
    except OSError:
        return False


def _cleanup_audio_cache(cache_dir: Path, *, max_bytes: int, max_files: int) -> None:
    """Remove invalid cache entries and abandoned temporary artifacts."""
    if not cache_dir.exists():
        return
    now = time.time()
    for path in cache_dir.iterdir():
        try:
            age = now - path.stat().st_mtime
            if path.name.endswith(".tmp") and age > _AUDIO_LOCK_STALE_SECONDS:
                path.unlink(missing_ok=True)
            elif path.name.endswith(".lock") and age > _AUDIO_LOCK_STALE_SECONDS:
                path.unlink(missing_ok=True)
            elif path.suffix == ".mp3" and not _valid_audio_cache(path, max_bytes=max_bytes):
                path.unlink(missing_ok=True)
        except OSError:
            continue
    with _audio_file_lock(cache_dir, "quota"):
        with _AUDIO_CACHE_GUARD:
            _prune_audio_cache(cache_dir, max_bytes=max_bytes, max_files=max_files)


# ---------- 端点 ----------


@router.get("/bootstrap")
def typing_bootstrap(user: User = Depends(current_user), db: Session = Depends(db_session)):
    """子应用启动单接口：档案 + 今日/累计完成数（供入口页高亮与统计角标）。"""
    profile = db.execute(select(TypingProfile).where(TypingProfile.student_id == user.id)).scalar_one_or_none()

    # 27 号文档 P1-10：日界必须按 Asia/Shanghai（与 focus.py 同口径），UTC 日界会把
    # 北京时间 00:00-08:00 的练习算成"昨天"
    now = datetime.now(UTC)
    today_start = _day_start_shanghai(now)
    today_count = db.execute(
        select(func.count(TypingSession.id)).where(
            TypingSession.student_id == user.id, TypingSession.created_at >= today_start
        )
    ).scalar_one()
    total_count = db.execute(
        select(func.count(TypingSession.id)).where(TypingSession.student_id == user.id)
    ).scalar_one()

    return {
        "profile": _profile_payload(profile),
        "stats": {"today_sections": today_count, "total_sections": total_count},
    }


@router.post("/profile")
def save_profile(
    payload: TypingProfileIn,
    request: Request,
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
):
    """保存/更新年龄段档案。年龄分段是产品级决策，服务端只校验取值合法。"""
    require_csrf(request)
    if payload.age_group not in AGE_GROUPS:
        raise HTTPException(status_code=422, detail=f"age_group 必须是 {sorted(AGE_GROUPS)} 之一")

    raw = payload.settings
    if len(raw.encode("utf-8") if isinstance(raw, str) else _json_bytes(raw)) > SETTINGS_MAX_BYTES:
        raise HTTPException(status_code=413, detail="settings 超过 32KB")

    row = db.execute(select(TypingProfile).where(TypingProfile.student_id == user.id)).scalar_one_or_none()
    if row is None:
        row = TypingProfile(student_id=user.id, age_group=payload.age_group, settings=payload.settings)
        db.add(row)
    else:
        row.age_group = payload.age_group
        row.settings = payload.settings
    db.commit()
    db.refresh(row)
    return {"profile": _profile_payload(row)}


@router.post("/sessions")
def upload_sessions(
    payload: list[TypingSessionIn],
    request: Request,
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
):
    """批量上报章节完成记录，client_uuid 幂等（已存在直接跳过）。"""
    require_csrf(request)
    if not payload:
        return {"inserted": 0, "skipped": 0}
    if len(payload) > SESSIONS_BATCH_MAX:
        raise HTTPException(status_code=422, detail=f"单批最多 {SESSIONS_BATCH_MAX} 条")

    inserted = 0
    skipped = 0
    for item in payload:
        # client_uuid 表级全局唯一（models.py unique=True）；查重口径必须一致，
        # 只按 client_uuid 判重，否则双标签页同 uuid 会两条都过查重、撞唯一索引 500
        exists = db.execute(
            select(TypingSession.id).where(TypingSession.client_uuid == item.client_uuid)
        ).scalar_one_or_none()
        if exists:
            skipped += 1
            continue
        db.add(
            TypingSession(
                student_id=user.id,
                client_uuid=item.client_uuid,
                dict_id=item.dict_id,
                chapter=item.chapter,
                duration_sec=item.duration_sec,
                count_input=item.count_input,
                count_correct=item.count_correct,
                count_typo=item.count_typo,
                mode_dictation=item.mode_dictation,
            )
        )
        # flush 让同批后续查重能看到本事务已插入的行（否则同批重复 uuid 撞唯一索引 500）
        db.flush()
        inserted += 1
    db.commit()
    return {"inserted": inserted, "skipped": skipped}


# ---------- 发音代理 ----------


@router.get("/audio")
def typing_audio(request: Request, word: str = "", type: str = "us"):
    """发音代理（25 号文档 §3.2 / 27 号文档 P0-5）：转发有道 dictvoice + 磁盘缓存。

    - **不鉴权**：游客（未登录）也要能发音，孩子打不了字不能因为没登录就没声音；
    - 缓存到 `data/audio_cache/`（按 word+type 哈希命名），命中直接回本地文件，
      弱网/离线可用，也不再把击键词汇直连第三方（学生产品合规）；
    - 只接受短词，杜绝把代理当开放拉取器。
    """
    word = (word or "").strip()
    if not word or len(word) > 64:
        raise HTTPException(status_code=422, detail="word 参数非法")
    settings = request.app.state.settings
    ip = client_ip(request)
    limit(request, "typing-audio", ip, settings.typing_audio_rate_limit_per_minute, 60)
    audio_type = type if type in YOUDAO_LE else "us"
    le = YOUDAO_LE[audio_type]
    url = f"https://dict.youdao.com/dictvoice?audio={quote(word)}&{le}"

    key = hashlib.sha256(f"{audio_type}:{word}".encode()).hexdigest()
    cache_dir = Path(settings.typing_audio_cache_root)
    path = cache_dir / f"{key}.mp3"
    if _valid_audio_cache(path, max_bytes=settings.typing_audio_response_max_bytes):
        try:
            path.touch()
        except OSError:
            pass
    else:
        cache_dir.mkdir(parents=True, exist_ok=True)
        with _audio_key_lock(key):
            with _audio_file_lock(cache_dir, key):
                # 等待同词请求期间，另一个线程或 worker 可能已经填好缓存。
                if not _valid_audio_cache(path, max_bytes=settings.typing_audio_response_max_bytes):
                    limit(request, "typing-audio-fetch", ip, settings.typing_audio_fetch_limit_per_minute, 60)
                    tmp = cache_dir / f".{key}.{os.getpid()}.{threading.get_ident()}.tmp"
                    tmp.unlink(missing_ok=True)
                    size = _fetch_audio(url, tmp, max_bytes=settings.typing_audio_response_max_bytes)
                    try:
                        if size > settings.typing_audio_cache_max_bytes:
                            raise HTTPException(status_code=502, detail="发音服务响应超过缓存配额")
                        with _audio_file_lock(cache_dir, "quota"):
                            with _AUDIO_CACHE_GUARD:
                                _prune_audio_cache(
                                    cache_dir,
                                    max_bytes=settings.typing_audio_cache_max_bytes,
                                    max_files=settings.typing_audio_cache_max_files,
                                    incoming_bytes=size,
                                )
                                os.replace(tmp, path)
                    finally:
                        tmp.unlink(missing_ok=True)
    return FileResponse(path, media_type="audio/mpeg", headers={"Cache-Control": "private, max-age=86400"})
