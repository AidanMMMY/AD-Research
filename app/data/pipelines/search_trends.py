"""Search-trends (Baidu + Google) ingestion pipeline.

Refreshes the ``search_trends`` table with daily observations for a
curated list of A-share-related keywords (indices / stocks / macro
topics).  Rotates through the keyword registry so each daily run
covers a different slice — full coverage within ~2-3 days.

Each sub-task (Baidu + Google) is independently guarded; a pytrends
rate-limit failure never aborts the akshare/Baidu sub-task, and vice
versa.

Idempotency: composite unique constraint
``(keyword, region, source, trade_date)`` — on conflict we **overwrite**
``value`` / ``fetched_at`` so the latest observation wins.

Scheduled at 03:00 Asia/Shanghai (after the search-index sources have
finished refreshing their intraday data).
"""

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.data.pipelines.base import ETLPipeline, ETLResult
from app.models.search_trends import SearchTrend
from app.services.search_index_service import (
    fetch_baidu_index,
    fetch_google_trends,
    flatten_keywords,
    load_keyword_registry,
    today_partial_keywords,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


class SearchTrendsPipeline(ETLPipeline):
    """Daily pipeline that refreshes the ``search_trends`` table.

    Sub-tasks:
      1. ``refresh_baidu``  — pull today's hot-search ranking for the
         rotated slice of baidu keywords.
      2. ``refresh_google`` — pull interest-over-time for the rotated
         slice of google keywords (60s sleep per call).

    Both sub-tasks run independently; one failure does not block the
    other.
    """

    job_name = "search_trends_daily"

    def __init__(self, db: Session, *, daily_limit: int = 8, lookback_days: int = 30) -> None:
        # Base class requires a ``DataProvider``; we don't really use
        # ``self.provider`` — pass a dummy that carries a ``name`` attr
        # so the ETLLog row gets a useful source field.
        from app.data.providers.base import DataProvider

        class _StubProvider(DataProvider):
            name = "search_trends"

        super().__init__(provider=_StubProvider(), db=db)
        self.daily_limit = max(1, int(daily_limit))
        self.lookback_days = max(1, int(lookback_days))

    def run(self) -> ETLResult:
        """Run the two search-trend sub-tasks independently."""
        result = ETLResult()
        self._create_log()

        baidu_written = 0
        google_written = 0
        warnings: list[str] = []

        try:
            try:
                baidu_written = self._refresh_baidu()
                logger.info("SearchTrendsPipeline[baidu]: upserted %d rows", baidu_written)
            except Exception as exc:
                msg = f"baidu refresh failed: {exc}"
                logger.exception("SearchTrendsPipeline %s", msg)
                warnings.append(msg)

            try:
                google_written = self._refresh_google()
                logger.info("SearchTrendsPipeline[google]: upserted %d rows", google_written)
            except Exception as exc:
                msg = f"google refresh failed: {exc}"
                logger.exception("SearchTrendsPipeline %s", msg)
                warnings.append(msg)

            result.records = baidu_written + google_written
            result.warnings.extend(warnings)
            # Best-effort: any sub-task succeeding → success.
            result.success = result.records > 0 or not warnings
            self._update_log(
                status="success" if result.success else "partial",
                records=result.records,
                error=None if result.success else "; ".join(warnings),
            )
        except Exception as exc:
            error_msg = str(exc)
            result.success = False
            result.error = error_msg
            self._update_log(status="failed", error=error_msg)
            logger.exception("SearchTrendsPipeline crashed: %s", exc)

        return result

    # The base class declares extract()/load() as abstract — we override
    # ``run()`` so we don't use them.
    def extract(self):  # pragma: no cover - unused
        raise NotImplementedError("SearchTrendsPipeline uses run() override")

    def load(self, data):  # pragma: no cover - unused
        raise NotImplementedError("SearchTrendsPipeline uses run() override")

    # ------------------------------------------------------------------
    # Sub-tasks
    # ------------------------------------------------------------------

    def _refresh_baidu(self) -> int:
        """Pull today's Baidu hot-search for the rotated slice."""
        registry = load_keyword_registry()
        keywords = today_partial_keywords(registry).get("baidu") or [
            kw for (kw, _cat, _src) in flatten_keywords(registry, "baidu")
        ][: self.daily_limit]

        rows: list[dict[str, Any]] = []
        for kw in keywords:
            try:
                fetched = fetch_baidu_index(kw, days=self.lookback_days)
            except Exception as exc:
                logger.warning("SearchTrendsPipeline[baidu] %s failed: %s", kw, exc)
                continue
            for entry in fetched:
                rows.append(
                    {
                        "keyword": kw,
                        "region": entry.get("region", "CN"),
                        "source": "baidu",
                        "trade_date": entry.get("trade_date"),
                        "value": int(entry.get("value") or 0),
                        "is_partial": bool(entry.get("is_partial", False)),
                        "category": self._category_for(registry, "baidu", kw),
                        "fetched_at": datetime.now(timezone.utc),
                    }
                )
        return self._upsert_rows(rows)

    def _refresh_google(self) -> int:
        """Pull today's Google Trends for the rotated slice.

        Each keyword blocks for ~60s due to pytrends rate limiting, so
        we cap the slice size at ``daily_limit`` to keep the whole
        pipeline under ~10 minutes.
        """
        registry = load_keyword_registry()
        keywords = today_partial_keywords(registry).get("google") or [
            kw for (kw, _cat, _src) in flatten_keywords(registry, "google_trends")
        ][: self.daily_limit]

        rows: list[dict[str, Any]] = []
        for kw in keywords:
            try:
                fetched = fetch_google_trends(kw, days=self.lookback_days)
            except Exception as exc:
                logger.warning("SearchTrendsPipeline[google] %s failed: %s", kw, exc)
                continue
            for entry in fetched:
                rows.append(
                    {
                        "keyword": kw,
                        "region": entry.get("region", "GLOBAL"),
                        "source": "google",
                        "trade_date": entry.get("trade_date"),
                        "value": int(entry.get("value") or 0),
                        "is_partial": bool(entry.get("is_partial", False)),
                        "category": self._category_for(registry, "google_trends", kw),
                        "fetched_at": datetime.now(timezone.utc),
                    }
                )
        return self._upsert_rows(rows)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _category_for(
        registry: dict[str, dict[str, list[str]]],
        source: str,
        keyword: str,
    ) -> str | None:
        section = registry.get(source) or {}
        for category in ("indices", "stocks", "macro"):
            values = section.get(category) or []
            if keyword in values:
                return category
        return None

    def _upsert_rows(self, rows: list[dict[str, Any]]) -> int:
        """Upsert rows idempotently via ``ON CONFLICT`` (Postgres + SQLite)."""
        if not rows:
            return 0
        # Filter out rows missing required columns.
        clean: list[dict[str, Any]] = []
        for r in rows:
            if r.get("keyword") and r.get("trade_date") and r.get("source") and r.get("region"):
                clean.append(r)
        if not clean:
            return 0

        dialect = self.db.bind.dialect.name if self.db.bind is not None else ""
        if dialect.startswith("postgres"):
            stmt = pg_insert(SearchTrend).values(clean)
            stmt = stmt.on_conflict_do_update(
                constraint="uq_search_trends_keyword_region_source_date",
                set_={
                    "value": stmt.excluded.value,
                    "is_partial": stmt.excluded.is_partial,
                    "category": stmt.excluded.category,
                    "fetched_at": stmt.excluded.fetched_at,
                },
            )
        else:
            stmt = sqlite_insert(SearchTrend).values(clean)
            stmt = stmt.on_conflict_do_update(
                index_elements=["keyword", "region", "source", "trade_date"],
                set_={
                    "value": stmt.excluded.value,
                    "is_partial": stmt.excluded.is_partial,
                    "category": stmt.excluded.category,
                    "fetched_at": stmt.excluded.fetched_at,
                },
            )
        self.db.execute(stmt)
        self.db.commit()
        return len(clean)