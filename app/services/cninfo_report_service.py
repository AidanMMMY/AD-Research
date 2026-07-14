"""Cninfo periodic report service.

Coordinates fetching announcements from the upstream cninfo API, writing
metadata into ``cninfo_reports``, downloading PDFs on demand, and
extracting a text preview.

The service is deliberately *fault-tolerant*: every public method logs
and continues on individual record failures rather than aborting the
whole batch — when scraping 800 companies, a few transient network
errors should not be allowed to wipe out the rest of the run.
"""

import logging
import os
from datetime import date, datetime
from pathlib import Path
from typing import Any

import requests
from sqlalchemy import and_, distinct, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.config import get_settings
from app.data.providers.cninfo_provider import CninfoProvider
from app.data.providers.exchange_provider import ExchangeProvider
from app.data.providers.tushare_provider import TushareProvider
from app.models.cninfo_report import CninfoReport
from app.models.etf import ETFInfo

logger = logging.getLogger(__name__)


# Local PDF storage directory.  Defaults to ``/data/alloy-research/cninfo_pdfs``
# (matches the deploy volume mount) but can be overridden via env.
_DEFAULT_PDF_DIR = Path(
    os.environ.get("CNINFO_PDF_DIR") or "/data/alloy-research/cninfo_pdfs"
)

# Cap on text length stored in ``extracted_text``.  We don't need the full
# 200-page PDF — 200k chars covers the management discussion + key tables.
_MAX_TEXT_LEN = 200_000

# Text preview length returned in the detail endpoint (500 chars).
_PREVIEW_LEN = 500


# ---------------------------------------------------------------------------
# Lazy / fault-tolerant PDF text extraction
# ---------------------------------------------------------------------------


def extract_text_with_pdfplumber(file_path: Path) -> str:
    """Extract text using pdfplumber. Returns concatenated page text."""
    import pdfplumber

    pieces: list[str] = []
    with pdfplumber.open(str(file_path)) as pdf:
        for page in pdf.pages:
            try:
                pieces.append(page.extract_text() or "")
            except Exception as exc:  # pragma: no cover - per-page fault
                logger.warning("pdfplumber page failed: %s", exc)
    return "\n".join(pieces)


def extract_text_with_pypdf2(file_path: Path) -> str:
    """Fallback text extractor using pypdf2 / PyPDF2 / pypdf."""
    # ``pypdf`` is the maintained successor to PyPDF2; both expose the
    # same ``PdfReader`` interface.
    try:
        import pypdf  # type: ignore

        reader = pypdf.PdfReader(str(file_path))
        return "\n".join(
            (page.extract_text() or "") for page in reader.pages
        )
    except ImportError:
        try:
            import PyPDF2  # type: ignore

            reader = PyPDF2.PdfReader(str(file_path))
            return "\n".join(
                (page.extract_text() or "") for page in reader.pages
            )
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "No PDF text extractor available — install pdfplumber or pypdf"
            ) from exc


def extract_text_with_pdfminer(file_path: Path) -> str:
    """Final fallback using pdfminer.six (no PyPDF2 dep required)."""
    from pdfminer.high_level import extract_text as _extract_text

    return _extract_text(str(file_path))


def extract_text(file_path: Path) -> str:
    """Best-effort PDF text extraction.

    Tries pdfplumber first (cleanest layout), then pypdf / PyPDF2, then
    pdfminer.six.  Raises ``RuntimeError`` if none of the libraries are
    installed.
    """
    try:
        return extract_text_with_pdfplumber(file_path)
    except ImportError:
        pass
    except Exception as exc:  # pragma: no cover - per-document fault
        logger.warning("pdfplumber failed for %s: %s", file_path, exc)

    try:
        return extract_text_with_pypdf2(file_path)
    except ImportError:
        pass
    except Exception as exc:  # pragma: no cover - per-document fault
        logger.warning("pypdf/PyPDF2 failed for %s: %s", file_path, exc)

    try:
        return extract_text_with_pdfminer(file_path)
    except ImportError as exc:
        raise RuntimeError(
            "No PDF text extractor available — install pdfplumber / pypdf / pdfminer.six"
        ) from exc


# ---------------------------------------------------------------------------
# Universe helpers
# ---------------------------------------------------------------------------


def get_hs300_cs500_universe(
    ts_token: str | None = None,
    batch_size: int = 800,
) -> list[str]:
    """Return up to ``batch_size`` ts_codes drawn from HS300 + CS500.

    Falls back to ``stock_basic`` (long history) when index constituents
    aren't available — free-tier Tushare users typically don't have
    access to ``index_weight``.  In both cases we cap the result at
    ``batch_size`` so the first run doesn't blow the rate budget.
    """
    ts = ts_token or get_settings().tushare_token
    provider = TushareProvider()
    seen: set[str] = set()

    if ts:
        for index_code in ("000300.SH", "000905.SH"):
            try:
                weights = provider.fetch_index_weight(
                    index_code=index_code
                )
                for row in weights or []:
                    code = row.get("con_code") or row.get("ts_code")
                    if code:
                        seen.add(str(code))
            except Exception as exc:  # pragma: no cover - free-tier fallthrough
                logger.info(
                    "index_weight(%s) unavailable: %s — falling back to stock_basic",
                    index_code,
                    exc,
                )

    if not seen and ts:
        try:
            df = provider.fetch_stock_basic(list_status="L")
            for _, row in df.iterrows():
                code = row.get("ts_code")
                if code:
                    seen.add(str(code))
        except Exception as exc:  # pragma: no cover
            logger.warning("stock_basic fallback failed: %s", exc)

    # Sort for stable ordering across runs and cap to batch_size.
    return sorted(seen)[:batch_size]


def get_all_org_id_universe() -> list[str]:
    """Return the full A-share universe from the cninfo org-id lookup table.

    Reads ``app/data/static/cninfo_org_ids.json`` and returns every
    ts_code that maps to a valid cninfo orgId.  This is the universe
    used by the daily pipeline (post-backfill) — ~3,200 stocks.
    """
    import json
    from pathlib import Path

    path = Path(__file__).parent.parent / "data" / "static" / "cninfo_org_ids.json"
    if not path.exists():
        logger.warning("cninfo org-id table not found at %s — falling back to HS300+CS500", path)
        return get_hs300_cs500_universe()

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Failed to read cninfo org-id table: %s", exc)
        return get_hs300_cs500_universe()

    codes = sorted(k for k in data if not k.startswith("_"))
    logger.info("cninfo full universe: %d stocks from org-id lookup", len(codes))
    return codes


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class CninfoReportService:
    """High-level orchestration around the cninfo provider + ORM."""

    def __init__(self, db: Session, provider: CninfoProvider | None = None) -> None:
        self.db = db
        self.provider = provider or CninfoProvider()

    # ------------------------------------------------------------------
    # Fetch + upsert
    # ------------------------------------------------------------------

    def fetch_for_stock(
        self,
        ts_code: str,
        start_date: date,
        end_date: date,
    ) -> int:
        """Fetch all four periodic reports for one ``ts_code`` and upsert.

        Returns the number of rows newly written (or refreshed via the
        ON CONFLICT branch).  Returns 0 if ``ts_code`` is not in the
        org-id lookup table (we don't try to guess).
        """
        org_id = self.provider.get_org_id(ts_code)
        if not org_id:
            logger.info("cninfo: no orgId for %s — skipping", ts_code)
            return 0

        stock_code = ts_code.split(".")[0]

        try:
            raw_records = self.provider.fetch_periodic_reports(
                org_id=org_id,
                start_date=start_date,
                end_date=end_date,
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("cninfo fetch failed for %s: %s", ts_code, exc)
            return 0

        if not raw_records:
            return 0

        written = 0
        for record in raw_records:
            try:
                written += self._upsert(record, ts_code, stock_code, org_id)
            except Exception as exc:
                logger.warning(
                    "cninfo upsert failed for %s ann=%s: %s",
                    ts_code,
                    record.get("announcement_id"),
                    exc,
                )
        return written

    def fetch_hs300_cs500_reports(
        self,
        start_date: date,
        end_date: date,
        batch_size: int = 50,
        universe: list[str] | None = None,
    ) -> int:
        """Walk the HS300 + CS500 universe and pull periodic reports.

        ``batch_size`` here is a *per-request* cap — we process every
        stock in the universe but only fetch ``batch_size`` at a time to
        avoid holding a single giant response.  Returns the total number
        of rows upserted.
        """
        codes = universe if universe is not None else get_hs300_cs500_universe(
            batch_size=800
        )
        if not codes:
            logger.warning("cninfo: empty universe — nothing to fetch")
            return 0

        total = 0
        for code in codes:
            try:
                total += self.fetch_for_stock(code, start_date, end_date)
            except Exception as exc:
                logger.warning("cninfo loop failed for %s: %s", code, exc)
                continue
        return total

    # ------------------------------------------------------------------
    # PDF download
    # ------------------------------------------------------------------

    def download_pdf(self, report_id: int) -> Path | None:
        """Download the PDF for one report, returning the local path.

        Writes to ``{CNINFO_PDF_DIR}/{ts_code}/{announcement_id}.pdf`` and
        updates ``file_path`` / ``file_size`` on the ORM row.  Returns
        ``None`` if the report doesn't exist, has no URL, or the
        upstream returns a non-200 response.
        """
        report = self.db.get(CninfoReport, report_id)
        if report is None:
            return None

        if not report.adjunct_url:
            logger.warning("cninfo: report %s has no adjunct_url", report_id)
            return None

        # cninfo URLs are relative paths under ``static.cninfo.com.cn``.
        url = report.adjunct_url
        if url.startswith("/"):
            url = "http://static.cninfo.com.cn" + url
        elif not url.startswith("http"):
            url = "http://static.cninfo.com.cn/" + url.lstrip("/")

        target_dir = _DEFAULT_PDF_DIR / report.ts_code
        try:
            target_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:  # pragma: no cover - permissions
            logger.warning("cninfo: cannot mkdir %s: %s", target_dir, exc)
            return None

        target = target_dir / f"{report.announcement_id}.pdf"

        try:
            with requests.get(url, timeout=30, stream=True) as resp:
                if resp.status_code != 200:
                    logger.warning(
                        "cninfo download HTTP %s for %s",
                        resp.status_code,
                        url,
                    )
                    return None
                with open(target, "wb") as fh:
                    for chunk in resp.iter_content(chunk_size=64 * 1024):
                        if chunk:
                            fh.write(chunk)
        except requests.RequestException as exc:
            logger.warning("cninfo download error for %s: %s", url, exc)
            return None

        size = target.stat().st_size if target.exists() else None

        report.file_path = str(target)
        report.file_size = size
        report.extraction_status = "downloaded"
        self.db.add(report)
        self.db.commit()
        return target

    # ------------------------------------------------------------------
    # Fallback PDF download (exchange → cninfo)
    # ------------------------------------------------------------------

    # Re-use cninfo's PDF directory layout so fallback hits the same
    # path the original ``download_pdf`` would have produced —
    # downstream code (extraction, API) needs no special-casing.
    def download_with_fallback(
        self,
        report_id: int,
        *,
        exchange_provider: ExchangeProvider | None = None,
    ) -> dict[str, Any]:
        """Try cninfo first; if it returns ``None``, walk SSE / SZSE /
        BSE listing pages and download from there.

        Returns::

            {
                "path": Path | None,
                "source": "cninfo" | "sse" | "szse" | "bse" | None,
                "fallback_used": bool,
                "error": str | None,  # only set when both failed
            }

        The ORM row's ``source`` and ``file_path`` / ``file_size``
        columns are kept in sync — so the rest of the pipeline
        (text extraction, the detail API) can't tell which channel
        the PDF originally came from.
        """
        report = self.db.get(CninfoReport, report_id)
        if report is None:
            return {"path": None, "source": None, "fallback_used": False,
                    "error": "report not found"}

        # Step 1: try the original cninfo URL via the existing
        # helper.  Its return value already walks the path-writing +
        # DB-update flow; we just inspect the side effects.
        try:
            path = self.download_pdf(report_id)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("cninfo download raised for %s: %s", report_id, exc)
            path = None

        if path is not None:
            # cninfo succeeded — make sure source is normalised to
            # 'cninfo' even if a prior fallback run wrote 'szse' etc.
            report.source = "cninfo"
            try:
                self.db.add(report)
                self.db.commit()
            except Exception:  # pragma: no cover - defensive
                self.db.rollback()
            return {
                "path": path,
                "source": "cninfo",
                "fallback_used": False,
                "error": None,
            }

        # Step 2: cninfo failed — try the official exchange listing.
        target_dir = _DEFAULT_PDF_DIR / report.ts_code
        try:
            target_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:  # pragma: no cover - permissions
            logger.warning("cannot mkdir %s: %s", target_dir, exc)
            return {"path": None, "source": None, "fallback_used": False,
                    "error": f"mkdir failed: {exc}"}
        target = target_dir / f"{report.announcement_id}.pdf"

        ann_dt = report.announcement_time
        ann_date = ann_dt.date() if hasattr(ann_dt, "date") else None
        if ann_date is None:
            return {"path": None, "source": None, "fallback_used": False,
                    "error": "no announcement_time"}

        provider = exchange_provider or ExchangeProvider()
        try:
            url = provider.find_report_pdf(
                report.ts_code,
                ann_date,
                title_hint=report.announcement_title,
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("ExchangeProvider error for %s: %s", report.ts_code, exc)
            url = None

        if not url:
            logger.info(
                "fallback: no exchange PDF for %s ann=%s on %s",
                report.ts_code,
                report.announcement_id,
                ann_date.isoformat(),
            )
            return {"path": None, "source": None, "fallback_used": False,
                    "error": "no exchange match"}

        # Step 3: download the candidate URL.
        ok, err, size = provider.download_candidate(url, str(target))
        if not ok:
            logger.info(
                "fallback: exchange download failed for %s url=%s err=%s",
                report.ts_code, url, err,
            )
            return {"path": None, "source": None, "fallback_used": False,
                    "error": f"exchange download failed: {err}"}

        # The exchange source depends on the URL host (covers
        # SSE / SZSE / BSE uniformly) — fall back to SZSE when the
        # host is unknown so we still record *something*.
        if "sse.com.cn" in url:
            source_label = "sse"
        elif "szse.cn" in url:
            source_label = "szse"
        elif "bse.cn" in url:
            source_label = "bse"
        else:
            source_label = "szse"

        report.file_path = str(target)
        report.file_size = size
        report.source = source_label
        report.extraction_status = "downloaded"
        try:
            self.db.add(report)
            self.db.commit()
        except Exception:  # pragma: no cover - defensive
            self.db.rollback()
            return {"path": None, "source": None, "fallback_used": False,
                    "error": "DB commit failed"}

        logger.info(
            "fallback: downloaded via %s for %s ann=%s url=%s size=%s",
            source_label,
            report.ts_code,
            report.announcement_id,
            url,
            size,
        )
        return {
            "path": target,
            "source": source_label,
            "fallback_used": True,
            "error": None,
        }

    # ------------------------------------------------------------------
    # PDF text extraction
    # ------------------------------------------------------------------

    def extract_text_for_report(self, report_id: int) -> bool:
        """Extract text from the downloaded PDF and store on the ORM row.

        Returns True if the row's ``extracted_text`` was populated.  The
        caller is expected to have run ``download_pdf`` first.
        """
        report = self.db.get(CninfoReport, report_id)
        if report is None:
            return False

        if not report.file_path:
            logger.warning(
                "cninfo: report %s has no file_path — download first",
                report_id,
            )
            return False

        pdf_path = Path(report.file_path)
        if not pdf_path.exists():
            logger.warning("cninfo: pdf file missing at %s", pdf_path)
            return False

        try:
            text = extract_text(pdf_path)
        except Exception as exc:
            logger.warning(
                "cninfo text extraction failed for %s: %s", report_id, exc
            )
            report.extraction_status = "failed"
            self.db.add(report)
            self.db.commit()
            return False

        # Cap to avoid blowing up the column on huge reports.
        text = (text or "")[:_MAX_TEXT_LEN]
        report.extracted_text = text
        report.extraction_status = "extracted"
        report.extracted_at = datetime.utcnow()
        self.db.add(report)
        self.db.commit()
        return True

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    def list_reports_for_download(
        self,
        ts_code: str,
        start_date: date,
        report_type: str = "all",
        only_pending: bool = True,
    ) -> list[CninfoReport]:
        """Return ORM rows for one ``ts_code`` that need a PDF download.

        Args:
            ts_code: Tushare 证券代码 (e.g. ``600519.SH``).
            start_date: Lower bound on ``announcement_time`` (inclusive).
            report_type: ``annual`` / ``semi`` / ``q1`` / ``q3`` / ``all``.
                Only applied when set to one of the four concrete values.
            only_pending: When ``True`` (default), skip rows that already
                have ``file_path`` set — used for idempotent re-runs.

        Returns:
            ORM rows ordered by ``announcement_time`` desc.
        """
        stmt = select(CninfoReport).where(
            and_(
                CninfoReport.ts_code == ts_code,
                CninfoReport.announcement_time >= start_date,
                CninfoReport.adjunct_url.isnot(None),
            )
        )
        if report_type in ("annual", "semi", "q1", "q3"):
            stmt = stmt.where(CninfoReport.adjunct_type == report_type)
        if only_pending:
            stmt = stmt.where(CninfoReport.file_path.is_(None))
        stmt = stmt.order_by(CninfoReport.announcement_time.desc())

        return list(self.db.execute(stmt).scalars().all())

    def list_reports(
        self,
        ts_code: str | None = None,
        fiscal_year: int | None = None,
        fiscal_quarter: int | None = None,
        adjunct_type: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        has_text: bool | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        """Return a paginated list of report rows + meta."""
        if page < 1:
            page = 1
        if page_size < 1 or page_size > 100:
            page_size = 20

        stmt = select(CninfoReport)
        count_stmt = select(func.count(CninfoReport.id))

        if ts_code:
            stmt = stmt.where(CninfoReport.ts_code == ts_code)
            count_stmt = count_stmt.where(CninfoReport.ts_code == ts_code)
        if fiscal_year is not None:
            stmt = stmt.where(CninfoReport.fiscal_year == fiscal_year)
            count_stmt = count_stmt.where(CninfoReport.fiscal_year == fiscal_year)
        if fiscal_quarter is not None:
            stmt = stmt.where(CninfoReport.fiscal_quarter == fiscal_quarter)
            count_stmt = count_stmt.where(CninfoReport.fiscal_quarter == fiscal_quarter)
        if adjunct_type:
            stmt = stmt.where(CninfoReport.adjunct_type == adjunct_type)
            count_stmt = count_stmt.where(CninfoReport.adjunct_type == adjunct_type)
        if start_date:
            stmt = stmt.where(CninfoReport.announcement_time >= start_date)
            count_stmt = count_stmt.where(
                CninfoReport.announcement_time >= start_date
            )
        if end_date:
            stmt = stmt.where(CninfoReport.announcement_time <= end_date)
            count_stmt = count_stmt.where(
                CninfoReport.announcement_time <= end_date
            )
        if has_text is True:
            stmt = stmt.where(CninfoReport.extracted_text.isnot(None))
            count_stmt = count_stmt.where(CninfoReport.extracted_text.isnot(None))
        elif has_text is False:
            stmt = stmt.where(CninfoReport.extracted_text.is_(None))
            count_stmt = count_stmt.where(CninfoReport.extracted_text.is_(None))

        stmt = stmt.order_by(CninfoReport.announcement_time.desc())
        stmt = stmt.offset((page - 1) * page_size).limit(page_size)

        rows = self.db.execute(stmt).scalars().all()
        total = self.db.execute(count_stmt).scalar() or 0

        ts_codes = [r.ts_code for r in rows]
        name_map = self._stock_name_map(ts_codes)

        latest = self.db.execute(
            select(func.max(CninfoReport.updated_at))
        ).scalar()

        return {
            "items": [_to_out(row, name_map=name_map) for row in rows],
            "total": int(total),
            "page": page,
            "page_size": page_size,
            "updated_at": latest.isoformat() if latest else None,
        }

    def _stock_name_map(self, ts_codes: list[str]) -> dict[str, str | None]:
        """Return a mapping of ts_code -> ETFInfo.name for the given codes."""
        if not ts_codes:
            return {}
        rows = self.db.execute(
            select(ETFInfo.code, ETFInfo.name).where(ETFInfo.code.in_(ts_codes))
        ).all()
        return {code: name for code, name in rows}

    def get_report(self, report_id: int) -> dict[str, Any] | None:
        report = self.db.get(CninfoReport, report_id)
        if report is None:
            return None
        name_map = self._stock_name_map([report.ts_code])
        return _to_detail(report, name_map=name_map)

    def get_coverage(self) -> dict[str, Any]:
        """Return aggregate counts for the dashboard."""
        total = self.db.execute(
            select(func.count(CninfoReport.id))
        ).scalar() or 0

        stocks_covered = self.db.execute(
            select(func.count(distinct(CninfoReport.ts_code)))
        ).scalar() or 0

        stocks_with_text = self.db.execute(
            select(func.count(distinct(CninfoReport.ts_code))).where(
                CninfoReport.extracted_text.isnot(None)
            )
        ).scalar() or 0

        year_rows = self.db.execute(
            select(
                CninfoReport.fiscal_year,
                func.count(CninfoReport.id),
            )
            .where(CninfoReport.fiscal_year.isnot(None))
            .group_by(CninfoReport.fiscal_year)
        ).all()
        fiscal_year_breakdown = {int(y): int(c) for y, c in year_rows if y is not None}

        adjunct_rows = self.db.execute(
            select(CninfoReport.adjunct_type, func.count(CninfoReport.id)).group_by(
                CninfoReport.adjunct_type
            )
        ).all()
        adjunct_breakdown = {str(t): int(c) for t, c in adjunct_rows if t}

        latest = self.db.execute(
            select(func.max(CninfoReport.updated_at))
        ).scalar()

        return {
            "total_reports": int(total),
            "stocks_covered": int(stocks_covered),
            "stocks_with_text": int(stocks_with_text),
            "fiscal_year_breakdown": fiscal_year_breakdown,
            "adjunct_type_breakdown": adjunct_breakdown,
            "updated_at": latest.isoformat() if latest else None,
        }

    # ------------------------------------------------------------------
    # Internal: upsert
    # ------------------------------------------------------------------

    def _upsert(
        self,
        record: dict[str, Any],
        ts_code: str,
        stock_code: str,
        org_id: str,
    ) -> int:
        """Upsert a single cninfo announcement into ``cninfo_reports``.

        Idempotent on the unique ``announcement_id`` constraint.  Returns
        1 on success, 0 on failure.
        """
        announcement_time = record.get("announcement_time")
        if isinstance(announcement_time, str):
            try:
                announcement_time = datetime.fromisoformat(
                    announcement_time.replace("Z", "+00:00")
                )
            except ValueError:
                announcement_time = datetime.utcnow()
        elif isinstance(announcement_time, (int, float)):
            # cninfo returns epoch MILLISECONDS as a number.  0 / very
            # small values are treated as missing — fall back to now().
            try:
                ts = float(announcement_time)
                if ts > 0:
                    # Heuristic: > 1e12 implies milliseconds; otherwise
                    # treat as seconds.
                    if ts > 1e12:
                        ts = ts / 1000.0
                    announcement_time = datetime.fromtimestamp(ts)
                else:
                    announcement_time = datetime.utcnow()
            except (OverflowError, OSError, ValueError):
                announcement_time = datetime.utcnow()
        # Naive datetimes are tagged UTC for the column's tz-aware type.
        if (
            isinstance(announcement_time, datetime)
            and announcement_time.tzinfo is None
        ):
            announcement_time = announcement_time.replace(tzinfo=None)

        fiscal_year = None
        try:
            if announcement_time is not None:
                # Periodic reports are published in the year AFTER the
                # fiscal year ends — an annual report published in
                # March 2026 is for fiscal year 2025.
                fiscal_year = announcement_time.year - 1
        except Exception:
            fiscal_year = None

        import json as _json

        raw_payload_json = _json.dumps(record.get("raw_payload") or {}, ensure_ascii=False)

        values = {
            "ts_code": ts_code,
            "stock_code": stock_code,
            "org_id": org_id,
            "sec_code": record.get("sec_code"),
            "announcement_id": record["announcement_id"],
            "announcement_title": record["announcement_title"],
            "adjunct_url": record["adjunct_url"],
            "announcement_time": announcement_time,
            "adjunct_type": record.get("adjunct_type") or "other",
            "is_periodic": bool(record.get("is_periodic", True)),
            "fiscal_year": fiscal_year,
            "fiscal_quarter": record.get("fiscal_quarter"),
            "source": "cninfo",
            "raw_payload": raw_payload_json,
        }

        stmt = pg_insert(CninfoReport).values(**values)
        excluded = stmt.excluded
        stmt = stmt.on_conflict_do_update(
            index_elements=["announcement_id"],
            set_={
                "extraction_status": excluded.extraction_status,
                "file_size": excluded.file_size,
                "updated_at": func.now(),
            },
        )
        try:
            self.db.execute(stmt)
            self.db.commit()
            return 1
        except Exception:
            # PG aborts the transaction on the first error; without this
            # rollback every subsequent insert is doomed with
            # ``InFailedSqlTransaction``.
            try:
                self.db.rollback()
            except Exception:  # pragma: no cover - defensive
                pass
            raise


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------


def _to_out(report: CninfoReport, name_map: dict[str, str | None] | None = None) -> dict[str, Any]:
    return {
        "id": report.id,
        "ts_code": report.ts_code,
        "stock_name": (name_map or {}).get(report.ts_code),
        "stock_code": report.stock_code,
        "org_id": report.org_id,
        "sec_code": report.sec_code,
        "announcement_id": report.announcement_id,
        "announcement_title": report.announcement_title,
        "adjunct_url": report.adjunct_url,
        "file_path": report.file_path,
        "file_size": report.file_size,
        "announcement_time": (
            report.announcement_time.isoformat()
            if report.announcement_time
            else None
        ),
        "adjunct_type": report.adjunct_type,
        "is_periodic": bool(report.is_periodic),
        "fiscal_year": report.fiscal_year,
        "fiscal_quarter": report.fiscal_quarter,
        "extraction_status": report.extraction_status,
        "extracted_at": report.extracted_at.isoformat() if report.extracted_at else None,
        "source": report.source,
        "created_at": report.created_at.isoformat() if report.created_at else None,
        "updated_at": report.updated_at.isoformat() if report.updated_at else None,
    }


def _to_detail(report: CninfoReport, name_map: dict[str, str | None] | None = None) -> dict[str, Any]:
    out = _to_out(report, name_map=name_map)
    # raw_payload is stored as TEXT (JSON string); parse for detail view.
    raw = None
    if report.raw_payload:
        import json as _json

        try:
            raw = _json.loads(report.raw_payload)
        except (TypeError, ValueError):
            raw = None
    out["raw_payload"] = raw
    out["extracted_text_preview"] = (
        (report.extracted_text or "")[:_PREVIEW_LEN]
        if report.extracted_text
        else None
    )
    return out