"""ETF business logic service.

Provides CRUD operations and filtering for ETF basic information.
Enriches A-share individual stocks with latest valuation data (market cap,
PE, PB) from the stock_fundamental table.
"""


from datetime import date as _date
from typing import Iterable

from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from app.core.cache import cache_get, cache_set
from app.models.etf import ETFHolding, ETFInfo, StockFundamental
from app.schemas.etf import ETFFilterParams, ETFInfoResponse, ETFListResponse


class ETFService:
    """Service for ETF basic information operations."""

    def __init__(self, db: Session):
        self.db = db

    def _enrich_with_fundamentals(
        self, items: list[ETFInfo]
    ) -> dict[str, StockFundamental]:
        """Batch-fetch latest StockFundamental rows for A-share stocks.

        Returns a dict keyed by stock_code. Only queries stocks where
        instrument_type == "STOCK" and market == "A股".
        """
        stock_codes = [
            item.code
            for item in items
            if item.instrument_type == "STOCK" and item.market == "A股"
        ]
        if not stock_codes:
            return {}

        # Subquery: latest trade_date per stock_code
        latest_dates = (
            self.db.query(
                StockFundamental.stock_code,
                func.max(StockFundamental.trade_date).label("max_date"),
            )
            .filter(StockFundamental.stock_code.in_(stock_codes))
            .group_by(StockFundamental.stock_code)
            .subquery()
        )

        rows = (
            self.db.query(StockFundamental)
            .join(
                latest_dates,
                and_(
                    StockFundamental.stock_code == latest_dates.c.stock_code,
                    StockFundamental.trade_date == latest_dates.c.max_date,
                ),
            )
            .all()
        )

        return {sf.stock_code: sf for sf in rows}

    @staticmethod
    def _to_response(
        etf: ETFInfo,
        fundamental: StockFundamental | None = None,
    ) -> ETFInfoResponse:
        """Convert ORM object to response schema with field mapping.

        When ``fundamental`` is provided (A-share stocks), market-cap and
        valuation fields are enriched from stock_fundamental data.
        """
        fund_size = float(etf.fund_size) if etf.fund_size is not None else None
        market_cap = float(etf.market_cap) if etf.market_cap is not None else None

        if fundamental is not None:
            # total_mv from Tushare daily_basic is in 万元 (10k CNY).
            # Convert to 元 (base currency unit) so frontend formatting
            # (v / 1e8 → 亿) works correctly.
            # Populate both fund_size and market_cap for A-shares so the
            # unified instrument list shows market cap for all instrument types.
            if fundamental.total_mv is not None:
                fund_size = float(fundamental.total_mv) * 10_000  # 万元 → 元
                market_cap = fund_size

        return ETFInfoResponse(
            code=etf.code,
            name=etf.name,
            name_zh=etf.name_zh,
            exchange=etf.exchange,
            market=etf.market,
            category=etf.category,
            sub_category=etf.sub_category,
            manager=etf.manager,
            currency=etf.currency or "CNY",
            is_qdii=etf.is_qdii or False,
            underlying_index=etf.underlying_index,
            inception_date=etf.inception_date,
            status=etf.status or "active",
            created_at=etf.created_at,
            updated_at=etf.updated_at,
            fund_manager=etf.manager,
            fund_size=fund_size,
            instrument_type=etf.instrument_type,
            sector=etf.sector,
            industry=etf.industry,
            market_cap=market_cap,
            country=etf.country,
            listing_market=etf.listing_market,
            board=etf.board,
        )

    def _apply_filters(
        self,
        query,
        params: ETFFilterParams,
        exclude: str | None = None,
    ):
        """Apply common ETF filters to a query, optionally excluding one field."""
        if params.market and exclude != "market":
            query = query.filter(ETFInfo.market == params.market)
        if params.category and exclude != "category":
            query = query.filter(ETFInfo.category == params.category)
        if params.sub_category and exclude != "sub_category":
            query = query.filter(ETFInfo.sub_category == params.sub_category)
        if params.sector and exclude != "sector":
            query = query.filter(ETFInfo.sector == params.sector)
        if params.industry and exclude != "industry":
            query = query.filter(ETFInfo.industry == params.industry)
        if params.country and exclude != "country":
            query = query.filter(ETFInfo.country == params.country)
        if params.manager and exclude != "manager":
            query = query.filter(ETFInfo.manager == params.manager)
        if params.underlying_index and exclude != "underlying_index":
            query = query.filter(ETFInfo.underlying_index == params.underlying_index)
        if params.currency and exclude != "currency":
            query = query.filter(ETFInfo.currency == params.currency)
        if params.is_qdii is not None and exclude != "is_qdii":
            query = query.filter(ETFInfo.is_qdii == params.is_qdii)
        if params.status and exclude != "status":
            query = query.filter(ETFInfo.status == params.status)
        if params.instrument_type and exclude != "instrument_type":
            query = query.filter(ETFInfo.instrument_type == params.instrument_type)
        if params.listing_market and exclude != "listing_market":
            query = query.filter(ETFInfo.listing_market == params.listing_market)
        if params.board and exclude != "board":
            query = query.filter(ETFInfo.board == params.board)
        if params.exchange and exclude != "exchange":
            query = query.filter(ETFInfo.exchange == params.exchange)
        if params.min_fund_size is not None and exclude != "min_fund_size":
            query = query.filter(ETFInfo.fund_size >= params.min_fund_size)
        if params.max_fund_size is not None and exclude != "max_fund_size":
            query = query.filter(ETFInfo.fund_size <= params.max_fund_size)
        return query

    def list_etfs(self, params: ETFFilterParams) -> ETFListResponse:
        """List ETFs with filtering and pagination.

        A-share individual stocks are enriched with latest valuation data
        (market cap, PE, PB) from the stock_fundamental table.
        """
        cache_key = f"etf:list:{params.model_dump_json()}"
        cached = cache_get(cache_key)
        if cached is not None:
            return ETFListResponse(**cached)

        query = self.db.query(ETFInfo)
        query = self._apply_filters(query, params)

        if params.search:
            search = f"%{params.search}%"
            query = query.filter(
                (ETFInfo.code.ilike(search)) | (ETFInfo.name.ilike(search))
            )

        total = query.count()
        offset = (params.page - 1) * params.page_size
        items = query.offset(offset).limit(params.page_size).all()

        # Enrich A-share stocks with latest fundamental data
        fundamentals = self._enrich_with_fundamentals(items)

        response = ETFListResponse(
            items=[
                self._to_response(item, fundamentals.get(item.code))
                for item in items
            ],
            total=total,
            page=params.page,
            page_size=params.page_size,
        )
        cache_set(cache_key, response.model_dump(), ttl=300)
        return response

    def get_etf(self, code: str) -> ETFInfoResponse | None:
        """Get a single ETF by code, enriched with latest fundamental data."""
        cache_key = f"etf:detail:{code}"
        cached = cache_get(cache_key)
        if cached is not None:
            return ETFInfoResponse(**cached) if cached else None

        etf = self.db.query(ETFInfo).filter(ETFInfo.code == code).first()
        if etf is None:
            cache_set(cache_key, None, ttl=600)
            return None

        # Enrich A-share stocks with latest fundamental data
        fundamentals = self._enrich_with_fundamentals([etf])
        response = self._to_response(etf, fundamentals.get(etf.code))
        cache_set(cache_key, response.model_dump() if response else None, ttl=600)
        return response

    def _facet_values(
        self,
        column,
        params: ETFFilterParams | None,
        facet_name: str,
        exclude_field: str,
    ) -> list[str]:
        """Get distinct values for a facet column, applying all other filters."""
        if params is None:
            params = ETFFilterParams()
        cache_key = (
            f"etf:{facet_name}:"
            f"{params.model_dump_json(exclude={exclude_field, 'page', 'page_size'})}"
        )
        cached = cache_get(cache_key)
        if cached is not None:
            return cached

        query = self.db.query(column).distinct()
        query = self._apply_filters(query, params, exclude=exclude_field)
        results = query.all()
        # Filter out both NULL and empty-string values so the frontend
        # dropdown never shows a blank "无" option. (Empty strings leak
        # into PostgreSQL TEXT columns when ETL backfills without
        # normalising — see ETF list 分类 bug 2026-07-08.)
        values = [r[0] for r in results if r[0] is not None and r[0] != ""]
        cache_set(cache_key, values, ttl=600)
        return values

    def get_categories(
        self,
        params: ETFFilterParams | None = None,
        market: str | None = None,
        instrument_type: str | None = None,
    ) -> list[str]:
        """Get distinct ETF categories, optionally filtered by market and type."""
        if params is None:
            params = ETFFilterParams(market=market, instrument_type=instrument_type)
        return self._facet_values(ETFInfo.category, params, "categories", "category")

    def get_sectors(
        self,
        params: ETFFilterParams | None = None,
        market: str | None = None,
        instrument_type: str | None = None,
    ) -> list[str]:
        """Get distinct ETF sectors, optionally filtered by market and type."""
        if params is None:
            params = ETFFilterParams(market=market, instrument_type=instrument_type)
        return self._facet_values(ETFInfo.sector, params, "sectors", "sector")

    def get_industries(
        self,
        params: ETFFilterParams | None = None,
        market: str | None = None,
        instrument_type: str | None = None,
    ) -> list[str]:
        """Get distinct ETF industries, optionally filtered by market and type."""
        if params is None:
            params = ETFFilterParams(market=market, instrument_type=instrument_type)
        return self._facet_values(ETFInfo.industry, params, "industries", "industry")

    def get_sub_categories(
        self,
        params: ETFFilterParams | None = None,
        market: str | None = None,
        instrument_type: str | None = None,
    ) -> list[str]:
        """Get distinct ETF sub-categories, optionally filtered by market and type."""
        if params is None:
            params = ETFFilterParams(market=market, instrument_type=instrument_type)
        return self._facet_values(
            ETFInfo.sub_category, params, "sub_categories", "sub_category"
        )

    def get_managers(
        self,
        params: ETFFilterParams | None = None,
        market: str | None = None,
        instrument_type: str | None = None,
    ) -> list[str]:
        """Get distinct ETF managers, optionally filtered by market and type."""
        if params is None:
            params = ETFFilterParams(market=market, instrument_type=instrument_type)
        return self._facet_values(ETFInfo.manager, params, "managers", "manager")

    def get_currencies(
        self,
        params: ETFFilterParams | None = None,
        market: str | None = None,
        instrument_type: str | None = None,
    ) -> list[str]:
        """Get distinct ETF currencies, optionally filtered by market and type."""
        if params is None:
            params = ETFFilterParams(market=market, instrument_type=instrument_type)
        return self._facet_values(ETFInfo.currency, params, "currencies", "currency")

    def get_countries(
        self,
        params: ETFFilterParams | None = None,
        market: str | None = None,
        instrument_type: str | None = None,
    ) -> list[str]:
        """Get distinct ETF countries, optionally filtered by market and type."""
        if params is None:
            params = ETFFilterParams(market=market, instrument_type=instrument_type)
        return self._facet_values(ETFInfo.country, params, "countries", "country")

    def get_underlying_indices(
        self,
        params: ETFFilterParams | None = None,
        market: str | None = None,
        instrument_type: str | None = None,
    ) -> list[str]:
        """Get distinct underlying indices, optionally filtered by market and type."""
        if params is None:
            params = ETFFilterParams(market=market, instrument_type=instrument_type)
        return self._facet_values(
            ETFInfo.underlying_index,
            params,
            "underlying_indices",
            "underlying_index",
        )

    def get_markets(self) -> list[str]:
        """Get all distinct ETF markets."""
        cache_key = "etf:markets"
        cached = cache_get(cache_key)
        if cached is not None:
            return cached

        results = self.db.query(ETFInfo.market).distinct().all()
        markets = [r[0] for r in results if r[0]]
        cache_set(cache_key, markets, ttl=600)
        return markets

    def get_listing_markets(
        self,
        params: ETFFilterParams | None = None,
        market: str | None = None,
        instrument_type: str | None = None,
    ) -> list[str]:
        """Get distinct A-share listing markets (上海/深圳/北京), optionally filtered."""
        if params is None:
            params = ETFFilterParams(market=market, instrument_type=instrument_type)
        return self._facet_values(
            ETFInfo.listing_market, params, "listing_markets", "listing_market"
        )

    def get_boards(
        self,
        params: ETFFilterParams | None = None,
        market: str | None = None,
        instrument_type: str | None = None,
    ) -> list[str]:
        """Get distinct A-share boards (主板/创业板/科创板/北交所), optionally filtered."""
        if params is None:
            params = ETFFilterParams(market=market, instrument_type=instrument_type)
        return self._facet_values(ETFInfo.board, params, "boards", "board")

    # ------------------------------------------------------------------
    # Holdings name backfill
    # ------------------------------------------------------------------
    def _holding_name_map(self, holding_codes: Iterable[str]) -> dict[str, str]:
        """Return a code -> display-name map for the given holding codes.

        Some data providers (e.g. certain ETF disclosure filings) only supply
        the underlying security code without a human-readable name. When the
        code exists in our ``ETFInfo`` table we can backfill the display name
        from the canonical instrument record, so the front-end tables never
        show a bare code column with an empty name column.
        """
        codes = [c for c in holding_codes if c]
        if not codes:
            return {}
        rows = (
            self.db.query(ETFInfo.code, ETFInfo.name, ETFInfo.name_zh)
            .filter(ETFInfo.code.in_(codes))
            .all()
        )
        return {r.code: (r.name or r.name_zh) for r in rows if r.name or r.name_zh}

    # ------------------------------------------------------------------
    # Holdings (ETF 持仓穿透)
    # ------------------------------------------------------------------

    def get_holdings(self, code: str) -> dict:
        """Return the latest holdings snapshot for an ETF.

        Response shape::

            {
                "holdings": [
                    {
                        "etf_code": str,
                        "holding_code": str,
                        "holding_name": str | None,
                        "weight": float | None,
                        "shares": float | None,
                        "market_value": float | None,
                        "holdings_as_of_date": date | None,
                    },
                    ...
                ],
                "holdings_as_of_date": date | None,
            }

        The top-level ``holdings_as_of_date`` is the max of the per-row
        ``holdings_as_of_date`` so callers can render a single "as of"
        hint without having to scan the list. Returns ``None`` for the
        field when no row carries a date (pre-migration snapshots).

        Backwards-compat: the call is purely additive — callers that
        ignore the new field keep working unchanged.
        """
        rows = (
            self.db.query(ETFHolding)
            .filter(ETFHolding.etf_code == code)
            .order_by(ETFHolding.weight.desc().nullslast())
            .all()
        )
        name_map = self._holding_name_map([h.holding_code for h in rows])
        holdings = [
            {
                "etf_code": h.etf_code,
                "holding_code": h.holding_code,
                "holding_name": name_map.get(h.holding_code, h.holding_name),
                "weight": float(h.weight) if h.weight is not None else None,
                "shares": float(h.shares) if h.shares is not None else None,
                "market_value": float(h.market_value)
                if h.market_value is not None
                else None,
                "holdings_as_of_date": h.holdings_as_of_date,
            }
            for h in rows
        ]
        as_of = max(
            (h.holdings_as_of_date for h in rows if h.holdings_as_of_date),
            default=None,
        )
        return {"holdings": holdings, "holdings_as_of_date": as_of}

    def get_holdings_by_date(self, code: str, as_of_date) -> dict:
        """Return the holdings for an ETF on a specific reporting date.

        Mirrors :py:meth:`get_holdings` but filters to a single
        ``holdings_as_of_date`` snapshot. Rows with NULL
        ``holdings_as_of_date`` are intentionally excluded — they
        represent pre-migration data that cannot be attributed to any
        specific quarter.

        The top-level ``holdings_as_of_date`` echoes the requested
        date so the frontend can render a stable "as of" hint even
        when the underlying data has gaps. The new ``snapshot_date``
        field is populated with the same value for callers that have
        migrated to the upsert identity column.
        """
        rows = (
            self.db.query(ETFHolding)
            .filter(
                ETFHolding.etf_code == code,
                ETFHolding.holdings_as_of_date == as_of_date,
            )
            .order_by(ETFHolding.weight.desc().nullslast())
            .all()
        )
        name_map = self._holding_name_map([h.holding_code for h in rows])
        holdings = [
            {
                "etf_code": h.etf_code,
                "holding_code": h.holding_code,
                "holding_name": name_map.get(h.holding_code, h.holding_name),
                "weight": float(h.weight) if h.weight is not None else None,
                "shares": float(h.shares) if h.shares is not None else None,
                "market_value": float(h.market_value)
                if h.market_value is not None
                else None,
                "holdings_as_of_date": h.holdings_as_of_date,
                "snapshot_date": h.holdings_as_of_date,
            }
            for h in rows
        ]
        return {
            "holdings": holdings,
            "holdings_as_of_date": as_of_date,
            "snapshot_date": as_of_date,
        }

    def list_holdings_snapshots(self, code: str) -> list[dict]:
        """Return the list of distinct reporting-period snapshots.

        For each ``holdings_as_of_date`` we return the row count and
        the sum of weights (when available) so the frontend can render
        a timeline without re-fetching every snapshot. Sorted newest
        first.
        """
        rows = (
            self.db.query(
                ETFHolding.holdings_as_of_date.label("as_of"),
                func.count(ETFHolding.id).label("cnt"),
                func.coalesce(func.sum(ETFHolding.weight), 0).label("sum_w"),
                func.max(ETFHolding.source).label("src"),
            )
            .filter(
                ETFHolding.etf_code == code,
                ETFHolding.holdings_as_of_date.isnot(None),
            )
            .group_by(ETFHolding.holdings_as_of_date)
            .order_by(ETFHolding.holdings_as_of_date.desc())
            .all()
        )
        return [
            {
                "holdings_as_of_date": r.as_of,
                "holding_count": int(r.cnt),
                "total_weight": float(r.sum_w) if r.sum_w is not None else None,
                "source": r.src,
            }
            for r in rows
        ]

    def diff_holdings(
        self,
        code: str,
        from_date: _date,
        to_date: _date,
    ) -> dict:
        """Compute the diff between two reporting periods.

        Returns per-holding deltas (weight + shares), aggregate
        counters (added / removed / increased / decreased /
        unchanged), and the change in total weight. The two periods
        are treated as unordered sets for "added" / "removed"
        detection; an existing holding whose weight changed is
        ``increased`` / ``decreased`` / ``unchanged`` based on the
        signed delta of ``to_weight - from_weight`` (with a 1bp
        tolerance to absorb floating-point noise).
        """
        from_rows = (
            self.db.query(ETFHolding)
            .filter(
                ETFHolding.etf_code == code,
                ETFHolding.holdings_as_of_date == from_date,
            )
            .all()
        )
        to_rows = (
            self.db.query(ETFHolding)
            .filter(
                ETFHolding.etf_code == code,
                ETFHolding.holdings_as_of_date == to_date,
            )
            .all()
        )

        def _index(rows: Iterable[ETFHolding]) -> dict[str, ETFHolding]:
            return {r.holding_code: r for r in rows}

        from_idx = _index(from_rows)
        to_idx = _index(to_rows)
        codes = set(from_idx) | set(to_idx)
        name_map = self._holding_name_map(codes)

        entries: list[dict] = []
        added = removed = increased = decreased = unchanged = 0
        from_total = 0.0
        to_total = 0.0
        for hcode in codes:
            f = from_idx.get(hcode)
            t = to_idx.get(hcode)
            f_w = float(f.weight) if (f is not None and f.weight is not None) else None
            t_w = float(t.weight) if (t is not None and t.weight is not None) else None
            f_s = float(f.shares) if (f is not None and f.shares is not None) else None
            t_s = float(t.shares) if (t is not None and t.shares is not None) else None

            if f_w is not None:
                from_total += f_w
            if t_w is not None:
                to_total += t_w

            if f is None:
                status = "added"
                added += 1
            elif t is None:
                status = "removed"
                removed += 1
            else:
                if f_w is None and t_w is None:
                    delta = 0.0
                else:
                    delta = (t_w or 0.0) - (f_w or 0.0)
                # 1bp (0.0001) tolerance for floating-point noise
                if delta > 0.0001:
                    status = "increased"
                    increased += 1
                elif delta < -0.0001:
                    status = "decreased"
                    decreased += 1
                else:
                    status = "unchanged"
                    unchanged += 1

            base_name = (t or f).holding_name
            entries.append(
                {
                    "holding_code": hcode,
                    "holding_name": name_map.get(hcode, base_name),
                    "from_weight": f_w,
                    "to_weight": t_w,
                    "weight_change": (
                        (t_w - f_w) if (t_w is not None and f_w is not None) else None
                    ),
                    "from_shares": f_s,
                    "to_shares": t_s,
                    "shares_change": (
                        (t_s - f_s) if (t_s is not None and f_s is not None) else None
                    ),
                    "status": status,
                }
            )

        # Sort: added/removed first (most actionable), then by absolute
        # weight-change descending, then by holding_code for stability.
        status_order = {
            "added": 0,
            "removed": 1,
            "increased": 2,
            "decreased": 3,
            "unchanged": 4,
        }
        entries.sort(
            key=lambda e: (
                status_order.get(e["status"], 99),
                -abs(e["weight_change"] or 0.0),
                e["holding_code"],
            )
        )

        return {
            "from_date": from_date,
            "to_date": to_date,
            "entries": entries,
            "added_count": added,
            "removed_count": removed,
            "increased_count": increased,
            "decreased_count": decreased,
            "unchanged_count": unchanged,
            "total_weight_change": (to_total - from_total) or None,
            "from_total_weight": from_total or None,
            "to_total_weight": to_total or None,
        }

    def upsert_holdings(
        self,
        etf_code: str,
        rows: list[dict],
        as_of_date,
    ) -> int:
        """Upsert holdings for an ETF, stamped with ``as_of_date``.

        Each item in ``rows`` is expected to carry: ``holding_code``,
        ``holding_name`` (optional), ``weight`` (optional), ``shares``
        (optional), ``market_value`` (optional). Existing rows matching
        ``(etf_code, holding_code, holdings_as_of_date)`` are updated in
        place; new rows are inserted. Returns the number of rows written.

        Strictly additive — callers that don't supply ``as_of_date`` get
        rows persisted with ``holdings_as_of_date = NULL`` (the historical
        default before this field existed).
        """
        if not rows:
            return 0
        written = 0
        for r in rows:
            existing = (
                self.db.query(ETFHolding)
                .filter(
                    ETFHolding.etf_code == etf_code,
                    ETFHolding.holding_code == r.get("holding_code"),
                    ETFHolding.holdings_as_of_date == as_of_date,
                )
                .first()
            )
            if existing is not None:
                existing.holding_name = r.get("holding_name", existing.holding_name)
                existing.weight = r.get("weight", existing.weight)
                existing.shares = r.get("shares", existing.shares)
                existing.market_value = r.get("market_value", existing.market_value)
            else:
                self.db.add(
                    ETFHolding(
                        etf_code=etf_code,
                        holding_code=r["holding_code"],
                        holding_name=r.get("holding_name"),
                        weight=r.get("weight"),
                        shares=r.get("shares"),
                        market_value=r.get("market_value"),
                        holdings_as_of_date=as_of_date,
                    )
                )
            written += 1
        if written:
            self.db.commit()
        return written
