"""Failed-login limiter. In-memory and per-process: enough for a small closed UAT.

Deployment note (refdocs/guides/env_setup.md): the key is the TCP peer address, so behind a
proxy uvicorn must be started with `--proxy-headers --forwarded-allow-ips=<proxy address>`
(never a wildcard), or every user shares the proxy's bucket. Run a single worker.
"""

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
