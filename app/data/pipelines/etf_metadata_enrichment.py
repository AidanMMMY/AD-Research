"""ETF metadata enrichment & discovery pipeline.

Fills missing ETF product metadata (manager, category, underlying index,
fund size, inception_date, list_date) from Tushare ``fund_basic()``, AND
upserts newly-discovered A-share ETFs that are not yet in ``etf_info``.

Behaviour change (B12 fix, 2026-07-04):
  * Previously this pipeline only updated existing rows. New ETFs were
    only added by the akshare-based ETF scanner, which has no
    ``fund_type`` mapping and therefore cannot populate ``category``.
  * Now we upsert: insert new rows with the Tushare-sourced metadata,
    and update existing rows in a non-destructive way (only fill NULL /
    empty fields, never overwrite a real value with NULL).

Designed to run weekly alongside the ETF market scan.
"""

import pandas as pd
from sqlalchemy.orm import Session

from app.data.pipelines.base import ETLPipeline
from app.data.providers.tushare_provider import TushareProvider
from app.models.etf import ETFInfo


class ETFMetadataEnrichmentPipeline(ETLPipeline):
    """Enrich / upsert A-share ETF metadata from Tushare fund_basic."""

    @property
    def job_name(self) -> str:
        return "etf_metadata_enrichment"

    def __init__(self, db: Session):
        super().__init__(provider=TushareProvider(), db=db)

    def extract(self) -> pd.DataFrame:
        """Fetch ETF metadata from Tushare."""
        return self.provider.fetch_etf_metadata()

    def run(self):
        """Override base run() to skip OHLCV validation.

        Discovery / enrichment operates on instrument metadata, not
        price bars, so the four-layer validator does not apply.
        """
        from app.data.pipelines.base import ETLResult

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

    def load(self, df: pd.DataFrame) -> int:
        """Upsert ETFInfo rows with fetched metadata.

        For each row in the Tushare dataframe:
          * If the ETF is already in the DB, fill in NULL/empty fields
            with non-NULL Tushare values. Never overwrite a real value
            with NULL.
          * If the ETF is not in the DB, insert it with the Tushare
            metadata as the source of truth for ``category``, ``name``,
            ``manager``, ``underlying_index``, dates, and ``fund_size``.

        Returns the number of rows touched (inserted + updated).
        """
        if df is None or df.empty:
            return 0

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

        # Pre-load all relevant rows in one query to minimize round-trips.
        codes = {
            str(c)
            for c in df["code"].tolist()
            if c and not pd.isna(c)
        }
        if not codes:
            return 0

        existing_rows = (
            self.db.query(ETFInfo).filter(ETFInfo.code.in_(codes)).all()
        )
        existing_map = {row.code: row for row in existing_rows}

        inserted = 0
        updated = 0

        for _, row in df.iterrows():
            code = row.get("code")
            if not code or pd.isna(code):
                continue
            code = str(code)

            info = existing_map.get(code)
            if info is None:
                # New ETF — insert a row using Tushare as source of truth
                kwargs: dict = {
                    "code": code,
                    "market": "A股",
                    "instrument_type": "ETF",
                    "currency": "CNY",
                    "status": "active",
                }
                # Always copy name + exchange + market from the Tushare row.
                raw_name = row.get("name")
                if raw_name is not None and not pd.isna(raw_name) and str(raw_name):
                    kwargs["name"] = str(raw_name)
                else:
                    # Skip — a primary key without a name is unusable.
                    continue

                # Derive exchange from code suffix (e.g. 510050.SH -> SH)
                if code.endswith(".SH"):
                    kwargs["exchange"] = "SH"
                elif code.endswith(".SZ"):
                    kwargs["exchange"] = "SZ"
                elif code.endswith(".BJ"):
                    kwargs["exchange"] = "BJ"

                for src_col, dst_attr in field_map.items():
                    if src_col == "name":
                        continue  # handled above
                    value = row.get(src_col)
                    if value is None or pd.isna(value):
                        continue
                    if dst_attr in ("inception_date", "list_date"):
                        # pd.to_datetime may yield Timestamp/date/NaT
                        if hasattr(value, "date"):
                            kwargs[dst_attr] = value
                        else:
                            continue
                    else:
                        kwargs[dst_attr] = value

                self.db.add(ETFInfo(**kwargs))
                inserted += 1
                continue

            # Existing row — fill in NULL/empty fields only.
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

        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

        return inserted + updated

    def post_process(self) -> None:  # type: ignore[override]
        """Log summary after load (kept for backwards-compat signature).

        ``result`` is also available via ``self._log.records_count`` for
        callers that want a structured view.
        """
        if self._log is None:
            return
        print(
            f"[ETFMetadataEnrichmentPipeline] {self._log.records_count} rows touched"
        )
