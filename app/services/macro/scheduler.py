"""China macro indicator scheduler wrapper.

Iterates over the ``AkshareProvider`` macro fetchers (GDP / CPI / PPI /
M2 / PMI / SHIBOR / RRR), upserts the resulting observations into the
``macro_indicator`` table, and returns a small status summary so the
scheduler log / manual-refresh endpoint can report what happened.

The function is defensive: any single indicator that fails (upstream
rate limit, network blip, schema change) is logged and skipped. The
job never crashes the APScheduler thread.
"""

from __future__ import annotations

import logging
from typing import Any

from app.core.etl_log_helper import record_etl

logger = logging.getLogger(__name__)


# Indicator → provider method map. Keep alphabetical so adding a new
# one is a trivial diff.  Each tuple is ``(code_prefix, fn)``; the
# provider method already returns ``list[dict]`` shaped as the service
# expects.
def _provider_methods(provider):
    return [
        ("gdp", provider.fetch_china_macro_gdp),
        ("cpi", provider.fetch_china_macro_cpi),
        ("ppi", provider.fetch_china_macro_ppi),
        ("m2", provider.fetch_china_macro_m2),
        ("pmi", provider.fetch_china_macro_pmi),
        ("shibor", provider.fetch_china_macro_shibor),
        ("rrr", provider.fetch_china_macro_rrr),
    ]


@record_etl("china_macro_daily", source="akshare")
def run_china_macro_refresh() -> dict[str, Any]:
    """Fetch latest China macro indicators and upsert into macro_indicator.

    Returns a dict with:

    * ``fetched`` — total observations returned by the provider (before
      upsert dedup).
    * ``written`` — total rows upserted.
    * ``per_series`` — per-indicator fetched/written counts.
    * ``failed`` — list of indicator names that failed (best-effort).

    Never raises — failures inside any single indicator are logged and
    skipped so the scheduler keeps running.
    """
    from app.core.database import SessionLocal
    from app.data.providers.akshare_provider import AkshareProvider
    from app.services.macro_service import MacroDataService

    provider = AkshareProvider()
    methods = _provider_methods(provider)

    db = SessionLocal()
    try:
        service = MacroDataService(db)
        per_series: dict[str, dict[str, int]] = {}
        failed: list[str] = []
        total_fetched = 0
        total_written = 0

        for name, fn in methods:
            try:
                observations = fn() or []
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning(
                    "[china_macro_refresh] %s fetch raised: %s", name, exc
                )
                failed.append(name)
                continue

            if not observations:
                # Empty result is treated as "no fresh data today" rather
                # than a failure — common for monthly indicators whose
                # period hasn't changed.
                per_series[name] = {"fetched": 0, "written": 0}
                continue

            try:
                written = service.upsert_observations(
                    region="cn",
                    source="akshare",
                    observations=observations,
                )
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning(
                    "[china_macro_refresh] %s upsert failed: %s", name, exc
                )
                failed.append(name)
                per_series[name] = {"fetched": len(observations), "written": 0}
                continue

            total_fetched += len(observations)
            total_written += written
            per_series[name] = {
                "fetched": len(observations),
                "written": written,
            }

        return {
            "fetched": total_fetched,
            "written": total_written,
            "per_series": per_series,
            "failed": failed,
        }
    except Exception as exc:  # pragma: no cover - last-resort guard
        logger.exception("[china_macro_refresh] job failed: %s", exc)
        return {
            "fetched": 0,
            "written": 0,
            "per_series": {},
            "failed": ["__job__"],
            "error": str(exc),
        }
    finally:
        db.close()
