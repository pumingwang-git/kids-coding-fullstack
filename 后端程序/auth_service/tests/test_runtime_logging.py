import json
import logging
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import DEV_FERNET_KEY, Settings
from app.main import create_app


def _client(tmp_path: Path) -> TestClient:
    settings = Settings(
        environment="test",
        database_url=f"sqlite:///{tmp_path / 'logging.db'}",
        outbox_encryption_key=DEV_FERNET_KEY,
        redis_url=None,
        captcha_enabled=False,
        pwned_check_enabled=False,
        log_level="INFO",
    )
    return TestClient(create_app(settings))


def test_request_id_is_returned_and_logged_for_real_http_request(tmp_path, caplog):
    with _client(tmp_path) as client:
        with caplog.at_level(logging.INFO, logger="auth_service.request"):
            response = client.get("/api/auth/csrf", headers={"X-Request-ID": "trace-test-01"})

    assert response.status_code == 200
    assert response.headers["x-request-id"] == "trace-test-01"
    completed = next(record for record in caplog.records if record.message == "request completed")
    assert completed.request_id == "trace-test-01"
    assert completed.method == "GET"
    assert completed.path == "/api/auth/csrf"
    assert completed.status_code == 200
    assert completed.duration_ms >= 0


def test_request_log_does_not_include_query_string(tmp_path, caplog):
    secret = "token-that-must-not-be-logged"
    with _client(tmp_path) as client:
        with caplog.at_level(logging.INFO, logger="auth_service.request"):
            response = client.get(f"/api/auth/csrf?access_token={secret}")

    assert response.status_code == 200
    messages = [record.getMessage() for record in caplog.records]
    assert all(secret not in message for message in messages)
    completed = next(record for record in caplog.records if record.message == "request completed")
    assert completed.path == "/api/auth/csrf"


def test_json_formatter_emits_machine_readable_fields(caplog):
    from app.logging_config import JsonFormatter, request_id_context

    token = request_id_context.set("formatter-test")
    try:
        record = logging.LogRecord("test", logging.INFO, __file__, 1, "hello", (), None)
        record.method = "GET"
        record.path = "/health"
        record.status_code = 200
        record.duration_ms = 1.25
        payload = json.loads(JsonFormatter().format(record))
    finally:
        request_id_context.reset(token)

    assert payload["request_id"] == "formatter-test"
    assert payload["status_code"] == 200
    assert payload["duration_ms"] == 1.25
