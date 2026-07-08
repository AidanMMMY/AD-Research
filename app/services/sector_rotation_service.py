"""Sector rotation analysis service.

Provides sector performance tracking, relative strength calculation,
momentum ranking, and rotation signal detection.

This service is intentionally scoped to A-share (沪深北) instruments
(individual stocks + ETFs). Crypto and US/HK/JP instruments are out of
scope for sector rotation because:

  - crypto markets do not map cleanly onto traditional industry taxonomies
  - US/HK/JP stocks use GICS but their indices, sector composition and
    trading hours differ materially — mixing them into a single "market
    average" would mislead the relative-strength signal.

Each row in the response corresponds to a GICS sector (level-1) or
industry (level-2), aggregated across both STOCKs and ETFs whose
``etf_info.sector`` field is populated. ETFs without an explicit sector
get one inferred from their ``sub_category`` / ``underlying_index`` via a
heuristic mapping (``ETF_SUB_CATEGORY_HINTS`` below).

Industry classification rationale (2026-07-08)
-----------------------------------------------
Project data state on the A-share universe (verified via the
``a_share_stock_discovery`` pipeline + ``backfill_a_share_industry``):

  - STOCKs (CSRC name from Tushare → GICS sector)  : ~5,000 rows, all populated
  - ETFs                                              : no sector populated, only ``category``/``sub_category``
  - US/HK stocks                                      : GICS populated

GICS (Global Industry Classification Standard) was chosen over 申万 /
中信 / CSRC for the following reasons:

  1. The existing ETL already populates ``etf_info.sector`` with GICS for
     A-share stocks and US stocks. Re-using it gives cross-market
     comparability if/when HK/JP are added.
  2. 申万 / 中信 change their constituents on an annual basis and have
     overlapping boundaries — keeping them in sync requires a dedicated
     refresh job. Defer to Phase 6+ (see TODO at end of file).
  3. CSRC classification is the broadest (门类→大类→中类→小类) and is
     already used internally as the *source* for the GICS mapping, so
     exposing CSRC would be redundant.

Individual stock vs ETF (analysis decision)
--------------------------------------------
Both are aggregated into the same sector bucket for two reasons:

  1. Practitioners care about *industry exposure* — a 半导体 ETF and a
     半导体 龙头 stock both belong to the "semiconductors" trade.
     Splitting them into separate sector rows inflates counts and
     dilutes the RS signal.
  2. The double-counting risk (an ETF holding constituent stocks) is
     bounded: A-share ETFs are mostly broad-market / sector-tracking,
     and the platform already exposes per-instrument detail for anyone
     who wants to drill down.

Per ETF/stock counts are still exposed (``stock_count`` / ``etf_count``)
so the user can see composition without splitting the aggregation.
"""

from datetime import date, timedelta
from typing import Any

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.models.etf import ETFIndicator, ETFInfo

# ---------------------------------------------------------------------------
# ETF sub_category / underlying_index → GICS sector heuristic mapping.
#
# Heuristics are intentionally conservative — we only assign a sector when
# the sub_category or underlying_index contains a known keyword. Anything
# unmatched falls back to "Broad Market" (宽基) and is reported as its own
# sector row so the user can see what slipped through the mapping.
# ---------------------------------------------------------------------------

ETF_SECTOR_HINTS: list[tuple[str, str]] = [
    # (keyword, GICS sector)
    ("半导体", "Information Technology"),
    ("芯片", "Information Technology"),
    ("软件", "Information Technology"),
    ("互联网", "Communication Services"),
    ("传媒", "Communication Services"),
    ("通信", "Communication Services"),
    ("5G", "Communication Services"),
    ("云计算", "Information Technology"),
    ("AI", "Information Technology"),
    ("人工智能", "Information Technology"),
    ("科技", "Information Technology"),
    ("TMT", "Information Technology"),
    ("计算机", "Information Technology"),
    ("电子", "Information Technology"),
    ("医药", "Health Care"),
    ("医疗", "Health Care"),
    ("生物", "Health Care"),
    ("创新药", "Health Care"),
    ("银行", "Financials"),
    ("证券", "Financials"),
    ("保险", "Financials"),
    ("金融", "Financials"),
    ("地产", "Real Estate"),
    ("房地产", "Real Estate"),
    ("白酒", "Consumer Staples"),
    ("酒", "Consumer Staples"),
    ("食品", "Consumer Staples"),
    ("饮料", "Consumer Staples"),
    ("家电", "Consumer Discretionary"),
    ("汽车", "Consumer Discretionary"),
    ("消费", "Consumer Staples"),
    ("零售", "Consumer Discretionary"),
    ("旅游", "Consumer Discretionary"),
    ("军工", "Industrials"),
    ("国防", "Industrials"),
    ("工业", "Industrials"),
    ("制造", "Industrials"),
    ("新能源", "Utilities"),
    ("光伏", "Information Technology"),
    ("锂电", "Industrials"),
    ("电池", "Industrials"),
    ("环保", "Utilities"),
    ("公用", "Utilities"),
    ("电力", "Utilities"),
    ("煤炭", "Energy"),
    ("石油", "Energy"),
    ("石化", "Energy"),
    ("钢铁", "Materials"),
    ("有色", "Materials"),
    ("化工", "Materials"),
    ("建材", "Materials"),
    ("农业", "Consumer Staples"),
    ("畜牧", "Consumer Staples"),
    ("养殖", "Consumer Staples"),
    ("教育", "Consumer Discretionary"),
    ("传媒娱乐", "Communication Services"),
]

# Broad-market fallback — applies when an ETF is category=股票型 but no
# sub_category / underlying_index hint matched.
BROAD_MARKET_SECTOR = "Broad Market"
BROAD_MARKET_LABEL_ZH = "宽基指数"


def _resolve_etf_sector(info: ETFInfo) -> str | None:
    """Resolve an ETF's GICS sector from its metadata.

    Order:
      1. Pre-populated ``etf_info.sector`` (e.g. manually enriched ETFs)
      2. Keyword match against ``sub_category`` / ``underlying_index``
      3. ``BROAD_MARKET_SECTOR`` for generic stock-type ETFs (宽基)
      4. None for non-equity ETFs (bond/gold/money-market) — they are
         filtered out of sector rotation entirely.
    """
    if info.sector:
        return info.sector

    haystack_parts = [
        info.sub_category or "",
        info.underlying_index or "",
        info.category or "",
    ]
    haystack = " ".join(haystack_parts).lower()

    for keyword, sector in ETF_SECTOR_HINTS:
        if keyword.lower() in haystack:
            return sector

    # Generic equity ETF without a thematic tag → broad market bucket.
    if (info.category or "").startswith("股票"):
        return BROAD_MARKET_SECTOR

    # Bond / commodity / money-market — not industry sectors.
    return None


def _resolve_sector(info: ETFInfo) -> str | None:
    """Resolve the GICS sector for any instrument (ETF or STOCK)."""
    if info.instrument_type == "STOCK":
        return info.sector or None
    if info.instrument_type == "ETF":
        return _resolve_etf_sector(info)
    # CRYPTO / others — out of scope.
    return None


class SectorRotationService:
    """Service for sector rotation analysis.

    Scope: A-share universe (沪深北), ETF + STOCK only.
    """

    # Scope constants — keep callers from drifting outside A-share.
    _SCOPE_MARKET = "A股"
    _SCOPE_INSTRUMENT_TYPES = ("ETF", "STOCK")

    def __init__(self, db: Session):
        self.db = db

    def get_sector_list(self) -> list[dict[str, Any]]:
        """List distinct GICS sectors with A-share ETF+stock counts."""
        # Resolve sector for every instrument via a per-row CASE expression
        # so we can group by the resolved value in SQL.
        # For STOCKs we use ``sector`` directly; for ETFs we apply the
        # keyword-heuristic mapping inline.
        resolved = case(
            (ETFInfo.instrument_type == "STOCK", ETFInfo.sector),
            else_=None,
        ).label("sector")

        rows = (
            self.db.query(
                ETFInfo.code,
                ETFInfo.instrument_type,
                ETFInfo.sector,
                ETFInfo.sub_category,
                ETFInfo.underlying_index,
                ETFInfo.category,
            )
            .filter(
                ETFInfo.market == self._SCOPE_MARKET,
                ETFInfo.instrument_type.in_(self._SCOPE_INSTRUMENT_TYPES),
                ETFInfo.status == "active",
            )
            .all()
        )

        counts: dict[str, dict[str, int]] = {}
        for r in rows:
            # Mirror ORM row → ad-hoc object
            info = ETFInfo(
                code=r.code,
                instrument_type=r.instrument_type,
                sector=r.sector,
                sub_category=r.sub_category,
                underlying_index=r.underlying_index,
                category=r.category,
            )
            sector = _resolve_sector(info)
            if not sector:
                continue
            bucket = counts.setdefault(
                sector, {"count": 0, "stock_count": 0, "etf_count": 0}
            )
            bucket["count"] += 1
            if r.instrument_type == "STOCK":
                bucket["stock_count"] += 1
            elif r.instrument_type == "ETF":
                bucket["etf_count"] += 1

        # Sort by total count desc.
        return [
            {"sector": sector, **stats}
            for sector, stats in sorted(
                counts.items(), key=lambda kv: kv[1]["count"], reverse=True
            )
        ]

    def analyze_sectors(
        self,
        trade_date: date | None = None,
        window_weeks: int = 4,
    ) -> dict[str, Any]:
        """Analyze sector performance and rotation signals.

        Args:
            trade_date: Date to analyze. Defaults to latest available
                indicator date in the A-share ETF/STOCK universe.
            window_weeks: Unused kept for API compatibility — momentum
                windows are now driven by indicator periods (1w/1m/3m/6m/1y).

        Returns:
            Dict with sector performance, relative strength, momentum
            ranking, and rotation signals.
        """
        if trade_date is None:
            latest = (
                self.db.query(func.max(ETFIndicator.trade_date))
                .join(ETFInfo, ETFIndicator.etf_code == ETFInfo.code)
                .filter(
                    ETFInfo.market == self._SCOPE_MARKET,
                    ETFInfo.instrument_type.in_(self._SCOPE_INSTRUMENT_TYPES),
                )
                .scalar()
            )
            if latest is None:
                return self._empty_result()
            trade_date = latest

        # Pull indicators + joined instrument metadata for the trade date.
        rows = (
            self.db.query(ETFIndicator, ETFInfo)
            .join(ETFInfo, ETFIndicator.etf_code == ETFInfo.code)
            .filter(
                ETFIndicator.trade_date == trade_date,
                ETFInfo.market == self._SCOPE_MARKET,
                ETFInfo.instrument_type.in_(self._SCOPE_INSTRUMENT_TYPES),
            )
            .all()
        )

        if not rows:
            return self._empty_result(trade_date=trade_date)

        # ------------------------------------------------------------------
        # Per-sector aggregation
        # ------------------------------------------------------------------
        # values[sector] = {
        #   'count': int,
        #   'stock_count': int,
        #   'etf_count': int,
        #   'returns_1w/1m/3m/6m/1y': list[float],
        #   'sharpe_1y': list[float],
        #   'volatility_20d': list[float],
        #   'rsi14': list[float],
        #   'amount': list[float],
        # }
        sectors: dict[str, dict[str, Any]] = {}
        market_returns: dict[str, list[float]] = {
            "return_1w": [], "return_1m": [], "return_3m": [],
            "return_6m": [], "return_1y": [],
        }
        market_sharpe: list[float] = []

        for ind, info in rows:
            sector = _resolve_sector(info)
            if not sector:
                continue

            bucket = sectors.setdefault(
                sector,
                {
                    "count": 0,
                    "stock_count": 0,
                    "etf_count": 0,
                    "return_1w": [],
                    "return_1m": [],
                    "return_3m": [],
                    "return_6m": [],
                    "return_1y": [],
                    "sharpe_1y": [],
                    "volatility_20d": [],
                    "rsi14": [],
                    "amount": [],
                },
            )
            bucket["count"] += 1
            if info.instrument_type == "STOCK":
                bucket["stock_count"] += 1
            elif info.instrument_type == "ETF":
                bucket["etf_count"] += 1

            for period in ("1w", "1m", "3m", "6m", "1y"):
                col = getattr(ind, f"return_{period}", None)
                if col is not None:
                    f = float(col)
                    bucket[f"return_{period}"].append(f)
                    market_returns[f"return_{period}"].append(f)

            if ind.sharpe_1y is not None:
                bucket["sharpe_1y"].append(float(ind.sharpe_1y))
                market_sharpe.append(float(ind.sharpe_1y))
            if ind.volatility_20d is not None:
                bucket["volatility_20d"].append(float(ind.volatility_20d))
            if ind.rsi14 is not None:
                bucket["rsi14"].append(float(ind.rsi14))
            if ind.amount is not None:
                bucket["amount"].append(float(ind.amount))

        if not sectors:
            return self._empty_result(trade_date=trade_date)

        market_avg: dict[str, float] = {}
        for period, vals in market_returns.items():
            market_avg[period] = (sum(vals) / len(vals)) if vals else 0.0
        market_avg["sharpe_1y"] = (
            (sum(market_sharpe) / len(market_sharpe)) if market_sharpe else 0.0
        )

        # ------------------------------------------------------------------
        # Build sector summary
        # ------------------------------------------------------------------
        sector_rows: list[dict[str, Any]] = []
        for sector, vals in sectors.items():
            if not vals["return_1m"]:
                continue

            avg = lambda lst: (sum(lst) / len(lst)) if lst else 0.0  # noqa: E731

            avg_1m = avg(vals["return_1m"])
            avg_3m = avg(vals["return_3m"])

            # Relative Strength = sector return / market average return
            rs_1m = (avg_1m / market_avg["return_1m"]) if market_avg["return_1m"] else 1.0
            rs_3m = (avg_3m / market_avg["return_3m"]) if market_avg["return_3m"] else 1.0
            rs_1w = (
                avg(vals["return_1w"]) / market_avg["return_1w"]
                if market_avg["return_1w"]
                else 1.0
            )

            sector_rows.append({
                "sector": sector,
                "count": vals["count"],
                "stock_count": vals["stock_count"],
                "etf_count": vals["etf_count"],
                "return_1w": round(avg(vals["return_1w"]), 4),
                "return_1m": round(avg_1m, 4),
                "return_3m": round(avg_3m, 4),
                "return_6m": round(avg(vals["return_6m"]), 4),
                "return_1y": round(avg(vals["return_1y"]), 4),
                "sharpe_1y": round(avg(vals["sharpe_1y"]), 4),
                "volatility_20d": round(avg(vals["volatility_20d"]), 4),
                "rsi14": round(avg(vals["rsi14"]), 2),
                "amount_total": round(sum(vals["amount"]), 2),
                "relative_strength_1w": round(rs_1w, 4),
                "relative_strength_1m": round(rs_1m, 4),
                "relative_strength_3m": round(rs_3m, 4),
            })

        # Sort by 1-month return for momentum ranking
        sector_rows.sort(key=lambda x: x["return_1m"], reverse=True)
        for rank, row in enumerate(sector_rows, 1):
            row["momentum_rank"] = rank

        rotation_signals = self._detect_rotation_signals(sector_rows, trade_date)

        return {
            "trade_date": trade_date.isoformat(),
            "scope": {
                "market": self._SCOPE_MARKET,
                "instrument_types": list(self._SCOPE_INSTRUMENT_TYPES),
                "classification": "GICS",
            },
            "sectors": sector_rows,
            "market_avg": {k: round(v, 4) for k, v in market_avg.items()},
            "rotation_signals": rotation_signals,
        }

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _empty_result(
        self, trade_date: date | None = None
    ) -> dict[str, Any]:
        return {
            "trade_date": trade_date.isoformat() if trade_date else None,
            "scope": {
                "market": self._SCOPE_MARKET,
                "instrument_types": list(self._SCOPE_INSTRUMENT_TYPES),
                "classification": "GICS",
            },
            "sectors": [],
            "market_avg": None,
            "rotation_signals": [],
        }

    def _detect_rotation_signals(
        self,
        current_sectors: list[dict[str, Any]],
        trade_date: date,
    ) -> list[dict[str, Any]]:
        """Detect sector rotation by comparing with previous period.

        The previous period is the most recent indicator date strictly
        before ``trade_date`` (typically one week earlier on a daily
        refresh). We re-aggregate by sector for that date and compare
        rank deltas.

        A swing of ≥ 3 positions in the 1-month return ranking is
        surfaced as a signal.
        """
        prev_available = (
            self.db.query(func.max(ETFIndicator.trade_date))
            .filter(ETFIndicator.trade_date < trade_date)
            .scalar()
        )
        if prev_available is None:
            return []

        prev_rows = (
            self.db.query(ETFIndicator, ETFInfo)
            .join(ETFInfo, ETFIndicator.etf_code == ETFInfo.code)
            .filter(
                ETFIndicator.trade_date == prev_available,
                ETFInfo.market == self._SCOPE_MARKET,
                ETFInfo.instrument_type.in_(self._SCOPE_INSTRUMENT_TYPES),
            )
            .all()
        )

        if not prev_rows:
            return []

        prev_returns: dict[str, list[float]] = {}
        for ind, info in prev_rows:
            sector = _resolve_sector(info)
            if not sector or ind.return_1m is None:
                continue
            prev_returns.setdefault(sector, []).append(float(ind.return_1m))

        if not prev_returns:
            return []

        prev_avg = {
            s: (sum(v) / len(v))
            for s, v in prev_returns.items()
            if v
        }
        prev_ranked = sorted(prev_avg.items(), key=lambda x: x[1], reverse=True)
        prev_rank_map = {sector: rank for rank, (sector, _) in enumerate(prev_ranked, 1)}

        signals: list[dict[str, Any]] = []
        for sector in current_sectors:
            current_rank = sector["momentum_rank"]
            prev_rank = prev_rank_map.get(sector["sector"])
            if prev_rank is None:
                continue

            rank_change = prev_rank - current_rank  # positive = moved up
            if rank_change >= 3:
                signals.append({
                    "sector": sector["sector"],
                    "type": "up",
                    "message": (
                        f"{sector['sector']} 板块排名上升 {rank_change} 位，动量增强"
                    ),
                    "current_rank": current_rank,
                    "previous_rank": prev_rank,
                    "rank_change": rank_change,
                })
            elif rank_change <= -3:
                signals.append({
                    "sector": sector["sector"],
                    "type": "down",
                    "message": (
                        f"{sector['sector']} 板块排名下降 {abs(rank_change)} 位，动量减弱"
                    ),
                    "current_rank": current_rank,
                    "previous_rank": prev_rank,
                    "rank_change": rank_change,
                })

        return signals


# ---------------------------------------------------------------------------
# TODO(phase-6+): 申万行业分类 support
#
# 申万 / 中信 are the dominant Chinese sector taxonomies and are what
# buy-side desks actually quote ("今天 SW801010 农林牧渔 涨多少"). To
# support them we will:
#
#   1. Add a ``industry_sw`` table: (code, name, level) e.g. SW801010.
#   2. Add a ``instrument_industry`` table linking instrument_code → sw_code.
#   3. Backfill from akshare's ``stock_industry_sw`` for A-share stocks.
#   4. Extend ``SectorRotationService.analyze_sectors`` with a
#      ``classification="SW2021"`` toggle and a parallel return path.
#   5. Add a tab on the SectorRotation UI for SW vs GICS.
#
# Until that ships, GICS is the canonical view.
# ---------------------------------------------------------------------------