"""Pembatasan jumlah pembuatan job per sesi/IP."""
from __future__ import annotations

import threading
import time
from collections import deque


class JobRateLimiter:
    def __init__(self, limit: int = 5, window_seconds: int = 3600) -> None:
        self.limit = max(1, limit)
        self.window_seconds = max(1, window_seconds)
        self._events: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str, now: float | None = None) -> tuple[bool, int]:
        """Return (allowed, retry_after_seconds) for a new job request."""
        current = time.monotonic() if now is None else now
        cutoff = current - self.window_seconds
        with self._lock:
            events = self._events.setdefault(key, deque())
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= self.limit:
                return False, max(1, int(events[0] + self.window_seconds - current))
            events.append(current)
            return True, 0

    def clear(self) -> None:
        with self._lock:
            self._events.clear()
