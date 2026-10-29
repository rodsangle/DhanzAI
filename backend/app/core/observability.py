"""Request IDs, structured logs, Prometheus metrics and request-size limits.

* Every request gets an ID (taken from a valid incoming `X-Request-ID`, otherwise generated),
  returned in the `X-Request-ID` response header and attached to every log line.
* `LOG_FORMAT=json` writes one JSON object per line for log collectors (Loki, CloudWatch, ...).
* Metrics are exposed at `GET /metrics` when `METRICS_TOKEN` is set (Bearer auth).
"""

from __future__ import annotations

import contextvars
import json
import logging
import re
import time
import uuid

from prometheus_client import Counter, Gauge, Histogram

request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("request_id", default=None)
access_log = logging.getLogger("dhanz.access")

_VALID_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

# ---- metrics (process-wide; one API process per container) -------------------------------

HTTP_REQUESTS = Counter("dhanz_http_requests_total", "HTTP requests", ["method", "route", "status"])
HTTP_LATENCY = Histogram(
    "dhanz_http_request_duration_seconds",
    "Time to the response headers (streams continue afterwards)",
    ["method", "route"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)
CHAT_TURNS = Counter("dhanz_chat_replies_total", "Finished replies by outcome", ["outcome"])
LLM_TOKENS = Counter("dhanz_llm_tokens_total", "Tokens used, by provider", ["provider", "direction"])
ACTIVE_REPLIES = Gauge("dhanz_active_replies", "Replies currently being generated")
PUSH_SENT = Counter("dhanz_push_notifications_total", "Push notification attempts", ["platform", "result"])
MAINTENANCE_DELETED = Counter("dhanz_maintenance_deleted_total", "Rows removed by the retention job", ["kind"])


def record_reply(final_event: dict | None) -> None:
    final_event = final_event or {}
    CHAT_TURNS.labels(final_event.get("type", "unknown")).inc()
    message = final_event.get("message") or {}
    provider = message.get("provider")
    if provider:
        for direction in ("input", "output"):
            if tokens := message.get(f"{direction}_tokens"):
                LLM_TOKENS.labels(provider, direction).inc(tokens)


# ---- logging ---------------------------------------------------------------------------------


class _RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get() or "-"
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "time": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", None),
        }
        for key in ("method", "path", "status", "duration_ms", "user_id"):
            if hasattr(record, key):
                entry[key] = getattr(record, key)
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str)


def configure_logging(level: str, fmt: str) -> None:
    handler = logging.StreamHandler()
    handler.addFilter(_RequestIdFilter())
    if fmt == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s [%(request_id)s] %(name)s: %(message)s"))
    root = logging.getLogger()
    root.handlers = [h for h in root.handlers if not getattr(h, "_dhanz", False)]
    handler._dhanz = True  # type: ignore[attr-defined]
    root.addHandler(handler)
    root.setLevel(level)


# ---- middleware ------------------------------------------------------------------------------


def _route_template(scope) -> str:
    """The matched path template (e.g. /api/v1/conversations/{conversation_id}), so IDs don't explode labels."""
    # FastAPI keeps the full template (router prefix included) in its effective route context.
    context = (scope.get("fastapi") or {}).get("effective_route_context")
    template = getattr(context, "path_format", None) or getattr(scope.get("route"), "path", None)
    return template or "unmatched"


class RequestContextMiddleware:
    """Pure ASGI (does not buffer streamed responses)."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        incoming = dict(scope.get("headers") or []).get(b"x-request-id", b"").decode("latin-1")
        request_id = incoming if _VALID_ID.match(incoming) else uuid.uuid4().hex
        token = request_id_var.set(request_id)
        start = time.perf_counter()
        status_code = 500

        async def send_wrapper(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                message.setdefault("headers", [])
                message["headers"] = [*message["headers"], (b"x-request-id", request_id.encode())]
                duration = time.perf_counter() - start
                route = _route_template(scope)
                if route != "/metrics":
                    HTTP_REQUESTS.labels(scope["method"], route, str(status_code)).inc()
                    HTTP_LATENCY.labels(scope["method"], route).observe(duration)
                    access_log.info(
                        "%s %s %s %.1fms",
                        scope["method"],
                        scope["path"],
                        status_code,
                        duration * 1000,
                        extra={
                            "method": scope["method"],
                            "path": scope["path"],
                            "status": status_code,
                            "duration_ms": round(duration * 1000, 1),
                            "user_id": str((scope.get("state") or {}).get("user_id") or "") or None,
                        },
                    )
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            request_id_var.reset(token)


class BodySizeLimitMiddleware:
    """Refuse oversized request bodies before they are read into memory (HTTP 413)."""

    def __init__(self, app, *, default_limit: int, limits: dict[str, int]) -> None:
        self.app = app
        self.default_limit = default_limit
        self.limits = limits  # path suffix -> limit (uploads)

    def _limit_for(self, path: str) -> int:
        for suffix, limit in self.limits.items():
            if path.endswith(suffix):
                return limit
        return self.default_limit

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] in ("GET", "HEAD", "OPTIONS"):
            return await self.app(scope, receive, send)
        limit = self._limit_for(scope["path"])
        length = dict(scope.get("headers") or []).get(b"content-length")
        if length is not None and length.isdigit() and int(length) > limit:
            return await self._reject(send, limit)

        received = 0
        too_large = False

        async def limited_receive():
            nonlocal received, too_large
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    too_large = True
                    raise _TooLarge
            return message

        started = False

        async def tracking_send(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracking_send)
        except _TooLarge:
            if not started:
                await self._reject(send, limit)

    @staticmethod
    async def _reject(send, limit: int) -> None:
        body = json.dumps({"detail": f"Request too large (limit {limit // 1024} KB)"}).encode()
        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())],
            }
        )
        await send({"type": "http.response.body", "body": body})


class _TooLarge(Exception):
    pass
