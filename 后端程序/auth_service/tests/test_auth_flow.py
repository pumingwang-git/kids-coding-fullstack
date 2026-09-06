from datetime import timedelta
from email.message import EmailMessage
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import select

from app.config import DEV_FERNET_KEY, Settings
from app.login_risk import process_login_risk
from app.mailer import build_login_alert_email, build_verification_email, safe_smtp_error
from app.main import create_app
from app.models import AuditEvent, AuthSession, LoginHistory, User
from app.pwned import enforce_breach_policy, sha1_hex
from app.rate_limit import RateLimiterUnavailable
from app.schemas import RegisterRequest
from app.security import mint_access_token, password_hash, totp_code, utcnow

PASSWORD = "A-long-password-123!"


def test_verification_email_has_html_and_plain_text():
    message = build_verification_email("sender@example.com", "learner@example.com", "123456")
    assert isinstance(message, EmailMessage)
    assert str(message["Subject"]) == "【启程学堂】注册邮箱验证码"
    assert str(message["To"]) == "learner@example.com"
    assert message.is_multipart()
    assert "123456" in message.get_body(preferencelist=("html",)).get_content()
    assert "完成本次注册" in message.get_body(preferencelist=("plain",)).get_content()


@pytest.mark.parametrize(
    "password",
    [
        "letters-only!",
        "123456789012!",
        "LettersAndDigits12",
        "A1!short",
    ],
)
def test_register_password_requires_12_characters_letter_number_and_symbol(password):
    with pytest.raises(ValidationError):
        RegisterRequest(username="learner", email="learner@example.com", password=password)


def test_register_password_accepts_matching_requirements():
    request = RegisterRequest(username="learner", email="learner@example.com", password=PASSWORD)
    assert request.password == PASSWORD


def test_smtp_error_redacts_email_addresses():
    error = RuntimeError("recipient learner@example.com was rejected")
    assert "learner@example.com" not in safe_smtp_error(error)
    assert "[redacted-email]" in safe_smtp_error(error)


def test_new_ip_alert_email_masks_ip_and_includes_security_action():
    message = build_login_alert_email(
        "sender@example.com",
        "learner@example.com",
        '{"ip":"203.0.113.55","city":"上海","time":"2026-08-04T10:00:00Z"}',
    )
    content = message.get_content()
    assert "203.0.113.***" in content
    assert "重置密码" in content


def test_first_login_creates_baseline_and_later_new_ip_sends_alert(tmp_path):
    with client(tmp_path) as test_client:
        headers = csrf_headers(test_client)
        active_client(test_client, headers, "riskuser", "risk@example.com")
        process_login_risk(
            test_client.app.state.session_factory,
            test_client.app.state.mailer,
            test_client.app.state.settings,
            1,
            "203.0.113.10",
            "Test Browser",
            None,
        )
        assert not [
            mail
            for mail in test_client.app.state.mailer.sent
            if mail["event_type"] == "login_alert"
        ]
        process_login_risk(
            test_client.app.state.session_factory,
            test_client.app.state.mailer,
            test_client.app.state.settings,
            1,
            "203.0.113.11",
            "Test Browser",
            None,
        )
        assert test_client.app.state.mailer.sent[-1]["event_type"] == "login_alert"
        db = test_client.app.state.session_factory()
        try:
            history = list(
                db.scalars(
                    select(LoginHistory).where(LoginHistory.user_id == 1).order_by(LoginHistory.id)
                )
            )
            assert len(history) == 2
            assert history[0].anomaly is False
            assert history[1].anomaly is True
            assert history[0].ip_hmac != "203.0.113.10"
        finally:
            db.close()


def test_production_rejects_default_outbox_encryption_key():
    settings = Settings(
        environment="production",
        database_url="postgresql+psycopg://user:password@127.0.0.1:5432/auth_test",
        jwt_secret_key="test-jwt-secret-not-for-production",
        verification_hmac_key="test-verification-hmac-not-for-production",
        refresh_token_hmac_key="test-refresh-hmac-not-for-production",
        outbox_encryption_key=DEV_FERNET_KEY,
        redis_url="redis://127.0.0.1:6379/0",
        cors_origins="https://app.example.test",
        cookie_secure=True,
        smtp_host="smtp.example.test",
        smtp_username="mailer",
        smtp_password="test-password",
        smtp_from="mailer@example.test",
    )
    with pytest.raises(RuntimeError, match="开发密钥"):
        settings.validate_production()


def client(tmp_path: Path, **overrides):
    settings = Settings(
        environment="test",
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        outbox_encryption_key=DEV_FERNET_KEY,
        cookie_secure=False,
        smtp_host=None,
        smtp_username=None,
        smtp_password=None,
        smtp_from=None,
        captcha_enabled=False,
        # 钉死 redis_url=None：与 test_exam.build_app 同因，避免 .env 的
        # REDIS_URL 让限流器升格 RedisRateLimiter、计数跨轮累积。
        redis_url=None,
        mfa_enabled=True,
        pwned_check_enabled=False,
        **overrides,
    )
    return TestClient(create_app(settings))


def csrf_headers(test_client):
    assert test_client.get("/api/auth/csrf").status_code == 200
    return {"X-CSRF-Token": test_client.cookies.get("csrf_token")}


def test_register_verify_login_and_logout(tmp_path):
    with client(tmp_path) as test_client:
        headers = csrf_headers(test_client)
        response = test_client.post(
            "/api/auth/register",
            headers=headers,
            json={"username": "learner", "email": "learner@example.com", "password": PASSWORD},
        )
        assert response.status_code == 202
        assert (
            test_client.post(
                "/api/auth/login",
                headers=headers,
                json={"identifier": "learner", "password": PASSWORD},
            ).status_code
            == 401
        )
        code = test_client.app.state.mailer.sent[-1]["code"]
        assert (
            test_client.post(
                "/api/auth/verify-email",
                headers=headers,
                json={"email": "learner@example.com", "code": code},
            ).status_code
            == 200
        )
        assert (
            test_client.post(
                "/api/auth/login",
                headers=headers,
                json={"identifier": "learner", "password": PASSWORD},
            ).status_code
            == 200
        )
        assert test_client.get("/api/auth/me").json()["username"] == "learner"
        headers = {"X-CSRF-Token": test_client.cookies.get("csrf_token")}
        assert test_client.post("/api/auth/logout", headers=headers).status_code == 204
        assert test_client.get("/api/auth/me").status_code == 401


def test_access_token_sid_and_sub_must_belong_to_same_user(tmp_path):
    with client(tmp_path) as test_client:
        db = test_client.app.state.session_factory()
        try:
            user_a = User(
                username="session-owner",
                email="session-owner@example.com",
                hashed_password=password_hash.hash(PASSWORD),
                status="active",
            )
            user_b = User(
                username="claim-target",
                email="claim-target@example.com",
                hashed_password=password_hash.hash(PASSWORD),
                status="active",
            )
            db.add_all([user_a, user_b])
            db.commit()
            # The session is created directly to keep this test focused on JWT binding.
            session = AuthSession(
                id="session-owner-id",
                user_id=user_a.id,
                family_id="session-owner-family",
                refresh_token_hmac="unused-refresh-hmac",
                expires_at=utcnow() + timedelta(hours=1),
                absolute_expires_at=utcnow() + timedelta(days=1),
            )
            db.add(session)
            db.commit()
            token = mint_access_token(test_client.app.state.settings, user_b.id, session.id)
        finally:
            db.close()
        test_client.cookies.set("access_token", token)
        assert test_client.get("/api/auth/me").status_code == 401


def test_resend_invalidates_previous_code(tmp_path):
    with client(tmp_path) as test_client:
        headers = csrf_headers(test_client)
        payload = {"username": "reader", "email": "reader@example.com", "password": PASSWORD}
        test_client.post("/api/auth/register", headers=headers, json=payload)
        first = test_client.app.state.mailer.sent[-1]["code"]
        test_client.post(
            "/api/auth/resend-verification", headers=headers, json={"email": "reader@example.com"}
        )
        second = test_client.app.state.mailer.sent[-1]["code"]
        assert first != second
        assert (
            test_client.post(
                "/api/auth/verify-email",
                headers=headers,
                json={"email": "reader@example.com", "code": first},
            ).status_code
            == 400
        )
        assert (
            test_client.post(
                "/api/auth/verify-email",
                headers=headers,
                json={"email": "reader@example.com", "code": second},
            ).status_code
            == 200
        )


def test_post_requires_csrf(tmp_path):
    with client(tmp_path) as test_client:
        response = test_client.post(
            "/api/auth/register",
            json={"username": "reader", "email": "reader@example.com", "password": PASSWORD},
        )
        assert response.status_code == 403


def test_refresh_token_reuse_revokes_its_session_family(tmp_path):
    # 严格模式（宽限期为 0）：重放旧 refresh token 吊销整个会话族。
    with client(tmp_path, refresh_reuse_grace_seconds=0) as test_client:
        headers = csrf_headers(test_client)
        payload = {"username": "refresher", "email": "refresher@example.com", "password": PASSWORD}
        assert (
            test_client.post("/api/auth/register", headers=headers, json=payload).status_code == 202
        )
        code = test_client.app.state.mailer.sent[-1]["code"]
        assert (
            test_client.post(
                "/api/auth/verify-email",
                headers=headers,
                json={"email": payload["email"], "code": code},
            ).status_code
            == 200
        )
        assert (
            test_client.post(
                "/api/auth/login",
                headers=headers,
                json={"identifier": payload["username"], "password": PASSWORD},
            ).status_code
            == 200
        )
        original_refresh = test_client.cookies.get("refresh_token")
        headers = {"X-CSRF-Token": test_client.cookies.get("csrf_token")}
        assert test_client.post("/api/auth/refresh", headers=headers).status_code == 200
        test_client.cookies.set("refresh_token", original_refresh)
        headers = {"X-CSRF-Token": test_client.cookies.get("csrf_token")}
        assert test_client.post("/api/auth/refresh", headers=headers).status_code == 401
        assert test_client.get("/api/auth/me").status_code == 401


def test_refresh_reuse_within_grace_is_treated_as_concurrent(tmp_path):
    # 宽限期内重放旧 refresh token 视为并发刷新（多标签页/并发请求）：正常轮换、留痕、不吊销会话族。
    with client(tmp_path) as test_client:
        headers = csrf_headers(test_client)
        payload = active_client(test_client, headers, username="gracer", email="gracer@example.com")
        assert (
            test_client.post(
                "/api/auth/login",
                headers=headers,
                json={"identifier": payload["username"], "password": PASSWORD},
            ).status_code
            == 200
        )
        original_refresh = test_client.cookies.get("refresh_token")
        headers = {"X-CSRF-Token": test_client.cookies.get("csrf_token")}
        assert test_client.post("/api/auth/refresh", headers=headers).status_code == 200
        test_client.cookies.set("refresh_token", original_refresh)
        headers = {"X-CSRF-Token": test_client.cookies.get("csrf_token")}
        assert test_client.post("/api/auth/refresh", headers=headers).status_code == 200
        assert test_client.get("/api/auth/me").status_code == 200
        db = test_client.app.state.session_factory()
        try:
            events = list(
                db.scalars(
                    select(AuditEvent).where(
                        AuditEvent.event_type == "refresh",
                        AuditEvent.outcome == "reuse_in_grace",
                    )
                )
            )
            assert len(events) == 1
        finally:
            db.close()


def test_refresh_reuse_after_grace_revokes(tmp_path):
    # 超出宽限期后重放仍按令牌被盗处理：吊销整个会话族。
    with client(tmp_path, refresh_reuse_grace_seconds=30) as test_client:
        headers = csrf_headers(test_client)
        payload = active_client(test_client, headers, username="late", email="late@example.com")
        assert (
            test_client.post(
                "/api/auth/login",
                headers=headers,
                json={"identifier": payload["username"], "password": PASSWORD},
            ).status_code
            == 200
        )
        original_refresh = test_client.cookies.get("refresh_token")
        headers = {"X-CSRF-Token": test_client.cookies.get("csrf_token")}
        assert test_client.post("/api/auth/refresh", headers=headers).status_code == 200
        db = test_client.app.state.session_factory()
        try:
            rotated = db.scalar(select(AuthSession).where(AuthSession.revocation_reason == "rotated"))
            rotated.revoked_at = utcnow() - timedelta(seconds=60)
            db.commit()
        finally:
            db.close()
        test_client.cookies.set("refresh_token", original_refresh)
        headers = {"X-CSRF-Token": test_client.cookies.get("csrf_token")}
        assert test_client.post("/api/auth/refresh", headers=headers).status_code == 401
        assert test_client.get("/api/auth/me").status_code == 401


def active_client(test_client, headers, username="secure", email="secure@example.com"):
    payload = {"username": username, "email": email, "password": PASSWORD}
    assert test_client.post("/api/auth/register", headers=headers, json=payload).status_code == 202
    code = test_client.app.state.mailer.sent[-1]["code"]
    assert (
        test_client.post(
            "/api/auth/verify-email", headers=headers, json={"email": email, "code": code}
        ).status_code
        == 200
    )
    return payload


def test_progressive_lock_rejects_correct_password_until_expiry(tmp_path):
    with client(tmp_path) as test_client:
        headers = csrf_headers(test_client)
        payload = active_client(test_client, headers)
        for _ in range(5):
            assert (
                test_client.post(
                    "/api/auth/login",
                    headers=headers,
                    json={"identifier": payload["username"], "password": "wrong-password"},
                ).status_code
                == 401
            )
        assert (
            test_client.post(
                "/api/auth/login",
                headers=headers,
                json={"identifier": payload["username"], "password": PASSWORD},
            ).status_code
            == 401
        )


def test_refresh_cannot_pass_absolute_session_expiry(tmp_path):
    with client(tmp_path) as test_client:
        headers = csrf_headers(test_client)
        payload = active_client(test_client, headers, "absolute", "absolute@example.com")
        assert (
            test_client.post(
                "/api/auth/login",
                headers=headers,
                json={"identifier": payload["username"], "password": PASSWORD},
            ).status_code
            == 200
        )
        db = test_client.app.state.session_factory()
        try:
            session = db.scalar(select(AuthSession).where(AuthSession.user_id == 1))
            session.absolute_expires_at = utcnow() - timedelta(seconds=1)
            db.commit()
        finally:
            db.close()
        headers = {"X-CSRF-Token": test_client.cookies.get("csrf_token")}
        assert test_client.post("/api/auth/refresh", headers=headers).status_code == 401


def test_mfa_and_password_reset_are_separate_security_flows(tmp_path):
    with client(tmp_path) as test_client:
        headers = csrf_headers(test_client)
        payload = active_client(test_client, headers, "mfauser", "mfa@example.com")
        assert (
            test_client.post(
                "/api/auth/login",
                headers=headers,
                json={"identifier": payload["username"], "password": PASSWORD},
            ).status_code
            == 200
        )
        headers = {"X-CSRF-Token": test_client.cookies.get("csrf_token")}
        setup = test_client.post("/api/auth/mfa/setup", headers=headers).json()
        assert (
            test_client.post(
                "/api/auth/mfa/confirm", headers=headers, json={"code": totp_code(setup["secret"])}
            ).status_code
            == 200
        )
        assert test_client.post("/api/auth/logout", headers=headers).status_code == 204
        headers = csrf_headers(test_client)
        assert (
            test_client.post(
                "/api/auth/login",
                headers=headers,
                json={"identifier": payload["username"], "password": PASSWORD},
            ).status_code
            == 401
        )
        assert (
            test_client.post(
                "/api/auth/login",
                headers=headers,
                json={
                    "identifier": payload["username"],
                    "password": PASSWORD,
                    "mfa_code": totp_code(setup["secret"]),
                },
            ).status_code
            == 200
        )
        headers = {"X-CSRF-Token": test_client.cookies.get("csrf_token")}
        assert (
            test_client.post(
                "/api/auth/password-reset/request",
                headers=headers,
                json={"email": payload["email"]},
            ).status_code
            == 202
        )
        reset_code = test_client.app.state.mailer.sent[-1]["code"]
        assert (
            test_client.post(
                "/api/auth/password-reset/confirm",
                headers=headers,
                json={
                    "email": payload["email"],
                    "code": reset_code,
                    "new_password": "A-new-password-123!",
                    "mfa_code": totp_code(setup["secret"]),
                },
            ).status_code
            == 200
        )
        headers = csrf_headers(test_client)
        assert (
            test_client.post(
                "/api/auth/login",
                headers=headers,
                json={
                    "identifier": payload["username"],
                    "password": PASSWORD,
                    "mfa_code": totp_code(setup["secret"]),
                },
            ).status_code
            == 401
        )
        assert (
            test_client.post(
                "/api/auth/login",
                headers=headers,
                json={
                    "identifier": payload["username"],
                    "password": "A-new-password-123!",
                    "mfa_code": totp_code(setup["secret"]),
                },
            ).status_code
            == 200
        )


def test_sha1_hex_matches_hibp_k_anonymity_format():
    # SHA-1 of "password" is a well-known Pwned Passwords entry; only the
    # first five characters ("5BAA6") are ever sent to the API.
    assert sha1_hex("password") == "5BAA61E4C9B93F3F0682250B6CF8331B7EE68FD8"


def test_breach_policy_rejects_or_fails_open(monkeypatch):
    from app import pwned

    stub = SimpleNamespace(
        pwned_check_enabled=True,
        pwned_check_strict=False,
        pwned_api_base_url="http://unused",
        pwned_timeout_seconds=0.5,
    )
    monkeypatch.setattr(pwned, "breach_count", lambda password, **kwargs: 42)
    with pytest.raises(HTTPException) as exc_info:
        enforce_breach_policy(stub, "Pwned-pass-123!")
    assert exc_info.value.status_code == 400
    assert "42" in exc_info.value.detail
    # Fail-open: an unavailable database allows the password.
    monkeypatch.setattr(pwned, "breach_count", lambda password, **kwargs: None)
    enforce_breach_policy(stub, "Pwned-pass-123!")
    # Fail-closed: strict mode refuses to proceed when the database is down.
    strict = SimpleNamespace(
        pwned_check_enabled=True,
        pwned_check_strict=True,
        pwned_api_base_url="http://unused",
        pwned_timeout_seconds=0.5,
    )
    with pytest.raises(HTTPException) as exc_info:
        enforce_breach_policy(strict, "Pwned-pass-123!")
    assert exc_info.value.status_code == 503


def test_register_rejects_breached_password(tmp_path, monkeypatch):
    from app import pwned

    settings = Settings(
        environment="test",
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        outbox_encryption_key=DEV_FERNET_KEY,
        cookie_secure=False,
        smtp_host=None,
        smtp_username=None,
        smtp_password=None,
        smtp_from=None,
        captcha_enabled=False,
        redis_url=None,
        mfa_enabled=True,
        pwned_check_enabled=True,
    )
    with TestClient(create_app(settings)) as test_client:
        headers = csrf_headers(test_client)
        monkeypatch.setattr(
            pwned, "breach_count", lambda password, **kwargs: 7 if "Pwned" in password else 0
        )
        response = test_client.post(
            "/api/auth/register",
            headers=headers,
            json={
                "username": "breached",
                "email": "breached@example.com",
                "password": "Pwned-pass-123!",
            },
        )
        assert response.status_code == 400
        assert "7" in response.json()["detail"]
        response = test_client.post(
            "/api/auth/register",
            headers=headers,
            json={"username": "cleanuser", "email": "clean@example.com", "password": PASSWORD},
        )
        assert response.status_code == 202


def test_password_reset_rejects_recently_used_passwords(tmp_path):
    with client(tmp_path) as test_client:
        headers = csrf_headers(test_client)
        payload = active_client(test_client, headers, "histuser", "hist@example.com")
        headers = {"X-CSRF-Token": test_client.cookies.get("csrf_token")}
        assert (
            test_client.post(
                "/api/auth/password-reset/request",
                headers=headers,
                json={"email": payload["email"]},
            ).status_code
            == 202
        )
        reset_code = test_client.app.state.mailer.sent[-1]["code"]
        assert (
            test_client.post(
                "/api/auth/password-reset/confirm",
                headers=headers,
                json={
                    "email": payload["email"],
                    "code": reset_code,
                    "new_password": "Fresh-pass-456!",
                },
            ).status_code
            == 200
        )
        # The original password is now archived and must be rejected.
        headers = {"X-CSRF-Token": test_client.cookies.get("csrf_token")}
        assert (
            test_client.post(
                "/api/auth/password-reset/request",
                headers=headers,
                json={"email": payload["email"]},
            ).status_code
            == 202
        )
        reset_code = test_client.app.state.mailer.sent[-1]["code"]
        response = test_client.post(
            "/api/auth/password-reset/confirm",
            headers=headers,
            json={"email": payload["email"], "code": reset_code, "new_password": PASSWORD},
        )
        assert response.status_code == 400
        assert "最近使用过" in response.json()["detail"]
        # The same reset code stays usable with a different, compliant password.
        response = test_client.post(
            "/api/auth/password-reset/confirm",
            headers=headers,
            json={
                "email": payload["email"],
                "code": reset_code,
                "new_password": "Another-pass-789!",
            },
        )
        assert response.status_code == 200


def test_password_reset_rejects_an_unregistered_email(tmp_path):
    with client(tmp_path) as test_client:
        headers = csrf_headers(test_client)
        response = test_client.post(
            "/api/auth/password-reset/request",
            headers=headers,
            json={"email": "unknown@example.com"},
        )
        assert response.status_code == 404
        assert "未注册" in response.json()["detail"]
        assert test_client.app.state.mailer.sent == []


def test_password_change_requires_current_password_and_revokes_other_sessions(tmp_path):
    with client(tmp_path) as test_client:
        headers = csrf_headers(test_client)
        payload = active_client(test_client, headers, "changer", "changer@example.com")
        assert (
            test_client.post(
                "/api/auth/login",
                headers=headers,
                json={"identifier": payload["username"], "password": PASSWORD},
            ).status_code
            == 200
        )
        session_a_refresh = test_client.cookies.get("refresh_token")
        # A second login creates a second session; cookies now belong to it.
        headers = {"X-CSRF-Token": test_client.cookies.get("csrf_token")}
        assert (
            test_client.post(
                "/api/auth/login",
                headers=headers,
                json={"identifier": payload["username"], "password": PASSWORD},
            ).status_code
            == 200
        )
        headers = {"X-CSRF-Token": test_client.cookies.get("csrf_token")}
        assert (
            test_client.post(
                "/api/auth/password-change/request",
                headers=headers,
                json={"current_password": "wrong-current"},
            ).status_code
            == 400
        )
        assert (
            test_client.post(
                "/api/auth/password-change/request",
                headers=headers,
                json={"current_password": PASSWORD},
            ).status_code
            == 202
        )
        change_code = test_client.app.state.mailer.sent[-1]["code"]
        assert (
            test_client.post(
                "/api/auth/password-change",
                headers=headers,
                json={
                    "current_password": PASSWORD,
                    "new_password": "Changed-pass-456!",
                    "code": "000000",
                },
            ).status_code
            == 400
        )
        # Reusing the current password is rejected before any change.
        assert (
            test_client.post(
                "/api/auth/password-change",
                headers=headers,
                json={"current_password": PASSWORD, "new_password": PASSWORD, "code": change_code},
            ).status_code
            == 400
        )
        assert (
            test_client.post(
                "/api/auth/password-change",
                headers=headers,
                json={
                    "current_password": PASSWORD,
                    "new_password": "Changed-pass-456!",
                    "code": change_code,
                },
            ).status_code
            == 200
        )
        # Every pre-change session is revoked and the response establishes a new one.
        test_client.cookies.set("refresh_token", session_a_refresh)
        headers = {"X-CSRF-Token": test_client.cookies.get("csrf_token")}
        assert test_client.post("/api/auth/refresh", headers=headers).status_code == 401
        assert test_client.get("/api/auth/me").status_code == 200
        # Old password no longer works; the new one does.
        headers = csrf_headers(test_client)
        assert (
            test_client.post(
                "/api/auth/login",
                headers=headers,
                json={"identifier": payload["username"], "password": PASSWORD},
            ).status_code
            == 401
        )
        assert (
            test_client.post(
                "/api/auth/login",
                headers=headers,
                json={"identifier": payload["username"], "password": "Changed-pass-456!"},
            ).status_code
            == 200
        )
        # The archived original password cannot be reused on the next change.
        headers = {"X-CSRF-Token": test_client.cookies.get("csrf_token")}
        assert (
            test_client.post(
                "/api/auth/password-change/request",
                headers=headers,
                json={"current_password": "Changed-pass-456!"},
            ).status_code
            == 202
        )
        change_code = test_client.app.state.mailer.sent[-1]["code"]
        response = test_client.post(
            "/api/auth/password-change",
            headers=headers,
            json={
                "current_password": "Changed-pass-456!",
                "new_password": PASSWORD,
                "code": change_code,
            },
        )
        assert response.status_code == 400
        assert "最近使用过" in response.json()["detail"]


def test_refresh_is_rate_limited_per_token(tmp_path):
    """会话真死之后，客户端如果没有闩锁就会每个请求都刷一次。

    前端已经加了闩锁（services/auth.js），但服务端不能把自己的可用性押在客户端行为上——
    /refresh 每次都要 SELECT ... FOR UPDATE 上行锁，必须自己有闸门。
    令牌桶只在"反复拿同一个令牌失败"时累积：续期成功会轮换令牌，正常用户早就换桶了。
    """
    with client(tmp_path) as test_client:
        headers = csrf_headers(test_client)
        test_client.cookies.set("refresh_token", "a-stale-refresh-token")
        statuses = [
            test_client.post("/api/auth/refresh", headers=headers).status_code for _ in range(22)
        ]
        assert statuses[:20] == [401] * 20  # 令牌无效，但还没撞闸
        assert statuses[20:] == [429, 429]


def test_limiter_outage_keeps_sessions_alive_but_still_blocks_login(tmp_path):
    """限流器故障姿态的分工：/refresh、/csrf fail open，/login fail closed。

    反过来的话，Redis 抖一下 = 全站在线用户续期失败 = 集体登出，
    一次缓存故障被放大成一次全站事故。而登录闸门守的是凭据爆破，挂了就必须拒。
    """
    with client(tmp_path) as test_client:
        headers = csrf_headers(test_client)
        payload = active_client(test_client, headers)
        login = {"identifier": payload["username"], "password": PASSWORD}
        assert test_client.post("/api/auth/login", headers=headers, json=login).status_code == 200

        class DeadLimiter:
            def allow(self, *args):
                raise RateLimiterUnavailable("redis is down")

        test_client.app.state.rate_limiter = DeadLimiter()

        assert test_client.get("/api/auth/csrf").status_code == 200
        headers = {"X-CSRF-Token": test_client.cookies.get("csrf_token")}
        assert test_client.post("/api/auth/refresh", headers=headers).status_code == 200
        headers = {"X-CSRF-Token": test_client.cookies.get("csrf_token")}
        assert test_client.post("/api/auth/login", headers=headers, json=login).status_code == 503
