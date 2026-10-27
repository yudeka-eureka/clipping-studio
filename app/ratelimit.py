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

    def allow(self, *keys: str, now: float | None = None) -> tuple[bool, int]:
        """Return (allowed, retry_after_seconds) for a new job request."""
        current = time.monotonic() if now is None else now
        cutoff = current - self.window_seconds
        # Satu request hanya boleh menambah satu hit per key. Selain mencegah
        # penghitungan ganda, ini menjaga pemeriksaan beberapa key tetap atomik.
        valid_keys = list(dict.fromkeys(k for k in keys if k))
        if not valid_keys:
            valid_keys = ["unknown"]

        with self._lock:
            # 1. Bersihkan entri lama dan cek apakah ada key yang melebihi batas
            for key in valid_keys:
                events = self._events.setdefault(key, deque())
                while events and events[0] <= cutoff:
                    events.popleft()
                if len(events) >= self.limit:
                    retry_after = max(1, int(events[0] + self.window_seconds - current))
                    return False, retry_after

            # 2. Jika semua key diizinkan, catat timestamp untuk tiap key
            for key in valid_keys:
                self._events[key].append(current)

            # 3. Pencegahan kebocoran memori (Memory Exhaustion DoS)
            if len(self._events) > 5000:
                stale = [k for k, q in self._events.items() if not q or q[-1] <= cutoff]
                for k in stale:
                    del self._events[k]

            return True, 0

    def clear(self) -> None:
        with self._lock:
            self._events.clear()
