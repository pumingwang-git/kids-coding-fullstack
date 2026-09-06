"""运行时日志配置与请求级关联。

业务审计仍写入 ``audit_events``；本模块只负责服务运行日志，不替代审计事实。
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
import uuid
from contextvars import ContextVar
from datetime import UTC, datetime

from starlette.types import ASGIApp, Message, Receive, Scope, Send

request_id_context: ContextVar[str | None] = ContextVar("request_id", default=None)
_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_HANDLER_MARKER = "_auth_service_runtime_handler"


class JsonFormatter(logging.Formatter):
    """输出稳定字段，方便直接被 Loki/ELK 等日志系统解析。"""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": record.getMessage(),
        }
        request_id = request_id_context.get()
        if request_id:
            payload["request_id"] = request_id
        for key in (
            "method", "path", "status_code", "duration_ms", "event_type", "outcome",
            "user_id", "admin_user_id", "resource_type", "resource_id", "task_id",
        ):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def log_business_event(logger: logging.Logger, event_type: str, outcome: str, **fields) -> None:
    """记录业务事件的运行侧投影；业务审计仍由调用方写入数据库。"""
    allowed = {
        key: value
        for key, value in fields.items()
        if key in {"user_id", "admin_user_id", "resource_type", "resource_id", "task_id"}
        and value is not None
    }
    logger.info("business event", extra={"event_type": event_type, "outcome": outcome, **allowed})


def configure_logging(level: str | None = None) -> None:
    """配置进程级 JSON 日志；重复创建测试 app 时不会叠加 handler。"""
    root = logging.getLogger()
    normalized_level = (level or os.getenv("LOG_LEVEL", "INFO")).upper()
    root.setLevel(getattr(logging, normalized_level, logging.INFO))
    # httpx 的默认 access log 会把完整 URL（包括 query string）写入日志。
    # 请求中间件已提供脱敏后的访问记录，因此关闭这份重复且可能泄漏的记录。
    logging.getLogger("httpx").setLevel(logging.WARNING)
    if any(getattr(handler, _HANDLER_MARKER, False) for handler in root.handlers):
        return
    handler = logging.StreamHandler()
    setattr(handler, _HANDLER_MARKER, True)
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)


def _request_id(headers: list[tuple[bytes, bytes]]) -> str:
    for name, value in headers:
        if name.lower() == b"x-request-id":
            candidate = value.decode("latin-1")
            if _SAFE_REQUEST_ID.fullmatch(candidate):
                return candidate
    return str(uuid.uuid4())


class RequestLoggingMiddleware:
    """记录每个 HTTP 请求的关联 ID、结果和耗时，不读取请求体。"""

    def __init__(self, app: ASGIApp):
        self.app = app
        self.logger = logging.getLogger("auth_service.request")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = _request_id(scope.get("headers", []))
        token = request_id_context.set(request_id)
        started = time.perf_counter()
        status_code: int | None = None

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
                headers = list(message.get("headers", []))
                headers.append((b"x-request-id", request_id.encode("ascii")))
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            self.logger.exception(
                "request failed",
                extra={
                    "method": scope.get("method"),
                    "path": scope.get("path"),
                    "status_code": status_code or 500,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                    "request_id": request_id,
                },
            )
            raise
        finally:
            if status_code is not None:
                self.logger.info(
                    "request completed",
                    extra={
                        "method": scope.get("method"),
                        "path": scope.get("path"),
                        "status_code": status_code,
                        "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                        "request_id": request_id,
                    },
                )
            request_id_context.reset(token)
