"""ETL Pipeline abstract base class.

Provides the standard Extract-Transform-Load flow with logging,
validation, and retry logic for all data ingestion pipelines.
"""

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime

import pandas as pd
from sqlalchemy.orm import Session

from app.data.providers.base import DataProvider
from app.data.transformers.normalizer import normalize
from app.data.transformers.validator import validate_all, CHANGE_PCT_THRESHOLDS
from app.models.etl import ETLLog


# Map data provider names to the market they represent, used for market-specific
# validation thresholds.
_PROVIDER_MARKET_MAP = {
    "akshare": "A股",
    "tushare": "A股",
    "fmp": "US",
    "yfinance": "US",
    "tiingo": "US",
    "finnhub": "US",
    "binance": "CRYPTO",
}


@dataclass
class ETLResult:
    """Result of an ETL pipeline run."""

    success: bool = False
    records: int = 0
    error: str | None = None
    warnings: list[str] = field(default_factory=list)


class ETLPipeline(ABC):
    """Abstract base class for ETL pipelines.

    Subclasses must implement:
      - ``job_name`` property
      - ``extract()`` method
      - ``load()`` method

    The ``run()`` method orchestrates the full ETL flow:
    extract -> normalize -> validate -> load -> post_process.
    """

    def __init__(self, provider: DataProvider, db: Session) -> None:
        self.provider = provider
        self.db = db
        self._log: ETLLog | None = None
        self._expected_codes: list[str] | None = None

    @property
    @abstractmethod
    def job_name(self) -> str:
        """Return the unique name of this ETL job."""
        ...

    def _create_log(self) -> ETLLog:
        """Create a new ETLLog record with status 'running'."""
        log = ETLLog(
            job_name=self.job_name,
            source=self.provider.name,
            status="running",
            start_time=datetime.now(),
        )
        self.db.add(log)
        self.db.commit()
        self.db.refresh(log)
        self._log = log
        return log

    def _update_log(
        self,
        status: str,
        records: int = 0,
        error: str | None = None,
    ) -> None:
        """Update the current ETLLog record."""
        if self._log is None:
            return
        self._log.status = status
        self._log.end_time = datetime.now()
        self._log.records_count = records
        if error:
            self._log.error_msg = error
        self.db.commit()

    @abstractmethod
    def extract(self) -> pd.DataFrame:
        """Extract raw data and return a DataFrame.

        Must be implemented by subclasses.
        """
        ...

    @abstractmethod
    def load(self, data: pd.DataFrame) -> int:
        """Load validated data into the database.

        Must be implemented by subclasses.  Returns the number of
        records written.
        """
        ...

    def post_process(self) -> None:  # noqa: B027
        """Optional post-load hook (e.g. refresh materialized views).

        Subclasses may override this method. It is intentionally a no-op
        rather than abstract because overriding is optional.
        """
        ...

    def run(self) -> ETLResult:
        """Execute the full ETL pipeline.

        Steps:
        1. Create ETLLog (status=running)
        2. extract() raw data
        3. normalize() column names and types
        4. validate_all() four-layer validation
        5. load() into database
        6. post_process()
        7. Update ETLLog (status=success/failed)

        Returns an ETLResult summarising the outcome.
        """
        result = ETLResult()
        self._create_log()

        try:
            # 1. Extract
            raw_df = self.extract()
            if raw_df.empty:
                result.warnings.append("Extract returned empty DataFrame")

            # 2. Normalize
            normalized_df = normalize(raw_df)

            # 3. Validate
            market = _PROVIDER_MARKET_MAP.get(self.provider.name)
            validation = validate_all(
                normalized_df,
                expected_codes=self._expected_codes,
                market=market,
            )
            result.warnings.extend(validation.warnings)
            if not validation.is_valid:
                raise ValueError(f"Validation failed: {'; '.join(validation.errors)}")

            # 4. Load
            records = self.load(normalized_df)
            result.records = records

            # 5. Post-process
            self.post_process()

            # 6. Success
            result.success = True
            self._update_log(status="success", records=records)

        except Exception as exc:
            error_msg = str(exc)
            result.success = False
            result.error = error_msg
            self._update_log(status="failed", error=error_msg)

        return result

    def run_with_retry(self, max_attempts: int = 3) -> ETLResult:
        """Run the ETL pipeline with exponential backoff retry.

        Retry delays: 30s, 60s, 120s, ...
        """
        delays = [30 * (2 ** i) for i in range(max_attempts)]

        for attempt in range(max_attempts):
            result = self.run()
            if result.success:
                return result

            if attempt < max_attempts - 1:
                sleep_seconds = delays[attempt]
                print(
                    f"[ETL Retry] {self.job_name} attempt {attempt + 1} failed. "
                    f"Retrying in {sleep_seconds}s..."
                )
                time.sleep(sleep_seconds)

        return result
