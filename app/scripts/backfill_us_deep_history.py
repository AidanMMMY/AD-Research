#!/usr/bin/env python3
"""One-shot deep history backfill for US equities (2020-01-01 → today).

Strategy (Plan C):
  - Core 33 symbols → Tiingo primary (reliable, ~35 API calls)
  - Non-core ~534 symbols → yfinance primary, Tiingo fallback on failure
  - Respect Tiingo 500 symbols/month cap; track consumed count in Redis

Designed to run in batches via cron / manual invocation. Each run processes
a small batch to stay within yfinance rate limits. Resumable via Redis offset.

Usage:
    # Dry-run to see what would happen
    docker exec etf-backend python3 app/scripts/backfill_us_deep_history.py \\
        --tier core --dry-run

    # Core 33: Tiingo, 2020-01-01 → today
    docker exec etf-backend python3 app/scripts/backfill_us_deep_history.py \\
        --tier core --provider tiingo

    # Non-core: yfinance primary, Tiingo fallback, batch of 5 symbols
    docker exec etf-backend python3 app/scripts/backfill_us_deep_history.py \\
        --tier non-core --batch-size 5

    # Continue from where we left off (reads Redis offset)
    docker exec etf-backend python3 app/scripts/backfill_us_deep_history.py \\
        --tier non-core --batch-size 5

    # Custom date range
    docker exec etf-backend python3 app/scripts/backfill_us_deep_history.py \\
        --tier non-core --start 2018-01-01 --end 2024-12-31 --batch-size 5
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import date, datetime

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)


def _banner(msg: str) -> None:
    print(f"\n{'='*60}\n  {msg}\n{'='*60}")


# ── symbol selection ──────────────────────────────────────────────────

CORE_33 = [
    # Major US ETFs (7)
    "SPY.US", "QQQ.US", "VOO.US", "IVV.US", "VTI.US", "DIA.US", "IWM.US",
    # Magnificent 7 + key tech (8)
    "AAPL.US", "MSFT.US", "GOOGL.US", "AMZN.US", "TSLA.US", "NVDA.US", "META.US", "AVGO.US",
    # Blue chips — financials (6)
    "BRK.B.US", "JPM.US", "V.US", "MA.US", "BAC.US",
    # Blue chips — healthcare (5)
    "JNJ.US", "UNH.US", "ABBV.US", "TMO.US", "ABT.US",
    # Blue chips — consumer / energy / industrial (7)
    "PG.US", "KO.US", "PEP.US", "WMT.US", "COST.US", "MCD.US", "XOM.US",
    # Blue chips — misc (2)
    "HD.US", "PFE.US", "MRK.US",
]
CORE_33_SET = set(CORE_33)


def _resolve_tier(
    tier: str, db_session
) -> tuple[list[str], str]:
    """Return (sorted_codes, label) for the given tier."""
    from app.models.etf import ETFInfo

    active = (
        db_session.query(ETFInfo.code)
        .filter(ETFInfo.market == "US", ETFInfo.status == "active")
        .order_by(ETFInfo.code)
        .all()
    )
    all_codes = [c for (c,) in active]

    if tier == "core":
        codes = sorted(CORE_33_SET & set(all_codes))
        return codes, "core"
    elif tier == "non-core":
        codes = sorted(set(all_codes) - CORE_33_SET)
        return codes, "non-core"
    elif tier == "remaining":
        # Symbols that have NO price data yet
        from app.models.etf import ETFDailyBar

        with_price = {
            c
            for (c,) in db_session.query(ETFDailyBar.etf_code)
            .distinct()
            .filter(ETFDailyBar.etf_code.like("%.US"))
            .all()
        }
        codes = sorted(set(all_codes) - with_price)
        return codes, "remaining"
    else:  # "all"
        return sorted(all_codes), "all"


# ── data fetching ──────────────────────────────────────────────────────

def _fetch_tiingo_bars(
    codes: list[str], start_date: date, end_date: date
) -> dict[str, list[dict]]:
    """Fetch bars from Tiingo. Returns {code: [bar_dict, ...]}."""
    import os
    import requests
    from urllib.parse import urlencode

    api_key = os.getenv("TIINGO_API_KEY", "")
    if not api_key:
        raise RuntimeError("TIINGO_API_KEY not set")

    results: dict[str, list[dict]] = {}
    for code in codes:
        ticker = code.replace(".US", "")
        url = (
            f"https://api.tiingo.com/tiingo/daily/{ticker}/prices"
            f"?startDate={start_date.isoformat()}"
            f"&endDate={end_date.isoformat()}"
            f"&token={api_key}"
        )
        try:
            resp = requests.get(url, timeout=30)
            if resp.status_code == 404:
                logger.warning("Tiingo 404 for %s → skipping", code)
                results[code] = []
                continue
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            logger.warning("Tiingo failed for %s: %s", code, exc)
            results[code] = []  # empty = caller should retry with yfinance
            continue

        if not isinstance(data, list) or not data:
            results[code] = []
            continue

        bars = []
        for item in data:
            raw_date = item.get("date", "")
            try:
                trade_date_val = datetime.fromisoformat(
                    raw_date.replace("Z", "+00:00")
                ).date()
            except (ValueError, AttributeError):
                continue

            close_price = float(item.get("close", 0) or 0)
            volume_val = int(item.get("volume", 0) or 0)
            bars.append(
                {
                    "etf_code": code,
                    "trade_date": trade_date_val,
                    "open": float(item.get("open", 0) or 0),
                    "high": float(item.get("high", 0) or 0),
                    "low": float(item.get("low", 0) or 0),
                    "close": close_price,
                    "volume": volume_val,
                    "amount": volume_val * close_price,
                }
            )
        results[code] = bars
        time.sleep(1.5)  # Tiingo free tier: 50 req/hour
    return results


def _fetch_yfinance_bars(
    codes: list[str], start_date: date, end_date: date
) -> dict[str, list[dict]]:
    """Fetch bars from yfinance (single-ticker, slow but reliable).

    Returns {code: [bar_dict, ...]}. Empty list for a code means it failed.
    """
    import yfinance as yf

    results: dict[str, list[dict]] = {}
    for code in codes:
        ticker = code.replace(".US", "")
        try:
            hist = yf.Ticker(ticker).history(start=start_date, end=end_date)
        except Exception as exc:
            logger.warning("yfinance failed for %s: %s", code, exc)
            results[code] = []
            time.sleep(3.0)
            continue

        if hist.empty:
            logger.info("yfinance empty for %s", code)
            results[code] = []
            time.sleep(3.0)
            continue

        bars = []
        for idx, row in hist.iterrows():
            td = idx.date() if hasattr(idx, "date") else idx
            close_price = float(row.get("Close", 0) or 0)
            volume_val = int(row.get("Volume", 0) or 0)
            bars.append(
                {
                    "etf_code": code,
                    "trade_date": td,
                    "open": float(row.get("Open", 0) or 0),
                    "high": float(row.get("High", 0) or 0),
                    "low": float(row.get("Low", 0) or 0),
                    "close": close_price,
                    "volume": volume_val,
                    "amount": volume_val * close_price,
                }
            )
        results[code] = bars
        logger.info(
            "  yfinance ✓ %s → %d bars", code, len(bars)
        )
        time.sleep(3.0)  # be gentle to Yahoo
    return results


# ── DB write ───────────────────────────────────────────────────────────

def _upsert_bars(db_session, bars: list[dict]) -> int:
    """Insert or update bars into etf_daily_bar. Returns count of rows written."""
    from sqlalchemy.dialects.postgresql import insert
    from app.models.etf import ETFDailyBar

    if not bars:
        return 0

    records = []
    for b in bars:
        r = {k: v for k, v in b.items() if v is not None}
        records.append(r)

    stmt = (
        insert(ETFDailyBar)
        .values(records)
        .on_conflict_do_update(
            index_elements=["etf_code", "trade_date"],
            set_={
                "open": insert(ETFDailyBar).excluded.open,
                "high": insert(ETFDailyBar).excluded.high,
                "low": insert(ETFDailyBar).excluded.low,
                "close": insert(ETFDailyBar).excluded.close,
                "volume": insert(ETFDailyBar).excluded.volume,
                "amount": insert(ETFDailyBar).excluded.amount,
            },
        )
    )
    db_session.execute(stmt)
    db_session.commit()
    return len(records)


# ── offset tracking ────────────────────────────────────────────────────

_OFFSET_KEY = "us_deep_history:offset"


def _get_offset(redis_client) -> int:
    try:
        v = redis_client.get(_OFFSET_KEY)
        return int(v) if v else 0
    except Exception:
        return 0


def _set_offset(redis_client, offset: int) -> None:
    try:
        redis_client.set(_OFFSET_KEY, str(offset))
    except Exception:
        pass


def _tiingo_count_key(ym: str) -> str:
    return f"us_deep_history:tiingo:{ym}"


def _get_tiingo_consumed(redis_client, ym: str) -> int:
    try:
        v = redis_client.get(_tiingo_count_key(ym))
        return int(v) if v else 0
    except Exception:
        return 0


def _incr_tiingo_consumed(redis_client, ym: str, delta: int) -> None:
    try:
        redis_client.incrby(_tiingo_count_key(ym), delta)
    except Exception:
        pass


# ── main ───────────────────────────────────────────────────────────────

def run_backfill(
    *,
    tier: str = "all",
    provider: str = "auto",       # "tiingo" | "yfinance" | "auto"
    start_date: date | None = None,
    end_date: date | None = None,
    batch_size: int = 5,
    batch_offset: int | None = None,
    max_tiingo: int = 500,
    dry_run: bool = False,
) -> dict:
    """Run one batch of the deep history backfill.

    Returns a summary dict with keys: processed, success, failed, bars, tiingo_used.
    """
    from app.core.database import SessionLocal
    from app.core.redis_client import get_redis_client

    db = SessionLocal()
    redis_client = get_redis_client()
    start = start_date or date(2020, 1, 1)
    end = end_date or date.today()
    ym = end.strftime("%Y-%m")  # for Tiingo monthly tracking

    try:
        all_codes, tier_label = _resolve_tier(tier, db)
        logger.info(
            "Tier=%s → %d symbols eligible", tier_label, len(all_codes)
        )

        # Read / compute offset
        if batch_offset is None:
            offset = _get_offset(redis_client)
        else:
            offset = batch_offset
            _set_offset(redis_client, offset)

        if offset >= len(all_codes):
            offset = 0
            _set_offset(redis_client, 0)

        batch = all_codes[offset : offset + batch_size]
        logger.info(
            "Batch: %d symbols starting at offset %d/%d",
            len(batch), offset, len(all_codes),
        )
        if not batch:
            return {"processed": 0, "success": 0, "failed": 0, "bars": 0, "tiingo_used": 0}

        # ── fetch ──
        tiingo_codes: list[str] = []
        yf_codes: list[str] = []
        if provider == "tiingo":
            tiingo_codes = batch
        elif provider == "yfinance":
            yf_codes = batch
        else:  # auto
            yf_codes = batch

        all_bars: dict[str, list[dict]] = {}
        tiingo_used_this_run = 0

        # yfinance pass
        if yf_codes:
            _banner(f"yfinance: {len(yf_codes)} symbols")
            yf_results = _fetch_yfinance_bars(yf_codes, start, end)
            for code, bars in yf_results.items():
                all_bars[code] = bars

            # Collect codes yfinance failed on → fall back to Tiingo
            yf_failed = [c for c in yf_codes if not yf_results.get(c)]
            if yf_failed:
                logger.info(
                    "yfinance missed %d/%d codes → Tiingo fallback",
                    len(yf_failed), len(yf_codes),
                )

        # Tiingo pass (either primary or fallback)
        tiingo_remaining = tiingo_codes[:]
        if provider == "auto":
            tiingo_remaining = [
                c for c in batch if c not in all_bars or not all_bars[c]
            ]

        if tiingo_remaining:
            consumed_before = _get_tiingo_consumed(redis_client, ym)
            tiingo_budget = max(0, max_tiingo - consumed_before)

            if tiingo_budget <= 0:
                logger.warning(
                    "Tiingo monthly cap (%d symbols) reached — skipping %d symbols",
                    max_tiingo, len(tiingo_remaining),
                )
            else:
                tiingo_to_fetch = tiingo_remaining[:tiingo_budget]
                _banner(f"Tiingo: {len(tiingo_to_fetch)} symbols (budget {tiingo_budget})")
                tiingo_results = _fetch_tiingo_bars(tiingo_to_fetch, start, end)
                for code, bars in tiingo_results.items():
                    all_bars[code] = bars
                tiingo_used_this_run = len(tiingo_to_fetch)
                _incr_tiingo_consumed(redis_client, tiingo_used_this_run)
                logger.info(
                    "Tiingo consumed: %d this run, %d this month",
                    tiingo_used_this_run,
                    _get_tiingo_consumed(redis_client, ym),
                )

        # ── write ──
        total_bars = 0
        success = 0
        failed = 0
        for code in batch:
            bars = all_bars.get(code, [])
            if not bars:
                logger.warning("  ✗ %s: no data", code)
                failed += 1
                continue
            if dry_run:
                logger.info(
                    "  [DRY] %s: %d bars (%s ~ %s)",
                    code,
                    len(bars),
                    bars[0]["trade_date"],
                    bars[-1]["trade_date"],
                )
                total_bars += len(bars)
                success += 1
            else:
                n = _upsert_bars(db, bars)
                logger.info(
                    "  ✓ %s: %d rows written", code, n,
                )
                total_bars += n
                success += 1

        # Advance offset
        new_offset = offset + len(batch)
        if new_offset >= len(all_codes):
            new_offset = 0
        _set_offset(redis_client, new_offset)

        summary = {
            "processed": len(batch),
            "success": success,
            "failed": failed,
            "bars": total_bars,
            "tiingo_used": tiingo_used_this_run,
        }
        _banner(
            f"Summary: {success}/{len(batch)} success, {failed} failed, "
            f"{total_bars} bars, {tiingo_used_this_run} Tiingo, "
            f"next offset={new_offset}"
        )
        return summary

    finally:
        db.close()


# ── CLI ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="US equity deep history backfill (2020 → today)"
    )
    parser.add_argument(
        "--tier",
        choices=["core", "non-core", "remaining", "all"],
        default="remaining",
        help="Symbol tier: core=33 key symbols, non-core=everything else, "
        "remaining=only symbols without ANY price data, all=everything (default: remaining)",
    )
    parser.add_argument(
        "--provider",
        choices=["auto", "tiingo", "yfinance"],
        default="auto",
        help="Data source: auto=yfinance→Tiingo fallback, tiingo=Tiingo only, "
        "yfinance=yfinance only (default: auto)",
    )
    parser.add_argument(
        "--start",
        type=lambda s: datetime.strptime(s, "%Y-%m-%d").date(),
        default="2020-01-01",
        help="Start date (default: 2020-01-01)",
    )
    parser.add_argument(
        "--end",
        type=lambda s: datetime.strptime(s, "%Y-%m-%d").date(),
        default=None,
        help="End date (default: today)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=5,
        help="Symbols per invocation (default: 5)",
    )
    parser.add_argument(
        "--batch-offset",
        type=int,
        default=None,
        help="Start offset in the tier list (default: read from Redis, 0 if none)",
    )
    parser.add_argument(
        "--max-tiingo",
        type=int,
        default=500,
        help="Max Tiingo symbols to consume this month (default: 500)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=3.0,
        help="Delay in seconds between yfinance single-ticker calls (default: 3.0)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch data but do not write to database",
    )
    args = parser.parse_args()

    summary = run_backfill(
        tier=args.tier,
        provider=args.provider,
        start_date=args.start,
        end_date=args.end or date.today(),
        batch_size=args.batch_size,
        batch_offset=args.batch_offset,
        max_tiingo=args.max_tiingo,
        dry_run=args.dry_run,
    )

    rc = 0 if summary["failed"] == 0 else 1
    sys.exit(rc)
