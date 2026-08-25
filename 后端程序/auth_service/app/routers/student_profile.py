"""学生个人资料（文档 28 P2）：资料读取、学习签名更新、头像上传。

只服务当前登录学生，绝不接受 URL 参数里的任意 student_id——权限边界与错题本
（student_mistakes.py）一致：一律从会话取身份。

头像存储沿用题干配图的内容寻址方案（sha256 + 重编码），但**独立落盘区**
data/avatars + /avatars 静态挂载，理由见 config.avatar_upload_root 的注释：
cleanup_media 的孤儿扫描不认识 student_profiles.avatar_url，混进 data/media 会被当孤儿清掉。
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..mistake_book import mistake_summary
from ..models import AttemptAnswer, LessonProblemAttempt, PaperAttempt, StudentProfile
from ..routers.admin_media import _decode, _normalize
from ..security import as_utc
from ..audit_summary import diff_summary
from .auth_secure import audit, client_ip, current_user, db_session, limit, require_csrf


router = APIRouter(prefix="/api/student/profile", tags=["student-profile"])

# 学习签名上限（文档 28 §5.1：建议 80 字以内）。列宽留 255 是给 URL 等后续扩展余地。
SIGNATURE_MAX = 80


class ProfileUpdate(BaseModel):
    learning_signature: str = Field(default="", max_length=SIGNATURE_MAX)


def _avatar_relative_path(sha256: str, ext: str) -> str:
    return f"{sha256[:2]}/{sha256}.{ext}"


def _get_or_create_profile(db: Session, user_id: int) -> StudentProfile:
    row = db.get(StudentProfile, user_id)
    if row is None:
        row = StudentProfile(user_id=user_id)
        db.add(row)
    return row


def _profile_payload(row: StudentProfile | None) -> dict:
    return {
        "avatar_url": row.avatar_url if row else "",
        "learning_signature": row.learning_signature if row else "",
    }


def _answered_problem_count(db: Session, user_id: int) -> int:
    """累计完成题数：判过分的作答题去重计数。

    v1 口径（文档 28 §6.3）：
    - 整卷作答：attempt_answers.judge_status = 'judged' 的 problem_id_no 去重；
    - 课中练习：lesson_problem_attempts 一行即一道题（(user, block) 唯一），
      last_correct 非空 = 判过。

    已知偏差：同一道题既在考试又在课中练习被做过，会被计两次。这是引导性概览数字，
    首版接受该偏差，待统一 attempt 模型落地后再收紧口径。
    """
    papers = db.scalar(
        select(func.count(func.distinct(AttemptAnswer.problem_id_no)))
        .join(PaperAttempt, PaperAttempt.id == AttemptAnswer.attempt_id)
        .where(PaperAttempt.user_id == user_id, AttemptAnswer.judge_status == "judged")
    ) or 0
    lessons = db.scalar(
        select(func.count()).select_from(LessonProblemAttempt).where(
            LessonProblemAttempt.user_id == user_id,
            LessonProblemAttempt.last_correct.is_not(None),
        )
    ) or 0
    return papers + lessons


@router.get("")
def get_profile(request: Request, db: Session = Depends(db_session)):
    user = current_user(request, db)
    limit(request, "student-profile-read", str(user.id), 120, 60)
    profile = db.get(StudentProfile, user.id)
    return {
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "status": user.status,
            "created_at": as_utc(user.created_at).isoformat(),
        },
        **_profile_payload(profile),
        "overview": {
            **mistake_summary(db, user.id),
            "total_answered": _answered_problem_count(db, user.id),
        },
    }


@router.patch("")
def update_profile(payload: ProfileUpdate, request: Request, db: Session = Depends(db_session)):
    require_csrf(request)
    user = current_user(request, db)
    limit(request, "student-profile-write", str(user.id), 30, 60)
    profile = _get_or_create_profile(db, user.id)
    before = {"learning_signature": profile.learning_signature}
    profile.learning_signature = payload.learning_signature.strip()
    # 改名属身份类变更：历史记录要能对得上人，故记 old/new（《55》§8 裁定归 authz）。
    audit(db, request.app.state.settings, "profile_update", "success",
          client_ip(request), user.id,
          resource_type="student_profile", resource_id=user.id,
          summary=diff_summary(before, {"learning_signature": profile.learning_signature},
                               ("learning_signature",)))
    db.commit()
    db.refresh(profile)
    return _profile_payload(profile)


@router.post("/avatar", status_code=201)
async def upload_avatar(request: Request, file: UploadFile = File(...),
                        db: Session = Depends(db_session)):
    require_csrf(request)
    user = current_user(request, db)
    # 头像不是高频操作：12 次 / 5 分钟，与课包封面同档。
    limit(request, "student-avatar-upload", str(user.id), 12, 300)

    settings = request.app.state.settings
    raw = await file.read(settings.avatar_max_bytes + 1)
    if len(raw) > settings.avatar_max_bytes:
        raise HTTPException(413, f"头像不能超过 {settings.avatar_max_bytes // (1024 * 1024)} MB。")
    if not raw:
        raise HTTPException(400, "上传内容为空。")

    # 只信 Pillow 解码结果，不信 Content-Type 和扩展名（admin_media 同一套红线）。
    image, fmt = _decode(raw)
    try:
        data, ext, _save_format, _width, _height = _normalize(
            image, fmt, settings.avatar_max_dimension
        )
    except OSError as exc:
        raise HTTPException(400, "头像处理失败，请换一张或另存为 PNG 后重试。") from exc
    finally:
        image.close()

    # 哈希算重编码后的字节：同一张图不同来源（EXIF 等）哈希一致，可去重。
    digest = hashlib.sha256(data).hexdigest()
    relative = _avatar_relative_path(digest, ext)

    root = Path(settings.avatar_upload_root).resolve()
    target = (root / relative).resolve()
    if root not in target.parents:
        raise HTTPException(500, "头像存储目录配置无效。")
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        # 先写临时文件再 replace：直接写目标路径，进程中断会留下"文件名正常但字节半截"的坏图。
        temporary = target.with_suffix(f"{target.suffix}.part")
        try:
            temporary.write_bytes(data)
            temporary.replace(target)
        except OSError as exc:
            temporary.unlink(missing_ok=True)
            raise HTTPException(500, "头像写入失败。") from exc

    profile = _get_or_create_profile(db, user.id)
    before = {"avatar_url": profile.avatar_url}
    profile.avatar_url = f"/avatars/{relative}"
    # 只记路径，**不记头像二进制**（《55》§8）。
    audit(db, settings, "profile_update", "success", client_ip(request), user.id,
          resource_type="student_profile", resource_id=user.id,
          summary=diff_summary(before, {"avatar_url": profile.avatar_url}, ("avatar_url",)))
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(profile)
    return {"avatar_url": profile.avatar_url}
