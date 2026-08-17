"""Asynchronous new-IP / new-location detection for successful logins.

The web request only enqueues this work.  The database remains the audit
source of truth; Redis is an optional 90-day accelerator for known locations.
"""

import hashlib
import ipaddress
import logging
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import LoginHistory, User
from .security import hash_ip, utcnow

logger = logging.getLogger(__name__)
AUTH_SERVICE_ROOT = Path(__file__).resolve().parent.parent


def client_device_fingerprint(user_agent: str, supplied: str | None) -> str:
    # A client-provided fingerprint is only a signal, never authentication.
    value = (supplied or user_agent or "unknown")[:512]
    return hashlib.sha256(value.encode()).hexdigest()


def mask_ip(ip: str) -> str:
    """Keep only a display-safe IP fragment in the encrypted email payload."""
    return ip[: ip.rfind(".") + 1] + "***" if "." in ip else "已隐藏"


def resolve_database_path(configured_path: str | None) -> Path | None:
    """Resolve data files relative to auth_service, not the process CWD."""
    if not configured_path:
        return None
    path = Path(configured_path).expanduser()
    return path if path.is_absolute() else AUTH_SERVICE_ROOT / path


def locate_ip(settings, ip: str) -> dict[str, str | None]:
    unknown = {"country": None, "province": None, "city": None, "location_key": None}
    china_location = _locate_with_ip2region(settings, ip)
    if china_location:
        return china_location
    database = resolve_database_path(settings.geoip_database_path)
    if not database or not database.is_file():
        return unknown
    try:
        from geoip2.database import Reader

        with Reader(database) as reader:
            result = reader.city(ip)
        country = result.country.names.get("zh-CN") or result.country.iso_code
        province = (
            result.subdivisions.most_specific.names.get("zh-CN")
            or result.subdivisions.most_specific.iso_code
        )
        city = result.city.names.get("zh-CN") or result.city.name
        values = (country, province, city)
        return {
            "country": country,
            "province": province,
            "city": city,
            "location_key": "|".join(value or "" for value in values) if any(values) else None,
        }
    except Exception as exc:
        # Missing/corrupt GeoIP data must never block a successful login.
        logger.warning("GeoIP lookup skipped: error_type=%s", type(exc).__name__)
        return unknown


def _locate_with_ip2region(settings, ip: str) -> dict[str, str | None] | None:
    """Prefer the China-oriented local xdb source when it is configured."""
    try:
        version = ipaddress.ip_address(ip).version
    except ValueError:
        return None
    configured_path = (
        settings.ip2region_v4_database_path if version == 4 else settings.ip2region_v6_database_path
    )
    database = resolve_database_path(configured_path)
    if not database or not database.is_file():
        return None
    searcher = None
    try:
        import ip2region.searcher as xdb
        import ip2region.util as util

        searcher = xdb.new_with_file_only(util.IPv4 if version == 4 else util.IPv6, database)
        parts = searcher.search(ip).split("|")
        if not parts or not parts[0]:
            return None
        country, province, city = (parts + [None, None, None])[:3]
        # ip2region uses "0" for an unavailable field; do not treat it as a location.
        country, province, city = (
            None if value in ("", "0") else value for value in (country, province, city)
        )
        return {
            "country": country,
            "province": province,
            "city": city,
            "location_key": "|".join(value or "" for value in (country, province, city))
            if any((country, province, city))
            else None,
        }
    except Exception as exc:
        logger.warning("ip2region lookup skipped: error_type=%s", type(exc).__name__)
        return None
    finally:
        if searcher:
            searcher.close()


def _known_location_from_redis(settings, user_id: int, location_key: str | None) -> bool | None:
    if not settings.redis_url or not location_key:
        return None
    try:
        from redis import Redis

        redis = Redis.from_url(settings.redis_url, decode_responses=True)
        return bool(redis.sismember(f"auth:known-locations:{user_id}", location_key))
    except Exception as exc:
        logger.warning("Known-location cache unavailable: error_type=%s", type(exc).__name__)
        return None


def _remember_location_in_redis(settings, user_id: int, location_key: str | None) -> None:
    if not settings.redis_url or not location_key:
        return
    try:
        from redis import Redis

        redis = Redis.from_url(settings.redis_url, decode_responses=True)
        key = f"auth:known-locations:{user_id}"
        redis.sadd(key, location_key)
        redis.expire(key, settings.login_location_ttl_days * 24 * 60 * 60)
    except Exception as exc:
        logger.warning("Known-location cache update failed: error_type=%s", type(exc).__name__)


def process_login_risk(
    session_factory,
    sender,
    settings,
    user_id: int,
    ip: str,
    user_agent: str,
    supplied_fingerprint: str | None,
) -> None:
    """Record a successful login and queue an alert only for a later anomaly."""
    db: Session = session_factory()
    try:
        # Serialize per-user baselining so concurrent first logins cannot both
        # incorrectly regard themselves as the first login.
        user = db.scalar(select(User).where(User.id == user_id).with_for_update())
        if not user:
            return
        location = locate_ip(settings, ip)
        ip_hmac = hash_ip(settings, ip)
        has_baseline = (
            db.scalar(select(LoginHistory.id).where(LoginHistory.user_id == user_id).limit(1))
            is not None
        )
        known_ip = (
            db.scalar(
                select(LoginHistory.id)
                .where(LoginHistory.user_id == user_id, LoginHistory.ip_hmac == ip_hmac)
                .limit(1)
            )
            is not None
        )
        cached_location = _known_location_from_redis(settings, user_id, location["location_key"])
        known_location = cached_location is True or (
            cached_location is not True
            and bool(location["location_key"])
            and db.scalar(
                select(LoginHistory.id)
                .where(
                    LoginHistory.user_id == user_id,
                    LoginHistory.location_key == location["location_key"],
                )
                .limit(1)
            )
            is not None
        )
        anomaly = bool(
            has_baseline and (not known_ip or (location["location_key"] and not known_location))
        )
        db.add(
            LoginHistory(
                user_id=user_id,
                ip_hmac=ip_hmac,
                user_agent=(user_agent or None)[:512],
                device_hmac=client_device_fingerprint(user_agent, supplied_fingerprint),
                anomaly=anomaly,
                country=location["country"],
                province=location["province"],
                city=location["city"],
                location_key=location["location_key"],
            )
        )
        alert_id = None
        if anomaly:
            from .routers.auth_secure import queue_outbox

            alert_id = queue_outbox(
                db,
                settings,
                user,
                {
                    "event": "new_login_location",
                    "country": location["country"],
                    "province": location["province"],
                    "city": location["city"],
                    "ip": mask_ip(ip),
                    "user_agent": (user_agent or "未知设备")[:180],
                    "time": utcnow().isoformat(),
                },
                "login_alert",
            )
        db.commit()
        _remember_location_in_redis(settings, user_id, location["location_key"])
        if anomaly:
            # Email delivery uses the existing durable outbox and is retried by workers.
            from .mailer import deliver_outbox

            if alert_id:
                deliver_outbox(session_factory, sender, settings, alert_id)
    except Exception:
        db.rollback()
        logger.exception("Login risk processing failed")
    finally:
        db.close()
