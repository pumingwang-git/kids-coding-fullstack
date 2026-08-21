import hmac
import json
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response, status
from sqlalchemy import delete, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..mailer import deliver_outbox
from ..models import (
    AuditEvent,
    AuthSession,
    CaptchaChallenge,
    EmailOutbox,
    EmailVerification,
    MfaTotp,
    PasswordChangeVerification,
    PasswordReset,
    StudentProfile,
    User,
)
from ..password_history import archive_password, password_was_used_before
from ..pwned import enforce_breach_policy
from ..rate_limit import RateLimiterUnavailable
from ..schemas import (
    LoginRequest,
    MfaCodeRequest,
    PasswordChangeRequest,
    PasswordChangeVerificationRequest,
    PasswordResetConfirmRequest,
    PasswordResetRequest,
    RegisterRequest,
    ResendRequest,
    UserResponse,
    VerificationRequest,
)
from ..security import (
    DUMMY_PASSWORD_HASH,
    as_utc,
    captcha_image_data_url,
    decrypt_code,
    encrypt_code,
    hash_captcha,
    hash_code,
    hash_ip,
    hash_refresh,
    make_captcha_code,
    make_code,
    mint_access_token,
    new_csrf_token,
    new_refresh_token,
    new_totp_secret,
    normalize_email,
    normalize_username,
    password_hash,
    utcnow,
    verify_access_token,
    verify_totp,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])
GENERIC_LOGIN_ERROR = "账号或密码错误，或账号尚未激活。"
RESET_REQUEST_MESSAGE = "重置验证码已发送到已绑定邮箱。"


def db_session(request: Request):
    db = request.app.state.session_factory()
    # 错题缓存只在事务成功提交后失效，避免回滚请求污染 Redis 版本号。
    db.info["student_mistake_cache_redis_url"] = request.app.state.settings.redis_url
    try:
        yield db
    finally:
        db.close()


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def audit(db, settings, event, outcome, ip, user_id=None):
    db.add(
        AuditEvent(
            event_type=event, outcome=outcome, user_id=user_id, ip_hmac=hash_ip(settings, ip)
        )
    )


def set_cookie(response, key, value, request, httponly=True, max_age=None):
    response.set_cookie(
        key,
        value,
        httponly=httponly,
        secure=request.app.state.settings.cookie_secure,
        samesite="lax",
        max_age=max_age,
        path="/",
    )


def require_csrf(request: Request):
    cookie, header = request.cookies.get("csrf_token"), request.headers.get("X-CSRF-Token")
    if not cookie or not header or not hmac.compare_digest(cookie, header):
        raise HTTPException(403, "CSRF 校验失败。")


def limit(request: Request, bucket: str, key: str, maximum: int, seconds: int):
    try:
        allowed = request.app.state.rate_limiter.allow(bucket, key, maximum, seconds)
    except RateLimiterUnavailable as exc:
        raise HTTPException(503, "安全限流服务暂不可用，请稍后重试。") from exc
    if not allowed:
        raise HTTPException(429, "请求过于频繁，请稍后再试。")


def limit_soft(request: Request, bucket: str, key: str, maximum: int, seconds: int):
    """限流器不可用时**放行**的软限流。与 limit() 的差别只在故障姿态。

    limit() 守的是凭据爆破（登录/验证码/密码重置）：限流器一挂就必须拒绝，
    宁可登不上也不能把爆破窗口敞开——fail closed 是对的。

    limit_soft() 守的是资源滥用（/refresh、/csrf）：refresh token 是 48 字节随机串，
    爆破不现实，这里限的是打洪水。这类端点 fail closed 的代价是「Redis 抖一下 →
    全站在线用户集体续期失败 → 集体登出」，把一次缓存故障放大成一次全站事故，
    远比"限流短暂失效"严重。所以故障姿态必须反过来。
    """
    try:
        allowed = request.app.state.rate_limiter.allow(bucket, key, maximum, seconds)
    except RateLimiterUnavailable:
        return
    if not allowed:
        raise HTTPException(429, "请求过于频繁，请稍后再试。")


def lock_user(db: Session, *, email: str | None = None, username: str | None = None) -> User | None:
    filters = []
    if email:
        filters.append(User.email == email)
    if username:
        filters.append(User.username == username)
    return db.scalar(select(User).where(or_(*filters)).with_for_update()) if filters else None


def lock_user_by_id(db: Session, user_id: int) -> User | None:
    return db.scalar(select(User).where(User.id == user_id).with_for_update())


def queue_outbox(
    db: Session,
    settings,
    user: User,
    code: str | dict,
    event_type: str,
    verification_id: int | None = None,
) -> int:
    import json

    payload = json.dumps(code, ensure_ascii=False) if isinstance(code, dict) else code
    outbox = EmailOutbox(
        user_id=user.id,
        verification_id=verification_id,
        encrypted_code=encrypt_code(settings, payload),
        event_type=event_type,
        next_attempt_at=utcnow(),
    )
    db.add(outbox)
    db.flush()
    return outbox.id


def queue_verification(db: Session, settings, user: User) -> int:
    now = utcnow()
    db.execute(
        update(EmailVerification)
        .where(EmailVerification.user_id == user.id, EmailVerification.consumed_at.is_(None))
        .values(consumed_at=now)
    )
    verification = EmailVerification(
        user_id=user.id,
        code_hmac="pending",
        expires_at=now + timedelta(minutes=15),
        last_sent_at=now,
    )
    db.add(verification)
    db.flush()
    code = make_code()
    verification.code_hmac = hash_code(settings, verification.id, code)
    return queue_outbox(db, settings, user, code, "verification", verification.id)


def queue_password_reset(db: Session, settings, user: User) -> int:
    now = utcnow()
    db.execute(
        update(PasswordReset)
        .where(PasswordReset.user_id == user.id, PasswordReset.consumed_at.is_(None))
        .values(consumed_at=now)
    )
    reset = PasswordReset(
        user_id=user.id, code_hmac="pending", expires_at=now + timedelta(minutes=15)
    )
    db.add(reset)
    db.flush()
    code = make_code()
    reset.code_hmac = hash_code(settings, reset.id, code)
    return queue_outbox(db, settings, user, code, "password_reset")


def queue_password_change_verification(db: Session, settings, user: User) -> int:
    now = utcnow()
    db.execute(
        update(PasswordChangeVerification)
        .where(
            PasswordChangeVerification.user_id == user.id,
            PasswordChangeVerification.consumed_at.is_(None),
        )
        .values(consumed_at=now)
    )
    verification = PasswordChangeVerification(
        user_id=user.id,
        code_hmac="pending",
        expires_at=now + timedelta(minutes=15),
    )
    db.add(verification)
    db.flush()
    code = make_code()
    verification.code_hmac = hash_code(settings, verification.id, code)
    return queue_outbox(db, settings, user, code, "password_change")


def defer_delivery(background, request, outbox_ids):
    for outbox_id in outbox_ids:
        background.add_task(
            deliver_outbox,
            request.app.state.session_factory,
            request.app.state.mailer,
            request.app.state.settings,
            outbox_id,
        )


def verify_captcha(db: Session, settings, challenge_id: str | None, answer: str | None):
    if not settings.captcha_enabled:
        return
    now = utcnow()
    challenge = (
        db.scalar(
            select(CaptchaChallenge).where(CaptchaChallenge.id == challenge_id).with_for_update()
        )
        if challenge_id
        else None
    )
    valid = bool(
        challenge
        and answer
        and not challenge.consumed_at
        and as_utc(challenge.expires_at) >= now
        and challenge.attempt_count < 5
        and hmac.compare_digest(hash_captcha(settings, challenge_id, answer), challenge.answer_hmac)
    )
    if not valid:
        if challenge and not challenge.consumed_at:
            challenge.attempt_count += 1
            if challenge.attempt_count >= 5:
                challenge.consumed_at = now
        db.commit()
        raise HTTPException(400, "图片验证码无效或已过期，请刷新后重试。")
    challenge.consumed_at = now


@router.get("/captcha")
def captcha(request: Request, db: Session = Depends(db_session)):
    settings = request.app.state.settings
    limit(request, "captcha-ip", client_ip(request), 40, 300)
    now = utcnow()
    code, challenge_id = make_captcha_code(), str(uuid.uuid4())
    db.execute(
        delete(CaptchaChallenge).where(CaptchaChallenge.expires_at < now - timedelta(hours=24))
    )
    db.add(
        CaptchaChallenge(
            id=challenge_id,
            answer_hmac=hash_captcha(settings, challenge_id, code),
            expires_at=now + timedelta(minutes=5),
        )
    )
    db.commit()
    return {"captcha_id": challenge_id, "image": captcha_image_data_url(code), "expires_in": 300}


@router.get("/csrf")
def csrf(request: Request, response: Response):
    # 每次页面加载都会打一次，所以闸门开得很高——这里只是个滥用上限，不是安全边界。
    limit_soft(request, "csrf-ip", client_ip(request), 300, 300)
    set_cookie(
        response, "csrf_token", new_csrf_token(), request, httponly=False, max_age=60 * 60 * 8
    )
    return {"message": "ok"}


@router.post("/register", status_code=202)
def register(
    payload: RegisterRequest,
    request: Request,
    background: BackgroundTasks,
    db: Session = Depends(db_session),
):
    require_csrf(request)
    settings = request.app.state.settings
    ip = client_ip(request)
    email, username = normalize_email(str(payload.email)), normalize_username(payload.username)
    limit(request, "register-ip", ip, 8, 3600)
    limit(request, "register-email", email, 3, 3600)
    enforce_breach_policy(settings, payload.password)
    outbox_id = None
    try:
        user = lock_user(db, email=email, username=username)
        if not user:
            user = User(
                username=username, email=email, hashed_password=password_hash.hash(payload.password)
            )
            db.add(user)
            db.flush()
            outbox_id = queue_verification(db, settings, user)
            audit(db, settings, "register", "accepted", ip, user.id)
        elif user.email == email and user.status == "pending_verification":
            outbox_id = queue_verification(db, settings, user)
            audit(db, settings, "register", "resent", ip, user.id)
        else:
            audit(db, settings, "register", "generic", ip, user.id)
        db.commit()
    except IntegrityError:
        # A concurrent INSERT won the unique constraint. Return the same safe
        # accepted response rather than leaking a database error as HTTP 500.
        db.rollback()
        user = lock_user(db, email=email)
        if user and user.status == "pending_verification":
            outbox_id = queue_verification(db, settings, user)
            audit(db, settings, "register", "resent", ip, user.id)
            db.commit()
        else:
            audit(db, settings, "register", "generic", ip, user.id if user else None)
            db.commit()
    if outbox_id:
        defer_delivery(background, request, [outbox_id])
    return {"message": "如可创建或待验证，验证码已发送。", "verification_required": True}


@router.post("/verify-email")
def verify_email(payload: VerificationRequest, request: Request, db: Session = Depends(db_session)):
    require_csrf(request)
    settings = request.app.state.settings
    ip = client_ip(request)
    email = normalize_email(str(payload.email))
    limit(request, "verify-ip", ip, 15, 900)
    limit(request, "verify-email", email, 8, 900)
    user = lock_user(db, email=email)
    verification = (
        db.scalar(
            select(EmailVerification)
            .where(EmailVerification.user_id == user.id, EmailVerification.consumed_at.is_(None))
            .order_by(EmailVerification.id.desc())
            .with_for_update()
        )
        if user
        else None
    )
    now = utcnow()
    invalid = (
        not user
        or not verification
        or as_utc(verification.expires_at) < now
        or verification.attempt_count >= 5
    )
    if invalid:
        audit(db, settings, "email_verify", "failed", ip, user.id if user else None)
        db.commit()
        raise HTTPException(400, "验证码无效或已过期。")
    if not hmac.compare_digest(
        hash_code(settings, verification.id, payload.code), verification.code_hmac
    ):
        verification.attempt_count += 1
        if verification.attempt_count >= 5:
            verification.consumed_at = now
        audit(db, settings, "email_verify", "failed", ip, user.id)
        db.commit()
        raise HTTPException(400, "验证码无效或已过期。")
    verification.consumed_at = now
    user.status = "active"
    audit(db, settings, "email_verify", "success", ip, user.id)
    db.commit()
    return {"message": "邮箱验证完成。"}


@router.post("/resend-verification", status_code=202)
def resend(
    payload: ResendRequest,
    request: Request,
    background: BackgroundTasks,
    db: Session = Depends(db_session),
):
    require_csrf(request)
    settings = request.app.state.settings
    ip = client_ip(request)
    email = normalize_email(str(payload.email))
    limit(request, "resend-ip", ip, 8, 3600)
    limit(request, "resend-email", email, 3, 3600)
    user = lock_user(db, email=email)
    outbox_id = (
        queue_verification(db, settings, user)
        if user and user.status == "pending_verification"
        else None
    )
    audit(db, settings, "email_resend", "accepted", ip, user.id if user else None)
    db.commit()
    if outbox_id:
        defer_delivery(background, request, [outbox_id])
    return {"message": "如果账号待验证，新的验证码已发送。"}


def create_login_response(
    request: Request,
    user: User,
    db: Session,
    family_id: str | None = None,
    absolute_expires_at=None,
):
    settings = request.app.state.settings
    now = utcnow()
    raw_refresh = new_refresh_token()
    sid = str(uuid.uuid4())
    absolute_expires_at = absolute_expires_at or now + timedelta(
        days=settings.refresh_absolute_days
    )
    idle_expires_at = now + timedelta(days=settings.refresh_token_days)
    expires_at = min(idle_expires_at, as_utc(absolute_expires_at))
    db.add(
        AuthSession(
            id=sid,
            user_id=user.id,
            family_id=family_id or sid,
            refresh_token_hmac=hash_refresh(settings, raw_refresh),
            expires_at=expires_at,
            absolute_expires_at=absolute_expires_at,
        )
    )
    # 带 access_expires_at 给前端算主动续期时机（文档17 P1）。login/refresh 共用此响应，
    # 续期后前端据此更新定时器，不必重新调 /me。与 mint_access_token 里的 exp 同口径。
    access_exp_iso = (now + timedelta(minutes=settings.access_token_minutes)).isoformat()
    response = Response(
        content=json.dumps({"message": "登录成功。", "access_expires_at": access_exp_iso}),
        media_type="application/json",
    )
    refresh_seconds = max(0, int((as_utc(expires_at) - now).total_seconds()))
    set_cookie(
        response,
        "access_token",
        mint_access_token(settings, user.id, sid),
        request,
        max_age=settings.access_token_minutes * 60,
    )
    set_cookie(response, "refresh_token", raw_refresh, request, max_age=refresh_seconds)
    set_cookie(
        response, "csrf_token", new_csrf_token(), request, httponly=False, max_age=refresh_seconds
    )
    return response


def lock_delay_seconds(settings, failures: int) -> int:
    return min(
        settings.login_lock_base_seconds * (2 ** max(0, failures - settings.login_lock_threshold)),
        settings.login_lock_max_seconds,
    )


@router.post("/login")
def login(
    payload: LoginRequest,
    request: Request,
    background: BackgroundTasks,
    db: Session = Depends(db_session),
):
    require_csrf(request)
    settings = request.app.state.settings
    ip = client_ip(request)
    identity = payload.identifier.strip().casefold()
    limit(request, "login-ip", ip, 20, 900)
    limit(request, "login-id", identity, 8, 900)
    verify_captcha(db, settings, payload.captcha_id, payload.captcha_answer)
    conditions = [User.username == identity]
    if "@" in identity:
        conditions.append(User.email == normalize_email(identity))
    user = db.scalar(select(User).where(or_(*conditions)).with_for_update())
    password_ok = password_hash.verify(
        payload.password, user.hashed_password if user else DUMMY_PASSWORD_HASH
    )
    now = utcnow()
    mfa = db.get(MfaTotp, user.id) if settings.mfa_enabled and user else None
    mfa_ok = not (mfa and mfa.enabled_at) or verify_totp(
        decrypt_code(settings, mfa.encrypted_secret), payload.mfa_code or ""
    )
    locked = bool(user and user.locked_until and as_utc(user.locked_until) > now)
    if not user or not password_ok or user.status != "active" or locked or not mfa_ok:
        if user and not locked:
            user.failed_login_count += 1
            if user.failed_login_count >= settings.login_lock_threshold:
                user.locked_until = now + timedelta(
                    seconds=lock_delay_seconds(settings, user.failed_login_count)
                )
        audit(db, settings, "login", "failed", ip, user.id if user else None)
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, GENERIC_LOGIN_ERROR)
    user.failed_login_count = 0
    user.locked_until = None
    audit(db, settings, "login", "success", ip, user.id)
    response = create_login_response(request, user, db)
    db.commit()
    # Do not trust arbitrary X-Forwarded-For headers here. ProxyHeadersMiddleware
    # has already normalized request.client only when the peer is configured in
    # TRUSTED_PROXY_IPS; otherwise this is the direct socket peer.
    from ..login_risk import process_login_risk

    background.add_task(
        process_login_risk,
        request.app.state.session_factory,
        request.app.state.mailer,
        settings,
        user.id,
        ip,
        request.headers.get("user-agent", ""),
        request.headers.get("X-Device-Fingerprint"),
    )
    return response


def current_user(request: Request, db: Session = Depends(db_session)) -> User:
    try:
        claims = verify_access_token(
            request.app.state.settings, request.cookies.get("access_token") or ""
        )
    except ValueError:
        raise HTTPException(401, "登录已过期，请重新登录。")
    # 把 access_token 的 exp 顺手挂到 request.state，/me 据此返回 access_expires_at
    # 给前端算主动续期时机（文档17 P1）。不重复解 JWT。
    request.state.access_exp = claims.get("exp")
    session, user = db.get(AuthSession, claims["sid"]), db.get(User, int(claims["sub"]))
    now = utcnow()
    if (
        not session
        or session.user_id != int(claims["sub"])
        or session.revoked_at
        or as_utc(session.expires_at) < now
        or as_utc(session.absolute_expires_at) < now
        or not user
        or user.status != "active"
    ):
        raise HTTPException(401, "登录已失效，请重新登录。")
    return user


@router.get("/me", response_model=UserResponse)
def me(request: Request, user: User = Depends(current_user), db: Session = Depends(db_session)):
    settings = request.app.state.settings
    mfa = db.get(MfaTotp, user.id) if settings.mfa_enabled else None
    # current_user 已把 JWT 的 exp 挂到 request.state。exp 是 Unix timestamp（int），
    # 转成 aware UTC datetime，FastAPI 序列化为 ISO 字符串，前端 new Date(iso) 直用。
    access_exp = getattr(request.state, "access_exp", None)
    # 个人资料（文档 28 P2）：没建过资料行的老账号返回 None，前端回落默认头像。
    profile = db.get(StudentProfile, user.id)
    return UserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        status=user.status,
        mfa_enabled=bool(mfa and mfa.enabled_at),
        access_expires_at=(
            datetime.fromtimestamp(access_exp, tz=timezone.utc) if access_exp else None
        ),
        access_token_minutes=settings.access_token_minutes,
        avatar_url=profile.avatar_url if profile else None,
        learning_signature=profile.learning_signature if profile else None,
    )


@router.post("/refresh")
def refresh(request: Request, db: Session = Depends(db_session)):
    require_csrf(request)
    settings = request.app.state.settings
    now = utcnow()
    raw = request.cookies.get("refresh_token")
    # 两道闸，管的是两件不同的事：
    #   refresh-ip    洪水闸。开得远高于校园 NAT 的正常量（几百人共用一个出口 IP 是常态），
    #                 只拦真正的打洪水——这个端点每次都要 SELECT ... FOR UPDATE 上行锁。
    #   refresh-token 单会话闸。令牌每次续期成功就轮换，所以这个桶只会在**反复拿同一个
    #                 令牌失败**时累积，正好兜住前端续期风暴（客户端侧的闩锁见 auth.js）。
    limit_soft(request, "refresh-ip", client_ip(request), 300, 300)
    limit_soft(request, "refresh-token", hash_refresh(settings, raw or ""), 20, 300)
    session = db.scalar(
        select(AuthSession)
        .where(AuthSession.refresh_token_hmac == hash_refresh(settings, raw or ""))
        .with_for_update()
    )
    if session and session.revoked_at:
        # 宽限期内的“轮换后重放”视为并发刷新（多标签页/并发请求同时 401 后各自刷新），
        # 改取同族当前活跃会话继续正常轮换并留痕；超出宽限期才按令牌被盗吊销整个会话族。
        in_grace = (
            session.revocation_reason == "rotated"
            and as_utc(session.revoked_at) + timedelta(seconds=settings.refresh_reuse_grace_seconds) > now
        )
        if in_grace:
            audit(db, settings, "refresh", "reuse_in_grace", client_ip(request), session.user_id)
            live = db.scalar(
                select(AuthSession)
                .where(AuthSession.family_id == session.family_id, AuthSession.revoked_at.is_(None))
                .order_by(AuthSession.created_at.desc())
                .limit(1)
                .with_for_update()
            )
            if live:
                session = live
            else:
                db.commit()  # 会话族已被全部吊销，仅留下 reuse_in_grace 审计
                raise HTTPException(401, "登录已失效，请重新登录。")
        else:
            if session.revocation_reason == "rotated":
                db.execute(
                    update(AuthSession)
                    .where(AuthSession.family_id == session.family_id, AuthSession.revoked_at.is_(None))
                    .values(revoked_at=now, revocation_reason="refresh_reuse")
                )
                audit(db, settings, "refresh", "reuse_detected", client_ip(request), session.user_id)
                db.commit()
            raise HTTPException(401, "登录已失效，请重新登录。")
    if not session or as_utc(session.expires_at) < now or as_utc(session.absolute_expires_at) < now:
        raise HTTPException(401, "登录已过期，请重新登录。")
    user = db.get(User, session.user_id)
    if not user or user.status != "active":
        raise HTTPException(401, "登录已失效，请重新登录。")
    session.revoked_at = now
    session.revocation_reason = "rotated"
    audit(db, settings, "refresh", "success", client_ip(request), user.id)
    response = create_login_response(
        request, user, db, session.family_id, session.absolute_expires_at
    )
    db.commit()
    return response


@router.post("/logout", status_code=204)
def logout(request: Request, db: Session = Depends(db_session)):
    require_csrf(request)
    settings = request.app.state.settings
    raw = request.cookies.get("refresh_token")
    if raw:
        session = db.scalar(
            select(AuthSession)
            .where(AuthSession.refresh_token_hmac == hash_refresh(settings, raw))
            .with_for_update()
        )
        if session and not session.revoked_at:
            session.revoked_at = utcnow()
            session.revocation_reason = "logout"
            audit(db, settings, "logout", "success", client_ip(request), session.user_id)
            db.commit()
    response = Response(status_code=204)
    for name in ("access_token", "refresh_token", "csrf_token"):
        response.delete_cookie(name, path="/")
    return response


@router.post("/password-change/request", status_code=202)
def password_change_request(
    payload: PasswordChangeVerificationRequest,
    request: Request,
    background: BackgroundTasks,
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
):
    require_csrf(request)
    settings = request.app.state.settings
    ip = client_ip(request)
    limit(request, "password-change-request-ip", ip, 5, 900)
    limit(request, "password-change-request-user", f"user:{user.id}", 3, 900)
    locked_user = lock_user_by_id(db, user.id)
    if not locked_user or not password_hash.verify(
        payload.current_password, locked_user.hashed_password
    ):
        audit(db, settings, "password_change_request", "failed", ip, user.id)
        db.commit()
        raise HTTPException(400, "当前密码不正确。")
    outbox_id = queue_password_change_verification(db, settings, locked_user)
    audit(db, settings, "password_change_request", "accepted", ip, locked_user.id)
    db.commit()
    defer_delivery(background, request, [outbox_id])
    return {"message": "验证码已发送到已绑定邮箱，15 分钟内有效。"}


@router.post("/password-change")
def password_change(
    payload: PasswordChangeRequest,
    request: Request,
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
):
    """Change the password after current-password and email-code confirmation."""
    require_csrf(request)
    settings = request.app.state.settings
    ip = client_ip(request)
    now = utcnow()
    limit(request, "password-change-ip", ip, 10, 900)
    limit(request, "password-change-user", f"user:{user.id}", 5, 900)
    locked_user = lock_user_by_id(db, user.id)
    verification = db.scalar(
        select(PasswordChangeVerification)
        .where(
            PasswordChangeVerification.user_id == user.id,
            PasswordChangeVerification.consumed_at.is_(None),
        )
        .order_by(PasswordChangeVerification.id.desc())
        .with_for_update()
    )
    invalid = (
        not locked_user
        or not verification
        or as_utc(verification.expires_at) < now
        or verification.attempt_count >= 5
    )
    if not invalid and not hmac.compare_digest(
        hash_code(settings, verification.id, payload.code), verification.code_hmac
    ):
        verification.attempt_count += 1
        if verification.attempt_count >= 5:
            verification.consumed_at = now
        invalid = True
    if invalid:
        audit(db, settings, "password_change", "invalid_code", ip, user.id)
        db.commit()
        raise HTTPException(400, "邮箱验证码无效或已过期。")
    if not password_hash.verify(payload.current_password, locked_user.hashed_password):
        audit(db, settings, "password_change", "failed", ip, locked_user.id)
        db.commit()
        raise HTTPException(400, "当前密码不正确。")
    if password_was_used_before(
        db, locked_user.id, payload.new_password, current_hash=locked_user.hashed_password
    ):
        audit(db, settings, "password_change", "history_reuse", ip, user.id)
        db.commit()
        raise HTTPException(400, "新密码不能与当前或最近使用过的密码相同。")
    enforce_breach_policy(settings, payload.new_password)
    verification.consumed_at = now
    db.execute(
        update(AuthSession)
        .where(AuthSession.user_id == locked_user.id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=now, revocation_reason="password_change")
    )
    archive_password(
        db, locked_user.id, locked_user.hashed_password, settings.password_history_count
    )
    locked_user.hashed_password = password_hash.hash(payload.new_password)
    locked_user.failed_login_count = 0
    locked_user.locked_until = None
    response = create_login_response(request, locked_user, db)
    audit(db, settings, "password_change", "success", ip, locked_user.id)
    db.commit()
    return response


@router.post("/mfa/setup")
def mfa_setup(
    request: Request, user: User = Depends(current_user), db: Session = Depends(db_session)
):
    if not request.app.state.settings.mfa_enabled:
        raise HTTPException(404, "MFA 当前未启用。")
    require_csrf(request)
    mfa = db.scalar(select(MfaTotp).where(MfaTotp.user_id == user.id).with_for_update())
    if mfa and mfa.enabled_at:
        raise HTTPException(409, "MFA 已启用；请先使用受控流程停用。")
    secret = new_totp_secret()
    if mfa:
        mfa.encrypted_secret = encrypt_code(request.app.state.settings, secret)
    else:
        db.add(
            MfaTotp(
                user_id=user.id, encrypted_secret=encrypt_code(request.app.state.settings, secret)
            )
        )
    db.commit()
    issuer = request.app.state.settings.mfa_issuer
    return {
        "secret": secret,
        "otpauth_uri": f"otpauth://totp/{issuer}:{user.email}?secret={secret}&issuer={issuer}",
    }


@router.post("/mfa/confirm")
def mfa_confirm(
    payload: MfaCodeRequest,
    request: Request,
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
):
    if not request.app.state.settings.mfa_enabled:
        raise HTTPException(404, "MFA 当前未启用。")
    require_csrf(request)
    mfa = db.scalar(select(MfaTotp).where(MfaTotp.user_id == user.id).with_for_update())
    if not mfa or not verify_totp(
        decrypt_code(request.app.state.settings, mfa.encrypted_secret), payload.code
    ):
        raise HTTPException(400, "动态验证码无效。")
    mfa.enabled_at = utcnow()
    db.commit()
    return {"message": "MFA 已启用。"}


@router.post("/password-reset/request", status_code=202)
def password_reset_request(
    payload: PasswordResetRequest,
    request: Request,
    background: BackgroundTasks,
    db: Session = Depends(db_session),
):
    require_csrf(request)
    settings = request.app.state.settings
    ip = client_ip(request)
    email = normalize_email(str(payload.email))
    limit(request, "reset-ip", ip, 8, 3600)
    limit(request, "reset-email", email, 3, 3600)
    user = lock_user(db, email=email)
    if not user:
        audit(db, settings, "password_reset_request", "unregistered", ip)
        db.commit()
        raise HTTPException(status_code=404, detail="邮箱未注册，请先注册账号。")
    if user.status != "active":
        audit(db, settings, "password_reset_request", "inactive", ip, user.id)
        db.commit()
        raise HTTPException(status_code=400, detail="账号尚未完成邮箱验证，请先完成注册验证。")
    outbox_id = queue_password_reset(db, settings, user)
    audit(db, settings, "password_reset_request", "accepted", ip, user.id)
    db.commit()
    defer_delivery(background, request, [outbox_id])
    return {"message": RESET_REQUEST_MESSAGE}


@router.post("/password-reset/confirm")
def password_reset_confirm(
    payload: PasswordResetConfirmRequest, request: Request, db: Session = Depends(db_session)
):
    require_csrf(request)
    settings = request.app.state.settings
    ip = client_ip(request)
    email = normalize_email(str(payload.email))
    now = utcnow()
    limit(request, "reset-confirm-ip", ip, 12, 900)
    limit(request, "reset-confirm-email", email, 8, 900)
    user = lock_user(db, email=email)
    reset = (
        db.scalar(
            select(PasswordReset)
            .where(PasswordReset.user_id == user.id, PasswordReset.consumed_at.is_(None))
            .order_by(PasswordReset.id.desc())
            .with_for_update()
        )
        if user
        else None
    )
    invalid = not user or not reset or as_utc(reset.expires_at) < now or reset.attempt_count >= 5
    mfa = db.get(MfaTotp, user.id) if settings.mfa_enabled and user else None
    if (
        not invalid
        and mfa
        and mfa.enabled_at
        and not verify_totp(decrypt_code(settings, mfa.encrypted_secret), payload.mfa_code or "")
    ):
        invalid = True
    if not invalid and not hmac.compare_digest(
        hash_code(settings, reset.id, payload.code), reset.code_hmac
    ):
        reset.attempt_count += 1
        if reset.attempt_count >= 5:
            reset.consumed_at = now
        invalid = True
    if invalid:
        audit(db, settings, "password_reset_confirm", "failed", ip, user.id if user else None)
        db.commit()
        raise HTTPException(400, "验证码无效或已过期。")
    if password_was_used_before(
        db, user.id, payload.new_password, current_hash=user.hashed_password
    ):
        audit(db, settings, "password_reset_confirm", "history_reuse", ip, user.id)
        db.commit()
        raise HTTPException(400, "新密码不能与当前或最近使用过的密码相同。")
    enforce_breach_policy(settings, payload.new_password)
    reset.consumed_at = now
    archive_password(db, user.id, user.hashed_password, settings.password_history_count)
    user.hashed_password = password_hash.hash(payload.new_password)
    user.failed_login_count = 0
    user.locked_until = None
    db.execute(
        update(AuthSession)
        .where(AuthSession.user_id == user.id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=now, revocation_reason="password_reset")
    )
    audit(db, settings, "password_reset_confirm", "success", ip, user.id)
    db.commit()
    return {"message": "密码已重置，请重新登录。"}
