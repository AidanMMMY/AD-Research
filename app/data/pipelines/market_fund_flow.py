"""大盘资金流 ETL Pipeline。

持久化 ``ak.stock_market_fund_flow`` 返回的沪深 A 股整体资金流，并按
``individual_fund_flow`` 后缀聚合出沪市/深市净流入，用于前端大盘卡片。
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from app.data.pipelines.base import ETLPipeline, ETLResult
from app.data.providers.akshare_provider import AkshareProvider
from app.data.providers.fund_flow_provider import FundFlowProvider
from app.models.fund_flow import IndividualFundFlow, MarketFundFlow

logger = logging.getLogger(__name__)


class MarketFundFlowPipeline(ETLPipeline):
    """大盘资金流 Pipeline：从 akshare 拉整体市场数据，并派生 SH/SZ 口径。"""

    job_name = "market_fund_flow_daily"

    def __init__(
        self,
        db: Any,
        target_date: date | None = None,
        lookback_days: int = 0,
        dry_run: bool = False,
    ) -> None:
        super().__init__(provider=AkshareProvider(), db=db)
        self.target_date = target_date or date.today()
        self.lookback_days = lookback_days
        self.dry_run = dry_run
        self._ff_provider = FundFlowProvider()

    def extract(self) -> pd.DataFrame:  # pragma: no cover - unused
        raise NotImplementedError(
            "MarketFundFlowPipeline uses run() override"
        )

    def load(self, data: pd.DataFrame) -> int:  # pragma: no cover - unused
        raise NotImplementedError(
            "MarketFundFlowPipeline uses run() override"
        )

    def run(self) -> ETLResult:
        """Run market fund-flow ETL: ALL from akshare + SH/SZ derived."""
        result = ETLResult()
        self._create_log()

        try:
            raw_rows = self._ff_provider.fetch_market_fund_flow(days=120)
            if not raw_rows:
                msg = "fetch_market_fund_flow returned empty; nothing to upsert"
                result.warnings.append(msg)
                result.success = True
                self._update_log(status="partial", records=0, error=msg)
                return result

            start = self.target_date - timedelta(days=self.lookback_days)
            target_dates = {
                r["trade_date"]
                for r in raw_rows
                if isinstance(r.get("trade_date"), date)
                and start <= r["trade_date"] <= self.target_date
            }
            if not target_dates:
                msg = f"No market flow data between {start} and {self.target_date}"
                result.warnings.append(msg)
                result.success = True
                self._update_log(status="partial", records=0, error=msg)
                return result

            all_records, market_meta = self._build_all_records(raw_rows, target_dates)
            derived_records = self._derive_sh_sz_records(target_dates, market_meta)

            written_all = self._upsert_market(all_records)
            written_derived = self._upsert_market(derived_records)
            total = written_all + written_derived

            if self.dry_run:
                self.db.rollback()
            else:
                self.db.commit()

            result.records = total
            result.success = True
            self._update_log(status="success", records=total)
            logger.info(
                "MarketFundFlowPipeline: upserted %d rows (all=%d, derived=%d)",
                total,
                written_all,
                written_derived,
            )
        except Exception as exc:
            error_msg = str(exc)
            result.success = False
            result.error = error_msg
            try:
                self._update_log(status="failed", error=error_msg)
            except Exception:  # noqa: BLE001
                pass
            logger.exception("MarketFundFlowPipeline failed: %s", exc)
            try:
                self.db.rollback()
            except Exception:  # noqa: BLE001
                pass

        return result

    def _build_all_records(
        self,
        raw_rows: list[dict[str, Any]],
        target_dates: set[date],
    ) -> tuple[list[dict[str, Any]], dict[date, dict[str, Any]]]:
        """从 akshare 原始行构建 ``market='ALL'`` 记录，并返回每个日期的指数元数据。"""
        all_records: list[dict[str, Any]] = []
        market_meta: dict[date, dict[str, Any]] = {}
        for r in raw_rows:
            td = r.get("trade_date")
            if not isinstance(td, date) or td not in target_dates:
                continue
            market_meta[td] = {
                "sh_close": r.get("sh_close"),
                "sh_pct_change": r.get("sh_pct_change"),
                "sz_close": r.get("sz_close"),
                "sz_pct_change": r.get("sz_pct_change"),
            }
            all_records.append({
                "trade_date": td,
                "market": "ALL",
                "close_price": None,
                "pct_change": None,
                "main_net_inflow": r.get("main_net_inflow"),
                "main_net_pct": r.get("main_net_pct"),
                "super_large_net": r.get("super_large_net"),
                "large_net": r.get("large_net"),
                "medium_net": r.get("medium_net"),
                "small_net": r.get("small_net"),
                "total_amount": None,
                "source": "akshare",
            })
        return all_records, market_meta

    def _derive_sh_sz_records(
        self,
        target_dates: set[date],
        market_meta: dict[date, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """按 ``individual_fund_flow`` 后缀聚合沪市/深市净流入。"""
        records: list[dict[str, Any]] = []
        for td in sorted(target_dates):
            meta = market_meta.get(td, {})
            for suffix, market in ((".SH", "SH"), (".SZ", "SZ")):
                sums = self._aggregate_individual(td, suffix)
                if not sums:
                    continue
                records.append({
                    "trade_date": td,
                    "market": market,
                    "close_price": meta.get(f"{market.lower()}_close"),
                    "pct_change": meta.get(f"{market.lower()}_pct_change"),
                    "main_net_inflow": sums.get("main_net_inflow"),
                    "main_net_pct": None,
                    "super_large_net": sums.get("super_large_net"),
                    "large_net": sums.get("large_net"),
                    "medium_net": sums.get("medium_net"),
                    "small_net": sums.get("small_net"),
                    "total_amount": None,
                    "source": "derived",
                })
        return records

    def _aggregate_individual(
        self, trade_date: date, suffix: str
    ) -> dict[str, Any] | None:
        """Aggregate individual_fund_flow by ts_code suffix for a single date."""
        stmt = (
            select(
                func.coalesce(
                    func.sum(IndividualFundFlow.main_net_inflow), 0
                ).label("main_net_inflow"),
                func.coalesce(
                    func.sum(IndividualFundFlow.super_large_net), 0
                ).label("super_large_net"),
                func.coalesce(
                    func.sum(IndividualFundFlow.large_net), 0
                ).label("large_net"),
                func.coalesce(
                    func.sum(IndividualFundFlow.medium_net), 0
                ).label("medium_net"),
                func.coalesce(
                    func.sum(IndividualFundFlow.small_net), 0
                ).label("small_net"),
            )
            .where(IndividualFundFlow.trade_date == trade_date)
            .where(IndividualFundFlow.ts_code.endswith(suffix))
        )
        row = self.db.execute(stmt).one_or_none()
        if row is None:
            return None
        out: dict[str, Any] = {}
        for col in (
            "main_net_inflow",
            "super_large_net",
            "large_net",
            "medium_net",
            "small_net",
        ):
            value = getattr(row, col)
            out[col] = float(value) if value is not None else None
        if all(v is None or v == 0 for v in out.values()):
            return None
        return out

    def _upsert_market(self, records: list[dict[str, Any]]) -> int:
        """幂等 upsert ``market_fund_flow`` (唯一键 ``trade_date + market``)。"""
        if not records:
            return 0

        columns = {
            "trade_date",
            "market",
            "close_price",
            "pct_change",
            "main_net_inflow",
            "main_net_pct",
            "super_large_net",
            "large_net",
            "medium_net",
            "small_net",
            "total_amount",
            "source",
        }
        normalized = [{c: r.get(c) for c in columns} for r in records]

        stmt = insert(MarketFundFlow).values(normalized)
        excluded = insert(MarketFundFlow).excluded
        stmt = stmt.on_conflict_do_update(
            index_elements=["trade_date", "market"],
            set_={
                "close_price": excluded.close_price,
                "pct_change": excluded.pct_change,
                "main_net_inflow": excluded.main_net_inflow,
                "main_net_pct": excluded.main_net_pct,
                "super_large_net": excluded.super_large_net,
                "large_net": excluded.large_net,
                "medium_net": excluded.medium_net,
                "small_net": excluded.small_net,
                "total_amount": excluded.total_amount,
                "source": excluded.source,
            },
        )
        self.db.execute(stmt)
        return len(records)
