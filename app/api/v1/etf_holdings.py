"""ETF top-10 holdings — operations endpoints.

Most holdings *read* endpoints live in ``app.api.v1.etfs``. This
router exists for the operational side:

- ``POST /refresh`` — manually trigger the quarterly ``ETFHoldingsPipeline``
  outside the scheduled windows (e.g. after a deploy that aborted the
  most recent run, or right after a public disclosure).
- ``GET  /refresh/status`` — peek at the Redis lock so callers can
  tell whether a refresh is already in flight.

The underlying work is the same ``refresh_etf_holdings`` function that
the quarterly cron jobs call, so the lock and the result envelope are
shared.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_current_user
from app.core.redis_client import get_redis_client
from app.scheduler_jobs.etf_holdings_quarterly import (
    LOCK_KEY,
    QUARTERLY_TRIGGERS,
    refresh_etf_holdings,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/etf-holdings",
    tags=["ETF Holdings"],
    dependencies=[Depends(get_current_user)],
)


@router.get("/refresh/status")
def refresh_status() -> dict:
    """Report whether a quarterly ETF-holdings refresh is in flight.

    The lock lives at ``lock:{LOCK_KEY}`` in Redis (see
    ``app.core.redis_client.redis_lock``).  Returning the TTL lets the
    caller know whether a stuck refresh is about to expire on its own
    or whether they should wait it out.
    """
    client = get_redis_client()
    redis_key = f"lock:{LOCK_KEY}"
    token = client.get(redis_key)
    ttl = client.ttl(redis_key) if token is not None else None
    return {
        "lock_key": LOCK_KEY,
        "in_flight": token is not None,
        "ttl_seconds": ttl,
        "scheduled_triggers": [
            {"label": label, "month": month, "day": day, "hour": 2, "minute": 0}
            for label, month, day in QUARTERLY_TRIGGERS
        ],
    }


@router.post("/refresh")
def trigger_refresh(
    force: bool = Query(
        False,
        description=(
            "If true, bypass the in-flight Redis lock and re-run anyway. "
            "Use this after a deploy that aborted the previous run."
        ),
    ),
) -> dict:
    """Manually trigger the quarterly ETF holdings refresh.

    Thin wrapper over ``refresh_etf_holdings`` so the API surface and
    the scheduler share the same code path.  Without ``force=true`` a
    concurrent run will be reported as ``status=skipped``.
    """
    logger.info(
        "[API] Manual ETF holdings refresh requested (force=%s)", force
    )
    return refresh_etf_holdings(force=force)
