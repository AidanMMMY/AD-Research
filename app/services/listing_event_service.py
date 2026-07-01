"""Listing / IPO event service.

Provides paginated listing / filtering helpers and a facets method for
populating dropdowns.
"""

from datetime import date, datetime
from typing import Any

from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session

from app.core.cache import cache_get, cache_set
from app.models.listing import ListingEvent


DATE_FIELDS = ("list_date", "issue_date")
SORTABLE_FIELDS = (
    "list_date",
    "issue_date",
    "funds_raised",
    "issue_price",
    "pe_ratio",
    "updated_at",
)


class ListingEventService:
    """Service for listing / IPO events."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def list_events(
        self,
        page: int = 1,
        page_size: int = 20,
        boards: list[str] | None = None,
        markets: list[str] | None = None,
        statuses: list[str] | None = None,
        industry: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        date_field: str = "list_date",
        q: str | None = None,
        sort_by: str = "list_date",
        sort_dir: str = "desc",
    ) -> dict[str, Any]:
        """Return a paginated, filtered list of listing events."""
        if page < 1:
            page = 1
        if page_size < 1 or page_size > 100:
            page_size = 20

        if date_field not in DATE_FIELDS:
            date_field = "list_date"
        if sort_by not in SORTABLE_FIELDS:
            sort_by = "list_date"
        sort_dir_norm = sort_dir.lower() if sort_dir.lower() in ("asc", "desc") else "desc"

        stmt = select(ListingEvent)
        count_stmt = select(func.count(ListingEvent.id))

        if boards:
            stmt = stmt.where(ListingEvent.board.in_(boards))
            count_stmt = count_stmt.where(ListingEvent.board.in_(boards))
        if markets:
            stmt = stmt.where(ListingEvent.market.in_(markets))
            count_stmt = count_stmt.where(ListingEvent.market.in_(markets))
        if statuses:
            stmt = stmt.where(ListingEvent.status.in_(statuses))
            count_stmt = count_stmt.where(ListingEvent.status.in_(statuses))
        if industry:
            stmt = stmt.where(ListingEvent.industry == industry)
            count_stmt = count_stmt.where(ListingEvent.industry == industry)
        if start_date:
            col = getattr(ListingEvent, date_field)
            stmt = stmt.where(col >= start_date)
            count_stmt = count_stmt.where(col >= start_date)
        if end_date:
            col = getattr(ListingEvent, date_field)
            stmt = stmt.where(col <= end_date)
            count_stmt = count_stmt.where(col <= end_date)
        if q:
            pattern = f"%{q}%"
            stmt = stmt.where(
                (ListingEvent.name.ilike(pattern)) | (ListingEvent.ts_code.ilike(pattern))
            )
            count_stmt = count_stmt.where(
                (ListingEvent.name.ilike(pattern)) | (ListingEvent.ts_code.ilike(pattern))
            )

        sort_col = getattr(ListingEvent, sort_by)
        stmt = stmt.order_by(sort_col.desc() if sort_dir_norm == "desc" else sort_col.asc())

        total = self.db.execute(count_stmt).scalar() or 0
        rows = self.db.execute(
            stmt.offset((page - 1) * page_size).limit(page_size)
        ).scalars().all()

        latest = self.db.execute(
            select(func.max(ListingEvent.updated_at))
        ).scalar()

        return {
            "items": [_to_out(row) for row in rows],
            "total": int(total),
            "page": page,
            "page_size": page_size,
            "updated_at": latest.isoformat() if latest else None,
        }

    def get_event(self, event_id: int) -> dict[str, Any] | None:
        """Return a single listing event detail by id."""
        cache_key = f"listing_events:detail:{event_id}"
        cached = cache_get(cache_key)
        if cached is not None:
            return cached
        event = self.db.get(ListingEvent, event_id)
        if event is None:
            cache_set(cache_key, None, ttl=60)
            return None
        detail = _to_detail(event)
        cache_set(cache_key, detail, ttl=300)
        return detail

    def get_facets(self) -> dict[str, list[str]]:
        """Return distinct values for industries, boards, markets, statuses."""
        cache_key = "listing_events:facets"
        cached = cache_get(cache_key)
        if cached is not None:
            return cached

        def _distinct_values(column) -> list[str]:
            stmt = select(distinct(column)).where(column.isnot(None))
            rows = self.db.execute(stmt).scalars().all()
            return sorted([str(v) for v in rows if v])

        facets = {
            "industries": _distinct_values(ListingEvent.industry),
            "boards": _distinct_values(ListingEvent.board),
            "markets": _distinct_values(ListingEvent.market),
            "statuses": _distinct_values(ListingEvent.status),
        }
        cache_set(cache_key, facets, ttl=3600)
        return facets


def _to_out(event: ListingEvent) -> dict[str, Any]:
    return {
        "id": event.id,
        "ts_code": event.ts_code,
        "sub_code": event.sub_code,
        "name": event.name,
        "market": event.market,
        "board": event.board,
        "industry": event.industry,
        "issue_date": event.issue_date.isoformat() if event.issue_date else None,
        "list_date": event.list_date.isoformat() if event.list_date else None,
        "issue_price": float(event.issue_price) if event.issue_price is not None else None,
        "pe_ratio": float(event.pe_ratio) if event.pe_ratio is not None else None,
        "limit_amount": float(event.limit_amount) if event.limit_amount is not None else None,
        "funds_raised": float(event.funds_raised) if event.funds_raised is not None else None,
        "market_amount": float(event.market_amount) if event.market_amount is not None else None,
        "sponsor": event.sponsor,
        "underwriter": event.underwriter,
        "status": event.status,
        "source": event.source,
        "fetched_at": event.fetched_at.isoformat() if event.fetched_at else None,
        "updated_at": event.updated_at.isoformat() if event.updated_at else None,
    }


def _to_detail(event: ListingEvent) -> dict[str, Any]:
    payload = _to_out(event)
    payload["raw_payload"] = event.raw_payload
    payload["created_at"] = event.created_at.isoformat() if event.created_at else None
    return payload
