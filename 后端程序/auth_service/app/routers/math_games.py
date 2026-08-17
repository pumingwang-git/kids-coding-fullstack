"""数学星球：启动统计与幂等游戏记录上报。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import MathGameSession, User
from .auth_secure import current_user, db_session, require_csrf

router = APIRouter(prefix="/api/math-games", tags=["student-math-games"])

GAME_KEYS = {"game24"}
MODES = {"practice", "challenge"}
DIFFICULTIES = {"easy", "medium", "hard"}
SESSIONS_BATCH_MAX = 50


class MathGameSessionIn(BaseModel):
    client_uuid: str = Field(min_length=8, max_length=36)
    game_key: str = Field(min_length=1, max_length=32)
    mode: str = Field(min_length=1, max_length=16)
    difficulty: str = Field(min_length=1, max_length=16)
    duration_sec: int = Field(default=0, ge=0, le=24 * 3600)
    score: int = Field(default=0, ge=0, le=1_000_000)
    count_correct: int = Field(default=0, ge=0, le=1_000_000)
    count_wrong: int = Field(default=0, ge=0, le=1_000_000)
    max_combo: int = Field(default=0, ge=0, le=1_000_000)


def _validate_session(item: MathGameSessionIn) -> None:
    if item.game_key not in GAME_KEYS:
        raise HTTPException(status_code=422, detail="game_key 暂不支持")
    if item.mode not in MODES:
        raise HTTPException(status_code=422, detail="mode 必须是 practice 或 challenge")
    if item.difficulty not in DIFFICULTIES:
        raise HTTPException(status_code=422, detail="difficulty 必须是 easy、medium 或 hard")


@router.get("/bootstrap")
def math_games_bootstrap(
    user: User = Depends(current_user), db: Session = Depends(db_session)
):
    """返回大厅所需的当前学生累计统计。"""
    totals = db.execute(
        select(
            func.count(MathGameSession.id),
            func.coalesce(func.max(MathGameSession.score), 0),
            func.coalesce(func.sum(MathGameSession.count_correct), 0),
            func.coalesce(func.sum(MathGameSession.count_wrong), 0),
            func.coalesce(func.max(MathGameSession.max_combo), 0),
            func.max(MathGameSession.created_at),
        ).where(MathGameSession.student_id == user.id)
    ).one()
    total_sessions, best_score, total_correct, total_wrong, best_combo, last_played_at = totals
    return {
        "stats": {
            "total_sessions": int(total_sessions or 0),
            "best_score": int(best_score or 0),
            "total_correct": int(total_correct or 0),
            "total_wrong": int(total_wrong or 0),
            "best_combo": int(best_combo or 0),
            "last_played_at": last_played_at.isoformat() if last_played_at else None,
        }
    }


@router.post("/sessions")
def upload_math_game_sessions(
    payload: list[MathGameSessionIn],
    request: Request,
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
):
    """批量上报游戏完成记录，client_uuid 已存在时直接跳过。"""
    require_csrf(request)
    if not payload:
        return {"inserted": 0, "skipped": 0}
    if len(payload) > SESSIONS_BATCH_MAX:
        raise HTTPException(status_code=422, detail=f"单批最多 {SESSIONS_BATCH_MAX} 条")

    inserted = 0
    skipped = 0
    for item in payload:
        _validate_session(item)
        exists = db.execute(
            select(MathGameSession.id).where(MathGameSession.client_uuid == item.client_uuid)
        ).scalar_one_or_none()
        if exists:
            skipped += 1
            continue
        db.add(
            MathGameSession(
                student_id=user.id,
                client_uuid=item.client_uuid,
                game_key=item.game_key,
                mode=item.mode,
                difficulty=item.difficulty,
                duration_sec=item.duration_sec,
                score=item.score,
                count_correct=item.count_correct,
                count_wrong=item.count_wrong,
                max_combo=item.max_combo,
            )
        )
        db.flush()
        inserted += 1
    db.commit()
    return {"inserted": inserted, "skipped": skipped}
