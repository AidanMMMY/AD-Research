"""Container health / readiness probe (ops P1-13).

Exports :func:`readiness_check`, a single, side-effect-free function that
each container concern can be checked through:

* **db**        — a ``SELECT 1`` round-trip on the shared engine
* **redis**     — a ``PING`` on the cached client
* **scheduler** — the cross-worker heartbeat written by the leader worker
* **data**      — freshness of the most recent A-share / US daily bars

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
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

# A market bucket is "stale" once its latest daily bar is older than this
# many calendar days. 4 days tolerates a normal Fri→Mon weekend gap plus a
# public holiday without crying wolf.
_STALE_AFTER_DAYS = 4


def _check_db() -> dict[str, Any]:
    """Round-trip ``SELECT 1`` through the shared engine."""
    try:
        from sqlalchemy import text

        from app.core.database import engine

        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ok"}
    except Exception as exc:  # noqa: BLE001 — surface any infra failure
        return {"status": "error", "detail": exc.__class__.__name__}


def _check_redis() -> dict[str, Any]:
    """PING the configured Redis instance."""
    try:
        from app.core.redis_client import get_redis_client

        if get_redis_client().ping():
            return {"status": "ok"}
        return {"status": "error", "detail": "ping returned falsy"}
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
    except Exception as exc:  # noqa: BLE001
        return {"status": "warn", "detail": exc.__class__.__name__}


def _latest_bar_age_days(db, market: str) -> int | None:
    """Days since the most recent daily bar for ``market`` (None if empty)."""
    from sqlalchemy import func

    from app.models.etf import ETFInfo, InstrumentDailyBar

    sub = (
        db.query(InstrumentDailyBar.etf_code)
        .join(ETFInfo, ETFInfo.code == InstrumentDailyBar.etf_code)
        .filter(ETFInfo.market == market)
        .subquery()
    )
    row = (
        db.query(func.max(InstrumentDailyBar.trade_date))
        .filter(InstrumentDailyBar.etf_code.in_(sub))
        .first()
    )
    if not row or row[0] is None:
        return None
    latest = row[0]
    if isinstance(latest, datetime):
        latest = latest.date()
    return (date.today() - latest).days


def _check_data_staleness() -> dict[str, Any]:
    """Freshness of the most recent A-share / US daily bars.

    Non-critical: a stale market is reported as ``warn`` so monitors can
    alert, but it never flips the overall probe to ``degraded``.
    """
    from app.core.database import SessionLocal

    db = SessionLocal()
    markets: dict[str, Any] = {}
    stale: list[str] = []
    try:
        for label, market in (("a_share", "A股"), ("us_stock", "US")):
            try:
                age = _latest_bar_age_days(db, market)
            except Exception as exc:  # noqa: BLE001 — one bad query != probe failure
                markets[label] = {"status": "error", "detail": exc.__class__.__name__}
                continue
            if age is None:
                markets[label] = {"status": "warn", "age_days": None}
                stale.append(label)
            elif age > _STALE_AFTER_DAYS:
                markets[label] = {"status": "warn", "age_days": age}
                stale.append(label)
            else:
                markets[label] = {"status": "ok", "age_days": age}
    finally:
        db.close()

    return {
        "status": "warn" if stale else "ok",
        "stale_markets": stale,
        "markets": markets,
    }


def readiness_check() -> dict[str, Any]:
    """Probe every container concern and return a JSON-safe health report.

    Returns::

        {
          "status": "ok" | "degraded",   # degraded ⇢ a critical dep is down
          "ready":  bool,                 # == (status == "ok")
          "checked_at": "<iso8601>",
          "components": {
            "db":        {"status": "ok"|"error", ...},
            "redis":     {"status": "ok"|"error", ...},
            "scheduler": {"status": "ok"|"warn",  ...},
            "data":      {"status": "ok"|"warn",  ...},
          },
        }

    Only ``db`` and ``redis`` are treated as critical.
    """
    components = {
        "db": _check_db(),
        "redis": _check_redis(),
        "scheduler": _check_scheduler(),
        "data": _check_data_staleness(),
    }

    critical_ok = all(
        components[name]["status"] == "ok" for name in ("db", "redis")
    )

    return {
        "status": "ok" if critical_ok else "degraded",
        "ready": critical_ok,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "components": components,
    }
