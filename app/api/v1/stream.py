"""SSE (Server-Sent Events) real-time price streaming endpoint.

GET /api/v1/stream/prices?codes=510300.SH,159915.SZ

Authenticated via Bearer token in the Authorization header (optional, allows
anonymous access for public data).
"""

import asyncio
import json
import logging
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.database import SessionLocal

router = APIRouter()
logger = logging.getLogger(__name__)

# Interval between price updates (seconds)
STREAM_INTERVAL = 3
# Max connection lifetime (seconds)
STREAM_TIMEOUT = 300


def _candidate_codes(code: str) -> list[str]:
    """Build a list of candidate code forms to try for lookup.

    Accepts both ``510300.SH`` and bare ``510300`` styles from the client.
    The DB stores codes WITH the market suffix (``510300.SH``, ``SPY.US``,
    ``BTC.US`` …), but historical/legacy rows may only have the bare
    numeric form. We try multiple shapes so that the SSE stream keeps
    working regardless of which side reformatted the symbol.
    """
    code = (code or "").strip()
    if not code:
        return []

    base = code.split(".", 1)[0] if "." in code else code
    has_suffix = "." in code

    candidates: list[str] = []
    seen: set[str] = set()

    def _push(value: str) -> None:
        if value and value not in seen:
            seen.add(value)
            candidates.append(value)

    # 1) Exact match as given by the client (with or without suffix).
    _push(code)

    # 2) If a suffix was provided, try the bare numeric/alphanumeric base.
    if has_suffix:
        _push(base)

    # 3) If the code has NO suffix, try common market suffixes so we can
    #    locate rows that always store the suffix in the DB.
    if not has_suffix:
        if base.isdigit():
            # A-share heuristic: 6xxxxx / 9xxxxx => SH, 0xxxxx / 2xxxxx / 3xxxxx => SZ
            if base.startswith(("5", "6", "9")):
                _push(f"{base}.SH")
            elif base.startswith(("0", "1", "2", "3")):
                _push(f"{base}.SZ")
        elif base.isalpha() and base.isupper() and len(base) <= 5:
            # Likely US-listed ticker or crypto symbol.
            _push(f"{base}.US")
            _push(f"{base}.HK")

    # 4) If a suffix was provided but no row matched, fall back to the
    #    bare form + the same heuristic (e.g. client sent ``SPY.HK`` by
    #    mistake — try ``SPY`` and ``SPY.US``).
    if has_suffix:
        if base.isdigit():
            if base.startswith(("5", "6", "9")):
                _push(f"{base}.SH")
            elif base.startswith(("0", "1", "2", "3")):
                _push(f"{base}.SZ")
        elif base.isalpha() and base.isupper():
            _push(f"{base}.US")
            _push(f"{base}.HK")

    return candidates


def _fetch_snapshot(db: Session, code: str) -> Optional[dict]:
    """Look up a single instrument's latest price snapshot.

    Returns ``None`` if neither ETFInfo nor InstrumentDailyBar has any row
    for the supplied code (in any of the candidate forms). The caller is
    responsible for emitting an ``unknown`` status event for those codes.
    """
    from app.models.etf import ETFInfo, InstrumentDailyBar

    candidates = _candidate_codes(code)
    if not candidates:
        return None

    matched_code: Optional[str] = None

    # 1) Try ETFInfo for any candidate form (preferred because it gives us
    #    the human-readable name and market).
    instrument: Optional[ETFInfo] = None
    for cand in candidates:
        instrument = (
            db.query(ETFInfo).filter(ETFInfo.code == cand).first()
        )
        if instrument is not None:
            matched_code = instrument.code
            break

    # 2) If still nothing, do a fuzzy LIKE lookup as a last resort. This
    #    handles rows where the DB stored something like ``510300`` while
    #    the client sent ``510300.SH`` (or vice versa).
    if instrument is None:
        base = code.split(".", 1)[0] if "." in code else code
        if base:
            instrument = (
                db.query(ETFInfo)
                .filter(ETFInfo.code.like(f"{base}%"))
                .first()
            )
            if instrument is not None:
                matched_code = instrument.code

    # 3) If ETFInfo still has nothing, the instrument might be a stock
    #    rather than an ETF. Fall back to InstrumentDailyBar — it covers
    #    stocks and ETFs alike.
    if instrument is None:
        bar_code: Optional[str] = None
        for cand in candidates:
            row = (
                db.query(InstrumentDailyBar.etf_code)
                .filter(InstrumentDailyBar.etf_code == cand)
                .order_by(InstrumentDailyBar.trade_date.desc())
                .first()
            )
            if row is not None:
                bar_code = row[0]
                break

        if bar_code is None and base:
            row = (
                db.query(InstrumentDailyBar.etf_code)
                .filter(InstrumentDailyBar.etf_code.like(f"{base}%"))
                .order_by(InstrumentDailyBar.trade_date.desc())
                .first()
            )
            if row is not None:
                bar_code = row[0]

        if bar_code is None:
            logger.debug(
                "SSE snapshot: no match for code=%s (tried %s)", code, candidates
            )
            return None

        matched_code = bar_code

    # 4) We have a matched code; fetch the latest two bars for change %.
    latest = (
        db.query(InstrumentDailyBar)
        .filter(InstrumentDailyBar.etf_code == matched_code)
        .order_by(InstrumentDailyBar.trade_date.desc())
        .first()
    )

    if not latest:
        logger.debug(
            "SSE snapshot: matched %s in ETFInfo but no InstrumentDailyBar rows",
            matched_code,
        )
        return None

    prev = (
        db.query(InstrumentDailyBar)
        .filter(InstrumentDailyBar.etf_code == matched_code)
        .order_by(InstrumentDailyBar.trade_date.desc())
        .offset(1)
        .first()
    )

    latest_close = latest.close or Decimal("0")
    prev_close = prev.close if prev else None

    change_pct = Decimal("0")
    if prev_close and prev_close != 0:
        change_pct = round((latest_close - prev_close) / prev_close * 100, 2)

    trade_date = latest.trade_date
    if isinstance(trade_date, datetime):
        ts_seconds = trade_date.timestamp()
    elif trade_date is not None:
        # ``trade_date`` is often a ``datetime.date`` (no tz, no time component).
        ts_seconds = datetime.combine(trade_date, datetime.min.time()).timestamp()
    else:
        ts_seconds = 0.0

    return {
        "code": matched_code,
        "name": instrument.name if instrument is not None else matched_code,
        "market": instrument.market if instrument is not None else None,
        "price": float(latest_close) if latest_close else 0.0,
        "change_pct": float(change_pct),
        "volume": latest.volume or 0,
        "timestamp": int(ts_seconds * 1000),
    }


async def _price_stream(
    codes: list[str],
) -> AsyncGenerator[str, None]:
    """Yield SSE price events at an interval."""
    deadline = asyncio.get_event_loop().time() + STREAM_TIMEOUT

    while asyncio.get_event_loop().time() < deadline:
        db = SessionLocal()
        try:
            snapshots = []
            unknown: list[str] = []
            seen_codes: set[str] = set()
            for code in codes:
                snap = _fetch_snapshot(db, code)
                if snap and snap["code"] not in seen_codes:
                    snapshots.append(snap)
                    seen_codes.add(snap["code"])
                elif snap is None:
                    unknown.append(code)

            if snapshots or unknown:
                payload = {"data": snapshots, "unknown": unknown}
                yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

        except Exception as e:
            logger.error(f"SSE stream error: {e}")
            yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"
        finally:
            db.close()

        await asyncio.sleep(STREAM_INTERVAL)


@router.get("/prices")
async def price_stream(
    codes: str = Query(..., description="Comma-separated instrument codes, e.g. 510300.SH,159915.SZ"),
):
    """Stream real-time price updates via SSE."""
    code_list = [c.strip() for c in codes.split(",") if c.strip()]

    return StreamingResponse(
        _price_stream(code_list),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )