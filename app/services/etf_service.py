"""ETF business logic service.

Provides CRUD operations and filtering for ETF basic information.
Enriches A-share individual stocks with latest valuation data (market cap,
PE, PB) from the stock_fundamental table.
"""


from sqlalchemy import and_
from sqlalchemy.orm import Session
from sqlalchemy.sql import func

from app.core.cache import cache_get, cache_set
from app.models.etf import ETFInfo, StockFundamental
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
        )

    def list_etfs(self, params: ETFFilterParams) -> ETFListResponse:
        """List ETFs with filtering and pagination.

        A-share individual stocks are enriched with latest valuation data
        (market cap, PE, PB) from the stock_fundamental table.
        """
        cache_key = f"etf:list:{params.market}:{params.category}:{params.instrument_type}:{params.search}:{params.page}:{params.page_size}"
        cached = cache_get(cache_key)
        if cached is not None:
            return ETFListResponse(**cached)

        query = self.db.query(ETFInfo)

        if params.market:
            query = query.filter(ETFInfo.market == params.market)
        if params.category:
            query = query.filter(ETFInfo.category == params.category)
        if params.instrument_type:
            query = query.filter(ETFInfo.instrument_type == params.instrument_type)
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

    def get_categories(
        self, market: str | None = None, instrument_type: str | None = None
    ) -> list[str]:
        """Get distinct ETF categories, optionally filtered by market and type."""
        segments = ["etf:categories"]
        if market is not None:
            segments.append(f"market={market}")
        if instrument_type is not None:
            segments.append(f"instrument_type={instrument_type}")
        cache_key = ":".join(segments)
        cached = cache_get(cache_key)
        if cached is not None:
            return cached

        query = self.db.query(ETFInfo.category).distinct()
        if market is not None:
            query = query.filter(ETFInfo.market == market)
        if instrument_type is not None:
            query = query.filter(ETFInfo.instrument_type == instrument_type)
        results = query.all()
        categories = [r[0] for r in results if r[0]]
        cache_set(cache_key, categories, ttl=600)
        return categories

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
