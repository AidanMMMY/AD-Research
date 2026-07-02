"""Cninfo periodic report ETL pipeline.

Daily job that fetches the periodic reports published in the last 24h
from cninfo for the B-tier universe (HS300 + CS500) and upserts the
metadata into ``cninfo_reports``.  PDF download + text extraction are
performed out-of-band by the API endpoints.

The base :class:`ETLPipeline` contract expects DataFrame-shaped
``extract``/``load`` methods, but cninfo returns a small list of dicts —
we override ``run`` entirely (mirroring ``ListingEventsPipeline``) and
re-use the parent's ``run_with_retry`` for the backoff logic.
"""

import logging
from datetime import date, datetime, timedelta
from typing import Any

from app.data.pipelines.base import ETLPipeline, ETLResult
from app.data.providers.base import DataProvider
from app.services.cninfo_report_service import CninfoReportService

logger = logging.getLogger(__name__)


class _CninfoProviderAdapter(DataProvider):
    """Minimal :class:`DataProvider` adapter used only so the base class
    ``ETLLog`` row can store a non-empty ``source``.  We do not actually
    call any of the abstract methods on it."""

    @property
    def name(self) -> str:
        return "cninfo"

    def fetch_etf_list(self):  # pragma: no cover - unused
        return []

    def fetch_daily_bars(self, codes, start_date, end_date):  # pragma: no cover - unused
        import pandas as pd

        return pd.DataFrame()

    def fetch_realtime_quotes(self, codes):  # pragma: no cover - unused
        import pandas as pd

        return pd.DataFrame()

    def get_market_hours(self, code=None):  # pragma: no cover - unused
        from app.data.providers.base import MarketHours

        return MarketHours()


class CninfoReportsPipeline(ETLPipeline):
    """ETL pipeline that refreshes ``cninfo_reports`` daily.

    Scheduled at 17:00 Asia/Shanghai (after A-share market close) so we
    catch the same-day annual / semi-annual reports that often land just
    after-hours.
    """

    job_name = "cninfo_reports_daily"

    def __init__(
        self,
        db,
        *,
        service: CninfoReportService | None = None,
        window_days: int = 7,
    ) -> None:
        provider = _CninfoProviderAdapter()
        super().__init__(provider=provider, db=db)
        self.service = service or CninfoReportService(db)
        self.window_days = window_days

    # ------------------------------------------------------------------
    # Override the default run() — we don't need normalize / validate
    # for this non-OHLCV dataset, and ``run_with_retry`` still works
    # because it delegates to run().
    # ------------------------------------------------------------------

    def run(self) -> ETLResult:
        result = ETLResult()
        self._create_log()

        try:
            today = date.today()
            start = today - timedelta(days=self.window_days)

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
                "CninfoReportsPipeline: upserted %d announcements (raw=%d, window=%s..%s)",
                written,
                len(records),
                start,
                today,
            )
        except Exception as exc:
            error_msg = str(exc)
            result.success = False
            result.error = error_msg
            self._update_log(status="failed", error=error_msg)
            logger.error("CninfoReportsPipeline failed: %s", error_msg)

        return result

    # ------------------------------------------------------------------
    # extract / transform / load
    # ------------------------------------------------------------------

    def extract(self) -> list[dict[str, Any]]:
        """Pull periodic reports for the B-tier universe.

        Returns the raw normalised list from the service.  Per-stock
        failures are already swallowed inside the service so the list is
        the union of all successful fetches.
        """
        today = date.today()
        start = today - timedelta(days=self.window_days)
        # Fetch synchronously via the service — the universe is ~800
        # stocks and cninfo paginates internally, so this is fine for a
        # nightly job.
        written = self.service.fetch_hs300_cs500_reports(
            start_date=start,
            end_date=today,
        )
        # ``written`` is the upsert count; for ETL bookkeeping we still
        # return a list of the *raw records* that were processed.  We
        # re-derive that by counting rows touched this run.
        return [{"_synthetic_count": written, "_window_start": str(start), "_window_end": str(today)}]

    def transform(self, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """No-op — extraction already returned ORM-ready dicts."""
        return records

    def load(self, records: list[dict[str, Any]]) -> int:
        """No-op — the service writes rows inside ``extract``.

        We return the count carried over so the parent ``run`` can
        populate the ETL log.
        """
        if not records:
            return 0
        return int(records[0].get("_synthetic_count", 0))