"""Asynchronous token-bucket rate limiter for crawlers.

Each source gets its own bucket so a single noisy source cannot
starve the others. ``acquire`` blocks (asynchronously) until a
token is available — we never drop requests.
"""

from __future__ import annotations

import asyncio
import time
from typing import Awaitable, Callable


class AsyncTokenBucket:
    """Token-bucket rate limiter.

    Parameters
    ----------
    rate:
        Maximum number of tokens per ``period_seconds``. A bucket
        with rate=30 + period=60 allows 30 requests per minute.
    period_seconds:
        Window over which ``rate`` applies.
    initial_tokens:
        Tokens already in the bucket when the limiter starts. Use
        a small value (e.g. ``rate // 2``) so the very first burst
        can fire immediately without violating the long-term cap.
    """

    def __init__(
        self,
        rate: int,
        period_seconds: float = 60.0,
        initial_tokens: int | None = None,
    ) -> None:
        if rate <= 0:
            raise ValueError("rate must be a positive integer")
        if period_seconds <= 0:
            raise ValueError("period_seconds must be > 0")

        self.rate = int(rate)
        self.period = float(period_seconds)
        # Tokens added per second — the canonical refill speed.
        self.refill_per_sec = self.rate / self.period
        self.capacity = int(rate)

        initial = self.capacity if initial_tokens is None else min(int(initial_tokens), self.capacity)
        self._tokens = float(initial)
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    @property
    def available(self) -> float:
        """Current token count (best-effort; may be stale by nanoseconds)."""
        self._refill()
        return self._tokens

    def _refill(self) -> None:
        """Add tokens proportional to elapsed time since last refill."""
        now = time.monotonic()
        elapsed = now - self._last_refill
        if elapsed <= 0:
            return
        self._tokens = min(float(self.capacity), self._tokens + elapsed * self.refill_per_sec)
        self._last_refill = now

    async def acquire(self, tokens: int = 1) -> None:
        """Wait until at least ``tokens`` are available, then consume them.

        Never rejects — callers can safely wrap it around every
        outbound request without worrying about losing work.
        """
        if tokens <= 0:
            raise ValueError("tokens must be positive")
        if tokens > self.capacity:
            raise ValueError(
                f"requested {tokens} tokens but bucket capacity is {self.capacity}"
            )

        async with self._lock:
            while True:
                self._refill()
                if self._tokens >= tokens:
                    self._tokens -= tokens
                    return
                # Deficit in seconds before the next refill produces
                # enough tokens for this request.
                deficit = tokens - self._tokens
                wait = deficit / self.refill_per_sec
                # Release the lock while we sleep so other coroutines
                # still measure consistent refill timings. The
                # refresh after sleep is approximate but the capacity
                # cap keeps us honest.
                self._lock.release()
                try:
                    await asyncio.sleep(wait)
                finally:
                    await self._lock.acquire()

    async def __aenter__(self) -> "AsyncTokenBucket":
        await self.acquire()
        return self

    async def __aexit__(self, *exc) -> None:  # type: ignore[no-untyped-def]
        return None


# ---------------------------------------------------------------------------
# Convenience: registry pattern used by BaseCrawler
# ---------------------------------------------------------------------------
_default_clock: Callable[[], float] = time.monotonic
_test_clock: Callable[[], float] | None = None


def set_test_clock(clock: Callable[[], float] | None) -> None:
    """Override the monotonic clock — used by tests for deterministic timing."""
    global _test_clock
    _test_clock = clock


def _now() -> float:
    if _test_clock is not None:
        return _test_clock()
    return _default_clock()


async def with_limit(bucket: AsyncTokenBucket, awaitable: Awaitable):
    """Run ``awaitable`` after acquiring 1 token from ``bucket``."""
    await bucket.acquire()
    return await awaitable
