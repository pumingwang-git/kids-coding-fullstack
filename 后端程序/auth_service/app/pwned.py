"""HaveIBeenPwned Pwned Passwords k-anonymity breach check.

Only the first five characters of the SHA-1 digest leave this process; the
remaining suffix is matched locally against the returned range, so neither the
full password nor the full digest is ever transmitted.  Range files are
effectively static, so responses are cached in memory for 24 hours.

Default behaviour is fail-open (an unreachable database logs and allows the
request).  Set ``PWNED_CHECK_STRICT=true`` to fail closed instead.
"""

import hashlib
import logging
import threading
import time
from collections import OrderedDict

import httpx
from fastapi import HTTPException

logger = logging.getLogger(__name__)

_RANGE_CACHE: OrderedDict[str, tuple[float, dict[str, int]]] = OrderedDict()
_RANGE_CACHE_LOCK = threading.Lock()
_RANGE_CACHE_TTL_SECONDS = 24 * 60 * 60
_RANGE_CACHE_MAX_ENTRIES = 1024
_FETCH_SLOTS = threading.BoundedSemaphore(16)
_USER_AGENT = "study-auth-service/1.0 (breach-policy-check)"


class PwnedCheckUnavailable(RuntimeError):
    """Raised when the breach database cannot be reached or parsed."""


def sha1_hex(password: str) -> str:
    return hashlib.sha1(password.encode("utf-8")).hexdigest().upper()


def _fetch_range(prefix: str, base_url: str, timeout: float) -> dict[str, int]:
    """Return {suffix: occurrence_count} for a 5-character SHA-1 prefix."""
    with _RANGE_CACHE_LOCK:
        cached = _RANGE_CACHE.get(prefix)
        if cached and cached[0] > time.monotonic():
            _RANGE_CACHE.move_to_end(prefix)
            return cached[1]
    if not _FETCH_SLOTS.acquire(blocking=False):
        raise PwnedCheckUnavailable("breach range query capacity exhausted")
    try:
        response = httpx.get(
            f"{base_url.rstrip('/')}/range/{prefix}",
            timeout=timeout,
            headers={"User-Agent": _USER_AGENT, "Add-Padding": "true", "Accept": "text/plain"},
        )
        response.raise_for_status()
        if int(response.headers.get("content-length", "0") or 0) > 512 * 1024:
            raise PwnedCheckUnavailable("breach range response too large")
        suffixes: dict[str, int] = {}
        for line in response.text.splitlines():
            suffix, _, count = line.partition(":")
            suffix = suffix.strip().upper()
            if suffix and count.isdigit():
                suffixes[suffix] = int(count)
    except Exception as exc:
        raise PwnedCheckUnavailable(f"breach range query failed: {type(exc).__name__}") from exc
    finally:
        _FETCH_SLOTS.release()
    with _RANGE_CACHE_LOCK:
        while len(_RANGE_CACHE) >= _RANGE_CACHE_MAX_ENTRIES:
            _RANGE_CACHE.popitem(last=False)
        _RANGE_CACHE[prefix] = (time.monotonic() + _RANGE_CACHE_TTL_SECONDS, suffixes)
    return suffixes


def breach_count(
    password: str,
    *,
    base_url: str = "https://api.pwnedpasswords.com",
    timeout: float = 3.0,
) -> int | None:
    """How often `password` appears in known breach dumps.

    Returns ``None`` when the database is unreachable so the caller can decide
    whether to fail open or closed.
    """
    digest = sha1_hex(password)
    try:
        suffixes = _fetch_range(digest[:5], base_url, timeout)
    except PwnedCheckUnavailable:
        return None
    return suffixes.get(digest[5:], 0)


def enforce_breach_policy(settings, password: str) -> None:
    """Reject passwords that are public knowledge in breach dumps.

    Raises HTTP 400 for a breached password, HTTP 503 when the breach database
    is unreachable and ``pwned_check_strict`` is enabled, and returns silently
    otherwise (fail-open).
    """
    if not settings.pwned_check_enabled:
        return
    count = breach_count(
        password,
        base_url=settings.pwned_api_base_url,
        timeout=settings.pwned_timeout_seconds,
    )
    if count is None:
        if settings.pwned_check_strict:
            raise HTTPException(503, "密码泄露数据库暂不可用，请稍后重试。")
        logger.warning(
            "Pwned Passwords check unavailable; allowing password (fail-open). strict=%s",
            settings.pwned_check_strict,
        )
        return
    if count > 0:
        raise HTTPException(
            400, f"该密码已在公开泄露数据库中出现过 {count} 次，请更换一个未泄露的密码。"
        )
