"""A-share on-exchange ETF top-10 holdings ETL pipeline.

Fetches the latest quarterly top-10 holdings for every active A-share ETF
from Akshare (primary) and falls back to Tushare ``fund_portfolio`` when
Akshare has no data. The load step is idempotent per (etf_code,
holdings_as_of_date): existing rows for that snapshot are deleted before
new rows are inserted so re-runs do not duplicate holdings.
"""

import pandas as pd
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
        """Fetch holdings for all active A-share ETFs."""
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
        tushare_provider: TushareProvider | None = None
        tushare_unavailable = False

        for etf in etfs:
            df = self.provider.fetch_etf_holdings(etf.code)
            source = "akshare"

            if df is None or df.empty and not tushare_unavailable:
                try:
                    if tushare_provider is None:
                        tushare_provider = TushareProvider()
                    df = tushare_provider.fetch_etf_holdings(ts_code=etf.code)
                    source = "tushare"
                except Exception as exc:
                    tushare_unavailable = True
                    print(
                        f"[ETFHoldingsPipeline] Tushare fallback unavailable: {exc}"
                    )

            if df is None or df.empty:
                print(f"[ETFHoldingsPipeline] No holdings for {etf.code}")
                continue

            df = df.copy()
            df["source"] = source
            all_frames.append(df)

        if not all_frames:
            return pd.DataFrame()

        return pd.concat(all_frames, ignore_index=True)

    def load(self, df: pd.DataFrame) -> int:
        """Persist holdings, replacing existing snapshots per (code, date)."""
        if df is None or df.empty:
            return 0

        required_cols = {"etf_code", "holding_code", "holdings_as_of_date"}
        if not required_cols.issubset(df.columns):
            missing = required_cols - set(df.columns)
            raise ValueError(f"Missing required columns: {missing}")

        total_inserted = 0
        grouped = df.groupby(["etf_code", "holdings_as_of_date"])

        for (etf_code, as_of_date), group in grouped:
            self.db.query(ETFHolding).filter(
                ETFHolding.etf_code == etf_code,
                ETFHolding.holdings_as_of_date == as_of_date,
            ).delete(synchronize_session=False)

            for _, row in group.iterrows():
                holding = ETFHolding(
                    etf_code=str(row["etf_code"]),
                    holding_code=str(row["holding_code"]),
                    holding_name=str(row["holding_name"])
                    if pd.notna(row.get("holding_name"))
                    else None,
                    weight=float(row["weight"])
                    if pd.notna(row.get("weight"))
                    else None,
                    shares=float(row["shares"])
                    if pd.notna(row.get("shares"))
                    else None,
                    market_value=float(row["market_value"])
                    if pd.notna(row.get("market_value"))
                    else None,
                    holdings_as_of_date=as_of_date,
                    source=str(row["source"]) if pd.notna(row.get("source")) else None,
                )
                self.db.add(holding)
                total_inserted += 1

        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

        return total_inserted

    def post_process(self) -> None:
        """Log summary after load."""
        if self._log is None:
            return
        print(
            f"[ETFHoldingsPipeline] {self._log.records_count} holdings rows inserted"
        )
