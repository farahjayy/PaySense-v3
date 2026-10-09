"""Failed-login limiter. In-memory and per-process: enough for a small closed UAT.

Deployment note (refdocs/guides/env_setup.md): the key is the TCP peer address, so behind a
proxy uvicorn must be started with `--proxy-headers --forwarded-allow-ips=<proxy address>`
(never a wildcard), or every user shares the proxy's bucket. Run a single worker.
"""

import math
import time
from collections import deque
from collections.abc import Callable
from threading import Lock


class LoginRateLimiter:
    def __init__(
        self,
        max_failures: int = 10,
        window_seconds: float = 300,
        max_keys: int = 10_000,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._max = max_failures
        self.window_seconds = window_seconds
        self._max_keys = max_keys
        self._clock = clock
        self._failures: dict[str, deque[float]] = {}
        self._lock = Lock()

    def _recent(self, key: str) -> deque[float]:
        cutoff = self._clock() - self.window_seconds
        stamps = self._failures.get(key)
        if stamps is None:
            return deque()
        while stamps and stamps[0] <= cutoff:
            stamps.popleft()
        if not stamps:
            del self._failures[key]
            return deque()
        return stamps

    def _enforce_key_cap(self) -> None:
        if len(self._failures) <= self._max_keys:
            return
        for key in list(self._failures):  # first drop everything already expired
            self._recent(key)
        while len(self._failures) > self._max_keys:  # then the oldest keys (insertion order)
            del self._failures[next(iter(self._failures))]

    def tracked_keys(self) -> int:
        with self._lock:
            return len(self._failures)

    def is_blocked(self, key: str) -> bool:
        with self._lock:
            return len(self._recent(key)) >= self._max

    def record_failure(self, key: str) -> None:
        with self._lock:
            stamps = self._recent(key)
            stamps.append(self._clock())
            self._failures[key] = stamps
            self._enforce_key_cap()


class RequestRateLimiter:
    """Sliding-window cap on how often one user may call an expensive route.

    Same in-memory, single-process trade-off as the login limiter. Requests that are refused are
    not recorded, so hammering a blocked route does not extend the block.
    """

    def __init__(self, max_keys: int = 10_000, clock: Callable[[], float] = time.monotonic) -> None:
        self._max_keys = max_keys
        self._clock = clock
        self._hits: dict[str, deque[float]] = {}
        self._lock = Lock()

    def allow(self, key: str, max_requests: int, window_seconds: float) -> tuple[bool, int]:
        """(allowed, seconds to wait if not). Records the request only when it is allowed."""
        with self._lock:
            now = self._clock()
            stamps = self._hits.setdefault(key, deque())
            while stamps and stamps[0] <= now - window_seconds:
                stamps.popleft()
            if len(stamps) >= max_requests:
                return False, max(1, math.ceil(stamps[0] + window_seconds - now))
            stamps.append(now)
            self._enforce_key_cap(now, window_seconds)
            return True, 0

    def _enforce_key_cap(self, now: float, window_seconds: float) -> None:
        if len(self._hits) <= self._max_keys:
            return
        for key in [k for k, v in self._hits.items() if not v or v[-1] <= now - window_seconds]:
            del self._hits[key]
        while len(self._hits) > self._max_keys:  # then the oldest keys (insertion order)
            del self._hits[next(iter(self._hits))]

    def tracked_keys(self) -> int:
        with self._lock:
            return len(self._hits)
