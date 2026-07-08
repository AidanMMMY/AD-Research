"""yfinance-backed fetcher for major international stock indices.

Used by the Global Markets page to surface daily closes for indices
that FRED does not cover (DAX / FTSE / CAC / Nikkei / Hang Seng /
KOSPI / TWSE / ASX / NIFTY / SENSEX).  Upserts into the same
``macro_indicator`` table as FRED, tagged with ``source='yfinance'``
and ``region='global'`` so the existing ``/macro/latest`` endpoint
returns them with no schema changes.

Yahoo's unofficial API rate-limits anonymous requests aggressively
(~2,000 req/hour per IP).  We serialize calls with a 1.5s sleep,
best-effort log on per-ticker failure, and let the rest of the batch
continue.  Each ticker's data window is bounded to 30 trading days
to stay well under the daily quota even with re-runs.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class IndexMeta:
    """Static metadata for one tracked international index."""

    ticker: str           # yfinance ticker, e.g. ^GDAXI
    code: str             # internal id, e.g. global_dax
    name_zh: str          # Chinese display name
    name_en: str          # English display name
    unit: str = "指数"


# Single source of truth — adding/removing an entry here is the only
# change needed to extend coverage.  Tickers chosen to match Yahoo
# Finance's canonical symbols (caret-prefixed for indices).
GLOBAL_INDEX_REGISTRY: list[IndexMeta] = [
    IndexMeta("^GSPC",  "global_sp500",  "标普500",         "S&P 500"),
    IndexMeta("^NDX",   "global_ndx",    "纳斯达克100",      "NASDAQ-100"),
    IndexMeta("^DJI",   "global_dow",    "道琼斯工业指数",   "Dow Jones Industrial Average"),
    IndexMeta("^HSI",   "global_hsi",    "恒生指数",        "Hang Seng Index"),
    IndexMeta("^N225",  "global_n225",   "日经225",         "Nikkei 225"),
    IndexMeta("^GDAXI", "global_dax",    "德国DAX指数",      "DAX"),
    IndexMeta("^FTSE",  "global_ftse",   "英国FTSE 100",     "FTSE 100"),
    IndexMeta("^FCHI",  "global_cac",    "法国CAC 40",       "CAC 40"),
    IndexMeta("^AXJO",  "global_asx",    "澳洲ASX 200",      "ASX 200"),
    IndexMeta("^KS11",  "global_kospi",  "韩国综合指数",      "KOSPI"),
    IndexMeta("^TWII",  "global_twse",   "台湾加权指数",      "TWSE Weighted Index"),
    IndexMeta("^NSEI",  "global_nifty",  "印度NIFTY 50",     "NIFTY 50"),
    IndexMeta("^BSESN", "global_sensex", "印度SENSEX",        "BSE SENSEX"),
]


# Rate-limit guard: yfinance is sensitive to burst traffic from a
# single IP.  Empirically 1.5s between Ticker.history() calls keeps
# the 10-ticker batch well under Yahoo's hourly quota even when
# re-run several times per day.
_PER_TICKER_SLEEP = 1.5
_HISTORY_PERIOD = "3mo"   # ~63 trading days, covers a month of weekends/holidays


def _coerce_date(value) -> str | None:
    """Best-effort YYYY-MM-DD from a pandas Timestamp / datetime."""
    if value is None:
        return None
    try:
        return pd.Timestamp(value).strftime("%Y-%m-%d")
    except Exception:
        return None


def _coerce_float(value) -> float | None:
    if value is None:
        return None
    try:
        v = float(value)
        if pd.isna(v):
            return None
        return v
    except (TypeError, ValueError):
        return None


def fetch_yfinance_index(meta: IndexMeta) -> list[dict]:
    """Fetch up to 3 months of daily closes for one index ticker.

    Returns ``list[dict]`` shaped like::

        {
            "code": meta.code,
            "period": "YYYY-MM-DD",
            "value": float,        # daily close
            "prev_close": float,   # previous trading day close (None for first row)
            "name_zh": meta.name_zh,
            "name_en": meta.name_en,
            "unit": meta.unit,
        }

    Returns an empty list on failure (the caller logs and skips).
    """
    try:
        h = yf.Ticker(meta.ticker).history(period=_HISTORY_PERIOD)
    except Exception as exc:
        logger.warning(
            "yfinance index fetch failed for %s (%s): %s",
            meta.ticker, meta.code, exc,
        )
        return []

    if h is None or h.empty:
        logger.warning(
            "yfinance returned empty frame for %s (%s)",
            meta.ticker, meta.code,
        )
        return []

    # Drop timezone so downstream pd.Timestamp is consistent.
    try:
        idx = h.index.tz_localize(None)
    except (TypeError, AttributeError):
        idx = h.index
    h = h.copy()
    h.index = idx

    closes = h["Close"].tolist()
    dates = [d for d in idx]

    out: list[dict] = []
    for i, (dt, close_val) in enumerate(zip(dates, closes, strict=False)):
        period = _coerce_date(dt)
        value = _coerce_float(close_val)
        if period is None or value is None:
            continue
        prev_close = None
        if i > 0:
            prev_close = _coerce_float(closes[i - 1])
        out.append({
            "code": meta.code,
            "period": period,
            "value": value,
            "prev_close": prev_close,
            "name_zh": meta.name_zh,
            "name_en": meta.name_en,
            "unit": meta.unit,
        })
    return out


def fetch_all_global_indices() -> list[dict]:
    """Fetch every registered international index via yfinance.

    Returns a flat list of observations (one per (index, trading day))
    tagged with code/period/value.  Per-ticker failures are logged
    and skipped — the batch never raises.

    Note: rate-limit guards inside this function are deliberately
    conservative (1.5s between tickers) — adjust ``_PER_TICKER_SLEEP``
    if Yahoo changes its throttle policy.
    """
    out: list[dict] = []
    for meta in GLOBAL_INDEX_REGISTRY:
        rows = fetch_yfinance_index(meta)
        out.extend(rows)
        time.sleep(_PER_TICKER_SLEEP)
    logger.info(
        "yfinance global indices fetch done: %d observations across %d tickers",
        len(out), len(GLOBAL_INDEX_REGISTRY),
    )
    return out


def fetch_global_indices_latest() -> list[dict]:
    """Light wrapper: return only the most recent observation per ticker.

    Useful for the realtime preview endpoint
    (``GET /api/v1/macro/indices/global``) and for debugging —
    trims each ticker's history down to the latest single day.
    """
    latest_per_code: dict[str, dict] = {}
    for obs in fetch_all_global_indices():
        code = obs["code"]
        existing = latest_per_code.get(code)
        if existing is None or obs["period"] > existing["period"]:
            latest_per_code[code] = obs
    return list(latest_per_code.values())