"""Deployment safeguards: shared access code, per-visitor rate limits and a daily Claude budget.

All state is in memory (one process). That is deliberate: the hosting plan has a single instance, a restart
only resets the counters, and the hard spending limit lives in the Anthropic console, not here.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import threading
import time
from collections import deque
from datetime import datetime, timezone


def derive_token(code: str) -> str:
    """The value the browser keeps after a correct code: a slow, salted hash of it (stateless, so it survives restarts).

    Only /access/verify ever compares guesses against the real code (and it is rate limited). Every other route accepts this token,
    which cannot be guessed (256 bits) and cannot be turned back into the code cheaply. Changing the code invalidates every token.
    """
    return hashlib.pbkdf2_hmac("sha256", code.encode("utf-8"), b"kinema-access-token-v1", 200_000).hex()


def codes_match(given: str, expected: str) -> bool:
    """Constant-time comparison (no timing hints about how much of the code was right)."""
    return hmac.compare_digest(given.encode("utf-8"), expected.encode("utf-8"))


class SlidingWindow:
    """At most ``limit`` events per ``window`` seconds for each key."""

    def __init__(self, limit: int, window: float = 60.0) -> None:
        self.limit, self.window = limit, window
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def peek(self, key: str) -> bool:
        """Would one more event be allowed? (does not record anything)"""
        with self._lock:
            return self._count(key) < self.limit

    def hit(self, key: str) -> tuple[bool, int]:
        """Record an event. Returns (allowed, seconds until a slot frees up)."""
        now = time.monotonic()
        with self._lock:
            q = self._hits.setdefault(key, deque())
            self._trim(q, now)
            if len(q) >= self.limit:
                return False, max(1, int(q[0] + self.window - now) + 1)
            q.append(now)
            if len(self._hits) > 5000:  # forget visitors that went quiet
                for k in [k for k, v in self._hits.items() if not v or v[-1] < now - self.window]:
                    del self._hits[k]
            return True, 0

    def _count(self, key: str) -> int:
        q = self._hits.get(key)
        if not q:
            return 0
        self._trim(q, time.monotonic())
        return len(q)

    def _trim(self, q: deque[float], now: float) -> None:
        while q and q[0] <= now - self.window:
            q.popleft()


class DailyBudget:
    """A cap on Claude calls per UTC day (``limit <= 0`` means unlimited). Past the cap the app answers in offline mode."""

    def __init__(self, limit: int) -> None:
        self.limit = limit
        self._day = self._today()
        self._used = 0
        self._lock = threading.Lock()

    @staticmethod
    def _today() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def take(self) -> bool:
        if self.limit <= 0:
            return True
        with self._lock:
            today = self._today()
            if today != self._day:
                self._day, self._used = today, 0
            if self._used >= self.limit:
                return False
            self._used += 1
            return True

    @property
    def used(self) -> int:
        return self._used


# ------------------------------------------------------------------ request hygiene (pure ASGI, so it runs before any parsing or auth)
MAX_BODY_BYTES = 128 * 1024  # the largest legitimate request (a profile edit) is a few KB


class _TooLarge(BaseException):  # not an Exception on purpose: FastAPI turns any Exception raised while reading a body into a generic 400
    pass


class BodyLimitMiddleware:
    """Reject oversized request bodies BEFORE they are read into memory (a 60 MB body from a stranger used to add ~230 MB of RAM)."""

    def __init__(self, app, max_bytes: int = MAX_BODY_BYTES) -> None:
        self.app, self.max_bytes = app, max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        length = dict(scope["headers"]).get(b"content-length", b"")
        if length.isdigit() and int(length) > self.max_bytes:
            return await self._reject(send)
        received, started = 0, False

        async def counted_receive():
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:  # chunked upload that never declared its size
                    raise _TooLarge
            return message

        async def tracked_send(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, counted_receive, tracked_send)
        except _TooLarge:
            if not started:
                await self._reject(send)

    @staticmethod
    async def _reject(send) -> None:
        body = json.dumps({"error": {"code": "payload_too_large", "message": "That request is too large."}}).encode()
        await send({"type": "http.response.start", "status": 413, "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode()), (b"connection", b"close")]})
        await send({"type": "http.response.body", "body": body})


API_SECURITY_HEADERS = {
    b"x-content-type-options": b"nosniff",
    b"x-frame-options": b"DENY",
    b"referrer-policy": b"no-referrer",
    b"strict-transport-security": b"max-age=63072000",
    b"cache-control": b"no-store",  # API answers hold chat/profile data: never cache them in a shared proxy
}


class SecurityHeadersMiddleware:
    """Adds browser-protection headers to every API response (never overriding one a route set itself, e.g. the SSE cache-control)."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                present = {k.lower() for k, _ in message.get("headers", [])}
                message = {**message, "headers": [*message.get("headers", []), *[(k, v) for k, v in API_SECURITY_HEADERS.items() if k not in present]]}
            await send(message)

        await self.app(scope, receive, send_with_headers)
