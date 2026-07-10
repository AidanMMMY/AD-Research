#!/usr/bin/env python3
"""Refresh ``futures_contracts.underlying_instrument`` for DCE main contracts.

Background
----------
The previous DCE pipeline (commit fabb84e) populated
``futures_contracts.underlying_instrument`` with the rolled *continuous*
symbol returned by ``ak.futures_main_sina(symbol='<ROOT>0')`` (e.g.
``M0``). For DCE this is unusual — most platforms surface the actual
delivery-month contract (e.g. ``M2609`` for the September 2026 soybean
meal contract).

This script queries akshare for the recent daily history of every
near-term specific DCE contract and picks the one with the highest
``open_interest`` on the most recent trade date — that contract is the
"current main". The result is written to
``futures_contracts.underlying_instrument`` via ``FuturesService``.

The continuous ``code`` (e.g. ``M0``) is left untouched so the daily
bars pipeline / dashboard continue to aggregate rows by the continuous
symbol as before.

Run from the project root:

    python scripts/refresh_dce_underlying.py
    python scripts/refresh_dce_underlying.py --dry-run
    python scripts/refresh_dce_underlying.py --roots M Y P

Requires the same Python environment as the backend (akshare, sqlalchemy,
pandas).
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta

# Make `app` importable when running from the scripts/ directory.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import akshare as ak
import pandas as pd
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.futures import FuturesContract
from app.services.futures_service import FuturesService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Discovery: which specific contracts exist for a DCE root, and which is the
# "current main" (highest OI on the most recent trade date)?
# ---------------------------------------------------------------------------

# DCE contract naming: ``<ROOT><YY><MM>`` where YY is the 2-digit year and
# MM is the 2-digit month (e.g. ``M2609`` = soybean meal, September 2026).
# We probe a window of months centred on the current month because the
# "main" contract is typically the next 1-3 listed deliveries.
_PROBE_MONTHS_BACK = 2   # 2 months back from the current month
_PROBE_MONTHS_FORWARD = 6   # 6 months forward
_MAX_PROBE_WORKERS = 6


def _candidate_codes(root: str, today: date) -> list[str]:
    """Return the list of <ROOT>YYMM candidates to probe for a DCE root."""
    codes: list[str] = []
    year = today.year
    month = today.month
    for offset in range(-_PROBE_MONTHS_BACK, _PROBE_MONTHS_FORWARD + 1):
        m = month + offset
        y = year
        while m <= 0:
            m += 12
            y -= 1
        while m > 12:
            m -= 12
            y += 1
        codes.append(f"{root}{y % 100:02d}{m:02d}")
    return codes


def _fetch_one(symbol: str) -> tuple[str, date | None, float | None]:
    """Fetch one specific contract; return (symbol, last_date, last_OI).

    Returns (symbol, None, None) on any failure.
    """
    try:
        df = ak.futures_main_sina(symbol=symbol)
    except Exception as exc:
        logger.debug("futures_main_sina(%s) failed: %s", symbol, exc)
        return symbol, None, None
    if df is None or df.empty:
        return symbol, None, None
    try:
        last = df.iloc[-1]
        last_date = pd.to_datetime(last.iloc[0]).date()
        # Column index 6 = 持仓量 (open_interest) for the standard
        # ``futures_main_sina`` response shape (8 columns).
        raw_oi = last.iloc[6]
        last_oi = float(raw_oi) if pd.notna(raw_oi) else 0.0
        return symbol, last_date, last_oi
    except Exception as exc:
        logger.debug("parse failed for %s: %s", symbol, exc)
        return symbol, None, None


def _current_main_for_root(root: str, today: date | None = None) -> tuple[str, float]:
    """Return ``(specific_code, oi)`` for the active DCE main contract.

    Falls back to the standard DCE rule — the nearest non-expired
    delivery-month contract — if no probe returns a positive OI.
    """
    today = today or date.today()
    candidates = _candidate_codes(root, today)

    rows: list[tuple[str, date | None, float | None]] = []
    with ThreadPoolExecutor(max_workers=_MAX_PROBE_WORKERS) as ex:
        futures = {ex.submit(_fetch_one, sym): sym for sym in candidates}
        for fut in as_completed(futures):
            rows.append(fut.result())

    # Prefer rows whose last_date is within the most recent 7 calendar days
    # (so an expired/delisted contract doesn't accidentally win on stale OI).
    cutoff = today - timedelta(days=7)
    live = [
        (sym, d, oi)
        for sym, d, oi in rows
        if d is not None and d >= cutoff and oi is not None and oi > 0
    ]
    if live:
        live.sort(key=lambda r: (-r[2], r[0]))  # highest OI first, then code asc
        winner, last_date, oi = live[0]
        logger.info(
            "%s -> %s (OI=%s, last=%s)", root, winner, int(oi), last_date
        )
        return winner, oi

    # Fallback: nearest non-expired contract (lowest YYMM in the future).
    today_yyyymm = today.year * 100 + today.month
    future_codes = []
    for sym, _, _ in rows:
        try:
            yy = int(sym[-4:-2])
            mm = int(sym[-2:])
            yyyymm = (2000 + yy if yy < 80 else 1900 + yy) * 100 + mm
        except ValueError:
            continue
        if yyyymm >= today_yyyymm:
            future_codes.append(sym)
    if future_codes:
        fallback = sorted(future_codes)[0]
        logger.warning(
            "%s: no live OI data; falling back to nearest future code %s",
            root, fallback,
        )
        return fallback, 0.0

    # Last resort: the earliest candidate we probed.
    fallback = sorted(c for c, _, _ in rows)[0] if rows else f"{root}{today.year % 100:02d}09"
    logger.warning("%s: no future candidates; using %s as best guess", root, fallback)
    return fallback, 0.0


# ---------------------------------------------------------------------------
# DB I/O
# ---------------------------------------------------------------------------


def _dce_roots(session: Session) -> list[str]:
    """Return the alphabetic roots of every DCE main contract in the DB."""
    rows = (
        session.query(FuturesContract.code)
        .filter(FuturesContract.exchange == "DCE")
        .filter(FuturesContract.is_main == True)  # noqa: E712
        .all()
    )
    out: list[str] = []
    for (code,) in rows:
        root = "".join(ch for ch in code if ch.isalpha())
        if root:
            out.append(root)
    return sorted(set(out))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Refresh futures_contracts.underlying_instrument for DCE rows."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the picks without writing to the DB.",
    )
    parser.add_argument(
        "--roots",
        nargs="*",
        default=None,
        help="Only refresh these DCE roots (default: all DCE roots in DB).",
    )
    args = parser.parse_args()

    session = SessionLocal()
    try:
        if args.roots:
            roots = sorted({r.upper() for r in args.roots})
        else:
            roots = _dce_roots(session)
        if not roots:
            logger.error("No DCE roots to process.")
            return 1

        logger.info("Refreshing underlying_instrument for %d DCE roots: %s", len(roots), roots)

        # Resolve every root -> specific contract.
        picks: dict[str, tuple[str, float]] = {}
        for root in roots:
            picks[root] = _current_main_for_root(root)

        # Build the rows the service expects.
        # Each DB row's ``code`` is the continuous ``<ROOT>0`` value; we
        # only need to update ``underlying_instrument``, which keeps the
        # service's existing upsert behaviour idempotent.
        rows: list[dict] = []
        contracts = (
            session.query(FuturesContract)
            .filter(FuturesContract.exchange == "DCE")
            .filter(FuturesContract.is_main == True)  # noqa: E712
            .all()
        )
        for contract in contracts:
            root = "".join(ch for ch in contract.code if ch.isalpha())
            if root not in picks:
                continue
            specific, oi = picks[root]
            if contract.underlying_instrument == specific:
                logger.info(
                    "%s: underlying_instrument already %s; skipping",
                    contract.code, specific,
                )
                continue
            rows.append(
                {
                    "code": contract.code,
                    "name": contract.name,
                    "exchange": contract.exchange,
                    "product": contract.product,
                    "is_main": bool(contract.is_main),
                    "underlying_instrument": specific,
                    "contract_size": contract.contract_size,
                    "price_unit": contract.price_unit,
                    "quote_unit": contract.quote_unit,
                    "list_date": contract.list_date,
                    "delist_date": contract.delist_date,
                    "source": contract.source or "akshare",
                }
            )

        if not rows:
            logger.info("No changes required.")
            return 0

        logger.info("Updating %d futures_contracts rows:", len(rows))
        for r in rows:
            logger.info(
                "  %s.underlying_instrument = %s",
                r["code"], r["underlying_instrument"],
            )

        if args.dry_run:
            logger.info("--dry-run set; not writing to DB.")
            return 0

        service = FuturesService(session)
        written = service.upsert_contracts(rows)
        logger.info("Updated %d contracts.", written)
        return 0
    except Exception as exc:
        logger.exception("refresh_dce_underlying crashed: %s", exc)
        return 1
    finally:
        session.close()


if __name__ == "__main__":
    sys.exit(main())
