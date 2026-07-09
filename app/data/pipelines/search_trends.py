"""Search-trends (Xueqiu) ingestion pipeline.

Refreshes the ``search_trends`` table with daily observations for a
curated list of A-share-related keywords (indices / stocks / macro
topics).

Both the **baidu** and **google** slots are populated from Xueqiu's
public hot-rank endpoints because the original Baidu 指数 / Google
Trends upstreams are unreachable from the ECS IP (Baidu blocks our
datacenter ASN, Google Trends returns 429).  See
``app.services.search_index_service`` for the fetchers and retry /
cache strategy.

  * baidu  → ``ak.stock_hot_follow_xq``  (关注排行榜)
  * google → ``ak.stock_hot_deal_xq``    (分享交易排行榜)

Each sub-task (baidu + google) is independently guarded; a failure in
one slot never aborts the other.

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
      1. ``refresh_baidu``  — pull today's Xueqiu hot-follow ranking for
         the keyword slice (rank → score = 10000 - rank).
      2. ``refresh_google`` — pull today's Xueqiu hot-deal ranking for
         the keyword slice (same rank → score mapping).

    Both sub-tasks run independently; one failure does not block the
    other.
    """

    job_name = "search_trends_daily"

    def __init__(self, db: Session, *, daily_limit: int = 50, lookback_days: int = 30) -> None:
        # Base class requires a ``DataProvider``; we don't really use
        # ``self.provider`` — pass a dummy that carries a ``name`` attr
        # so the ETLLog row gets a useful source field.
        from app.data.providers.base import DataProvider

        class _StubProvider(DataProvider):
            @property
            def name(self) -> str:
                return "search_trends"

            def fetch_etf_list(self):
                return []

            def fetch_daily_bars(self, codes, start_date, end_date):
                import pandas as pd
                return pd.DataFrame()

            def fetch_realtime_quotes(self, codes):
                import pandas as pd
                return pd.DataFrame()

            def get_market_hours(self, code=None):
                from app.data.providers.base import MarketHours
                return MarketHours()

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
                baidu_written = self._refresh_slot("baidu")
                logger.info("SearchTrendsPipeline[baidu]: upserted %d rows", baidu_written)
            except Exception as exc:
                msg = f"baidu refresh failed: {exc}"
                logger.exception("SearchTrendsPipeline %s", msg)
                warnings.append(msg)

            try:
                google_written = self._refresh_slot("google")
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

    def _refresh_slot(self, slot: str) -> int:
        """Pull today's Xueqiu hot-rank snapshot for the rotated slice.

        ``slot`` is ``"baidu"`` (uses Xueqiu hot-follow via
        ``fetch_baidu_index``) or ``"google"`` (uses Xueqiu hot-deal via
        ``fetch_google_trends``).  Both helpers rank-map to
        ``value = max(0, 10000 - rank)`` so higher rank → higher value.
        """
        registry = load_keyword_registry()
        # Prefer the day-rotated slice; fall back to the full registry
        # if the slice helper returns nothing for this source.
        keywords = today_partial_keywords(registry).get(slot) or [
            kw for (kw, _cat, _src) in flatten_keywords(registry, slot)
        ]
        keywords = keywords[: self.daily_limit]
        region = "CN" if slot == "baidu" else "GLOBAL"

        fetch_fn = fetch_baidu_index if slot == "baidu" else fetch_google_trends

        rows: list[dict[str, Any]] = []
        for kw in keywords:
            try:
                fetched = fetch_fn(kw, days=self.lookback_days)
            except Exception as exc:
                logger.warning("SearchTrendsPipeline[%s] %s failed: %s", slot, kw, exc)
                continue
            for entry in fetched:
                rows.append(
                    {
                        "keyword": kw,
                        "region": entry.get("region", region),
                        "source": slot,
                        "trade_date": entry.get("trade_date"),
                        "value": int(entry.get("value") or 0),
                        "is_partial": bool(entry.get("is_partial", False)),
                        "category": self._category_for(registry, slot, kw),
                        "fetched_at": datetime.now(timezone.utc),
                    }
                )
        return self._upsert_rows(rows)

    # Kept as a thin alias so legacy callers / tests that referenced the
    # old ``_refresh_baidu`` / ``_refresh_google`` methods continue to
    # work.
    def _refresh_baidu(self) -> int:
        return self._refresh_slot("baidu")

    def _refresh_google(self) -> int:
        return self._refresh_slot("google")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _category_for(
        registry: dict[str, dict[str, list[str]]],
        source: str,
        keyword: str,
    ) -> str | None:
        """Return the registry category for ``keyword`` under ``source``.

        Accepts both the short (``baidu``/``google``) and canonical
        (``baidu_index``/``google_trends``) registry keys via
        ``search_index_service._SOURCE_ALIASES``.
        """
        from app.services.search_index_service import _SOURCE_ALIASES

        for key in _SOURCE_ALIASES.get(source, (source,)):
            section = registry.get(key) or {}
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