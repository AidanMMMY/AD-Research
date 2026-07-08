"""A-share on-exchange ETF top-10 holdings ETL pipeline.

Fetches the latest quarterly top-10 holdings for every active A-share ETF.
Sources are tried in priority order: Eastmoney fund F10 (primary) →
Tushare ``fund_portfolio`` bulk pull → cninfo quarterly/annual PDFs →
Akshare per-ETF fallback. The load
step is **upsert-only** — every snapshot is keyed on
``(etf_code, snapshot_date, holding_code)`` and earlier quarters are
preserved, so historical lookups via
``/etfs/{code}/holdings?date=YYYY-MM-DD`` always succeed once the data
has been written at least once.

The legacy ``holdings_as_of_date`` column is kept in sync with
``snapshot_date`` so API consumers that still reference the old field
keep working unchanged.
"""

import logging
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.data.pipelines.base import ETLPipeline, ETLResult
from app.data.providers import eastmoney_f10_provider
from app.data.providers.akshare_provider import AkshareProvider
from app.data.providers.cninfo_etf_holdings_provider import CninfoETFHoldingsProvider
from app.data.providers.tushare_provider import TushareProvider
from app.models.etf import ETFHolding, ETFHoldingFailed, ETFHoldingUnavailable, ETFInfo

logger = logging.getLogger(__name__)

# Fallback concurrency: per-ETF Akshare calls run in parallel because
# they are I/O-bound (HTTP) and a single ETF's request can be slow
# (Akshare times out for some funds). Keep the pool small — Akshare's
# upstream rate-limits aggressively.
_FALLBACK_WORKERS = 5

# Eastmoney F10 is the primary source and runs over the whole active-ETF
# universe, so it gets a slightly wider pool. Its endpoint is a plain
# static JSON feed with no aggressive per-IP throttling, unlike Akshare.
_EASTMONEY_WORKERS = 8

# Cninfo PDF fallback is I/O-bound (HTTP download + pdfplumber parse per
# ETF) and cninfo rate-limits at ~30 req/min, so we keep the worker
# count small to stay inside that budget.
_CNINFO_WORKERS = 3


class ETFHoldingsPipeline(ETLPipeline):
    """Collect top-10 A-share ETF holdings: Eastmoney F10 → Tushare (bulk) → cninfo PDF → Akshare."""

    job_name = "etf_holdings"

    def __init__(self, db: Session):
        super().__init__(provider=AkshareProvider(), db=db)

    def run(self) -> ETLResult:
        """Override base run() to skip OHLCV validation.

        Holdings are quarterly portfolio disclosures, not price bars, so
        the four-layer validator does not apply.
        """
        result = ETLResult()
        self._create_log()

        try:
            raw_df = self.extract()
            if raw_df.empty:
                result.warnings.append("Extract returned empty DataFrame")

            records = self.load(raw_df)
            result.records = records
            result.success = True
            self._update_log(status="success", records=records)
        except Exception as exc:
            error_msg = str(exc)
            result.success = False
            result.error = error_msg
            self._update_log(status="failed", error=error_msg)

        self.post_process()
        return result

    def extract(self) -> pd.DataFrame:
        """Fetch holdings for all active A-share ETFs.

        Phase 1 (primary): Eastmoney fund F10 is fetched for every
        active ETF in an 8-worker thread pool. It is the same 天天基金
        disclosure feed that covers the vast majority of equity ETFs.

        Phase 2: Tushare ``fund_portfolio`` bulk pull (paginated by
        ``period``/``offset``/``limit``) covers many of the remaining
        ETFs in a handful of API calls. Tushare does not support
        comma-separated ``ts_code`` lists, so pagination is used.

        Phase 3: cninfo quarterly/annual PDFs are parsed with
        pdfplumber for ETFs that Eastmoney and Tushare missed.

        Phase 4: Akshare per-ETF fallback in a 5-worker thread pool
        fills the remaining gaps.

        Phase 5: ETFs that still have no data are logged into
        ``etf_holding_failed`` so the next quarterly run can triage
        them.
        """
        etfs = (
            self.db.query(ETFInfo)
            .filter(
                ETFInfo.market == "A股",
                ETFInfo.instrument_type == "ETF",
                ETFInfo.status == "active",
            )
            .all()
        )
        etf_codes = [etf.code for etf in etfs]

        # Exclude structurally-unavailable ETFs (currency, physical gold,
        # etc.) from the bulk / fallback fetches. The blacklist is
        # curated in ``etf_holding_unavailable``; skipping them keeps
        # the Tushare / Akshare request slot for ETFs that actually
        # publish a top-10 list and prevents empty rows from dragging
        # the coverage KPI down.
        blacklisted_codes = {
            row.etf_code
            for row in self.db.query(ETFHoldingUnavailable.etf_code).all()
        }
        if blacklisted_codes:
            etf_codes = [c for c in etf_codes if c not in blacklisted_codes]
            logger.info(
                "[ETFHoldingsPipeline] Skipping %d blacklisted ETFs "
                "(structural: currency / gold / commodity).",
                len(blacklisted_codes),
            )

        all_frames: list[pd.DataFrame] = []
        akshare_provider = self.provider
        tushare_provider: TushareProvider | None = None
        today = pd.Timestamp.utcnow().normalize().date()

        def _stamp(df: pd.DataFrame, source: str) -> pd.DataFrame:
            """Attach ``source`` and a ``snapshot_date`` mirrored from
            ``holdings_as_of_date`` (falling back to today)."""
            df = df.copy()
            df["source"] = source
            if "snapshot_date" not in df.columns:
                df["snapshot_date"] = df.get("holdings_as_of_date")
            df["snapshot_date"] = df["snapshot_date"].fillna(today)
            return df

        # --- Phase 1: Eastmoney fund F10 (primary source) ---
        # Per-ETF quarterly disclosures fetched in a small thread pool.
        # This is the same 天天基金 feed Akshare wraps, but hit directly
        # with retries it is far more reliable from the ECS host and
        # covers the overwhelming majority of equity ETFs.
        eastmoney_frames = self._fetch_eastmoney(etf_codes)
        for _etf_code, df in eastmoney_frames.items():
            if df is None or df.empty:
                continue
            all_frames.append(_stamp(df, eastmoney_f10_provider.SOURCE))
        eastmoney_covered = set(eastmoney_frames.keys())
        pending_codes = [c for c in etf_codes if c not in eastmoney_covered]
        logger.info(
            "[ETFHoldingsPipeline] Eastmoney F10: %d/%d ETFs covered, "
            "%d remaining → Tushare/Akshare",
            len(eastmoney_covered), len(etf_codes), len(pending_codes),
        )

        # --- Phase 2: one bulk Tushare call (paginated) for the remainder ---
        bulk_mapping: dict[str, pd.DataFrame] = {}
        bulk_missing: list[str] = []
        bulk_error: str | None = None
        if pending_codes:
            try:
                if tushare_provider is None:
                    tushare_provider = TushareProvider()
                bulk_mapping, bulk_missing = tushare_provider.fetch_etf_holdings_batch(
                    ts_codes=pending_codes,
                )
            except Exception as exc:
                bulk_error = str(exc)
                logger.warning(
                    "[ETFHoldingsPipeline] Tushare bulk pull failed: %s", exc,
                )

        for _etf_code, df in bulk_mapping.items():
            if df is None or df.empty:
                continue
            all_frames.append(_stamp(df, "tushare"))

        if bulk_error is not None and not bulk_mapping:
            logger.info(
                "[ETFHoldingsPipeline] Bulk pull returned 0 rows (%s); "
                "falling back to per-ETF Akshare for %d ETFs.",
                bulk_error, len(pending_codes),
            )
            fallback_targets = pending_codes
        else:
            logger.info(
                "[ETFHoldingsPipeline] Tushare bulk pull: %d/%d remaining ETFs "
                "covered, %d missing → Akshare fallback",
                len(bulk_mapping), len(pending_codes), len(bulk_missing),
            )
            fallback_targets = bulk_missing

        # --- Phase 3: cninfo 季报 / 中报 PDF (mid-priority) ---
        # Trips the cninfo ``fulltextSearch`` + ``pdfplumber`` pipeline
        # for ETFs that Eastmoney / Tushare missed. This is the source
        # of truth for the 8/30 mid-year disclosure window — any ETF
        # that publishes a §7.3.1 table can be recovered here, even when
        # the Eastmoney F10 feed is lagging. SH-listed ETFs (51xxxx)
        # currently short-circuit to ``[]`` because cninfo's fulltext
        # index doesn't carry their filings (SSE-only path).
        if fallback_targets:
            cninfo_provider = CninfoETFHoldingsProvider()
            cninfo_frames = self._fetch_cninfo_pdf(cninfo_provider, fallback_targets)
            for _etf_code, df in cninfo_frames.items():
                if df is None or df.empty:
                    continue
                all_frames.append(_stamp(df, "cninfo"))
            # Recompute the still-missing set after the cninfo pass.
            cninfo_covered = set(cninfo_frames.keys())
            fallback_targets = [
                c for c in fallback_targets if c not in cninfo_covered
            ]

        # --- Phase 4: parallel Akshare fallback for the missing set ---
        if fallback_targets:
            fallback_frames = self._fetch_akshare_fallback(
                akshare_provider, fallback_targets,
            )
            for _etf_code, df in fallback_frames.items():
                if df is None or df.empty:
                    continue
                all_frames.append(_stamp(df, "akshare"))


        # --- Phase 5: log ETFs that still have no data ---
        covered = {f["etf_code"].iloc[0] for f in all_frames if not f.empty}
        failed_codes = [c for c in etf_codes if c not in covered]
        if failed_codes:
            self._record_holding_failures(failed_codes, note=bulk_error)

        if not all_frames:
            return pd.DataFrame()

        return pd.concat(all_frames, ignore_index=True)

    def _fetch_eastmoney(
        self, etf_codes: list[str],
    ) -> dict[str, pd.DataFrame]:
        """Fetch per-ETF holdings from Eastmoney fund F10 in a thread pool.

        Eastmoney has no bulk endpoint, so each ETF is one HTTP request.
        The feed is fast and lightly throttled, so an 8-worker pool clears
        the ~1 500-ETF universe in a couple of minutes. ETFs without any
        stock holdings (bond / gold / money-market funds) return ``None``
        and are simply left out of the mapping so the next source is tried.
        """
        results: dict[str, pd.DataFrame] = {}

        def _one(code: str) -> tuple[str, pd.DataFrame | None]:
            try:
                return code, eastmoney_f10_provider.fetch_etf_holdings(code)
            except Exception as exc:
                logger.warning(
                    "[ETFHoldingsPipeline] Eastmoney F10 for %s failed: %s",
                    code, exc,
                )
                return code, None

        with ThreadPoolExecutor(max_workers=_EASTMONEY_WORKERS) as pool:
            for code, df in pool.map(_one, etf_codes):
                if df is not None and not df.empty:
                    results[code] = df

        return results

    def _fetch_akshare_fallback(
        self, akshare_provider, etf_codes: list[str],
    ) -> dict[str, pd.DataFrame]:
        """Fetch per-ETF holdings from Akshare in a small thread pool.

        Akshare is slow (some funds time out at 30 s) but its per-ETF
        endpoint is what backs the bulk pull's gaps. 5 workers is
        conservative — Akshare's upstream rate-limits aggressively,
        and the fallback set is typically 0-200 ETFs.
        """
        results: dict[str, pd.DataFrame] = {}

        def _one(code: str) -> tuple[str, pd.DataFrame]:
            try:
                df = akshare_provider.fetch_etf_holdings(code)
            except Exception as exc:
                logger.warning(
                    "[ETFHoldingsPipeline] Akshare fallback for %s failed: %s",
                    code, exc,
                )
                return code, pd.DataFrame()
            return code, df if df is not None else pd.DataFrame()

        with ThreadPoolExecutor(max_workers=_FALLBACK_WORKERS) as pool:
            for code, df in pool.map(_one, etf_codes):
                if df is not None and not df.empty:
                    results[code] = df

        return results

    def _fetch_cninfo_pdf(
        self, cninfo_provider: CninfoETFHoldingsProvider, etf_codes: list[str],
    ) -> dict[str, pd.DataFrame]:
        """Fetch per-ETF holdings from cninfo's periodic-report PDFs.

        This is the Phase 3 fallback. Each call walks the cninfo
        ``fulltextSearch`` index for the latest ``<period>报告``
        announcement, downloads the PDF, and parses the §7.3.1 table
        with pdfplumber. The provider self-throttles at ~1.5s/call;
        the thread-pool cap keeps a single hung download from
        starving the rest.
        """
        results: dict[str, pd.DataFrame] = {}

        def _one(code: str) -> tuple[str, pd.DataFrame]:
            try:
                df = cninfo_provider.fetch_etf_holdings(code)
            except Exception as exc:
                logger.warning(
                    "[ETFHoldingsPipeline] Cninfo PDF for %s failed: %s",
                    code, exc,
                )
                return code, pd.DataFrame()
            return code, df if df is not None else pd.DataFrame()

        with ThreadPoolExecutor(max_workers=_CNINFO_WORKERS) as pool:
            for code, df in pool.map(_one, etf_codes):
                if df is not None and not df.empty:
                    results[code] = df

        return results

    def _record_holding_failures(
        self, failed_codes: list[str], note: str | None = None,
    ) -> None:
        """Upsert failed-ETF rows into ``etf_holding_failed``.

        Each row is incremented via ``retry_count`` so the operator
        can spot ETFs that consistently fail across quarterly
        windows. We swallow exceptions here — failure logging must
        not crash the ETL.
        """
        if not failed_codes:
            return
        try:
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc)
            # Try to bump retry_count where the row already exists;
            # otherwise insert a fresh row. Done in two statements
            # because SQLite/Postgres UPSERT semantics differ.
            existing = {
                row.etf_code: row
                for row in self.db.query(ETFHoldingFailed)
                .filter(ETFHoldingFailed.etf_code.in_(failed_codes))
                .all()
            }
            payload_insert: list[dict] = []
            for code in failed_codes:
                if code in existing:
                    row = existing[code]
                    row.retry_count = (row.retry_count or 0) + 1
                    row.last_error = note or row.last_error
                    row.last_attempt_at = now
                else:
                    payload_insert.append({
                        "etf_code": code,
                        "last_error": note,
                        "retry_count": 1,
                        "last_attempt_at": now,
                    })
            if payload_insert:
                self.db.bulk_insert_mappings(ETFHoldingFailed, payload_insert)
            self.db.commit()
            logger.info(
                "[ETFHoldingsPipeline] Logged %d failed ETFs "
                "(%d new, %d retry).",
                len(failed_codes),
                len(payload_insert),
                len(failed_codes) - len(payload_insert),
            )
        except Exception as exc:
            self.db.rollback()
            logger.warning(
                "[ETFHoldingsPipeline] Failed to log etf_holding_failed rows: %s",
                exc,
            )

    def load(self, df: pd.DataFrame) -> int:
        """Upsert holdings keyed on ``(etf_code, snapshot_date, holding_code)``.

        The previous implementation deleted existing rows per snapshot
        before re-inserting — that wiped the entire history every time
        the ETL ran. The new implementation does a true upsert: rows
        matching the identity are updated in place, new rows are
        inserted, and historical snapshots from prior quarters are
        left untouched.

        Both ``snapshot_date`` (the new upsert identity) and the
        legacy ``holdings_as_of_date`` column are populated from the
        same source value so consumers reading either column see the
        same date.
        """
        if df is None or df.empty:
            return 0

        required_cols = {"etf_code", "holding_code", "snapshot_date"}
        if not required_cols.issubset(df.columns):
            missing = required_cols - set(df.columns)
            raise ValueError(f"Missing required columns: {missing}")

        # Build the upsert payload. ``snapshot_date`` is also mirrored
        # to ``holdings_as_of_date`` for backwards compatibility.
        records: list[dict] = []
        for _, row in df.iterrows():
            snapshot = row["snapshot_date"]
            if hasattr(snapshot, "date"):
                snapshot = snapshot.date()
            elif isinstance(snapshot, str):
                # Defensive parse — providers should already return
                # date objects but tolerate ISO strings.
                snapshot = pd.to_datetime(snapshot).date()

            source_val = row.get("source")
            records.append(
                {
                    "etf_code": str(row["etf_code"]),
                    "holding_code": str(row["holding_code"]),
                    "holding_name": str(row["holding_name"])
                    if pd.notna(row.get("holding_name"))
                    else None,
                    "weight": float(row["weight"])
                    if pd.notna(row.get("weight"))
                    else None,
                    "shares": float(row["shares"])
                    if pd.notna(row.get("shares"))
                    else None,
                    "market_value": float(row["market_value"])
                    if pd.notna(row.get("market_value"))
                    else None,
                    "holdings_as_of_date": snapshot,
                    "snapshot_date": snapshot,
                    "source": str(source_val)
                    if pd.notna(source_val)
                    else None,
                }
            )

        if not records:
            return 0

        # PostgreSQL native ``INSERT ... ON CONFLICT DO UPDATE`` —
        # the underlying database is Postgres on the ECS host, so
        # this is the right primitive for the upsert identity. We
        # key on the new unique constraint
        # ``uq_etf_holding_snapshot_code (etf_code, snapshot_date,
        # holding_code)``.
        table = ETFHolding.__table__
        stmt = pg_insert(table).values(records)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_etf_holding_snapshot_code",
            set_={
                "holding_name": stmt.excluded.holding_name,
                "weight": stmt.excluded.weight,
                "shares": stmt.excluded.shares,
                "market_value": stmt.excluded.market_value,
                "holdings_as_of_date": stmt.excluded.holdings_as_of_date,
                "source": stmt.excluded.source,
            },
        )
        try:
            self.db.execute(stmt)
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

        return len(records)

    def post_process(self) -> None:
        """Log summary after load."""
        if self._log is None:
            return
        print(
            f"[ETFHoldingsPipeline] {self._log.records_count} holdings rows upserted"
        )
