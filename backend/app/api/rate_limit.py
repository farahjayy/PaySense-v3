"""Failed-login limiter. In-memory and per-process: enough for a small closed UAT."""

import time
from collections import deque
from collections.abc import Callable
from threading import Lock


class LoginRateLimiter:
    def __init__(
        self,
        max_failures: int = 10,
        window_seconds: float = 300,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._max = max_failures
        self._window = window_seconds
        self._clock = clock
        self._failures: dict[str, deque[float]] = {}
        self._lock = Lock()

    def _recent(self, key: str) -> deque[float]:
        cutoff = self._clock() - self._window
        stamps = self._failures.get(key)
        if stamps is None:
            return deque()
        while stamps and stamps[0] <= cutoff:
            stamps.popleft()
        if not stamps:
            del self._failures[key]
            return deque()
        return stamps

    def is_blocked(self, key: str) -> bool:
        with self._lock:
            return len(self._recent(key)) >= self._max

    def record_failure(self, key: str) -> None:
        with self._lock:
            stamps = self._recent(key)
            stamps.append(self._clock())
            self._failures[key] = stamps
