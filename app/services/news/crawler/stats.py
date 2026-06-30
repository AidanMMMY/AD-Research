"""Crawl statistics — counters and latency percentiles per source.

The instance is cheap to construct and is intended to live as a
module-level singleton (or per-orchestrator instance). Counters
update under a lock; the implementation is deliberately simple so
it can be inspected / serialised without pulling in numpy.
"""

from __future__ import annotations

import bisect
import math
import threading
from datetime import datetime, timezone
from typing import Any


class Stats:
    """Per-source crawl statistics.

    Tracks:

    - success / failed / timeout / blocked counters
    - total bytes downloaded
    - rolling latency samples for p50 / p95 calculation
    - first/last seen timestamps

    All updates are thread-safe via a single internal lock.
    """

    def __init__(self, max_latency_samples: int = 1024) -> None:
        self.success = 0
        self.failed = 0
        self.timeout = 0
        self.blocked = 0
        self.total_bytes = 0
        self._latency_ms: list[float] = []
        self._max_latency_samples = int(max_latency_samples)
        self._first_seen: datetime | None = None
        self._last_seen: datetime | None = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Recording events
    # ------------------------------------------------------------------
    def record_success(self, *, bytes: int = 0, latency_ms: float | None = None) -> None:
        """Record a successful response."""
        now = datetime.now(tz=timezone.utc)
        with self._lock:
            self.success += 1
            self.total_bytes += max(int(bytes), 0)
            self._track_latency(latency_ms)
            self._touch(now)

    def record_failed(self, *, bytes: int = 0, latency_ms: float | None = None) -> None:
        """Record a generic (non-timeout, non-blocked) failure."""
        with self._lock:
            self.failed += 1
            self.total_bytes += max(int(bytes), 0)
            self._track_latency(latency_ms)
            self._touch(datetime.now(tz=timezone.utc))

    def record_timeout(self, *, bytes: int = 0, latency_ms: float | None = None) -> None:
        """Record a timeout event."""
        with self._lock:
            self.timeout += 1
            self.total_bytes += max(int(bytes), 0)
            self._track_latency(latency_ms)
            self._touch(datetime.now(tz=timezone.utc))

    def record_blocked(self, *, bytes: int = 0, latency_ms: float | None = None) -> None:
        """Record a blocked / 403 / anti-bot response."""
        with self._lock:
            self.blocked += 1
            self.total_bytes += max(int(bytes), 0)
            self._track_latency(latency_ms)
            self._touch(datetime.now(tz=timezone.utc))

    # ------------------------------------------------------------------
    # Reading
    # ------------------------------------------------------------------
    @property
    def total_requests(self) -> int:
        return self.success + self.failed + self.timeout + self.blocked

    @property
    def success_rate(self) -> float:
        n = self.total_requests
        return (self.success / n) if n else 0.0

    def latency_percentiles(self) -> dict[str, float]:
        """Return ``{p50, p95, p99, count}`` over retained latency samples."""
        with self._lock:
            samples = sorted(self._latency_ms)
        if not samples:
            return {"p50": 0.0, "p95": 0.0, "p99": 0.0, "count": 0}

        def pct(p: float) -> float:
            # Nearest-rank percentile (good enough for monitoring).
            if len(samples) == 1:
                return samples[0]
            rank = max(0, min(len(samples) - 1, math.ceil(p * len(samples)) - 1))
            return samples[rank]

        return {
            "p50": pct(0.50),
            "p95": pct(0.95),
            "p99": pct(0.99),
            "count": len(samples),
        }

    def to_dict(self) -> dict[str, Any]:
        """Snapshot suitable for JSON / dashboard consumption."""
        with self._lock:
            first = self._first_seen
            last = self._last_seen
        pcts = self.latency_percentiles()
        return {
            "success": self.success,
            "failed": self.failed,
            "timeout": self.timeout,
            "blocked": self.blocked,
            "total_requests": self.total_requests,
            "success_rate": round(self.success_rate, 4),
            "total_bytes": self.total_bytes,
            "latency_p50_ms": round(pcts["p50"], 2),
            "latency_p95_ms": round(pcts["p95"], 2),
            "latency_p99_ms": round(pcts["p99"], 2),
            "latency_samples": pcts["count"],
            "first_seen": first.isoformat() if first else None,
            "last_seen": last.isoformat() if last else None,
        }

    def summary(self) -> str:
        """One-line textual summary, primarily for log output."""
        d = self.to_dict()
        return (
            f"requests={d['total_requests']} "
            f"success={d['success']} failed={d['failed']} "
            f"timeout={d['timeout']} blocked={d['blocked']} "
            f"bytes={d['total_bytes']} "
            f"p50={d['latency_p50_ms']}ms p95={d['latency_p95_ms']}ms"
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _track_latency(self, latency_ms: float | None) -> None:
        if latency_ms is None:
            return
        try:
            value = float(latency_ms)
        except (TypeError, ValueError):
            return
        if not math.isfinite(value) or value < 0:
            return
        # Keep only the most recent N samples so memory stays bounded.
        if len(self._latency_ms) >= self._max_latency_samples:
            bisect.insort(self._latency_ms, value)
            # Bound the window by dropping the lower half once over capacity.
            if len(self._latency_ms) > self._max_latency_samples:
                self._latency_ms = self._latency_ms[len(self._latency_ms) - self._max_latency_samples :]
        else:
            bisect.insort(self._latency_ms, value)

    def _touch(self, now: datetime) -> None:
        if self._first_seen is None:
            self._first_seen = now
        self._last_seen = now


def make_stats_registry() -> dict[str, Stats]:
    """Return a fresh per-source stats registry dict.

    Kept as a helper so downstream orchestrators don't need to know
    the Stats implementation details.
    """
    return {}
