"""答疑 WebSocket 的本机连接管理与 Redis 跨进程广播。"""
from __future__ import annotations

import asyncio
import json
import logging
import secrets
import threading
import uuid
from collections import defaultdict
from collections.abc import Mapping

from fastapi import WebSocket
from fastapi.encoders import jsonable_encoder

logger = logging.getLogger(__name__)
_CHANNEL_PATTERN = "help:line:*"
_TICKET_PREFIX = "help:ws-ticket:"
_TICKET_TTL_SECONDS = 60


class HelpRealtimeUnavailable(RuntimeError):
    """Redis is required for cross-process realtime delivery and WS tickets."""

class HelpRealtimeHub:
    def __init__(self) -> None:
        self._students: dict[int, set[WebSocket]] = defaultdict(set)
        self._admins: dict[int, set[WebSocket]] = defaultdict(set)
        self._loop: asyncio.AbstractEventLoop | None = None
        self._redis = None
        self._listener: threading.Thread | None = None
        self._stop = threading.Event()
        self._instance_id = uuid.uuid4().hex

    def start(self, redis_url: str | None) -> None:
        if not redis_url or self._listener is not None:
            return
        from redis import Redis

        self._redis = Redis.from_url(redis_url, decode_responses=True)
        self._stop.clear()
        self._listener = threading.Thread(target=self._listen, name="help-realtime-redis", daemon=True)
        self._listener.start()

    def stop(self) -> None:
        self._stop.set()
        listener, self._listener = self._listener, None
        if listener is not None:
            listener.join(timeout=2)
        if self._redis is not None:
            self._redis.close()
            self._redis = None
        self._loop = None

    def _listen(self) -> None:
        try:
            assert self._redis is not None
            with self._redis.pubsub(ignore_subscribe_messages=True) as pubsub:
                pubsub.psubscribe(_CHANNEL_PATTERN)
                while not self._stop.is_set():
                    message = pubsub.get_message(timeout=1)
                    if message is None or message.get("type") != "pmessage":
                        continue
                    try:
                        event = json.loads(message["data"])
                        if event.get("origin") != self._instance_id:
                            self._deliver(event)
                    except (TypeError, ValueError, KeyError):
                        logger.warning("ignored malformed help realtime event")
        except Exception:
            if not self._stop.is_set():
                logger.exception("help realtime Redis subscription stopped")

    async def connect_student(self, user_id: int, websocket: WebSocket) -> None:
        await websocket.accept(subprotocol="help-v1")
        self._loop = asyncio.get_running_loop()
        self._students[user_id].add(websocket)

    async def connect_admin(self, admin_id: int, websocket: WebSocket) -> None:
        await websocket.accept(subprotocol="help-v1")
        self._loop = asyncio.get_running_loop()
        self._admins[admin_id].add(websocket)

    def disconnect_student(self, user_id: int, websocket: WebSocket) -> None:
        self._discard(self._students, user_id, websocket)

    def disconnect_admin(self, admin_id: int, websocket: WebSocket) -> None:
        self._discard(self._admins, admin_id, websocket)

    @staticmethod
    def _discard(groups: dict[int, set[WebSocket]], principal_id: int, websocket: WebSocket) -> None:
        sockets = groups.get(principal_id)
        if not sockets:
            return
        sockets.discard(websocket)
        if not sockets:
            groups.pop(principal_id, None)

    def issue_ticket(self, principal_type: str, principal_id: int) -> str:
        if self._redis is None:
            raise HelpRealtimeUnavailable("Redis is unavailable")
        ticket = secrets.token_urlsafe(32)
        try:
            self._redis.setex(
                f"{_TICKET_PREFIX}{ticket}",
                _TICKET_TTL_SECONDS,
                f"{principal_type}:{principal_id}",
            )
        except Exception as exc:
            raise HelpRealtimeUnavailable("Redis is unavailable") from exc
        return ticket

    def consume_ticket(self, ticket: str | None, principal_type: str, principal_id: int) -> bool:
        if not ticket or self._redis is None:
            return False
        try:
            value = self._redis.getdel(f"{_TICKET_PREFIX}{ticket}")
        except Exception:
            logger.exception("failed to consume help realtime ticket")
            return False
        return value == f"{principal_type}:{principal_id}"

    def publish(
        self,
        *,
        line_id: int,
        student_id: int,
        admin_ids: set[int],
        event: str,
        serialized_payload: Mapping[str, object] | None = None,
    ) -> None:
        event_payload = {
            "origin": self._instance_id,
            "type": "help_chat_line_changed",
            "event": event,
            "chat_line_id": line_id,
            "student_id": student_id,
            "admin_ids": sorted(admin_ids),
        }
        if serialized_payload is not None:
            event_payload["payload"] = jsonable_encoder(serialized_payload)
        self._deliver(event_payload)
        if self._redis is not None:
            try:
                self._redis.publish(
                    f"help:line:{line_id}", json.dumps(event_payload, separators=(",", ":"))
                )
            except Exception:
                logger.exception("failed to publish help realtime event")

    def _deliver(self, event: Mapping[str, object]) -> None:
        if self._loop is None or self._loop.is_closed():
            return
        student_id = event.get("student_id")
        admin_ids = event.get("admin_ids")
        if not isinstance(student_id, int) or not isinstance(admin_ids, list):
            return
        payload = {
            "type": event["type"],
            "event": event["event"],
            "chat_line_id": event["chat_line_id"],
        }
        message_payload = event.get("payload")
        if isinstance(message_payload, dict):
            payload["payload"] = message_payload
        sockets = set(self._students.get(student_id, set()))
        for admin_id in admin_ids:
            if isinstance(admin_id, int):
                sockets.update(self._admins.get(admin_id, set()))
        if sockets:
            asyncio.run_coroutine_threadsafe(self._send(payload, sockets), self._loop)

    async def _send(self, payload: dict[str, int | str], sockets: set[WebSocket]) -> None:
        for websocket in sockets:
            try:
                await websocket.send_json(payload)
            except Exception:
                # 断开的连接会在接收循环退出时清理；发送失败不能影响已提交的业务写入。
                pass


help_realtime_hub = HelpRealtimeHub()
