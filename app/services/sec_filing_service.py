"""SEC EDGAR filing service.

Orchestrates SEC EDGAR → ``sec_filings`` upserts and exposes
listing / detail / metrics helpers for the API layer.

Public methods
--------------
- ``sync_filings_for_ticker(db, ticker) -> int``
    Fetch the full submissions feed for one ticker and upsert every
    10-K / 10-Q / 20-F (no 8-K — see ``sec_edgar_provider``).
- ``sync_all_sp500(db, batch_size=50) -> int``
    Walk the cached SEC ticker directory and upsert filings for each
    ticker with a CIK.  Processes ``batch_size`` tickers per call so
    one run never blocks for hours.
- ``extract_metrics_for_filing(db, accession_number) -> bool``
    Look up the filing row, hit the XBRL companyfacts endpoint and
    persist the extracted metrics + flip ``extraction_status`` to
    ``success`` / ``failed``.
"""

import logging
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.data.providers.sec_edgar_provider import SecEdgarProvider
from app.models.sec_filing import SecFiling

logger = logging.getLogger(__name__)


# Form types worth ingesting — mirrors ``sec_edgar_provider._TARGET_FORM_TYPES``
# but we re-list here to keep the service decoupled from the provider.
_TARGET_FORMS = {"10-K", "10-Q", "20-F", "20-F/A", "10-K/A", "10-Q/A"}


class SecFilingService:
    """Service for SEC EDGAR filing ingestion + read APIs."""

    def __init__(
        self,
        db: Session,
        provider: SecEdgarProvider | None = None,
    ) -> None:
        self.db = db
        self.provider = provider or SecEdgarProvider()

    # ------------------------------------------------------------------
    # Write path
    # ------------------------------------------------------------------

    def sync_filings_for_ticker(self, ticker: str) -> int:
        """Fetch the submissions feed for ``ticker`` and upsert each filing.

        Returns the number of newly written rows (conflicts counted as 0).
        """
        ticker = ticker.upper().strip()
        if not ticker:
            return 0

        # Resolve CIK — try cache first, fall back to a single network round-trip.
        ticker_map = self.provider.load_ticker_to_cik_map()
        cik = ticker_map.get(ticker)
        if not cik:
            logger.warning("SEC sync: ticker %s not found in directory", ticker)
            return 0

        try:
            payload = self.provider.fetch_submissions(cik)
        except Exception as exc:
            logger.warning("SEC sync: fetch_submissions(%s) failed: %s", cik, exc)
            return 0

        records = self._parse_recent_filings(payload, cik=cik, ticker=ticker)
        if not records:
            return 0
        return self._upsert_records(records)

    def sync_all_sp500(self, batch_size: int = 50) -> int:
        """Walk the cached SEC ticker directory and upsert filings.

        Iterates the full ticker map (~thousands) but caps each call at
        ``batch_size`` tickers so an interactive admin-triggered run
        finishes within a sane window.  The caller (scheduler) can
        invoke this repeatedly across days for natural load balancing.
        """
        ticker_map = self.provider.load_ticker_to_cik_map()
        if not ticker_map:
            logger.warning("SEC sync_all_sp500: empty ticker map")
            return 0

        written = 0
        # Stable ordering → idempotent batch selection per run.
        for ticker in sorted(ticker_map.keys())[: max(1, int(batch_size))]:
            try:
                written += self.sync_filings_for_ticker(ticker)
            except Exception as exc:
                # A single ticker failure must NOT block the batch.
                logger.warning("SEC sync: %s failed: %s", ticker, exc)
                continue
        logger.info("SEC sync_all_sp500 batch wrote %d rows", written)
        return written

    def extract_metrics_for_filing(self, accession_number: str) -> bool:
        """Pull XBRL metrics for one filing and persist them.

        Returns True if extraction succeeded (metrics stored,
        ``extraction_status`` flipped to ``success``).  Returns False
        if the filing was not found or the upstream XBRL call failed.
        """
        if not accession_number:
            return False

        stmt = select(SecFiling).where(SecFiling.accession_number == accession_number)
        filing = self.db.execute(stmt).scalar_one_or_none()
        if filing is None:
            logger.warning(
                "SEC extract_metrics: accession %s not found", accession_number,
            )
            return False

        try:
            facts = self.provider.fetch_company_facts(filing.cik)
        except Exception as exc:
            logger.warning(
                "SEC extract_metrics: companyfacts(%s) failed: %s", filing.cik, exc,
            )
            self._mark_extraction_failed(filing, error=str(exc))
            return False

        try:
            metrics = self.provider.extract_metrics(facts, tickers=[filing.ticker])
        except Exception as exc:
            logger.warning(
                "SEC extract_metrics: parse failed for %s: %s", accession_number, exc,
            )
            self._mark_extraction_failed(filing, error=str(exc))
            return False

        filing.extracted_metrics = metrics
        filing.extraction_status = "success"
        filing.extracted_at = datetime.now(timezone.utc)
        self.db.commit()
        return True

    # ------------------------------------------------------------------
    # Read path (used by the API)
    # ------------------------------------------------------------------

    def list_filings(
        self,
        page: int = 1,
        page_size: int = 20,
        ticker: str | None = None,
        cik: str | None = None,
        form_type: str | None = None,
        start_date: Any = None,
        end_date: Any = None,
        q: str | None = None,
        sort_by: str = "filing_date",
        sort_dir: str = "desc",
    ) -> dict[str, Any]:
        """Return a paginated, filtered list of SEC filings."""
        if page < 1:
            page = 1
        if page_size < 1 or page_size > 100:
            page_size = 20

        sortable = {"filing_date", "report_period", "created_at", "form_type", "ticker"}
        if sort_by not in sortable:
            sort_by = "filing_date"
        sort_dir_norm = sort_dir.lower() if sort_dir.lower() in ("asc", "desc") else "desc"

        stmt = select(SecFiling)
        count_stmt = select(func.count(SecFiling.id))

        if ticker:
            stmt = stmt.where(SecFiling.ticker == ticker.upper())
            count_stmt = count_stmt.where(SecFiling.ticker == ticker.upper())
        if cik:
            stmt = stmt.where(SecFiling.cik == cik)
            count_stmt = count_stmt.where(SecFiling.cik == cik)
        if form_type:
            stmt = stmt.where(SecFiling.form_type == form_type)
            count_stmt = count_stmt.where(SecFiling.form_type == form_type)
        if start_date:
            stmt = stmt.where(SecFiling.filing_date >= start_date)
            count_stmt = count_stmt.where(SecFiling.filing_date >= start_date)
        if end_date:
            stmt = stmt.where(SecFiling.filing_date <= end_date)
            count_stmt = count_stmt.where(SecFiling.filing_date <= end_date)
        if q:
            pattern = f"%{q}%"
            stmt = stmt.where(
                (SecFiling.company_name.ilike(pattern)) | (SecFiling.ticker.ilike(pattern))
            )
            count_stmt = count_stmt.where(
                (SecFiling.company_name.ilike(pattern)) | (SecFiling.ticker.ilike(pattern))
            )

        sort_col = getattr(SecFiling, sort_by)
        stmt = stmt.order_by(sort_col.desc() if sort_dir_norm == "desc" else sort_col.asc())

        total = self.db.execute(count_stmt).scalar() or 0
        rows = self.db.execute(
            stmt.offset((page - 1) * page_size).limit(page_size)
        ).scalars().all()

        return {
            "items": [_to_out(row) for row in rows],
            "total": int(total),
            "page": page,
            "page_size": page_size,
        }

    def get_filing(self, filing_id: int) -> dict[str, Any] | None:
        """Return one SEC filing detail by id, including extracted metrics."""
        filing = self.db.get(SecFiling, filing_id)
        if filing is None:
            return None
        return _to_detail(filing)

    def get_filing_by_accession(self, accession_number: str) -> dict[str, Any] | None:
        """Return one SEC filing detail by accession number."""
        if not accession_number:
            return None
        stmt = select(SecFiling).where(SecFiling.accession_number == accession_number)
        filing = self.db.execute(stmt).scalar_one_or_none()
        if filing is None:
            return None
        return _to_detail(filing)

    def get_coverage(self) -> dict[str, Any]:
        """Return coverage stats for the dashboard."""
        total = self.db.execute(select(func.count(SecFiling.id))).scalar() or 0
        tracked = self.db.execute(
            select(func.count(func.distinct(SecFiling.ticker)))
        ).scalar() or 0
        latest = self.db.execute(select(func.max(SecFiling.filing_date))).scalar()

        by_form: dict[str, int] = {}
        rows = self.db.execute(
            select(SecFiling.form_type, func.count(SecFiling.id)).group_by(SecFiling.form_type)
        ).all()
        for form, count in rows:
            if form:
                by_form[form] = int(count)

        status_counts = dict(
            self.db.execute(
                select(SecFiling.extraction_status, func.count(SecFiling.id)).group_by(
                    SecFiling.extraction_status
                )
            ).all()
        )

        return {
            "total_filings": int(total),
            "tracked_tickers": int(tracked),
            "by_form_type": by_form,
            "latest_filing_date": latest,
            "extractions_completed": int(status_counts.get("success", 0)),
            "extractions_failed": int(status_counts.get("failed", 0)),
            "extractions_pending": int(status_counts.get("pending", 0)),
        }

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_recent_filings(
        payload: dict[str, Any], *, cik: str, ticker: str
    ) -> list[dict[str, Any]]:
        """Map the SEC ``submissions`` JSON to upsert rows.

        The SEC submissions payload nests the most-recent ~1000 filings
        under ``filings.recent``.  Older archives live under
        ``filings.files`` — we ignore those because the recent window
        covers everything we'd ever refresh weekly.
        """
        if not isinstance(payload, dict):
            return []

        filings = payload.get("filings") or {}
        recent = filings.get("recent") or {}
        if not isinstance(recent, dict):
            return []

        # SEC ships parallel arrays — one entry per filing.
        forms = recent.get("form") or []
        filing_dates = recent.get("filingDate") or []
        report_dates = recent.get("reportDate") or []
        accession_numbers = recent.get("accessionNumber") or []
        primary_documents = recent.get("primaryDocument") or []

        company_name = payload.get("name") or ""

        records: list[dict[str, Any]] = []
        n = len(forms)
        for i in range(n):
            try:
                form = forms[i]
                filing_date_raw = filing_dates[i]
                accession = accession_numbers[i]
            except (IndexError, TypeError):
                continue
            if form not in _TARGET_FORMS:
                continue
            if not accession or not filing_date_raw:
                continue

            accession_clean = str(accession).replace("-", "")
            primary_doc = primary_documents[i] if i < len(primary_documents) else None
            report_date_raw = report_dates[i] if i < len(report_dates) else None

            filing_date = _coerce_date(filing_date_raw)
            report_date = _coerce_date(report_date_raw) if report_date_raw else None
            if filing_date is None:
                continue

            filing_url = (
                f"https://www.sec.gov/cgi-bin/browse-edgar"
                f"?action=getcompany&CIK={cik}&type={form}&dateb=&owner=include&count=40"
            )

            records.append(
                {
                    "cik": cik,
                    "ticker": ticker,
                    "company_name": company_name or None,
                    "form_type": form,
                    "filing_date": filing_date,
                    "report_period": report_date,
                    "accession_number": str(accession),
                    "primary_document": primary_doc or None,
                    "filing_url": filing_url,
                    "extraction_status": "pending",
                    "source": "sec_edgar",
                }
            )
            # accession_clean is unused today but kept for debugging hooks.
            del accession_clean

        return records

    def _upsert_records(self, records: list[dict[str, Any]]) -> int:
        """Upsert ``records`` into ``sec_filings`` idempotently.

        Uses the dialect-appropriate ``ON CONFLICT`` so tests under
        SQLite exercise the same code path as production Postgres.
        """
        if not records:
            return 0

        dialect = self.db.bind.dialect.name if self.db.bind is not None else ""
        if dialect.startswith("postgres"):
            stmt = pg_insert(SecFiling).values(records)
            stmt = stmt.on_conflict_do_update(
                index_elements=["accession_number"],
                set_={
                    "cik": stmt.excluded.cik,
                    "ticker": stmt.excluded.ticker,
                    "company_name": stmt.excluded.company_name,
                    "form_type": stmt.excluded.form_type,
                    "filing_date": stmt.excluded.filing_date,
                    "report_period": stmt.excluded.report_period,
                    "primary_document": stmt.excluded.primary_document,
                    "filing_url": stmt.excluded.filing_url,
                },
            )
        else:
            stmt = sqlite_insert(SecFiling).values(records)
            stmt = stmt.on_conflict_do_update(
                index_elements=["accession_number"],
                set_={
                    "cik": stmt.excluded.cik,
                    "ticker": stmt.excluded.ticker,
                    "company_name": stmt.excluded.company_name,
                    "form_type": stmt.excluded.form_type,
                    "filing_date": stmt.excluded.filing_date,
                    "report_period": stmt.excluded.report_period,
                    "primary_document": stmt.excluded.primary_document,
                    "filing_url": stmt.excluded.filing_url,
                },
            )

        self.db.execute(stmt)
        self.db.commit()
        return len(records)

    def _mark_extraction_failed(self, filing: SecFiling, *, error: str) -> None:
        filing.extraction_status = "failed"
        filing.extracted_at = datetime.now(timezone.utc)
        # Stash the error inside extracted_metrics so the UI can surface it
        # without growing the schema.
        filing.extracted_metrics = {"_error": error[:500]}
        self.db.commit()


# ---------------------------------------------------------------------------
# Serialisers
# ---------------------------------------------------------------------------


def _to_out(filing: SecFiling) -> dict[str, Any]:
    return {
        "id": filing.id,
        "cik": filing.cik,
        "ticker": filing.ticker,
        "company_name": filing.company_name,
        "form_type": filing.form_type,
        "filing_date": filing.filing_date.isoformat() if filing.filing_date else None,
        "report_period": filing.report_period.isoformat() if filing.report_period else None,
        "accession_number": filing.accession_number,
        "primary_document": filing.primary_document,
        "filing_url": filing.filing_url,
        "extraction_status": filing.extraction_status,
        "source": filing.source,
        "extracted_at": filing.extracted_at.isoformat() if filing.extracted_at else None,
        "created_at": filing.created_at.isoformat() if filing.created_at else None,
        "updated_at": filing.updated_at.isoformat() if filing.updated_at else None,
    }


def _to_detail(filing: SecFiling) -> dict[str, Any]:
    payload = _to_out(filing)
    payload["extracted_metrics"] = filing.extracted_metrics
    payload["xbrl_file_path"] = filing.xbrl_file_path
    return payload


def _coerce_date(value: Any) -> date | None:
    """Best-effort conversion of an SEC date string to ``date``.

    SEC returns dates as ISO-8601 ``YYYY-MM-DD`` strings; we accept
    that and also tolerate ``datetime`` instances.  Returns ``None`` on
    any unrecognised input so the caller can drop the row.
    """
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y%m%d"):
            try:
                return datetime.strptime(s[:10], fmt).date()
            except (TypeError, ValueError):
                continue
    return None