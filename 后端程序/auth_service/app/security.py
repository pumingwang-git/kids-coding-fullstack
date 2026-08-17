import base64
import hashlib
import hmac
import secrets
import time
from datetime import UTC, datetime, timedelta

from cryptography.fernet import Fernet
from jwt import (
    DecodeError,
    ExpiredSignatureError,
    InvalidTokenError,
    decode,
    encode,
    get_unverified_header,
)
from pwdlib import PasswordHash

from .config import Settings

password_hash = PasswordHash.recommended()
# Always verify this hash when an account is absent, so the password branch has
# substantially the same Argon2 cost as an existing account.
DUMMY_PASSWORD_HASH = password_hash.hash("not-a-real-password-for-timing-equalization")


def utcnow():
    return datetime.now(UTC)


def as_utc(value: datetime) -> datetime:
    """Normalize SQLite naive values and PostgreSQL aware values to UTC."""
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def normalize_username(value: str) -> str:
    return value.strip().casefold()


def normalize_email(value: str) -> str:
    local, domain = value.strip().rsplit("@", 1)
    return f"{local}@{domain.casefold()}"


def hmac_value(key: str, value: str) -> str:
    return hmac.new(key.encode(), value.encode(), hashlib.sha256).hexdigest()


def make_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def make_captcha_code() -> str:
    alphabet = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
    return "".join(secrets.choice(alphabet) for _ in range(5))


def hash_code(settings: Settings, verification_id: int, code: str) -> str:
    return hmac_value(settings.verification_hmac_key, f"verify:{verification_id}:{code}")


def hash_captcha(settings: Settings, challenge_id: str, answer: str) -> str:
    return hmac_value(
        settings.verification_hmac_key, f"captcha:{challenge_id}:{answer.strip().upper()}"
    )


def captcha_image_data_url(code: str) -> str:
    colors = ("#1f5c4f", "#314e75", "#7d4a36", "#45523b", "#62406e")
    glyphs = []
    for index, char in enumerate(code):
        x = 18 + index * 29 + secrets.randbelow(5)
        y = 36 + secrets.randbelow(9) - 4
        angle = secrets.randbelow(25) - 12
        glyphs.append(
            f'<text x="{x}" y="{y}" transform="rotate({angle} {x} {y})" font-family="Georgia,serif" font-size="30" font-weight="700" fill="{colors[index % len(colors)]}">{char}</text>'
        )
    glyph_markup = "".join(glyphs)
    dots = "".join(
        f'<circle cx="{secrets.randbelow(166) + 2}" cy="{secrets.randbelow(48) + 2}" r="{secrets.randbelow(2) + 1}" fill="#68716d" opacity=".35"/>'
        for _ in range(18)
    )
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="170" height="52" viewBox="0 0 170 52"><defs><linearGradient id="bg" x1="0" x2="1"><stop stop-color="#edf4ee"/><stop offset="1" stop-color="#d8e4db"/></linearGradient></defs><rect width="170" height="52" rx="4" fill="url(#bg)"/>{dots}<path d="M-4 37 C35 1 74 58 174 11" fill="none" stroke="#2f806e" stroke-width="2.2" opacity=".65"/><path d="M3 10 C49 48 112 -4 171 39" fill="none" stroke="#b95c50" stroke-width="1.3" opacity=".55"/>{glyph_markup}<path d="M9 47 L160 6" stroke="#68716d" stroke-width="1" opacity=".35"/></svg>"""
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()


def hash_refresh(settings: Settings, token: str) -> str:
    return hmac_value(settings.refresh_token_hmac_key, f"refresh:{token}")


def hash_ip(settings: Settings, ip: str) -> str:
    return hmac_value(settings.verification_hmac_key, f"ip:{ip}")


def new_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def encrypt_code(settings: Settings, code: str) -> str:
    return Fernet(settings.outbox_encryption_key.encode()).encrypt(code.encode()).decode()


def decrypt_code(settings: Settings, encrypted: str) -> str:
    return Fernet(settings.outbox_encryption_key.encode()).decrypt(encrypted.encode()).decode()


def new_totp_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def totp_code(secret: str, timestamp: int | None = None) -> str:
    counter = int((timestamp if timestamp is not None else time.time()) // 30)
    key = base64.b32decode(secret + "=" * (-len(secret) % 8), casefold=True)
    digest = hmac.new(key, counter.to_bytes(8, "big"), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = (int.from_bytes(digest[offset : offset + 4], "big") & 0x7FFF_FFFF) % 1_000_000
    return f"{value:06d}"


def verify_totp(secret: str, code: str, timestamp: int | None = None) -> bool:
    if not code or not code.isdigit() or len(code) != 6:
        return False
    now = int(timestamp if timestamp is not None else time.time())
    return any(
        hmac.compare_digest(totp_code(secret, now + offset * 30), code) for offset in (-1, 0, 1)
    )


def mint_access_token(settings: Settings, user_id: int, session_id: str) -> str:
    now = utcnow()
    claims = {
        "sub": str(user_id),
        "sid": session_id,
        "jti": secrets.token_urlsafe(18),
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_minutes),
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
    }
    return encode(
        claims,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
        headers={"kid": "current"},
    )


def verify_access_token(settings: Settings, token: str) -> dict:
    try:
        kid = get_unverified_header(token).get("kid", "current")
        key = (
            settings.jwt_secret_key
            if kid == "current"
            else settings.jwt_previous_secret_key
            if kid == "previous"
            else None
        )
        if not key:
            raise InvalidTokenError("unknown key")
        return decode(
            token,
            key,
            algorithms=[settings.jwt_algorithm],
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
            options={"require": ["sub", "sid", "jti", "iat", "exp", "iss", "aud"]},
        )
    except (DecodeError, ExpiredSignatureError, InvalidTokenError) as exc:
        raise ValueError("invalid access token") from exc


ADMIN_ISSUER = "study-admin-service"
ADMIN_AUDIENCE = "study-admin"


def mint_admin_access_token(settings: Settings, admin_id: int, session_id: str) -> str:
    """B 端短 access token，签发方/受众与学生端隔离。"""
    now = utcnow()
    claims = {
        "sub": str(admin_id),
        "sid": session_id,
        "jti": secrets.token_urlsafe(18),
        "iat": now,
        "exp": now + timedelta(minutes=settings.admin_access_minutes),
        "iss": ADMIN_ISSUER,
        "aud": ADMIN_AUDIENCE,
    }
    return encode(
        claims,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
        headers={"kid": "current"},
    )


def verify_admin_access_token(settings: Settings, token: str) -> dict:
    try:
        kid = get_unverified_header(token).get("kid", "current")
        key = (
            settings.jwt_secret_key
            if kid == "current"
            else settings.jwt_previous_secret_key
            if kid == "previous"
            else None
        )
        if not key:
            raise InvalidTokenError("unknown key")
        return decode(
            token,
            key,
            algorithms=[settings.jwt_algorithm],
            issuer=ADMIN_ISSUER,
            audience=ADMIN_AUDIENCE,
            options={"require": ["sub", "sid", "jti", "iat", "exp", "iss", "aud"]},
        )
    except (DecodeError, ExpiredSignatureError, InvalidTokenError) as exc:
        raise ValueError("invalid admin access token") from exc
