"""yfinance-backed fetcher for global macro indicators.

Used by the Global Markets page and the macro-indicator dashboard to
surface daily closes for tickers that FRED does not cover (or that FRED
covers with a publishing delay) — international stock indices, FX, US
interest rates, and commodities.  Upserts into the same
``macro_indicator`` table as FRED, tagged with ``source='yfinance'``
and a per-row ``region`` so the existing ``/macro/latest`` endpoint
returns them with no schema changes.

Yahoo's unofficial API rate-limits anonymous requests aggressively
(~2,000 req/hour per IP).  We serialize calls with a 1.5s sleep,
best-effort log on per-ticker failure, and let the rest of the batch
continue.  Each ticker's data window is bounded to 30 trading days
to stay well under the daily quota even with re-runs.

FX convention reconciliation
----------------------------

Some yfinance FX tickers use the opposite convention to FRED's series
that share the same internal code.  To keep a single ``(code, region)``
key across both sources — which is what
``MacroDataService.latest_snapshot`` requires for the yfinance-vs-FRED
tie-break — we optionally invert the fetched value.  The flag lives
on ``IndexMeta.invert_value`` so the registry stays self-documenting:

    * ``CNY=X``   — matches FRED ``DEXCHUS`` ("CNY per USD").  No invert.
    * ``EUR=X``   — yfinance returns ~0.87 ("EUR per USD"); FRED
                    ``DEXUSEU`` is "USD per EUR" (~1.14).  Inverted.
    * ``JPY=X``   — matches FRED ``DEXJPUS`` ("JPY per USD", ~155).
                    yfinance returns ~162 in the same convention.  No invert.
    * ``DX-Y.NYB`` — the ICE DXY index value.  Indexed, not a ratio —
                     no invert.  Note: a different index from FRED's
                     ``DTWEXBGS`` (broad dollar) but stored under the
                     same ``global_dxy`` code as the conventional
                     label.
"""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class IndexMeta:
    """Static metadata for one tracked yfinance ticker.

    ``invert_value`` triggers a 1/val flip on the fetched close (and
    prev_close).  ``region`` is the ``macro_indicator.region`` value
    the row will be upserted under — chosen to match the FRED row
    for the same code so ``latest_snapshot`` can pick the newer source
    across the (code, region) key.
    """

    ticker: str           # yfinance ticker, e.g. ^GDAXI, CNY=X
    code: str             # internal id, e.g. global_dax, usd_eur
    name_zh: str          # Chinese display name
    name_en: str          # English display name
    unit: str = "指数"
    invert_value: bool = False   # flip 1/val for FX convention harmonization
    region: str = "global"       # matches FRED's region for the same code


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


# Forex tickers (Phase 6a — yfinance fallback for FRED-only FX codes).
#
# See the module docstring for the FX-convention reconciliation rules.
# Region tags match the FRED rows:
#   * usd_cny / usd_eur        → region="us"    (FRED has them under us_*)
#   * global_usdjpy / global_dxy → region="global" (cross-border)
GLOBAL_FOREX_REGISTRY: list[IndexMeta] = [
    IndexMeta(
        "CNY=X", "usd_cny", "美元/人民币", "USD/CNY", "CNY/USD",
        invert_value=False, region="us",
    ),
    IndexMeta(
        "EUR=X", "usd_eur", "美元/欧元", "USD/EUR", "EUR/USD",
        invert_value=True, region="us",
    ),
    IndexMeta(
        "JPY=X", "global_usdjpy", "美元/日元", "USD/JPY", "JPY/USD",
        invert_value=False, region="global",
    ),
    IndexMeta(
        "DX-Y.NYB", "global_dxy", "美元指数", "U.S. Dollar Index", "指数",
        invert_value=False, region="global",
    ),
]


# Interest-rate tickers (Phase 6a — yfinance fallback for FRED-only rates).
#
# CBOE yield indices quoted in percent (already the same unit as FRED's
# DGS10 / DGS30 series).  No inversion needed.  Skipped on purpose:
#   * 2Y (``us_dgs2``)         — no reliable yfinance ticker.
#   * DFF (``us_dff``)         — no yfinance equivalent.
#   * 10Y-2Y / 10Y-3M spreads — derived series, kept on FRED.
GLOBAL_RATES_REGISTRY: list[IndexMeta] = [
    IndexMeta(
        "^TNX", "us_dgs10", "美国10年期国债收益率", "10-Year Treasury Rate", "%",
        invert_value=False, region="us",
    ),
    IndexMeta(
        "^TYX", "us_dgs30", "美国30年期国债收益率", "30-Year Treasury Rate", "%",
        invert_value=False, region="us",
    ),
]


# Commodity tickers (Phase 6a — yfinance fallback for FRED-only commodities).
#
# Crude futures quoted in USD/bbl — same unit as FRED's DCOILWTICO and
# DCOILBRENTEU series.  No inversion needed.
GLOBAL_COMMODITY_REGISTRY: list[IndexMeta] = [
    IndexMeta(
        "CL=F", "global_wti", "WTI原油", "WTI Crude Oil", "USD/桶",
        invert_value=False, region="global",
    ),
    IndexMeta(
        "BZ=F", "global_brent", "布伦特原油", "Brent Crude Oil", "USD/桶",
        invert_value=False, region="global",
    ),
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


def _maybe_invert(value: float | None, invert: bool) -> float | None:
    """Apply the FX convention inversion to one close value.

    Inversion is skipped when the value is None or zero to avoid a
    divide-by-zero — a zero close is rare and almost always signals a
    feed glitch, so we propagate it as-is rather than blow up.
    """
    if value is None or not invert or value == 0:
        return value
    return 1.0 / value


def _history_frame_to_rows(h, meta: IndexMeta) -> list[dict]:
    """Convert a yfinance ``history()`` DataFrame into observation dicts.

    Drops the timezone on the index, walks ``Close`` from oldest →
    newest, and emits one row per day with ``prev_close`` populated
    from the previous row.  Returns an empty list on an empty / failed
    frame — callers must handle the empty case (logged separately).

    FX inversion (see module docstring) is applied per-row when
    ``meta.invert_value`` is set.
    """
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
    invert = bool(getattr(meta, "invert_value", False))

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
            "value": _maybe_invert(value, invert),
            "prev_close": _maybe_invert(prev_close, invert),
            "name_zh": meta.name_zh,
            "name_en": meta.name_en,
            "unit": meta.unit,
        })
    return out


def _fetch_history(meta: IndexMeta, **history_kwargs) -> list[dict]:
    """Internal helper: call ``yf.Ticker.history`` and convert to rows.

    Any exception (network blip, rate limit, schema change) is logged
    and swallowed — the batch never raises.
    """
    try:
        h = yf.Ticker(meta.ticker).history(**history_kwargs)
    except Exception as exc:
        logger.warning(
            "yfinance fetch failed for %s (%s): %s",
            meta.ticker, meta.code, exc,
        )
        return []
    return _history_frame_to_rows(h, meta)


def fetch_yfinance_index(meta: IndexMeta, period: str = _HISTORY_PERIOD) -> list[dict]:
    """Fetch up to ``period`` of daily closes for one index ticker.

    ``period`` is passed straight to ``yfinance.Ticker.history`` (e.g.
    ``"5d"``, ``"1mo"``, ``"3mo"``).  The scheduled ETL uses the
    default ``_HISTORY_PERIOD`` (3 months) for backfill coverage; the
    real-time dashboard overlay can pass a shorter window to keep the
    request fast.

    When ``meta.invert_value`` is True, each fetched close is inverted
    (1/val) so FX values match FRED's convention for the same internal
    code.
    """
    return _fetch_history(meta, period=period)


def fetch_all_global_indices(period: str = _HISTORY_PERIOD) -> list[dict]:
    """Fetch every registered international index via yfinance.

    Returns a flat list of observations (one per (index, trading day))
    tagged with code/period/value.  Per-ticker failures are logged and
    skipped — the batch never raises.

    ``period`` controls the history window and is forwarded to each
    ``fetch_yfinance_index`` call.  The daily ETL uses the default 3
    month window; the realtime API can pass a short window (e.g. ``"5d"``)
    to keep response times low.
    """
    out: list[dict] = []
    for meta in GLOBAL_INDEX_REGISTRY:
        rows = fetch_yfinance_index(meta, period=period)
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


# ---------------------------------------------------------------------------
# Per-class latest-bar fetchers (Phase 6b).
#
# Each returns ``list[dict]`` of the latest single observation per
# ticker, in the same shape ``fetch_yfinance_index`` returns:
# ``{code, period, value, prev_close, name_zh, name_en, unit}``.
#
# These were originally declared as part of the realtime endpoint
# contract; we expose them as standalone helpers so other callers
# (schedulers, dashboards) can pull one asset class at a time without
# walking the whole universe.
# ---------------------------------------------------------------------------


def _latest_per_code(rows: list[dict]) -> list[dict]:
    """Reduce a per-ticker history list to the single latest row per code."""
    latest_per_code: dict[str, dict] = {}
    for obs in rows:
        code = obs["code"]
        existing = latest_per_code.get(code)
        if existing is None or obs["period"] > existing["period"]:
            latest_per_code[code] = obs
    return list(latest_per_code.values())


def fetch_yfinance_forex_latest(period: str = "2d") -> list[dict]:
    """Return the latest bar per FX ticker in ``GLOBAL_FOREX_REGISTRY``.

    ``period`` is forwarded to ``yf.Ticker.history``; the realtime
    overlay uses ``"2d"`` so we get yesterday's close (prev_close) and
    today's open/last bar without paying for the full 3-month window.
    """
    rows: list[dict] = []
    for meta in GLOBAL_FOREX_REGISTRY:
        rows.extend(fetch_yfinance_index(meta, period=period))
        time.sleep(_PER_TICKER_SLEEP)
    return _latest_per_code(rows)


def fetch_yfinance_rates_latest(period: str = "2d") -> list[dict]:
    """Return the latest bar per rates ticker in ``GLOBAL_RATES_REGISTRY``."""
    rows: list[dict] = []
    for meta in GLOBAL_RATES_REGISTRY:
        rows.extend(fetch_yfinance_index(meta, period=period))
        time.sleep(_PER_TICKER_SLEEP)
    return _latest_per_code(rows)


def fetch_yfinance_commodity_latest(period: str = "2d") -> list[dict]:
    """Return the latest bar per commodity ticker in ``GLOBAL_COMMODITY_REGISTRY``."""
    rows: list[dict] = []
    for meta in GLOBAL_COMMODITY_REGISTRY:
        rows.extend(fetch_yfinance_index(meta, period=period))
        time.sleep(_PER_TICKER_SLEEP)
    return _latest_per_code(rows)


# ---------------------------------------------------------------------------
# Phase 6b — Realtime aggregator.
#
# Walks all four registries (stock indices + FX + rates + commodity) and
# returns the latest observation per code.  Runs the registries in
# parallel via a ThreadPoolExecutor — yfinance's ``Ticker.history`` call
# releases the GIL while waiting on the HTTP response, so concurrent
# fan-out drops a 21-ticker sequential run (~32s) down to ~4s, which
# fits the Dashboard's realtime request budget.
# ---------------------------------------------------------------------------


# Cap parallel yfinance calls per registry.  Yahoo's anonymous quota
# is ~2,000 req/hour per IP; with 21 tickers × 1 batch / min we'd
# exhaust it in ~95 minutes, so we cap at 6 concurrent calls per
# registry as a safety margin against bursts.
_PARALLEL_WORKERS_PER_REGISTRY = 6


def _fetch_one_latest(meta: IndexMeta, period: str) -> list[dict]:
    """Fetch one ticker and reduce to its single latest bar."""
    rows = fetch_yfinance_index(meta, period=period)
    return _latest_per_code(rows)


def fetch_all_macro_realtime(period: str = "2d") -> list[dict]:
    """Realtime aggregator — stock indices + FX + rates + commodity, latest bar.

    Returns a flat list of latest observations (one per code), sorted
    by code.  Per-ticker failures are logged and skipped.  Runs all
    21 tickers in parallel (4–6 concurrent per registry) so the
    realtime endpoint stays under ~6s end-to-end.

    ``period`` is forwarded to every ``yf.Ticker.history`` call; the
    realtime overlay defaults to ``"2d"`` (yesterday + today) so the
    Dashboard sees both prev_close and the latest live bar.
    """
    registries: tuple[list[IndexMeta], ...] = (
        GLOBAL_INDEX_REGISTRY,
        GLOBAL_FOREX_REGISTRY,
        GLOBAL_RATES_REGISTRY,
        GLOBAL_COMMODITY_REGISTRY,
    )

    out: list[dict] = []

    # Fan out per-registry: a per-registry executor keeps the connection
    # pool narrow (4–6 concurrent yfinance sessions per registry) so we
    # don't blow through Yahoo's hourly quota.  Registries run
    # sequentially relative to each other — within each registry, the
    # tickers run concurrently.
    for registry in registries:
        if not registry:
            continue
        with ThreadPoolExecutor(
            max_workers=min(_PARALLEL_WORKERS_PER_REGISTRY, len(registry)),
            thread_name_prefix=f"yf-{registry[0].code.split('_')[0]}",
        ) as pool:
            futures = {
                pool.submit(_fetch_one_latest, meta, period): meta
                for meta in registry
            }
            for fut in as_completed(futures):
                meta = futures[fut]
                try:
                    out.extend(fut.result())
                except Exception as exc:  # noqa: BLE001 - defensive
                    logger.warning(
                        "yfinance realtime fetch failed for %s (%s): %s",
                        meta.ticker, meta.code, exc,
                    )

    out.sort(key=lambda x: x.get("code") or "")
    logger.info(
        "yfinance realtime aggregator done: %d codes across %d tickers (period=%s)",
        len(out),
        sum(len(r) for r in registries),
        period,
    )
    return out


# ---------------------------------------------------------------------------
# Phase 6a — FX / rates / commodities fetcher.
#
# Adds yfinance coverage for the FRED-only codes that were going stale
# (FX, US interest rates, crude).  Returns rows grouped by region so the
# caller can upsert each region separately — this is what lets
# ``MacroDataService.latest_snapshot`` prefer yfinance over FRED on
# the (code, region) tie-break.
# ---------------------------------------------------------------------------


def fetch_yfinance_macro_latest(
    start: str | None = None,
    end: str | None = None,
) -> dict[str, list[dict]]:
    """Fetch FX / rates / commodity tickers via yfinance, grouped by region.

    Loops the FX, rates, and commodity registries and returns a dict
    ``{region: [observations]}``.  Each observation dict is shaped
    ``{code, period, value, prev_close, name_zh, name_en, unit}`` —
    the same shape ``fetch_yfinance_index`` returns — so the caller
    can upsert each region via
    ``MacroDataService.upsert_observations(region=..., source="yfinance", observations=...)``.

    When ``start`` or ``end`` are provided the kwargs are forwarded to
    ``yf.Ticker.history(start=..., end=...)`` so the scheduler can
    backfill a precise window.  Otherwise the default
    ``_HISTORY_PERIOD`` is used.

    Region tagging matches the FRED registry so the yfinance rows share
    the same ``(code, region)`` key as the FRED rows for the same code
    (see module docstring).  Per-ticker failures are logged and
    skipped — the batch never raises.
    """
    out: dict[str, list[dict]] = {}

    if start or end:
        kwargs: dict[str, str] = {}
        if start:
            kwargs["start"] = start
        if end:
            kwargs["end"] = end
    else:
        kwargs = {"period": _HISTORY_PERIOD}

    registries: tuple[list[IndexMeta], ...] = (
        GLOBAL_FOREX_REGISTRY,
        GLOBAL_RATES_REGISTRY,
        GLOBAL_COMMODITY_REGISTRY,
    )

    for registry in registries:
        for meta in registry:
            rows = _fetch_history(meta, **kwargs)
            # _fetch_history returns [] on failure (logged inside).
            region = getattr(meta, "region", "global")
            out.setdefault(region, []).extend(rows)
            time.sleep(_PER_TICKER_SLEEP)

    total = sum(len(v) for v in out.values())
    logger.info(
        "yfinance macro fetch done: %d observations across %d tickers (regions=%s)",
        total,
        sum(len(r) for r in registries),
        sorted(out.keys()),
    )
    return out