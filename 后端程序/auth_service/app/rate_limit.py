import hashlib
import time
from collections import defaultdict, deque


class InMemoryRateLimiter:
    def __init__(self):
        self.events = defaultdict(deque)

    def allow(self, bucket: str, key: str, limit: int, window_seconds: int) -> bool:
        now = time.monotonic()
        events = self.events[(bucket, key)]
        while events and events[0] <= now - window_seconds:
            events.popleft()
        if len(events) >= limit:
            return False
        events.append(now)
        return True


class RateLimiterUnavailable(RuntimeError):
    """Redis must not silently degrade to per-process limiting in production."""


class RedisRateLimiter:
    _ALLOW_SCRIPT = """
local count = redis.call('INCR', KEYS[1])
if count == 1 or redis.call('TTL', KEYS[1]) < 0 then
  redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return count
"""

    def __init__(self, url: str):
        from redis import Redis

        self.client = Redis.from_url(url, decode_responses=True)

    def allow(self, bucket: str, key: str, limit: int, window_seconds: int) -> bool:
        redis_key = "auth-rate:" + hashlib.sha256(f"{bucket}:{key}".encode()).hexdigest()
        try:
            count = int(self.client.eval(self._ALLOW_SCRIPT, 1, redis_key, window_seconds))
        except Exception as exc:
            raise RateLimiterUnavailable("Redis rate limiter is unavailable") from exc
        return count <= limit
