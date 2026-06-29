"""ETF metadata enrichment pipeline.

Fills missing ETF product metadata (manager, category, underlying index,
fund size, inception_date, list_date) from Tushare ``fund_basic()``.
Designed to run weekly alongside the ETF market scan.
"""

from datetime import datetime

import pandas as pd
from sqlalchemy.dialects.postgresql import insert

from app.core.exceptions import DataProviderError
from app.data.pipelines.base import ETLPipeline
from app.data.providers.tushare_provider import TushareProvider
from app.models.etf import ETFInfo


class ETFMetadataEnrichmentPipeline(ETLPipeline):
    """Enrich A-share ETF metadata from Tushare fund_basic."""

    @property
    def job_name(self) -> str:
        return "etf_metadata_enrichment"

    def __init__(self, db):
        super().__init__(provider=TushareProvider(), db=db)

    def extract(self) -> pd.DataFrame:
        """Fetch ETF metadata from Tushare."""
        return self.provider.fetch_etf_metadata()

    def load(self, df: pd.DataFrame) -> int:
        """Update ETFInfo rows with fetched metadata.

        Only overwrites fields that are currently empty or that come from
        the enrichment source, preserving manually-curated values where
        present.
        """
        if df is None or df.empty:
            return 0

        updated = 0
        field_map = {
            "name": "name",
            "manager": "manager",
            "category": "category",
            "sub_category": "sub_category",
            "underlying_index": "underlying_index",
            "inception_date": "inception_date",
            "list_date": "list_date",
            "fund_size": "fund_size",
        }

        for _, row in df.iterrows():
            code = row.get("code")
            if not code:
                continue

            info = self.db.query(ETFInfo).filter(ETFInfo.code == code).first()
            if info is None:
                # Only update existing ETFs; discovery is handled elsewhere
                continue

            changed = False
            for src_col, dst_attr in field_map.items():
                value = row.get(src_col)
                if value is None or pd.isna(value):
                    continue
                current = getattr(info, dst_attr, None)
                if current is None or current == "":
                    setattr(info, dst_attr, value)
                    changed = True

            if changed:
                updated += 1

        self.db.commit()
        return updated

    def post_process(self, result) -> None:
        """Log summary after load."""
        print(
            f"[ETFMetadataEnrichmentPipeline] Updated {result.records} ETFInfo rows"
        )
