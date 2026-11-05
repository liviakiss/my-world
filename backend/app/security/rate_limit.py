import time
from collections import defaultdict, deque
from threading import Lock

from fastapi import HTTPException, Request, status

MAX_TRACKED_KEYS = 10_000


class RateLimiter:
    def __init__(self, max_requests: int, window_seconds: int) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def __call__(self, request: Request) -> None:
        client_ip = request.client.host if request.client else "unknown"
        key = f"{request.url.path}:{client_ip}"
        now = time.monotonic()
        window_start = now - self.window_seconds

        with self._lock:
            if len(self._hits) > MAX_TRACKED_KEYS:
                self._prune(window_start)

            hits = self._hits[key]
            while hits and hits[0] <= window_start:
                hits.popleft()

            if len(hits) >= self.max_requests:
                retry_after = int(hits[0] - window_start) + 1
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Too many requests. Try again later.",
                    headers={"Retry-After": str(retry_after)},
                )
            hits.append(now)

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()

    def _prune(self, window_start: float) -> None:
        stale = [key for key, hits in self._hits.items() if not hits or hits[-1] <= window_start]
        for key in stale:
            del self._hits[key]


signup_limiter = RateLimiter(max_requests=5, window_seconds=60)
login_limiter = RateLimiter(max_requests=10, window_seconds=60)
refresh_limiter = RateLimiter(max_requests=30, window_seconds=60)

ALL_LIMITERS = (signup_limiter, login_limiter, refresh_limiter)


def reset_rate_limits() -> None:
    for limiter in ALL_LIMITERS:
        limiter.reset()
