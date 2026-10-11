import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException


class RateLimiter:
    """Sliding one-minute window, in memory (per server process)."""

    def __init__(self) -> None:
        self._hits: defaultdict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str, limit: int, message: str = "Too many requests, please wait a moment") -> None:
        now = time.monotonic()
        with self._lock:
            hits = self._hits[key]
            while hits and now - hits[0] > 60:
                hits.popleft()
            if len(hits) >= limit:
                raise HTTPException(429, message)
            hits.append(now)

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


limiter = RateLimiter()
