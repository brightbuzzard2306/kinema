"""Deployment safeguards: shared access code, per-visitor rate limits and a daily Claude budget.

All state is in memory (one process). That is deliberate: the hosting plan has a single instance, a restart
only resets the counters, and the hard spending limit lives in the Anthropic console, not here.
"""

from __future__ import annotations

import hmac
import threading
import time
from collections import deque
from datetime import datetime, timezone


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
