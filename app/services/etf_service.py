"""ETF business logic service.

Provides CRUD operations and filtering for ETF basic information.
"""


from sqlalchemy.orm import Session

from app.core.cache import cache_get, cache_set
from app.models.etf import ETFInfo
from app.schemas.etf import ETFFilterParams, ETFInfoResponse, ETFListResponse


class ETFService:
    """Service for ETF basic information operations."""

    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def _to_response(etf: ETFInfo) -> ETFInfoResponse:
        """Convert ORM object to response schema with field mapping."""
        return ETFInfoResponse(
            code=etf.code,
            name=etf.name,
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
            fund_size=float(etf.fund_size) if etf.fund_size is not None else None,
        )

    def list_etfs(self, params: ETFFilterParams) -> ETFListResponse:
        """List ETFs with filtering and pagination."""
        cache_key = f"etf:list:{params.market}:{params.category}:{params.search}:{params.page}:{params.page_size}"
        cached = cache_get(cache_key)
        if cached is not None:
            return ETFListResponse(**cached)

        query = self.db.query(ETFInfo)

        if params.market:
            query = query.filter(ETFInfo.market == params.market)
        if params.category:
            query = query.filter(ETFInfo.category == params.category)
        if params.search:
            search = f"%{params.search}%"
            query = query.filter(
                (ETFInfo.code.ilike(search)) | (ETFInfo.name.ilike(search))
            )

        total = query.count()
        offset = (params.page - 1) * params.page_size
        items = query.offset(offset).limit(params.page_size).all()

        response = ETFListResponse(
            items=[self._to_response(item) for item in items],
            total=total,
            page=params.page,
            page_size=params.page_size,
        )
        cache_set(cache_key, response.model_dump(), ttl=300)
        return response

    def get_etf(self, code: str) -> ETFInfoResponse | None:
        """Get a single ETF by code."""
        cache_key = f"etf:detail:{code}"
        cached = cache_get(cache_key)
        if cached is not None:
            return ETFInfoResponse(**cached) if cached else None

        etf = self.db.query(ETFInfo).filter(ETFInfo.code == code).first()
        response = self._to_response(etf) if etf else None
        cache_set(cache_key, response.model_dump() if response else None, ttl=600)
        return response

    def get_categories(self) -> list[str]:
        """Get all distinct ETF categories."""
        cache_key = "etf:categories"
        cached = cache_get(cache_key)
        if cached is not None:
            return cached

        results = self.db.query(ETFInfo.category).distinct().all()
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
