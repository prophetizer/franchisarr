"""A shared outgoing-request limiter.

Lived in `tmdb_client` until fanart.tv needed the same thing. Both talk to a third party that
owes us nothing, and a first scan of a large library is exactly the traffic pattern that looks
like abuse if it goes out unthrottled.
"""

from __future__ import annotations

import threading
import time


class RateLimiter:
    """Smooths outgoing requests to a fixed ceiling. Thread-safe, since a scheduled scan and a
    web request can both be talking to the same API at once."""

    def __init__(self, max_per_second: int) -> None:
        self._min_interval = 1.0 / max(1, max_per_second)
        self._lock = threading.Lock()
        self._next_allowed = 0.0

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            sleep_for = self._next_allowed - now
            self._next_allowed = max(now, self._next_allowed) + self._min_interval
        if sleep_for > 0:
            time.sleep(sleep_for)
