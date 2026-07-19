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
from typing import Any, Literal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.data.indicators.a_share_sw_mapping import ETF_SW_HINTS
from app.models.etf import ETFIndicator, ETFInfo, StockFundamental

#: Industry classification systems supported by this service. ``GICS`` is the
#: cross-market default (also used for US/HK if ever added); ``SW`` is the
#: 申万2021一级行业 view exposed for A-share-only analysis.
Classification = Literal["GICS", "SW"]

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


def _resolve_etf_sector(
    info: ETFInfo, classification: Classification = "GICS"
) -> str | None:
    """Resolve an ETF's industry bucket from its metadata.

    ``classification`` selects the taxonomy:

      - ``GICS`` (default): pre-populated ``etf_info.sector`` → GICS keyword
        hints → broad-market → None.
      - ``SW``: pre-populated ``etf_info.sw_l1`` → 申万 keyword hints →
        broad-market → None.

    In both modes non-equity ETFs (bond/gold/money-market) resolve to None
    and are filtered out of sector rotation entirely.
    """
    if classification == "SW":
        if info.sw_l1:
            return info.sw_l1
        hints = ETF_SW_HINTS
    else:
        if info.sector:
            return info.sector
        hints = ETF_SECTOR_HINTS

    haystack_parts = [
        info.sub_category or "",
        info.underlying_index or "",
        info.category or "",
    ]
    haystack = " ".join(haystack_parts).lower()

    for keyword, bucket in hints:
        if keyword.lower() in haystack:
            return bucket

    # Generic equity ETF without a thematic tag → broad market bucket.
    if (info.category or "").startswith("股票"):
        return BROAD_MARKET_SECTOR

    # Bond / commodity / money-market — not industry sectors.
    return None


def _resolve_sector(
    info: ETFInfo, classification: Classification = "GICS"
) -> str | None:
    """Resolve the industry bucket for any instrument (ETF or STOCK).

    STOCKs use ``etf_info.sw_l1`` under SW and ``etf_info.sector`` under
    GICS; ETFs are resolved via ``_resolve_etf_sector``.
    """
    if info.instrument_type == "STOCK":
        if classification == "SW":
            return info.sw_l1 or None
        return info.sector or None
    if info.instrument_type == "ETF":
        return _resolve_etf_sector(info, classification)
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

    def get_sector_list(
        self, classification: Classification = "GICS"
    ) -> list[dict[str, Any]]:
        """List distinct industry buckets with A-share ETF+stock counts.

        ``classification`` selects GICS (default) or 申万一级 (SW).
        """
        rows = (
            self.db.query(
                ETFInfo.code,
                ETFInfo.instrument_type,
                ETFInfo.sector,
                ETFInfo.sw_l1,
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
                sw_l1=r.sw_l1,
                sub_category=r.sub_category,
                underlying_index=r.underlying_index,
                category=r.category,
            )
            sector = _resolve_sector(info, classification)
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

    def get_sector_constituents(
        self,
        sector: str,
        top_n: int = 20,
        trade_date: date | None = None,
        classification: Classification = "GICS",
    ) -> dict[str, Any]:
        """Top-N instruments inside a single GICS sector.

        Used by the SectorRotation UI's "成份股构成" tab — replaces the
        previous ETF-only summary with a mixed STOCK + ETF view, weighted
        by:

          - STOCK → most recent ``stock_fundamental.total_mv`` (万元 CNY,
            converted to 元). Falls back to ``etf_info.market_cap`` when
            no fundamental row is present.
          - ETF  → ``etf_info.fund_size`` (base currency, surfaced as 元
            since this service is scoped to A-share).

        Args:
            sector: GICS sector name (level-1). Must already exist in the
                universe — callers usually come from the
                ``/sector-rotation/sectors`` list.
            top_n: How many rows to return. Default 20. Hard-capped at
                200 to bound payload size.
            trade_date: Indicator snapshot date. Defaults to the latest
                indicator date across the universe (consistent with
                ``analyze_sectors``).

        Returns:
            Dict with ``sector``, ``trade_date``, ``count``,
            ``total_in_sector`` and ``items`` (list of constituent dicts).
            Each item carries the documented ``SectorConstituent`` fields.

        Design notes (2026-07-09):
            - We do NOT compute a weighted-aggregate return here. The UI
              shows the sector-level aggregate on the summary tab; the
              constituents tab is a *decomposition* view, not a
              re-aggregation.
            - When no ``stock_fundamental`` row exists for an A-share
              stock, we still include it (weight=None) so the user sees
              every sector member rather than a filtered subset. The
              list is then sorted with ``NULL`` weights last.
            - Broad-market ETFs (no specific sub_category) and bond /
              commodity ETFs are filtered out by ``_resolve_sector``
              which returns None — same logic as the main aggregation.
        """
        if top_n <= 0:
            top_n = 20
        top_n = min(top_n, 200)

        # Resolve trade_date (default = latest indicator date).
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
            trade_date = latest

        # Step 1: enumerate every ETF/STOCK in the A-share universe and
        # filter down to those that resolve to ``sector``. We materialise
        # the rows here so we can apply the same heuristic the aggregation
        # uses — keeping the two views consistent.
        info_rows = (
            self.db.query(ETFInfo)
            .filter(
                ETFInfo.market == self._SCOPE_MARKET,
                ETFInfo.instrument_type.in_(self._SCOPE_INSTRUMENT_TYPES),
                ETFInfo.status == "active",
            )
            .all()
        )

        members: list[ETFInfo] = []
        for info in info_rows:
            if _resolve_sector(info, classification) != sector:
                continue
            members.append(info)

        total_in_sector = len(members)
        if total_in_sector == 0:
            return {
                "sector": sector,
                "trade_date": trade_date.isoformat() if trade_date else None,
                "count": 0,
                "total_in_sector": 0,
                "items": [],
            }

        member_codes = [m.code for m in members]
        code_to_info = {m.code: m for m in members}

        # Step 2: pull the most-recent ``stock_fundamental`` per member
        # code (for STOCKs only). One sub-query per code is fine — the
        # total universe here is bounded by the sector size.
        latest_mv: dict[str, float] = {}
        if trade_date is not None:
            # Window the lookup to ±7 days of the trade date so a stock
            # that briefly disappeared from the daily_basic feed (e.g.
            # suspension, new listing) still gets a weight.
            window_lo = trade_date - timedelta(days=7)
            window_hi = trade_date
            for code in member_codes:
                row = (
                    self.db.query(StockFundamental.total_mv)
                    .filter(
                        StockFundamental.stock_code == code,
                        StockFundamental.trade_date <= window_hi,
                        StockFundamental.trade_date >= window_lo,
                        StockFundamental.total_mv.isnot(None),
                    )
                    .order_by(StockFundamental.trade_date.desc())
                    .first()
                )
                if row and row[0] is not None:
                    # total_mv is in 万元 (10,000 CNY) → convert to 元.
                    latest_mv[code] = float(row[0]) * 10_000.0

        # Step 3: pull the indicator snapshot for the trade_date — covers
        # BOTH STOCK and ETF (ETFIndicator is the unified table).
        indicator_by_code: dict[str, ETFIndicator] = {}
        if trade_date is not None:
            ind_rows = (
                self.db.query(ETFIndicator)
                .filter(
                    ETFIndicator.trade_date == trade_date,
                    ETFIndicator.etf_code.in_(member_codes),
                )
                .all()
            )
            indicator_by_code = {r.etf_code: r for r in ind_rows}

        # Step 4: build the constituents list, sorting by weight desc
        # (None / 0 last).
        items: list[dict[str, Any]] = []
        for info in members:
            if info.instrument_type == "STOCK":
                weight_value = latest_mv.get(info.code)
                weight_label = "市值"
                if weight_value is None and info.market_cap is not None:
                    # ETFInfo.market_cap is in USD for US stocks; for
                    # A-share this column isn't populated by the A-share
                    # pipeline but we surface it anyway as a best-effort
                    # fallback. We *do not* FX-convert here — the unit
                    # label stays "元" only when we know the source is
                    # CNY. For foreign listings we leave weight=None so
                    # the UI doesn't display a misleading number.
                    if info.market == "A股":
                        weight_value = float(info.market_cap)
                weight_unit = "元"
            elif info.instrument_type == "ETF":
                weight_value = (
                    float(info.fund_size) if info.fund_size is not None else None
                )
                weight_label = "规模"
                weight_unit = "元"
            else:
                # Should never reach here (filtered above) but keep the
                # type-narrowing honest.
                continue

            ind = indicator_by_code.get(info.code)
            items.append({
                "code": info.code,
                "name": info.name,
                "instrument_type": info.instrument_type,
                "resolved_sector": sector,
                "weight": weight_value,
                "weight_unit": weight_unit,
                "weight_label": weight_label,
                "return_1w": float(ind.return_1w) if ind and ind.return_1w is not None else None,
                "return_1m": float(ind.return_1m) if ind and ind.return_1m is not None else None,
                "return_3m": float(ind.return_3m) if ind and ind.return_3m is not None else None,
                "return_6m": float(ind.return_6m) if ind and ind.return_6m is not None else None,
                "return_1y": float(ind.return_1y) if ind and ind.return_1y is not None else None,
                "sharpe_1y": float(ind.sharpe_1y) if ind and ind.sharpe_1y is not None else None,
                "rsi14": float(ind.rsi14) if ind and ind.rsi14 is not None else None,
                "amount_total": float(ind.amount) if ind and ind.amount is not None else None,
            })

        # Sort: non-null weight desc → null weight last. Ties broken by
        # 1m return desc (best performers first), then by code.
        def _sort_key(row: dict[str, Any]) -> tuple[int, float, float, str]:
            w = row.get("weight")
            r1m = row.get("return_1m") or 0.0
            # (has_weight_flag, -weight, -return_1m, code) → weight desc
            return (
                0 if w is not None else 1,
                -float(w) if w is not None else 0.0,
                -float(r1m),
                row["code"],
            )

        items.sort(key=_sort_key)
        top_items = items[:top_n]

        return {
            "sector": sector,
            "trade_date": trade_date.isoformat() if trade_date else None,
            "count": len(top_items),
            "total_in_sector": total_in_sector,
            "items": top_items,
        }

    def analyze_sectors(
        self,
        trade_date: date | None = None,
        window_weeks: int = 4,
        classification: Classification = "GICS",
    ) -> dict[str, Any]:
        """Analyze sector performance and rotation signals.

        Args:
            trade_date: Date to analyze. Defaults to latest available
                indicator date in the A-share ETF/STOCK universe.
            window_weeks: Unused kept for API compatibility — momentum
                windows are now driven by indicator periods (1w/1m/3m/6m/1y).
            classification: Industry taxonomy — ``GICS`` (default, global)
                or ``SW`` (申万2021一级, A-share only). Under ``SW`` STOCKs
                bucket by ``etf_info.sw_l1`` and ETFs by 申万 keyword hints.

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
                return self._empty_result(classification=classification)
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
            return self._empty_result(
                trade_date=trade_date, classification=classification
            )

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
            sector = _resolve_sector(info, classification)
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
            return self._empty_result(
                trade_date=trade_date, classification=classification
            )

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

            # Relative Strength = excess return over market average (percentage points).
            # Using a difference instead of a ratio prevents colour/direction reversal
            # when the overall market is negative.
            rs_1m = avg_1m - market_avg["return_1m"]
            rs_3m = avg_3m - market_avg["return_3m"]
            rs_1w = avg(vals["return_1w"]) - market_avg["return_1w"]

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

        rotation_signals = self._detect_rotation_signals(
            sector_rows, trade_date, classification
        )

        return {
            "trade_date": trade_date.isoformat(),
            "scope": {
                "market": self._SCOPE_MARKET,
                "instrument_types": list(self._SCOPE_INSTRUMENT_TYPES),
                "classification": classification,
            },
            "sectors": sector_rows,
            "market_avg": {k: round(v, 4) for k, v in market_avg.items()},
            "rotation_signals": rotation_signals,
        }

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _empty_result(
        self,
        trade_date: date | None = None,
        classification: Classification = "GICS",
    ) -> dict[str, Any]:
        return {
            "trade_date": trade_date.isoformat() if trade_date else None,
            "scope": {
                "market": self._SCOPE_MARKET,
                "instrument_types": list(self._SCOPE_INSTRUMENT_TYPES),
                "classification": classification,
            },
            "sectors": [],
            "market_avg": None,
            "rotation_signals": [],
        }

    def _find_lookback_date(
        self, trade_date: date, trading_days: int = 5
    ) -> date | None:
        """Return the N-th available trading date strictly before ``trade_date``.

        Counts only A-share ETF/STOCK indicator dates. If history is shorter
        than ``trading_days`` days, returns ``None`` so the caller can skip
        signal generation.
        """
        row = (
            self.db.query(ETFIndicator.trade_date)
            .join(ETFInfo, ETFIndicator.etf_code == ETFInfo.code)
            .filter(
                ETFIndicator.trade_date < trade_date,
                ETFInfo.market == self._SCOPE_MARKET,
                ETFInfo.instrument_type.in_(self._SCOPE_INSTRUMENT_TYPES),
            )
            .distinct()
            .order_by(ETFIndicator.trade_date.desc())
            .offset(trading_days - 1)
            .limit(1)
            .first()
        )
        return row[0] if row else None

    def _detect_rotation_signals(
        self,
        current_sectors: list[dict[str, Any]],
        trade_date: date,
        classification: Classification = "GICS",
    ) -> list[dict[str, Any]]:
        """Detect sector rotation by comparing with ~1 week prior.

        The previous period is the 5-th available trading date strictly before
        ``trade_date`` (≈ one trading week). We re-aggregate by sector for that
        date and compare 1-month return rank deltas.

        A swing of ≥ 3 positions in the 1-month return ranking is surfaced as a
        signal. If history is shorter than 5 trading days, no signals are emitted.
        """
        prev_available = self._find_lookback_date(trade_date, trading_days=5)
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
            sector = _resolve_sector(info, classification)
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

    # TODO(Phase 3): Add an official industry index return view (e.g. 申万/中信
    # industry indices). The current equal-weight average of constituent stocks +
    # ETFs is a practical approximation but is not identical to the official
    # index return. Implementation should use a dedicated index-return table or
    # an external source without relying on ``etf_indicator`` + ``etf_info.sw_l1``
    # alone.
#
# ``analyze_sectors`` / ``get_sector_list`` accept ``classification="SW"`` to
# bucket A-share instruments by the 31 申万2021一级行业 instead of GICS. The
# per-stock SW label lives in ``etf_info.sw_l1`` / ``etf_info.sw_l1_code``,
# populated by ``app.scripts.backfill_a_share_sw`` (CSRC→SW static map by
# default, or authoritative Tushare ``index_classify`` + ``index_member`` via
# ``--from-tushare``). ETFs are mapped by the ``ETF_SW_HINTS`` keyword table.
# GICS remains the cross-market default.
# ---------------------------------------------------------------------------