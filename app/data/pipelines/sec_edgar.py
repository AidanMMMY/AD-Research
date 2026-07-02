"""SEC EDGAR ingestion pipeline.

Refreshes the ``sec_filings`` table for the S&P 500 universe by walking
the cached SEC ticker directory and upserting every 10-K / 10-Q / 20-F
(no 8-K — see ``sec_edgar_provider``) into the table.  After the bulk
ingest, attempts XBRL extraction for any rows still in
``extraction_status='pending'``.

Designed to be invoked from:
  - APScheduler (weekly Saturday 06:00 UTC = ~14:00 Asia/Shanghai)
  - Admin manual refresh API
  - One-shot CLI / test fixtures

The pipeline overrides ``run()`` to bypass the OHLCV validation in the
base class (we are not loading daily price bars) and to keep each
sub-task isolated under its own try/except guard.
"""

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.data.pipelines.base import ETLPipeline, ETLResult
from app.data.providers.sec_edgar_provider import SecEdgarProvider
from app.models.sec_filing import SecFiling
from app.services.sec_filing_service import SecFilingService

logger = logging.getLogger(__name__)


class SecEdgarPipeline(ETLPipeline):
    """Pipeline that refreshes the ``sec_filings`` table weekly.

    Sub-tasks (each independently guarded):
      1. ``sync_filings``  — pull submissions for the next batch of
         S&P 500 tickers and upsert new filings.
      2. ``extract_metrics`` — attempt XBRL extraction for pending rows.
    """

    job_name = "sec_edgar_daily"

    def __init__(self, db: Session, batch_size: int = 50) -> None:
        # The base class expects a ``DataProvider``; we don't really use
        # ``self.provider`` so a sentinel is fine.
        provider = SecEdgarProvider()
        super().__init__(provider=provider, db=db)
        self.service = SecFilingService(db=db, provider=provider)
        self.batch_size = max(1, int(batch_size))

    def run(self) -> ETLResult:
        """Run the two SEC sub-tasks independently."""
        result = ETLResult()
        self._create_log()

        sync_written = 0
        extract_done = 0
        warnings: list[str] = []

        try:
            try:
                sync_written = self.service.sync_all_sp500(batch_size=self.batch_size)
                logger.info("SecEdgarPipeline: ingested %d filings", sync_written)
            except Exception as exc:
                msg = f"sync_filings failed: {exc}"
                logger.exception("SecEdgarPipeline %s", msg)
                warnings.append(msg)

            try:
                extract_done = self._extract_pending(limit=20)
                logger.info("SecEdgarPipeline: extracted metrics for %d filings", extract_done)
            except Exception as exc:
                msg = f"extract_metrics failed: {exc}"
                logger.exception("SecEdgarPipeline %s", msg)
                warnings.append(msg)

            result.records = sync_written + extract_done
            result.warnings.extend(warnings)
            # Treat partial success as success: at least one sub-task ran.
            result.success = (sync_written + extract_done) > 0 or not warnings
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
            logger.exception("SecEdgarPipeline crashed: %s", exc)

        return result

    # The base class declares extract()/load() as abstract — we override
    # ``run()`` so we don't use them.
    def extract(self):  # pragma: no cover - unused
        raise NotImplementedError("SecEdgarPipeline uses run() override")

    def load(self, data):  # pragma: no cover - unused
        raise NotImplementedError("SecEdgarPipeline uses run() override")

    # ------------------------------------------------------------------
    # Sub-task helpers
    # ------------------------------------------------------------------

    def _extract_pending(self, limit: int = 20) -> int:
        """Attempt XBRL extraction for ``limit`` pending filings.

        Picks the oldest pending rows first so a slow backlog drains
        steadily.  Failures are logged inside ``extract_metrics_for_filing``
        and do not abort the loop.
        """
        stmt = (
            select(SecFiling)
            .where(SecFiling.extraction_status == "pending")
            .order_by(SecFiling.filing_date.asc())
            .limit(limit)
        )
        rows = self.db.execute(stmt).scalars().all()
        done = 0
        for row in rows:
            try:
                if self.service.extract_metrics_for_filing(row.accession_number):
                    done += 1
            except Exception as exc:
                logger.warning(
                    "SecEdgarPipeline.extract_pending %s failed: %s",
                    row.accession_number, exc,
                )
                continue
        return done