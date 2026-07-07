"""Global market indices orchestrator (Phase 5d).

Pulls daily closes for the major international indices from two
sources and upserts them into the same ``macro_indicator`` table
that FRED and akshare already use:

  * ``yfinance``        — Hang Seng, Nikkei, DAX, FTSE, CAC, ASX,
                          KOSPI, TWSE, NIFTY 50, SENSEX
  * ``akshare``         — 上证综指 (sh000001), 深证成指 (sz399001),
                          沪深300 (sh000300)

Both write rows tagged ``region='global'`` so the existing
``/macro/latest?region=global`` endpoint surfaces them with no
schema changes.  Source tag distinguishes them downstream:
``source='yfinance'`` and ``source='akshare'`` respectively.

Designed to be invoked from:
  - APScheduler daily at 16:00 Asia/Shanghai (after Asia close)
  - Admin manual refresh API
  - One-shot CLI / test fixtures

The orchestrator is defensive: a single ticker failure (network
blip, rate limit, schema change) is logged and skipped — the batch
never crashes the scheduler.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from app.core.database import SessionLocal
from app.services.macro_service import MacroDataService

logger = logging.getLogger(__name__)


# Static registry of A-share indices we pull from akshare.  Each
# entry maps the akshare symbol → the internal macro_indicator code
# used across the platform.
A_SHARE_INDEX_REGISTRY: list[dict[str, str]] = [
    {"symbol": "sh000001", "code": "global_shcomp",  "name_zh": "上证综指"},
    {"symbol": "sz399001", "code": "global_szse",    "name_zh": "深证成指"},
    {"symbol": "sh000300", "code": "global_csi300",  "name_zh": "沪深300"},
]


def fetch_a_share_indices(lookback_days: int = 30) -> list[dict]:
    """Fetch A-share index daily bars from akshare.

    Returns observations shaped as
    ``{code, period, value, name_zh, unit}`` (one row per index-day).
    Per-symbol failures are logged and skipped.
    """
    from app.data.providers.akshare_provider import AkshareProvider

    provider = AkshareProvider()
    out: list[dict] = []
    for entry in A_SHARE_INDEX_REGISTRY:
        try:
            rows = provider.fetch_a_share_index_daily(
                symbol=entry["symbol"],
                code=entry["code"],
                name_zh=entry["name_zh"],
                lookback_days=lookback_days,
            )
            out.extend(rows)
        except Exception as exc:  # noqa: BLE001 - defensive
            logger.warning(
                "[global_indices] akshare fetch failed for %s: %s",
                entry["symbol"], exc,
            )
    return out


def fetch_international_indices() -> list[dict]:
    """Fetch international indices via yfinance.

    Returns observations shaped as
    ``{code, period, value, prev_close, name_zh, name_en, unit}``.
    Per-ticker failures are logged and skipped inside
    ``fetch_all_global_indices``.
    """
    from app.data.providers.yfinance_indices_provider import fetch_all_global_indices

    try:
        return fetch_all_global_indices()
    except Exception as exc:  # noqa: BLE001 - last-resort guard
        logger.exception("[global_indices] yfinance batch crashed: %s", exc)
        return []


def fetch_all_global_indices() -> list[dict]:
    """Combined orchestrator: A-share (akshare) + international (yfinance).

    Returned observations are tagged with ``code`` only — the caller
    is responsible for setting ``region`` and ``source`` on upsert
    (the orchestrator does not mutate the dict shape so the same
    rows can be reused by both the realtime endpoint and the
    persistent upsert path).
    """
    a_share = fetch_a_share_indices()
    international = fetch_international_indices()
    logger.info(
        "[global_indices] a_share=%d international=%d total=%d",
        len(a_share), len(international), len(a_share) + len(international),
    )
    return a_share + international


# ---------------------------------------------------------------------------
# Write path — used by the scheduler and the admin manual-refresh endpoint.
# ---------------------------------------------------------------------------


def run_global_indices_refresh() -> dict[str, Any]:
    """Fetch + upsert global indices into ``macro_indicator``.

    Returns a summary dict with per-source counts so the scheduler log
    / manual-refresh endpoint can report what happened:

      * ``fetched`` — total observations returned by providers
      * ``written`` — total rows upserted into the table
      * ``per_source`` — {source: {"fetched", "written"}}
      * ``failed``   — list of codes that failed (best-effort)
      * ``started_at`` / ``finished_at`` — UTC timestamps

    Never raises — failures inside any single provider are logged and
    skipped so the scheduler keeps running.
    """
    started = datetime.now(timezone.utc)
    a_share = fetch_a_share_indices()
    international = fetch_international_indices()

    db = SessionLocal()
    try:
        service = MacroDataService(db)
        per_source: dict[str, dict[str, int]] = {}
        failed: list[str] = []

        # ── akshare / A-share ──
        if a_share:
            try:
                written_cn = service.upsert_observations(
                    region="global",
                    source="akshare",
                    observations=a_share,
                )
                per_source["akshare"] = {
                    "fetched": len(a_share),
                    "written": written_cn,
                }
            except Exception as exc:  # noqa: BLE001 - defensive
                logger.exception(
                    "[global_indices] akshare upsert failed: %s", exc,
                )
                failed.extend({obs["code"] for obs in a_share})
                per_source["akshare"] = {"fetched": len(a_share), "written": 0}
        else:
            per_source["akshare"] = {"fetched": 0, "written": 0}

        # ── yfinance / international ──
        if international:
            try:
                written_yf = service.upsert_observations(
                    region="global",
                    source="yfinance",
                    observations=international,
                )
                per_source["yfinance"] = {
                    "fetched": len(international),
                    "written": written_yf,
                }
            except Exception as exc:  # noqa: BLE001 - defensive
                logger.exception(
                    "[global_indices] yfinance upsert failed: %s", exc,
                )
                failed.extend({obs["code"] for obs in international})
                per_source["yfinance"] = {
                    "fetched": len(international),
                    "written": 0,
                }
        else:
            per_source["yfinance"] = {"fetched": 0, "written": 0}

        finished = datetime.now(timezone.utc)
        total_fetched = len(a_share) + len(international)
        total_written = sum(s.get("written", 0) for s in per_source.values())

        logger.info(
            "[global_indices] refresh done: fetched=%d written=%d failed=%d elapsed=%.1fs",
            total_fetched, total_written, len(failed),
            (finished - started).total_seconds(),
        )

        return {
            "fetched": total_fetched,
            "written": total_written,
            "per_source": per_source,
            "failed": failed,
            "started_at": started,
            "finished_at": finished,
        }
    except Exception as exc:  # noqa: BLE001 - last-resort guard
        logger.exception("[global_indices] refresh crashed: %s", exc)
        return {
            "fetched": 0,
            "written": 0,
            "per_source": {},
            "failed": ["__job__"],
            "error": str(exc),
            "started_at": started,
            "finished_at": datetime.now(timezone.utc),
        }
    finally:
        db.close()