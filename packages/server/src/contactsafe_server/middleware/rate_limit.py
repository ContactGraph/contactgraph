"""Simple in-memory rate limiting for sensitive auth endpoints."""

from __future__ import annotations

import json
import time
from collections import defaultdict
from dataclasses import dataclass, field

from starlette.types import ASGIApp, Receive, Scope, Send

_DEFAULT_LIMIT: int = 30
_DEFAULT_WINDOW_SECONDS: float = 60.0

_PROTECTED_PREFIXES: tuple[str, ...] = (
    "/api/poll-connect/",
    "/api/public/",
    "/oauth/token",
    "/oauth/authorize",
)


@dataclass(slots=True)
class _RateBucket:
    window_start: float
    count: int = 0


@dataclass(slots=True)
class RateLimitState:
    buckets: dict[str, _RateBucket] = field(default_factory=dict)


def _client_key(scope: Scope) -> str:
    client: tuple[str, int] | None = scope.get("client")
    if client is not None:
        return f"{client[0]}:{client[1]}"
    return "unknown"


def _path_matches(path: str) -> bool:
    return any(path.startswith(prefix) for prefix in _PROTECTED_PREFIXES) or path in {
        "/oauth/token",
        "/oauth/authorize",
    }


class RateLimitMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        *,
        limit: int = _DEFAULT_LIMIT,
        window_seconds: float = _DEFAULT_WINDOW_SECONDS,
    ) -> None:
        self._app: ASGIApp = app
        self._limit: int = limit
        self._window_seconds: float = window_seconds
        self._state: RateLimitState = RateLimitState()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        path: str = scope.get("path", "")
        if not _path_matches(path):
            await self._app(scope, receive, send)
            return

        key: str = f"{_client_key(scope)}:{path}"
        now: float = time.monotonic()
        bucket: _RateBucket = self._state.buckets.get(key, _RateBucket(window_start=now))
        if now - bucket.window_start >= self._window_seconds:
            bucket = _RateBucket(window_start=now, count=0)
        bucket.count += 1
        self._state.buckets[key] = bucket

        if bucket.count > self._limit:
            await self._send_rate_limited(send)
            return

        await self._app(scope, receive, send)

    async def _send_rate_limited(self, send: Send) -> None:
        body: bytes = json.dumps(
            {"error": "rate_limit_exceeded", "detail": "Too many requests"}
        ).encode()
        headers: list[tuple[bytes, bytes]] = [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(body)).encode()),
            (b"retry-after", str(int(self._window_seconds)).encode()),
        ]
        await send({"type": "http.response.start", "status": 429, "headers": headers})
        await send({"type": "http.response.body", "body": body})
