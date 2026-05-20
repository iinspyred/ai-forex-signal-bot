import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Deque

from fastapi import HTTPException, Request, status


@dataclass
class InMemoryRateLimiter:
    max_requests: int
    window_seconds: int
    _hits: dict[str, Deque[float]] = field(default_factory=lambda: defaultdict(deque))

    def check(self, key: str) -> None:
        now = time.monotonic()
        hits = self._hits[key]

        while hits and now - hits[0] > self.window_seconds:
            hits.popleft()

        if len(hits) >= self.max_requests:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded",
            )

        hits.append(now)


def client_key(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"
