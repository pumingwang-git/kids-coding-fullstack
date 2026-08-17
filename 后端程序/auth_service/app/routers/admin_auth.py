"""B 端管理后台认证：滑块验证码登录、会话轮换、CSRF、审计。

与学生端 auth_secure 同模式，但完全隔离：
- 独立 admin_users / admin_sessions 表
- 独立 cookie：admin_access_token / admin_refresh_token / admin_csrf_token
- JWT issuer/audience 独立（study-admin-service / study-admin）
- 审计事件 admin_ 前缀，admin_user_id 记录在 audit_events.admin_user_id
"""
import hmac
import json
import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from ..models import AdminSession, AdminUser, AuditEvent, SliderCaptchaChallenge
from ..permissions import (
    KNOWN_ROLE_NAMES,
    ROLE_LABELS,
    SUPER_ROLE,
    is_super,
    validate_admin_role,
)
from ..rate_limit import RateLimiterUnavailable
from ..schemas import (
    AdminLoginRequest,
    AdminRoleUpdateRequest,
    AdminStatusUpdateRequest,
    SliderVerifyRequest,
)
from ..security import (
    DUMMY_PASSWORD_HASH,
    as_utc,
    encrypt_code,
    hash_ip,
    hash_refresh,
    mint_admin_access_token,
    new_csrf_token,
    new_refresh_token,
    password_hash,
    utcnow,
    verify_admin_access_token,
)
from ..slider_captcha import (
    EXPIRED_MESSAGE,
    MISALIGNED_MESSAGE,
    PIECE,
    check_slider_challenge,
    consume_slider_challenge,
    create_slider_challenge,
)

router = APIRouter(prefix="/api/admin", tags=["admin"])
GENERIC_LOGIN_ERROR = "用户名或密码错误。"


def db_session(request: Request):
    db = request.app.state.session_factory()
    try:
        yield db
    finally:
        db.close()


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def audit(
    db,
    settings,
    event: str,
    outcome: str,
    ip: str,
    admin_user_id: int | None = None,
    *,
    resource_type: str | None = None,
    resource_id: int | None = None,
    summary: dict | None = None,
):
    db.add(
        AuditEvent(
            event_type=f"admin_{event}",
            outcome=outcome,
            admin_user_id=admin_user_id,
            ip_hmac=hash_ip(settings, ip),
            resource_type=resource_type,
            resource_id=resource_id,
            summary_json=json.dumps(summary, ensure_ascii=False, sort_keys=True) if summary else None,
        )
    )


def _admin_user_payload(admin: AdminUser) -> dict:
    return {
        "id": admin.id,
        "username": admin.username,
        "display_name": admin.display_name,
        "role": admin.role,
        "status": admin.status,
        "created_at": admin.created_at,
        "updated_at": admin.updated_at,
    }


ACTIVE_STATUS = "active"
DISABLED_STATUS = "disabled"


def _remaining_active_supers(db: Session, exclude_id: int) -> int:
    """除 exclude_id 外，还有几个能登录的超管。

    降级和停用是把超管降到零的两条路，而改角色只有超管能做（ADR-001 §2.4）——
    归零之后网页后台里再没有任何人能改回来，只能上服务器跑 create_admin 重建。
    两条路**共用这一处计数**：抄第二份就迟早会出现"改角色拦住了、停用没拦住"
    这种不报错的漏洞，正是 permissions.py 文件头警告过的失败模式。

    只数 active：停用的超管登不进来（current_admin 会 401），不构成兜底。
    """
    return db.scalar(
        select(func.count())
        .select_from(AdminUser)
        .where(
            AdminUser.role == SUPER_ROLE,
            AdminUser.status == ACTIVE_STATUS,
            AdminUser.id != exclude_id,
        )
    )


def _role_change_summary(
    *,
    old_role: str | None = None,
    new_role: str | None = None,
    reason_code: str | None = None,
) -> dict:
    summary: dict[str, int | str] = {"schema_version": 1}
    if old_role is not None:
        summary["old_role"] = old_role
    if new_role is not None:
        summary["new_role"] = new_role
    if reason_code is not None:
        summary["reason_code"] = reason_code
    return summary


def _status_change_summary(
    *,
    old_status: str | None = None,
    new_status: str | None = None,
    reason_code: str | None = None,
) -> dict:
    summary: dict[str, int | str] = {"schema_version": 1}
    if old_status is not None:
        summary["old_status"] = old_status
    if new_status is not None:
        summary["new_status"] = new_status
    if reason_code is not None:
        summary["reason_code"] = reason_code
    return summary


def _audit_admin_user_event(
    db: Session,
    request: Request,
    event: str,
    actor_id: int,
    target_id: int,
    outcome: str,
    summary: dict,
) -> None:
    """管理员账号类事件的统一落点：actor 进 admin_user_id，目标进 resource。

    两者不能倒置——《37、审计事件字段规范》§2.1、§6.2。
    """
    audit(
        db,
        request.app.state.settings,
        event,
        outcome,
        client_ip(request),
        actor_id,
        resource_type="admin_user",
        resource_id=target_id,
        summary=summary,
    )


def _audit_role_change(
    db: Session,
    request: Request,
    actor_id: int,
    target_id: int,
    outcome: str,
    summary: dict,
) -> None:
    _audit_admin_user_event(db, request, "role_change", actor_id, target_id, outcome, summary)


def _audit_status_change(
    db: Session,
    request: Request,
    actor_id: int,
    target_id: int,
    outcome: str,
    summary: dict,
) -> None:
    _audit_admin_user_event(
        db, request, "account_status_change", actor_id, target_id, outcome, summary
    )


def set_cookie(response: Response, key: str, value: str, request: Request, httponly=True, max_age=None):
    response.set_cookie(
        key,
        value,
        httponly=httponly,
        secure=request.app.state.settings.cookie_secure,
        samesite="lax",
        max_age=max_age,
        path="/",
    )


def limit(request: Request, bucket: str, key: str, maximum: int, seconds: int):
    if not request.app.state.rate_limiter.allow(bucket, key, maximum, seconds):
        raise HTTPException(429, "请求过于频繁，请稍后再试。")


def limit_soft(request: Request, bucket: str, key: str, maximum: int, seconds: int):
    """限流器不可用时**放行**的软限流。理由同 auth_secure.limit_soft：
    /refresh、/csrf 这类端点 fail closed 会把一次 Redis 故障放大成全员登出。"""
    try:
        allowed = request.app.state.rate_limiter.allow(bucket, key, maximum, seconds)
    except RateLimiterUnavailable:
        return
    if not allowed:
        raise HTTPException(429, "请求过于频繁，请稍后再试。")


def require_csrf(request: Request):
    cookie, header = request.cookies.get("admin_csrf_token"), request.headers.get("X-CSRF-Token")
    if not cookie or not header or not hmac.compare_digest(cookie, header):
        raise HTTPException(403, "CSRF 校验失败。")


@router.get("/csrf")
def csrf(request: Request, response: Response):
    limit_soft(request, "admin-csrf-ip", client_ip(request), 300, 300)
    set_cookie(response, "admin_csrf_token", new_csrf_token(), request, httponly=False, max_age=60 * 60 * 8)
    return {"message": "ok"}


@router.get("/captcha-slider")
def slider_captcha(request: Request, db: Session = Depends(db_session)):
    settings = request.app.state.settings
    limit(request, "admin-captcha-ip", client_ip(request), 40, 300)
    now = utcnow()
    db.execute(
        delete(SliderCaptchaChallenge).where(SliderCaptchaChallenge.expires_at < now - timedelta(hours=24))
    )
    challenge = create_slider_challenge()
    db.add(
        SliderCaptchaChallenge(
            id=challenge["challenge_id"],
            answer_x_encrypted=encrypt_code(settings, str(challenge["answer_x"])),
            answer_y=challenge["answer_y"],
            expires_at=challenge["expires_at"],
        )
    )
    db.commit()
    return {
        "challenge_id": challenge["challenge_id"],
        "background": challenge["background"],
        "piece": challenge["piece"],
        "piece_y": challenge["answer_y"],
        "piece_size": PIECE,
        "expires_in": 300,
    }


def lock_delay_seconds(settings, failures: int) -> int:
    return min(
        settings.login_lock_base_seconds * (2 ** max(0, failures - settings.login_lock_threshold)),
        settings.login_lock_max_seconds,
    )


def create_admin_login_response(request: Request, admin: AdminUser, db: Session, family_id: str | None = None):
    settings = request.app.state.settings
    now = utcnow()
    raw_refresh = new_refresh_token()
    sid = str(uuid.uuid4())
    absolute = now + timedelta(days=settings.admin_refresh_absolute_days)
    idle = now + timedelta(hours=settings.admin_refresh_hours)
    expires_at = min(idle, absolute)
    db.add(
        AdminSession(
            id=sid,
            admin_user_id=admin.id,
            family_id=family_id or sid,
            refresh_token_hmac=hash_refresh(settings, raw_refresh),
            expires_at=expires_at,
            absolute_expires_at=absolute,
        )
    )
    response = Response(content='{"message":"登录成功。"}', media_type="application/json")
    refresh_seconds = max(0, int((as_utc(expires_at) - now).total_seconds()))
    set_cookie(
        response,
        "admin_access_token",
        mint_admin_access_token(settings, admin.id, sid),
        request,
        max_age=settings.admin_access_minutes * 60,
    )
    set_cookie(response, "admin_refresh_token", raw_refresh, request, max_age=refresh_seconds)
    set_cookie(response, "admin_csrf_token", new_csrf_token(), request, httponly=False, max_age=refresh_seconds)
    return response


@router.post("/captcha-slider/verify")
def verify_slider(request: Request, payload: SliderVerifyRequest, db: Session = Depends(db_session)):
    """拖动松手后的预校验：通过不消费挑战，登录时再消费（一次性）。"""
    require_csrf(request)
    settings = request.app.state.settings
    limit(request, "admin-slider-verify-ip", client_ip(request), 20, 300)
    if settings.slider_captcha_enabled:
        slider_status = check_slider_challenge(db, settings, payload.slider_id, payload.slider_x)
        if slider_status != "valid":
            raise HTTPException(400, EXPIRED_MESSAGE if slider_status == "dead" else MISALIGNED_MESSAGE)
    return {"ok": True}


@router.post("/login")
def login(payload: AdminLoginRequest, request: Request, db: Session = Depends(db_session)):
    require_csrf(request)
    settings = request.app.state.settings
    ip = client_ip(request)
    username = payload.username.strip().casefold()
    limit(request, "admin-login-ip", ip, 10, 900)
    limit(request, "admin-login-user", username, 5, 900)
    # 滑块预校验：失败计一次尝试；成功不消费，登录完全成功后才消费。
    if settings.slider_captcha_enabled:
        slider_status = check_slider_challenge(db, settings, payload.slider_id, payload.slider_x)
        if slider_status != "valid":
            raise HTTPException(400, EXPIRED_MESSAGE if slider_status == "dead" else MISALIGNED_MESSAGE)
    admin = db.scalar(select(AdminUser).where(AdminUser.username == username).with_for_update())
    password_ok = password_hash.verify(payload.password, admin.password_hash if admin else DUMMY_PASSWORD_HASH)
    now = utcnow()
    locked = bool(admin and admin.locked_until and as_utc(admin.locked_until) > now)
    if not admin or not password_ok or admin.status != "active" or locked:
        if admin and not locked:
            admin.failed_login_count += 1
            if admin.failed_login_count >= settings.login_lock_threshold:
                admin.locked_until = now + timedelta(seconds=lock_delay_seconds(settings, admin.failed_login_count))
        audit(db, settings, "login", "failed", ip, admin.id if admin else None)
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, GENERIC_LOGIN_ERROR)
    # 密码与状态全部通过后才一次性消费滑块挑战；密码错误不消耗，可原地重试。
    if settings.slider_captcha_enabled:
        consume_slider_challenge(db, settings, payload.slider_id, payload.slider_x)
    admin.failed_login_count = 0
    admin.locked_until = None
    admin.last_login_at = now
    audit(db, settings, "login", "success", ip, admin.id)
    response = create_admin_login_response(request, admin, db)
    db.commit()
    return response


def current_admin(request: Request, db: Session = Depends(db_session)) -> AdminUser:
    try:
        claims = verify_admin_access_token(request.app.state.settings, request.cookies.get("admin_access_token") or "")
    except ValueError:
        raise HTTPException(401, "登录已过期，请重新登录。")
    session, admin = db.get(AdminSession, claims["sid"]), db.get(AdminUser, int(claims["sub"]))
    now = utcnow()
    if (
        not session
        or session.revoked_at
        or as_utc(session.expires_at) < now
        or as_utc(session.absolute_expires_at) < now
        or not admin
        or admin.status != "active"
    ):
        raise HTTPException(401, "登录已失效，请重新登录。")
    return admin


@router.get("/me")
def me(admin: AdminUser = Depends(current_admin)):
    return {
        "id": admin.id,
        "username": admin.username,
        "display_name": admin.display_name,
        "role": admin.role,
        "can_manage_admin_roles": is_super(admin),
    }


@router.get("/admin-users")
def list_admin_users(request: Request, db: Session = Depends(db_session)):
    actor = current_admin(request, db)
    if not is_super(actor):
        raise HTTPException(403, "仅超级管理员可查看后台账号角色。")
    admins = db.scalars(select(AdminUser).order_by(AdminUser.id)).all()
    return {
        "items": [_admin_user_payload(admin) for admin in admins],
        "roles": [
            {"value": role, "label": ROLE_LABELS[role]} for role in KNOWN_ROLE_NAMES
        ],
    }


@router.put("/admin-users/{admin_user_id}/role")
def update_admin_user_role(
    admin_user_id: int,
    payload: AdminRoleUpdateRequest,
    request: Request,
    db: Session = Depends(db_session),
):
    require_csrf(request)
    actor = current_admin(request, db)
    target = db.get(AdminUser, admin_user_id)

    if not is_super(actor):
        try:
            attempted_role = validate_admin_role(payload.role)
        except ValueError:
            attempted_role = None
        _audit_role_change(
            db,
            request,
            actor.id,
            admin_user_id,
            "failure",
            _role_change_summary(
                old_role=target.role if target else None,
                new_role=attempted_role,
                reason_code="forbidden",
            ),
        )
        db.commit()
        raise HTTPException(403, "仅超级管理员可变更后台账号角色。")

    try:
        new_role = validate_admin_role(payload.role)
    except ValueError as exc:
        _audit_role_change(
            db,
            request,
            actor.id,
            admin_user_id,
            "failure",
            _role_change_summary(
                old_role=target.role if target else None,
                reason_code="invalid_role",
            ),
        )
        db.commit()
        raise HTTPException(422, str(exc)) from exc

    target = db.scalar(
        select(AdminUser).where(AdminUser.id == admin_user_id).with_for_update()
    )
    if target is None:
        _audit_role_change(
            db,
            request,
            actor.id,
            admin_user_id,
            "failure",
            _role_change_summary(new_role=new_role, reason_code="not_found"),
        )
        db.commit()
        raise HTTPException(404, "后台账号不存在。")
    if target.role == new_role:
        _audit_role_change(
            db,
            request,
            actor.id,
            target.id,
            "failure",
            _role_change_summary(
                old_role=target.role,
                new_role=new_role,
                reason_code="conflict",
            ),
        )
        db.commit()
        raise HTTPException(409, "目标账号已经是该角色。")

    # 最后一名超管不能降级。交接不受影响：先把接班人提成超管，再改自己，两步都能过。
    # 计数与停用共用 _remaining_active_supers，见该函数的注释。
    if target.role == SUPER_ROLE and new_role != SUPER_ROLE:
        if not _remaining_active_supers(db, target.id):
            _audit_role_change(
                db,
                request,
                actor.id,
                target.id,
                "failure",
                _role_change_summary(
                    old_role=target.role,
                    new_role=new_role,
                    reason_code="invalid_state",
                ),
            )
            db.commit()
            raise HTTPException(409, "系统必须至少保留一名超级管理员。")

    old_role = target.role
    target.role = new_role
    _audit_role_change(
        db,
        request,
        actor.id,
        target.id,
        "success",
        _role_change_summary(old_role=old_role, new_role=new_role),
    )
    db.commit()
    return _admin_user_payload(target)


@router.put("/admin-users/{admin_user_id}/status")
def update_admin_user_status(
    admin_user_id: int,
    payload: AdminStatusUpdateRequest,
    request: Request,
    db: Session = Depends(db_session),
):
    """启用/停用后台账号（《41、管理端账号管理范围裁决》§2）。

    停用不删除任何历史数据：审计记录、内容关联全部原样保留，随时可以再启用。
    """
    require_csrf(request)
    actor = current_admin(request, db)
    new_status = payload.status
    target = db.get(AdminUser, admin_user_id)

    if not is_super(actor):
        _audit_status_change(
            db,
            request,
            actor.id,
            admin_user_id,
            "failure",
            _status_change_summary(
                old_status=target.status if target else None,
                new_status=new_status,
                reason_code="forbidden",
            ),
        )
        db.commit()
        raise HTTPException(403, "仅超级管理员可变更后台账号状态。")

    target = db.scalar(
        select(AdminUser).where(AdminUser.id == admin_user_id).with_for_update()
    )
    if target is None:
        _audit_status_change(
            db,
            request,
            actor.id,
            admin_user_id,
            "failure",
            _status_change_summary(new_status=new_status, reason_code="not_found"),
        )
        db.commit()
        raise HTTPException(404, "后台账号不存在。")
    if target.status == new_status:
        _audit_status_change(
            db,
            request,
            actor.id,
            target.id,
            "failure",
            _status_change_summary(
                old_status=target.status,
                new_status=new_status,
                reason_code="conflict",
            ),
        )
        db.commit()
        raise HTTPException(409, "目标账号已经是该状态。")

    # 停用最后一名活跃超管与降级同源：都会让角色管理彻底失去可操作的人。
    if new_status == DISABLED_STATUS and target.role == SUPER_ROLE:
        if not _remaining_active_supers(db, target.id):
            _audit_status_change(
                db,
                request,
                actor.id,
                target.id,
                "failure",
                _status_change_summary(
                    old_status=target.status,
                    new_status=new_status,
                    reason_code="invalid_state",
                ),
            )
            db.commit()
            raise HTTPException(409, "系统必须至少保留一名启用状态的超级管理员。")

    old_status = target.status
    target.status = new_status
    if new_status == DISABLED_STATUS:
        # current_admin() 已按 status 拦住（401），停用本身就即时生效；显式吊销
        # 是让 admin_sessions 的记录与事实一致，便于审计复盘，不是安全兜底。
        db.execute(
            update(AdminSession)
            .where(
                AdminSession.admin_user_id == target.id,
                AdminSession.revoked_at.is_(None),
            )
            .values(revoked_at=utcnow(), revocation_reason="account_disabled")
        )
    _audit_status_change(
        db,
        request,
        actor.id,
        target.id,
        "success",
        _status_change_summary(old_status=old_status, new_status=new_status),
    )
    db.commit()
    return _admin_user_payload(target)


@router.post("/refresh")
def refresh(request: Request, db: Session = Depends(db_session)):
    require_csrf(request)
    settings = request.app.state.settings
    now = utcnow()
    raw = request.cookies.get("admin_refresh_token")
    # 两道闸，见 auth_secure.refresh 的说明：IP 桶拦洪水，令牌桶兜前端续期风暴。
    # 管理端并发用户远少于学员端，闸门相应收紧。
    limit_soft(request, "admin-refresh-ip", client_ip(request), 120, 300)
    limit_soft(request, "admin-refresh-token", hash_refresh(settings, raw or ""), 20, 300)
    session = db.scalar(
        select(AdminSession)
        .where(AdminSession.refresh_token_hmac == hash_refresh(settings, raw or ""))
        .with_for_update()
    )
    if session and session.revoked_at:
        # 宽限期内的“轮换后重放”视为并发刷新（多标签页/并发请求同时 401 后各自刷新），
        # 改取同族当前活跃会话继续正常轮换；超出宽限期才按令牌被盗吊销整个会话族。
        in_grace = (
            session.revocation_reason == "rotated"
            and as_utc(session.revoked_at) + timedelta(seconds=settings.admin_refresh_reuse_grace_seconds) > now
        )
        if in_grace:
            # 留痕：区分“前端已修好、不再并发刷新”与“并发仍存在、被宽限期吸收”。
            audit(db, settings, "refresh", "reuse_in_grace", client_ip(request), session.admin_user_id)
            live = db.scalar(
                select(AdminSession)
                .where(
                    AdminSession.family_id == session.family_id,
                    AdminSession.revoked_at.is_(None),
                )
                .order_by(AdminSession.created_at.desc())
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
                    update(AdminSession)
                    .where(
                        AdminSession.family_id == session.family_id,
                        AdminSession.revoked_at.is_(None),
                    )
                    .values(revoked_at=now, revocation_reason="refresh_reuse")
                )
                audit(db, settings, "refresh", "reuse_detected", client_ip(request), session.admin_user_id)
                db.commit()
            raise HTTPException(401, "登录已失效，请重新登录。")
    if not session or as_utc(session.expires_at) < now or as_utc(session.absolute_expires_at) < now:
        raise HTTPException(401, "登录已过期，请重新登录。")
    admin = db.get(AdminUser, session.admin_user_id)
    if not admin or admin.status != "active":
        raise HTTPException(401, "登录已失效，请重新登录。")
    session.revoked_at = now
    session.revocation_reason = "rotated"
    audit(db, settings, "refresh", "success", client_ip(request), admin.id)
    response = create_admin_login_response(request, admin, db, session.family_id)
    db.commit()
    return response


@router.post("/logout", status_code=204)
def logout(request: Request, db: Session = Depends(db_session)):
    require_csrf(request)
    settings = request.app.state.settings
    raw = request.cookies.get("admin_refresh_token")
    if raw:
        session = db.scalar(
            select(AdminSession).where(AdminSession.refresh_token_hmac == hash_refresh(settings, raw)).with_for_update()
        )
        if session and not session.revoked_at:
            session.revoked_at = utcnow()
            session.revocation_reason = "logout"
            audit(db, settings, "logout", "success", client_ip(request), session.admin_user_id)
            db.commit()
    response = Response(status_code=204)
    for name in ("admin_access_token", "admin_refresh_token", "admin_csrf_token"):
        response.delete_cookie(name, path="/")
    return response
