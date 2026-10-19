import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException


class RateLimiter:
    """Sliding-window counters, in memory (per server process)."""

    def __init__(self) -> None:
        self._hits: defaultdict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str, limit: int, window: float = 60) -> bool:
        """Count one hit; False when the key already reached `limit` within `window` seconds."""
        now = time.monotonic()
        with self._lock:
            hits = self._hits[key]
            while hits and now - hits[0] > window:
                hits.popleft()
            if len(hits) >= limit:
                return False
            hits.append(now)
            return True

    def blocked(self, key: str, limit: int, window: float = 60) -> bool:
        """True when the key already reached `limit` within `window` seconds, without counting a hit."""
        now = time.monotonic()
        with self._lock:
            hits = self._hits.get(key)
            if not hits:
                return False
            while hits and now - hits[0] > window:
                hits.popleft()
            return len(hits) >= limit

    def hit(self, key: str) -> None:
        """Count one hit without checking (pair with `blocked`, e.g. to count only failures)."""
        with self._lock:
            self._hits[key].append(time.monotonic())

    def check(self, key: str, limit: int, message: str = "Too many requests, please wait a moment",
              window: float = 60) -> None:
        if not self.allow(key, limit, window):
            raise HTTPException(429, message)

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


limiter = RateLimiter()
