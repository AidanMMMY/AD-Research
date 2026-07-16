"""Container health / readiness probe (ops P1-13).

Exports :func:`readiness_check`, a single, side-effect-free function that
each container concern can be checked through:

* **db**        — a ``SELECT 1`` round-trip on the shared engine
* **redis**     — a ``PING`` on the cached client
* **scheduler** — the cross-worker heartbeat written by the leader worker
* **data**      — freshness of the most recent daily bar

The result is a JSON-safe dict with an overall ``status`` and a
per-component breakdown so that ECS / load balancers / on-call engineers
can see *which* dependency is degraded without SSH-ing in to read logs.

Design contract:

* **Never raises.** Every probe is individually guarded; a probe failure
  becomes ``{"status": "error", ...}`` for that component, never an
  exception out of :func:`readiness_check`.
* **Degraded ≠ dead.** ``db`` and ``redis`` are *critical* (they flip the
  overall status to ``degraded``). Stale data and a missing scheduler
  heartbeat are *warnings* — surfaced but non-fatal — because a fresh
  deploy or a weekend can legitimately produce stale bars.
* **Never blocks the response.** Probes run concurrently with a hard
  overall deadline. A slow DB query or a stuck scheduler call cannot make
  the whole ``/health`` endpoint time out (see ops incident 2026-07-16).
* **Cheap under pressure.** Health checks use dedicated short-lived DB
  connections in autocommit mode and set a short ``statement_timeout`` so
  they do not compete with the main ORM connection pool for long-running
  queries.
"""

from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from datetime import date, datetime, timezone
from typing import Any

# A market bucket is "stale" once its latest daily bar is older than this
# many calendar days. 4 days tolerates a normal Fri→Mon weekend gap plus a
# public holiday without crying wolf.
_STALE_AFTER_DAYS = 4

# Overall /health response must return faster than this. Load balancers and
# ECS probes typically use 5–10s; we keep a 4s ceiling so there is headroom.
_HEALTH_TIMEOUT_SECONDS = 4.0

# Short-lived cache so a burst of health probes during deploy does not
# hammer DB/Redis. 5s is enough to let nginx/backend startup probes share
# one result without making the check feel stale.
_CACHE_TTL_SECONDS = 5.0

# Reusable thread pool for concurrent probes. Thread-safe; created lazily.
_executor: ThreadPoolExecutor | None = None
_executor_lock = threading.Lock()

_cache: dict[str, Any] = {}
_cache_lock = threading.Lock()


def _get_executor() -> ThreadPoolExecutor:
    """Return the shared probe executor, creating it lazily."""
    global _executor  # noqa: PLW0603
    if _executor is None:
        with _executor_lock:
            if _executor is None:
                # 4 probes in parallel; max_workers=4 is plenty.
                _executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="health-")
    return _executor


def _classify_exception(exc: Exception) -> dict[str, Any]:
    """Return a structured error dict that distinguishes pool exhaustion."""
    from sqlalchemy.exc import OperationalError, TimeoutError as SATimeoutError

    detail = exc.__class__.__name__
    if isinstance(exc, SATimeoutError):
        detail = "QueuePoolTimeout"
    elif isinstance(exc, OperationalError):
        # psycopg2 OperationalError message usually contains the real cause.
        msg = str(exc).lower()
        if "connection" in msg and ("refused" in msg or "closed" in msg):
            detail = "DBConnectionError"
        elif "too many clients" in msg:
            detail = "DBTooManyClients"
    return {"status": "error", "detail": detail}


def _check_db() -> dict[str, Any]:
    """Round-trip ``SELECT 1`` using a dedicated autocommit connection.

    Using ``engine.connect()`` with AUTOCOMMIT avoids entering the shared
    ORM session pool and lets us set a tight ``statement_timeout`` without
    affecting application sessions.
    """
    try:
        from sqlalchemy import text

        from app.core.database import engine

        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            # Cancel any query that takes longer than 2s so a hung DB cannot
            # pin this probe thread indefinitely.
            conn.execute(text("SET LOCAL statement_timeout = '2s'"))
            conn.execute(text("SELECT 1"))
        return {"status": "ok"}
    except FutureTimeoutError:
        return {"status": "error", "detail": "probe_timeout"}
    except Exception as exc:  # noqa: BLE001
        return _classify_exception(exc)


def _check_redis() -> dict[str, Any]:
    """PING the configured Redis instance."""
    try:
        from app.core.redis_client import get_redis_client

        if get_redis_client().ping():
            return {"status": "ok"}
        return {"status": "error", "detail": "ping returned falsy"}
    except FutureTimeoutError:
        return {"status": "error", "detail": "probe_timeout"}
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "detail": exc.__class__.__name__}


def _check_scheduler() -> dict[str, Any]:
    """Report scheduler liveness via the cross-worker Redis heartbeat."""
    try:
        from app.core.scheduler import is_scheduler_running

        running = is_scheduler_running()
        # A missing heartbeat is a warning, not a hard failure — the API
        # worker is not necessarily the scheduler leader.
        return {"status": "ok" if running else "warn", "running": running}
    except FutureTimeoutError:
        return {"status": "warn", "detail": "probe_timeout"}
    except Exception as exc:  # noqa: BLE001
        return {"status": "warn", "detail": exc.__class__.__name__}


def _check_data_staleness() -> dict[str, Any]:
    """Freshness of the most recent daily bar in ``instrument_daily_bar``.

    Non-critical: stale data is reported as ``warn`` so monitors can alert,
    but it never flips the overall probe to ``degraded``.

    ops incident 2026-07-16: the previous per-market join against ``etf_info``
    scanned ~16M rows and took 6–15s, which made the whole ``/health``
    endpoint time out and cascaded into QueuePool exhaustion. We now use the
    much cheaper ``max(trade_date)`` over the whole table with a tight
    ``statement_timeout``.
    """
    from sqlalchemy import text

    from app.core.database import engine

    try:
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            conn.execute(text("SET LOCAL statement_timeout = '3s'"))
            row = conn.execute(
                text("SELECT max(trade_date) FROM instrument_daily_bar")
            ).one()
            overall_max = row[0]
    except FutureTimeoutError:
        return {"status": "warn", "detail": "probe_timeout"}
    except Exception as exc:  # noqa: BLE001
        return {"status": "warn", "detail": exc.__class__.__name__}

    if overall_max is None:
        return {"status": "warn", "stale_markets": ["all"], "markets": {}}
    if isinstance(overall_max, datetime):
        overall_max = overall_max.date()
    age = (date.today() - overall_max).days
    status = "ok" if age <= _STALE_AFTER_DAYS else "warn"
    return {
        "status": status,
        "stale_markets": [] if status == "ok" else ["all"],
        "markets": {
            "overall": {
                "status": status,
                "age_days": age,
                "latest_date": overall_max.isoformat(),
            }
        },
    }


def _run_probes() -> dict[str, Any]:
    """Run all four probes concurrently and return their results."""
    executor = _get_executor()
    probes = {
        "db": _check_db,
        "redis": _check_redis,
        "scheduler": _check_scheduler,
        "data": _check_data_staleness,
    }
    futures = {name: executor.submit(fn) for name, fn in probes.items()}
    components: dict[str, Any] = {}
    for name, future in futures.items():
        try:
            components[name] = future.result(timeout=_HEALTH_TIMEOUT_SECONDS)
        except FutureTimeoutError:
            components[name] = {"status": "error" if name in ("db", "redis") else "warn", "detail": "probe_timeout"}
    return components


def _pool_status() -> dict[str, int]:
    """Return SQLAlchemy connection pool counters for observability."""
    try:
        from app.core.database import engine

        pool = engine.pool
        return {
            "size": pool.size(),
            "checked_in": pool.checked_in(),
            "checked_out": pool.checked_out(),
            "overflow": pool.overflow(),
        }
    except Exception:  # noqa: BLE001
        return {"size": -1, "checked_in": -1, "checked_out": -1, "overflow": -1}


def readiness_check() -> dict[str, Any]:
    """Probe every container concern and return a JSON-safe health report.

    The check is cached for ``_CACHE_TTL_SECONDS`` so a burst of deploy
    probes / load balancer checks does not overload DB/Redis.
    """
    with _cache_lock:
        cached = _cache.get("report")
        cached_at = _cache.get("cached_at", 0.0)
        if cached and (time.time() - cached_at) < _CACHE_TTL_SECONDS:
            return cached

    components = _run_probes()

    critical_ok = all(
        components[name]["status"] == "ok" for name in ("db", "redis")
    )

    report = {
        "status": "ok" if critical_ok else "degraded",
        "ready": critical_ok,
        "version": __import__("app.main", fromlist=["__version__"]).__version__,
        "git_sha": __import__("app.main", fromlist=["GIT_SHA"]).GIT_SHA,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "pool": _pool_status(),
        "components": components,
    }

    with _cache_lock:
        _cache["report"] = report
        _cache["cached_at"] = time.time()

    return report


def _warm_cache() -> None:
    """Best-effort background warm-up of the health cache at startup."""
    try:
        readiness_check()
    except Exception as exc:  # noqa: BLE001
        logging.getLogger(__name__).debug("Health cache warm-up failed: %s", exc)


# Warm the cache in a background thread when this module is first imported,
# so the very first HTTP /health request is served from cache.
threading.Thread(target=_warm_cache, daemon=True, name="health-warmup").start()
