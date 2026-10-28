"""In-process sliding-window rate limiter.

Suitable for a single backend instance. When running several replicas, put a shared
limiter (e.g. Redis or the reverse proxy) in front; see docs/SECURITY.md.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from threading import Lock

from fastapi import HTTPException, Request, status


class SlidingWindowLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def hit(self, key: str, limit: int, window_seconds: float = 60.0) -> float | None:
        """Record a hit. Returns None if allowed, otherwise seconds until a slot frees up."""
        now = time.monotonic()
        with self._lock:
            q = self._hits[key]
            while q and q[0] <= now - window_seconds:
                q.popleft()
            if len(q) >= limit:
                return max(0.0, q[0] + window_seconds - now)
            q.append(now)
            return None

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


limiter = SlidingWindowLimiter()


def client_ip(request: Request) -> str:
    # Deploy behind a trusted proxy that sets X-Forwarded-For; uvicorn --proxy-headers rewrites client.host.
    return request.client.host if request.client else "unknown"


def enforce(key: str, limit: int) -> None:
    retry_after = limiter.hit(key, limit)
    if retry_after is not None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Please slow down.",
            headers={"Retry-After": str(int(retry_after) + 1)},
        )
