"""Listing / IPO events pipeline.

Fetches upcoming and recently-listed A-share IPO events from Tushare
``new_share`` (with automatic fallback to ``stock_basic`` for free-tier
users) and upserts them into the ``listing_events`` table.

Daily schedule: 09:30 Asia/Shanghai (after the morning market open, when
A-share IPO subscription typically starts).
"""

import logging
from datetime import date, datetime, timedelta
from typing import Any

import pandas as pd
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.data.pipelines.base import ETLPipeline, ETLResult
from app.data.providers.tushare_provider import (
    TushareProvider,
    compute_listing_status,
    derive_board,
    derive_market,
)
from app.models.listing import ListingEvent

logger = logging.getLogger(__name__)


def _coerce_date(value: Any) -> date | None:
    """Best-effort conversion of a Tushare date value to ``date``."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value.isdigit() and len(value) == 8:
        try:
            return datetime.strptime(value, "%Y%m%d").date()
        except (ValueError, TypeError):
            return None
    if isinstance(value, str):
        for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
            try:
                return datetime.strptime(value, fmt).date()
            except (ValueError, TypeError):
                continue
    return None


def _coerce_numeric(value: Any) -> float | None:
    """Best-effort conversion to ``float`` for monetary / ratio fields."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _to_upsert_dict(record: dict[str, Any], today: date) -> dict[str, Any] | None:
    """Convert a raw Tushare record to a ``listing_events`` upsert dict."""
    ts_code = record.get("ts_code")
    name = record.get("name")
    if not ts_code or not name:
        return None

    issue_date = _coerce_date(record.get("issue_date") or record.get("ipo_date"))
    list_date = _coerce_date(record.get("list_date"))
    status = compute_listing_status(issue_date, list_date, today=today)

    return {
        "ts_code": str(ts_code),
        "sub_code": record.get("sub_code"),
        "name": str(name),
        "market": derive_market(str(ts_code)) or None,
        "board": derive_board(str(ts_code)),
        "industry": record.get("industry"),
        "issue_date": issue_date,
        "list_date": list_date,
        "issue_price": _coerce_numeric(record.get("price")),
        "pe_ratio": _coerce_numeric(record.get("pe")),
        "limit_amount": _coerce_numeric(record.get("limit_amount")),
        "funds_raised": _coerce_numeric(record.get("funds")),
        "market_amount": _coerce_numeric(record.get("market_amount")),
        "sponsor": record.get("sponsor"),
        "underwriter": record.get("underwriter"),
        "status": status,
        "source": "tushare",
        "raw_payload": record,
    }


class ListingEventsPipeline(ETLPipeline):
    """Pipeline that refreshes the ``listing_events`` table daily.

    Overrides ``run()`` to skip the OHLCV validation that the base class
    performs, since we are not loading daily price bars.
    """

    job_name = "listing_events_daily"

    def __init__(self, db: Session) -> None:
        provider = TushareProvider()
        super().__init__(provider=provider, db=db)

    def run(self) -> ETLResult:
        """Run the full pipeline: extract -> transform -> load."""
        result = ETLResult()
        self._create_log()

        try:
            records = self.extract()
            if not records:
                result.warnings.append("Extract returned empty list")
                result.success = True
                self._update_log(status="success", records=0)
                return result

            upserts = self.transform(records)
            written = self.load(upserts)
            result.records = written
            result.success = True
            self._update_log(status="success", records=written)
            logger.info(
                "ListingEventsPipeline: Upserted %d listing events (raw=%d)",
                written,
                len(records),
            )
        except Exception as exc:
            error_msg = str(exc)
            result.success = False
            result.error = error_msg
            self._update_log(status="failed", error=error_msg)
            logger.error("ListingEventsPipeline failed: %s", error_msg)

        return result

    def extract(self) -> list[dict[str, Any]]:
        """Fetch IPO events from Tushare (with free-tier fallback)."""
        provider = TushareProvider()
        today = date.today()
        start = (today - timedelta(days=7)).strftime("%Y%m%d")
        end = (today + timedelta(days=30)).strftime("%Y%m%d")
        return provider.fetch_new_share(start_date=start, end_date=end)

    def transform(self, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Map raw Tushare records to upsert dicts."""
        today = date.today()
        upserts: list[dict[str, Any]] = []
        for record in records:
            payload = _to_upsert_dict(record, today)
            if payload is not None:
                upserts.append(payload)
        return upserts

    def load(self, records: list[dict[str, Any]]) -> int:
        """Upsert the prepared records into ``listing_events``."""
        if not records:
            return 0

        stmt = insert(ListingEvent).values(records)
        excluded = insert(ListingEvent).excluded
        stmt = stmt.on_conflict_do_update(
            index_elements=["ts_code"],
            set_={
                "sub_code": excluded.sub_code,
                "name": excluded.name,
                "market": excluded.market,
                "board": excluded.board,
                "industry": excluded.industry,
                "issue_date": excluded.issue_date,
                "list_date": excluded.list_date,
                "issue_price": excluded.issue_price,
                "pe_ratio": excluded.pe_ratio,
                "limit_amount": excluded.limit_amount,
                "funds_raised": excluded.funds_raised,
                "market_amount": excluded.market_amount,
                "sponsor": excluded.sponsor,
                "underwriter": excluded.underwriter,
                "status": excluded.status,
                "raw_payload": excluded.raw_payload,
                "fetched_at": excluded.fetched_at,
            },
        )

        self.db.execute(stmt)
        self.db.commit()
        return len(records)
