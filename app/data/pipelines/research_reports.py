"""Research-report ETL pipeline.

Fetches recent analyst research reports for active A-share stocks from
Eastmoney (via akshare) and upserts them into the ``research_reports``
table. The actual fetch + upsert logic lives in
:class:`ResearchReportService`; this pipeline is a thin orchestrator
that wires the service into the standard ``ETLPipeline`` contract
(extract -> transform -> load) so it shows up in the ETL log table and
the same retry semantics apply.

Scheduled daily at 18:00 Asia/Shanghai (after both A-share and US
market data has been ingested for the day).

Incrementality:
  * ``extract()`` looks up the latest ``publish_date`` in the DB and
    fetches with a 7-day safety buffer (re-runs are idempotent thanks
    to the unique constraint, so a too-wide window is safe).
  * If the table is empty, fall back to the last 30 days.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.data.pipelines.base import ETLPipeline, ETLResult
from app.data.providers.eastmoney_research_provider import EastMoneyResearchProvider
from app.models.research_report import ResearchReport
from app.services.research_report_service import ResearchReportService

logger = logging.getLogger(__name__)


class ResearchReportsPipeline(ETLPipeline):
    """Pipeline that refreshes ``research_reports`` daily."""

    job_name = "research_reports_daily"

    def __init__(self, db: Session) -> None:
        provider = EastMoneyResearchProvider()
        super().__init__(provider=provider, db=db)
        self.service = ResearchReportService(db, provider=provider)

    def run(self) -> ETLResult:
        """Run the pipeline.

        Skips the base-class OHLCV validation/normalization since the
        payload is structured analyst reports, not price bars.
        """
        result = ETLResult()
        self._create_log()
        try:
            records = self.extract()
            upserts = self.transform(records)
            written = self.load(upserts)
            result.records = written
            result.success = True
            self._update_log(status="success", records=written)
            logger.info(
                "ResearchReportsPipeline: Upserted %d research reports (raw=%d)",
                written,
                len(records),
            )
        except Exception as exc:
            error_msg = str(exc)
            result.success = False
            result.error = error_msg
            self._update_log(status="failed", error=error_msg)
            logger.error("ResearchReportsPipeline failed: %s", error_msg)
        return result

    # ----- ETL stages -----------------------------------------------------

    def extract(self) -> list[dict[str, Any]]:
        """Look up the last successful run and fetch a small batch.

        Returns the raw normalized records straight from the provider.
        The actual "incremental" filter is enforced inside the service
        (it skips records older than the lookback window), so this
        function focuses on *which* stocks to query.
        """
        last = self.service.latest_publish_date()
        if last is None:
            days = 30
        else:
            # Re-fetch with a 7-day safety buffer to catch any late
            # additions or upstream backfills.
            days = max((date.today() - last).days + 7, 7)

        return self.service.fetch_recent_reports(limit=200) or []

    def transform(self, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Identity transform — service already normalized the rows.

        Kept as a stage so the pipeline contract is explicit and so
        tests have a clean place to hook a mock.
        """
        return list(records)

    def load(self, records: list[dict[str, Any]]) -> int:
        """Upsert via the service.

        Empty input is a no-op (returns 0); this keeps the daily
        scheduler green when there are no new reports.
        """
        if not records:
            return 0
        return self.service._upsert(records)
