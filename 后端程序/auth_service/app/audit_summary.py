"""审计摘要的唯一构造入口。"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from typing import Any, Sequence

_SENSITIVE = ("password", "token", "secret", "ip", "email")
_MAX_BYTES = 4 * 1024


def _safe_name(name: str) -> bool:
    lowered = name.lower()
    return not any(part in lowered for part in _SENSITIVE)


def _json_value(value: Any) -> Any:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if isinstance(value, date):
        return value.isoformat()
    return value


def diff_summary(before: dict, after: dict, fields: Sequence[str]) -> dict:
    """Return a bounded, allow-listed old/new diff with stable schema version 1."""
    changed: dict[str, dict[str, Any]] = {}
    for field in fields:
        if not _safe_name(field):
            continue
        old = _json_value(before.get(field))
        new = _json_value(after.get(field))
        if old != new:
            changed[field] = {"old": old, "new": new}
    result: dict[str, Any] = {"schema_version": 1, "changed": changed}
    if len(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")) <= _MAX_BYTES:
        return result
    bounded: dict[str, dict[str, Any]] = {}
    for field in sorted(changed):
        candidate = {"schema_version": 1, "changed": {**bounded, field: changed[field]}, "truncated": True}
        if len(json.dumps(candidate, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")) > _MAX_BYTES:
            break
        bounded[field] = changed[field]
    return {"schema_version": 1, "changed": bounded, "truncated": True}
