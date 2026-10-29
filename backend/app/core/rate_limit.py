"""Sliding-window rate limiting, shared through Redis when REDIS_URL is set.

Without Redis every API process keeps its own counters (fine for a single instance). With
several replicas set REDIS_URL so the limits apply across all of them. If Redis becomes
unreachable the limiter falls back to per-process counters instead of failing requests.
"""

from __future__ import annotations

import logging
import math
import time
import uuid
from collections import defaultdict, deque
from threading import Lock

from fastapi import HTTPException, Request, status

log = logging.getLogger(__name__)


class MemoryBackend:
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def _trim(self, q: deque[float], now: float, window: float) -> None:
        while q and q[0] <= now - window:
            q.popleft()

    async def hit(self, key: str, limit: int, window: float) -> float | None:
        """Record a hit. Returns None if allowed, otherwise seconds until a slot frees up."""
        now = time.monotonic()
        with self._lock:
            q = self._hits[key]
            self._trim(q, now, window)
            if len(q) >= limit:
                return max(0.0, q[0] + window - now)
            q.append(now)
            return None

    async def peek(self, key: str, limit: int, window: float) -> float | None:
        """Like hit() but without recording anything."""
        now = time.monotonic()
        with self._lock:
            q = self._hits.get(key)
            if not q:
                return None
            self._trim(q, now, window)
            return max(0.0, q[0] + window - now) if len(q) >= limit else None

    async def clear(self, key: str) -> None:
        with self._lock:
            self._hits.pop(key, None)

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


class RedisBackend:
    """One sorted set per key (scores = hit times), so the window slides exactly like MemoryBackend."""

    PREFIX = "dhanz:rl:"

    def __init__(self, client) -> None:
        self.client = client

    async def hit(self, key: str, limit: int, window: float) -> float | None:
        k, now = self.PREFIX + key, time.time()
        member = f"{now}:{uuid.uuid4().hex}"
        async with self.client.pipeline(transaction=True) as pipe:
            pipe.zremrangebyscore(k, 0, now - window)
            pipe.zadd(k, {member: now})
            pipe.zcard(k)
            pipe.zrange(k, 0, 0, withscores=True)
            pipe.expire(k, math.ceil(window) + 1)
            _, _, count, oldest, _ = await pipe.execute()
        if count > limit:
            await self.client.zrem(k, member)
            return max(0.0, oldest[0][1] + window - now)
        return None

    async def peek(self, key: str, limit: int, window: float) -> float | None:
        k, now = self.PREFIX + key, time.time()
        async with self.client.pipeline(transaction=True) as pipe:
            pipe.zremrangebyscore(k, 0, now - window)
            pipe.zcard(k)
            pipe.zrange(k, 0, 0, withscores=True)
            _, count, oldest = await pipe.execute()
        return max(0.0, oldest[0][1] + window - now) if count >= limit and oldest else None

    async def clear(self, key: str) -> None:
        await self.client.delete(self.PREFIX + key)


class RateLimiter:
    def __init__(self) -> None:
        self.memory = MemoryBackend()
        self.redis: RedisBackend | None = None

    def use_redis(self, client) -> None:
        self.redis = RedisBackend(client) if client is not None else None

    async def _call(self, method: str, *args):
        if self.redis is not None:
            try:
                return await getattr(self.redis, method)(*args)
            except Exception as exc:  # noqa: BLE001 - Redis outage must not take the API down
                log.warning("Redis rate limiter unavailable (%s); using per-process limits", exc)
        return await getattr(self.memory, method)(*args)

    async def hit(self, key: str, limit: int, window_seconds: float = 60.0) -> float | None:
        return await self._call("hit", key, limit, window_seconds)

    async def peek(self, key: str, limit: int, window_seconds: float = 60.0) -> float | None:
        return await self._call("peek", key, limit, window_seconds)

    async def clear(self, key: str) -> None:
        await self._call("clear", key)

    def reset(self) -> None:
        """Forget all per-process counters (tests)."""
        self.memory.reset()


limiter = RateLimiter()


def client_ip(request: Request) -> str:
    # Deploy behind a trusted proxy that sets X-Forwarded-For; uvicorn --proxy-headers rewrites client.host.
    return request.client.host if request.client else "unknown"


def too_many(retry_after: float, detail: str = "Too many requests. Please slow down.") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail=detail,
        headers={"Retry-After": str(int(retry_after) + 1)},
    )


async def enforce(key: str, limit: int, window_seconds: float = 60.0) -> None:
    retry_after = await limiter.hit(key, limit, window_seconds)
    if retry_after is not None:
        raise too_many(retry_after)
