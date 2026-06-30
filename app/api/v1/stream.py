"""SSE (Server-Sent Events) real-time price streaming endpoint.

GET /api/v1/stream/prices?codes=510300,159915

Authenticated via Bearer token in the Authorization header (optional, allows
anonymous access for public data).
"""

import asyncio
import json
import logging
from collections.abc import AsyncGenerator
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


def _fetch_snapshot(db: Session, code: str) -> Optional[dict]:
    """Look up a single instrument's latest price snapshot."""
    from app.models.etf import ETFInfo, InstrumentDailyBar

    instrument = db.query(ETFInfo).filter(ETFInfo.code == code).first()
    if not instrument:
        return None

    latest = (
        db.query(InstrumentDailyBar)
        .filter(InstrumentDailyBar.etf_code == code)
        .order_by(InstrumentDailyBar.trade_date.desc())
        .first()
    )

    if not latest:
        return None

    prev = (
        db.query(InstrumentDailyBar)
        .filter(InstrumentDailyBar.etf_code == code)
        .order_by(InstrumentDailyBar.trade_date.desc())
        .offset(1)
        .first()
    )

    latest_close = latest.close or Decimal("0")
    prev_close = prev.close if prev else None

    change_pct = Decimal("0")
    if prev_close and prev_close != 0:
        change_pct = round((latest_close - prev_close) / prev_close * 100, 2)

    return {
        "code": instrument.code,
        "name": instrument.name,
        "market": instrument.market,
        "price": float(latest_close) if latest_close else 0.0,
        "change_pct": float(change_pct),
        "volume": latest.volume or 0,
        "timestamp": int(latest.trade_date.timestamp() * 1000) if latest.trade_date else 0,
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
            for code in codes:
                snap = _fetch_snapshot(db, code)
                if snap:
                    snapshots.append(snap)

            if snapshots:
                # SSE format: "data: <json>\n\n"
                yield f"data: {json.dumps(snapshots, ensure_ascii=False)}\n\n"

        except Exception as e:
            logger.error(f"SSE stream error: {e}")
            yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"
        finally:
            db.close()

        await asyncio.sleep(STREAM_INTERVAL)


@router.get("/prices")
async def price_stream(
    codes: str = Query(..., description="Comma-separated instrument codes, e.g. 510300,159915"),
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
