"""Tiny in-memory sliding-window rate limiter, keyed by (bucket, client IP).

Good enough for a single-process deployment. With several instances, move the
counters to Redis (or rate-limit at the reverse proxy instead).
"""

import threading
import time
from collections import deque
from typing import Optional


class RateLimiter:
    def __init__(self) -> None:
        self._hits: dict[tuple[str, str], deque] = {}
        self._lock = threading.Lock()

    def hit(self, bucket: str, ip: str, limit: int, window: float) -> Optional[int]:
        """Record one request. Returns None if allowed, else seconds to wait.

        limit <= 0 disables the check for that bucket.
        """
        if limit <= 0:
            return None
        now = time.monotonic()
        key = (bucket, ip)
        with self._lock:
            q = self._hits.setdefault(key, deque())
            while q and now - q[0] >= window:
                q.popleft()
            if len(q) >= limit:
                return max(1, int(window - (now - q[0])) + 1)
            q.append(now)
            return None

    def prune(self, max_window: float = 3600.0) -> None:
        """Drop idle keys so the dict can't grow forever."""
        now = time.monotonic()
        with self._lock:
            for key in [k for k, q in self._hits.items() if not q or now - q[-1] >= max_window]:
                del self._hits[key]
