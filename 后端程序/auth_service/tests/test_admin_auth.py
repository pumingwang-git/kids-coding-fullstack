from datetime import timedelta
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import DEV_FERNET_KEY, Settings
from app.database import build_database
from app.main import create_app
from app.models import AdminSession, AdminUser, AuditEvent, Base, SliderCaptchaChallenge
from app.security import decrypt_code, password_hash, utcnow

ADMIN_PASSWORD = "Admin-pass-123!"


def admin_client(tmp_path: Path, slider: bool = False, **overrides):
    settings = Settings(
        environment="test",
        database_url=f"sqlite:///{tmp_path / 'admin_test.db'}",
        outbox_encryption_key=DEV_FERNET_KEY,
        cookie_secure=False,
        smtp_host=None,
        smtp_username=None,
        smtp_password=None,
        smtp_from=None,
        captcha_enabled=False,
        # 钉死 redis_url=None：避免 .env 的 REDIS_URL 让限流器升格
        # RedisRateLimiter、计数跨轮累积（与 test_exam.build_app 同因）。
        redis_url=None,
        mfa_enabled=False,
        pwned_check_enabled=False,
        slider_captcha_enabled=slider,
        **overrides,
    )
    # Pre-create tables so the seed admin can be inserted before entering the
    # TestClient context (lifespan create_all runs only inside `with`).
    engine, _ = build_database(settings.database_url)
    Base.metadata.create_all(engine)
    engine.dispose()
    client = TestClient(create_app(settings))
    db = client.app.state.session_factory()
    try:
        db.add(
            AdminUser(
                username="root",
                password_hash=password_hash.hash(ADMIN_PASSWORD),
                display_name="Root",
                role="super_admin",
            )
        )
        db.commit()
    finally:
        db.close()
    return client


def admin_csrf_headers(client):
    assert client.get("/api/admin/csrf").status_code == 200
    return {"X-CSRF-Token": client.cookies.get("admin_csrf_token")}


def admin_login(client, headers, password=ADMIN_PASSWORD, username="root", slider_id=None, slider_x=None):
    return client.post(
        "/api/admin/login",
        headers=headers,
        json={
            "username": username,
            "password": password,
            "slider_id": slider_id,
            "slider_x": slider_x,
        },
    )


def test_admin_login_requires_csrf(tmp_path):
    with admin_client(tmp_path) as client:
        response = client.post(
            "/api/admin/login", json={"username": "root", "password": ADMIN_PASSWORD}
        )
        assert response.status_code == 403


def test_admin_login_success_me_logout(tmp_path):
    with admin_client(tmp_path) as client:
        headers = admin_csrf_headers(client)
        assert admin_login(client, headers).status_code == 200
        me = client.get("/api/admin/me")
        assert me.status_code == 200
        assert me.json()["username"] == "root"
        assert me.json()["role"] == "super_admin"
        headers = {"X-CSRF-Token": client.cookies.get("admin_csrf_token")}
        assert client.post("/api/admin/logout", headers=headers).status_code == 204
        assert client.get("/api/admin/me").status_code == 401


def test_admin_login_rejects_wrong_password(tmp_path):
    with admin_client(tmp_path) as client:
        headers = admin_csrf_headers(client)
        assert admin_login(client, headers, password="Wrong-pass-123!").status_code == 401
        assert admin_login(client, headers).status_code == 200


def test_admin_slider_captcha_required_and_verified(tmp_path):
    with admin_client(tmp_path, slider=True) as client:
        headers = admin_csrf_headers(client)
        challenge = client.get("/api/admin/captcha-slider").json()
        assert challenge["piece_size"] == 48
        # Wrong x is rejected and consumes one attempt.
        assert (
            admin_login(client, headers, slider_id=challenge["challenge_id"], slider_x=0).status_code
            == 400
        )
        # Correct x (decrypted from the DB, as the server sees it) is accepted.
        db = client.app.state.session_factory()
        try:
            row = db.scalar(
                select(SliderCaptchaChallenge).where(
                    SliderCaptchaChallenge.id == challenge["challenge_id"]
                )
            )
            answer = int(decrypt_code(client.app.state.settings, row.answer_x_encrypted))
        finally:
            db.close()
        assert (
            admin_login(
                client, headers, slider_id=challenge["challenge_id"], slider_x=answer
            ).status_code
            == 200
        )
        # The challenge is consumed: the same answer cannot be reused.
        headers = admin_csrf_headers(client)
        assert (
            admin_login(
                client, headers, slider_id=challenge["challenge_id"], slider_x=answer
            ).status_code
            == 400
        )


def test_admin_slider_verify_endpoint_does_not_consume(tmp_path):
    with admin_client(tmp_path, slider=True) as client:
        headers = admin_csrf_headers(client)
        challenge = client.get("/api/admin/captcha-slider").json()
        # Wrong x is rejected.
        response = client.post(
            "/api/admin/captcha-slider/verify",
            headers=headers,
            json={"slider_id": challenge["challenge_id"], "slider_x": 0},
        )
        assert response.status_code == 400
        # Correct x passes without consuming the challenge.
        db = client.app.state.session_factory()
        try:
            row = db.scalar(
                select(SliderCaptchaChallenge).where(
                    SliderCaptchaChallenge.id == challenge["challenge_id"]
                )
            )
            answer = int(decrypt_code(client.app.state.settings, row.answer_x_encrypted))
        finally:
            db.close()
        response = client.post(
            "/api/admin/captcha-slider/verify",
            headers=headers,
            json={"slider_id": challenge["challenge_id"], "slider_x": answer},
        )
        assert response.status_code == 200
        assert response.json() == {"ok": True}
        # The same challenge is still valid for login (consumed only there).
        assert (
            admin_login(
                client, headers, slider_id=challenge["challenge_id"], slider_x=answer
            ).status_code
            == 200
        )


def test_admin_verified_slider_survives_failed_login(tmp_path):
    """Regression: a verified challenge must not be consumed by a failed login."""
    with admin_client(tmp_path, slider=True) as client:
        headers = admin_csrf_headers(client)
        challenge = client.get("/api/admin/captcha-slider").json()
        db = client.app.state.session_factory()
        try:
            row = db.scalar(
                select(SliderCaptchaChallenge).where(
                    SliderCaptchaChallenge.id == challenge["challenge_id"]
                )
            )
            answer = int(decrypt_code(client.app.state.settings, row.answer_x_encrypted))
        finally:
            db.close()
        # Wrong password: 401, but the challenge stays valid.
        assert (
            admin_login(
                client, headers, password="Wrong-pass-123!",
                slider_id=challenge["challenge_id"], slider_x=answer,
            ).status_code
            == 401
        )
        # Retry with the correct password and the same challenge: 200.
        assert (
            admin_login(
                client, headers, slider_id=challenge["challenge_id"], slider_x=answer
            ).status_code
            == 200
        )


def test_admin_slider_misaligned_vs_expired_messages(tmp_path):
    """Misalignment keeps the challenge alive; exhausting attempts kills it."""
    with admin_client(tmp_path, slider=True) as client:
        headers = admin_csrf_headers(client)
        challenge = client.get("/api/admin/captcha-slider").json()
        for _ in range(4):
            response = client.post(
                "/api/admin/captcha-slider/verify",
                headers=headers,
                json={"slider_id": challenge["challenge_id"], "slider_x": 0},
            )
            assert response.status_code == 400
            assert "未对齐" in response.json()["detail"]
        # The 5th failure consumes the challenge.
        response = client.post(
            "/api/admin/captcha-slider/verify",
            headers=headers,
            json={"slider_id": challenge["challenge_id"], "slider_x": 0},
        )
        assert response.status_code == 400
        assert "已失效" in response.json()["detail"]


def test_admin_refresh_rotates_and_reuse_revokes(tmp_path):
    # 严格模式（宽限期为 0）：重放旧 refresh token 吊销整个会话族。
    with admin_client(tmp_path, admin_refresh_reuse_grace_seconds=0) as client:
        headers = admin_csrf_headers(client)
        assert admin_login(client, headers).status_code == 200
        original_refresh = client.cookies.get("admin_refresh_token")
        headers = {"X-CSRF-Token": client.cookies.get("admin_csrf_token")}
        assert client.post("/api/admin/refresh", headers=headers).status_code == 200
        # Replaying the old refresh token revokes the whole session family.
        client.cookies.set("admin_refresh_token", original_refresh)
        headers = {"X-CSRF-Token": client.cookies.get("admin_csrf_token")}
        assert client.post("/api/admin/refresh", headers=headers).status_code == 401
        assert client.get("/api/admin/me").status_code == 401


def test_admin_refresh_reuse_within_grace_is_treated_as_concurrent(tmp_path):
    # 宽限期内重放旧 refresh token 视为并发刷新（多标签页/并发请求）：正常轮换、留痕、不吊销会话族。
    with admin_client(tmp_path) as client:
        headers = admin_csrf_headers(client)
        assert admin_login(client, headers).status_code == 200
        original_refresh = client.cookies.get("admin_refresh_token")
        headers = {"X-CSRF-Token": client.cookies.get("admin_csrf_token")}
        assert client.post("/api/admin/refresh", headers=headers).status_code == 200
        client.cookies.set("admin_refresh_token", original_refresh)
        headers = {"X-CSRF-Token": client.cookies.get("admin_csrf_token")}
        assert client.post("/api/admin/refresh", headers=headers).status_code == 200
        assert client.get("/api/admin/me").status_code == 200
        db = client.app.state.session_factory()
        try:
            events = list(
                db.scalars(
                    select(AuditEvent).where(
                        AuditEvent.event_type == "admin_refresh",
                        AuditEvent.outcome == "reuse_in_grace",
                    )
                )
            )
            assert len(events) == 1
        finally:
            db.close()


def test_admin_refresh_reuse_after_grace_revokes(tmp_path):
    # 超出宽限期后重放仍按令牌被盗处理：吊销整个会话族。
    with admin_client(tmp_path, admin_refresh_reuse_grace_seconds=30) as client:
        headers = admin_csrf_headers(client)
        assert admin_login(client, headers).status_code == 200
        original_refresh = client.cookies.get("admin_refresh_token")
        headers = {"X-CSRF-Token": client.cookies.get("admin_csrf_token")}
        assert client.post("/api/admin/refresh", headers=headers).status_code == 200
        db = client.app.state.session_factory()
        try:
            rotated = db.scalar(select(AdminSession).where(AdminSession.revocation_reason == "rotated"))
            rotated.revoked_at = utcnow() - timedelta(seconds=60)
            db.commit()
        finally:
            db.close()
        client.cookies.set("admin_refresh_token", original_refresh)
        headers = {"X-CSRF-Token": client.cookies.get("admin_csrf_token")}
        assert client.post("/api/admin/refresh", headers=headers).status_code == 401
        assert client.get("/api/admin/me").status_code == 401
