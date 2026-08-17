"""Optional Redis cache for student mistake-book reads.

The database remains the source of truth. Cache writes and invalidation are
best-effort so Redis outages cannot block a student's learning workflow.
"""
from __future__ import annotations

import json
import logging
from functools import lru_cache
from typing import Any

from sqlalchemy import event
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

VERSION_KEY = "student-mistakes:version:{}"
LIST_KEY = "student-mistakes:list:{}:{}:{}:{}:v{}"
SUMMARY_KEY = "student-mistakes:summary:{}:v{}"
LIST_TTL_SECONDS = 120
SUMMARY_TTL_SECONDS = 60


@lru_cache(maxsize=4)
def _client(redis_url: str | None):
    if not redis_url:
        return None
    try:
        from redis import Redis

        return Redis.from_url(
            redis_url,
            decode_responses=True,
            socket_connect_timeout=0.25,
            socket_timeout=0.25,
        )
    except Exception as exc:  # pragma: no cover - defensive dependency boundary
        logger.warning("Mistake cache client unavailable: error_type=%s", type(exc).__name__)
        return None


def _read_json(client, key: str) -> dict[str, Any] | None:
    try:
        raw = client.get(key)
        return json.loads(raw) if raw else None
    except Exception as exc:
        logger.warning("Mistake cache read failed: error_type=%s", type(exc).__name__)
        return None


def get_json(redis_url: str | None, key: str) -> dict[str, Any] | None:
    client = _client(redis_url)
    return _read_json(client, key) if client else None


def set_json(redis_url: str | None, key: str, value: dict[str, Any], ttl: int) -> None:
    client = _client(redis_url)
    if client is None:
        return
    try:
        client.setex(key, ttl, json.dumps(value, ensure_ascii=False, separators=(",", ":")))
    except Exception as exc:
        logger.warning("Mistake cache write failed: error_type=%s", type(exc).__name__)


def version(redis_url: str | None, student_id: int) -> int:
    client = _client(redis_url)
    if client is None:
        return 0
    try:
        return int(client.get(VERSION_KEY.format(student_id)) or 0)
    except Exception as exc:
        logger.warning("Mistake cache version read failed: error_type=%s", type(exc).__name__)
        return 0


def list_key(student_id: int, status: str, page: int, size: int, cache_version: int, filters: str = "") -> str:
    scope = ":".join(part or "all" for part in (status, filters))
    return LIST_KEY.format(student_id, scope, page, size, cache_version)


def summary_key(student_id: int, cache_version: int) -> str:
    return SUMMARY_KEY.format(student_id, cache_version)


def mark_dirty(db: Session, student_id: int) -> None:
    """Queue invalidation until the surrounding database transaction commits."""
    db.info.setdefault("student_mistake_cache_students", set()).add(int(student_id))


@event.listens_for(Session, "after_commit")
def _bump_versions_after_commit(session: Session) -> None:
    students = session.info.pop("student_mistake_cache_students", set())
    redis_url = session.info.get("student_mistake_cache_redis_url")
    if not students or not redis_url:
        return
    client = _client(redis_url)
    if client is None:
        return
    try:
        for student_id in students:
            client.incr(VERSION_KEY.format(student_id))
    except Exception as exc:
        logger.warning("Mistake cache invalidation failed: error_type=%s", type(exc).__name__)


@event.listens_for(Session, "after_rollback")
def _discard_versions_after_rollback(session: Session) -> None:
    session.info.pop("student_mistake_cache_students", None)
