"""A-share on-exchange ETF top-10 holdings ETL pipeline.

Fetches the latest quarterly top-10 holdings for every active A-share ETF
from Tushare ``fund_portfolio`` (primary) and falls back to Akshare when
Tushare has no data. The load step is **upsert-only** — every snapshot
is keyed on ``(etf_code, snapshot_date, holding_code)`` and earlier
quarters are preserved, so historical lookups via
``/etfs/{code}/holdings?date=YYYY-MM-DD`` always succeed once the data
has been written at least once.

The legacy ``holdings_as_of_date`` column is kept in sync with
``snapshot_date`` so API consumers that still reference the old field
keep working unchanged.
"""

import pandas as pd
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.data.pipelines.base import ETLPipeline, ETLResult
from app.data.providers.akshare_provider import AkshareProvider
from app.data.providers.tushare_provider import TushareProvider
from app.models.etf import ETFHolding, ETFInfo


class ETFHoldingsPipeline(ETLPipeline):
    """Collect top-10 A-share ETF holdings from Akshare / Tushare."""

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

        Uses Tushare as the primary source because Akshare's ETF holding
        endpoint times out frequently from the ECS host. Falls back to
        Akshare only when Tushare has no data for an ETF.

        Each row is stamped with a ``snapshot_date`` — for now we reuse
        ``holdings_as_of_date`` (the quarter-end date returned by the
        providers) so the upsert identity is the actual disclosure
        date rather than "today". If a provider ever returns no
        ``holdings_as_of_date`` we fall back to the current date so
        the row still has a usable snapshot identity.
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

        all_frames: list[pd.DataFrame] = []
        akshare_provider = self.provider
        tushare_provider: TushareProvider | None = None
        tushare_unavailable = False
        today = pd.Timestamp.utcnow().normalize().date()

        for etf in etfs:
            df: pd.DataFrame | None = None
            source = "tushare"

            if not tushare_unavailable:
                try:
                    if tushare_provider is None:
                        tushare_provider = TushareProvider()
                    df = tushare_provider.fetch_etf_holdings(ts_code=etf.code)
                except Exception as exc:
                    tushare_unavailable = True
                    print(
                        f"[ETFHoldingsPipeline] Tushare primary unavailable: {exc}"
                    )

            if df is None or df.empty:
                df = akshare_provider.fetch_etf_holdings(etf.code)
                source = "akshare"

            if df is None or df.empty:
                print(f"[ETFHoldingsPipeline] No holdings for {etf.code}")
                continue

            df = df.copy()
            df["source"] = source

            # Ensure every row has a snapshot_date. Providers already
            # populate ``holdings_as_of_date`` (= quarter-end); mirror
            # it into ``snapshot_date`` so the upsert identity matches.
            if "snapshot_date" not in df.columns:
                df["snapshot_date"] = df.get("holdings_as_of_date")
            df["snapshot_date"] = df["snapshot_date"].fillna(today)

            all_frames.append(df)

        if not all_frames:
            return pd.DataFrame()

        return pd.concat(all_frames, ignore_index=True)

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
