"""申万一级行业指数回报 pipeline (Phase 3 sector rotation 数据源).

数据流
------
1. AKShare ``ak.index_hist_sw(symbol="801xxx")`` 一次取一个 SW2021
   一级指数的全历史日线 (数千行)。
2. 本地按交易日升序排序，计算 1w / 1m / 3m / 6m / 1y 回报 (5/21/63/
   126/252 交易日窗口，与 ``ETFIndicator`` 现有 return_* 一致)。
3. UPSERT 到 ``sw_industry_index_return`` 表 (pk=sw_l1_code+trade_date)。

调用方
------
* Celery task ``app.tasks.sw_industry.refresh_sw_industry_returns``
  (queue="industry")，每周一上午 09:30 调度一次。
* 手动触发 ``python -m app.data.pipelines.sw_industry_index``。

为什么不用 Tushare
------------------
Tushare ``index_classify(level="L1", src="SW")`` 在我们这个套餐下返
回 0 行 (实测 2026-07-19)。AKShare 免费、稳定，且行业指数命名与项目
``etf_info.sw_l1`` SW2021 名称一一对齐。

为什么不用 ETLPipeline 基类
---------------------------
``ETLPipeline`` 要求实现 ``extract() -> DataFrame`` / ``load()``
两个抽象方法，但本 pipeline 一次跑 31 个 industry，循环内部各自
fetch + upsert（不是「拉一张大表 → 全量 load」），自定义 run 更清晰。
仍直接复用 ``ETLLog`` 写执行日志，便于 ``etl_log`` 表统一监控。
"""

import logging
from datetime import date, datetime, timezone

import pandas as pd
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.data.providers.akshare_provider import AkshareProvider
from app.models.etl import ETLLog
from app.models.sw_industry_index import SWIndustryIndexReturn

logger = logging.getLogger(__name__)


# 申万一级行业回报窗口（交易日数），与 ETFIndicator 现有口径一致。
_LOOKBACK_TRADING_DAYS = {
    "return_1w": 5,
    "return_1m": 21,
    "return_3m": 63,
    "return_6m": 126,
    "return_1y": 252,
}


# ----- 简易 ETLResult，等价 base.ETLResult 但字段名不冲突 ----------
class _Phase3Result:
    def __init__(self) -> None:
        self.records_processed: int = 0
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.metadata: dict = {}


def _load_sw_codes_from_db(db: Session) -> list[str]:
    """从 etf_info.sw_l1_code 拉所有 distinct 的 SW 一级行业代码。

    这样新增/删除行业时无需改代码；etf_info.sw_l1_code 是上一步
    backfill_a_share_sw 写的，权威性高。
    """
    rows = db.execute(
        text(
            """
            SELECT DISTINCT sw_l1_code
              FROM etf_info
             WHERE market = 'A股'
               AND sw_l1_code IS NOT NULL
             ORDER BY sw_l1_code
            """
        )
    ).all()
    return [r[0] for r in rows if r[0]]


def _rolling_returns(close_series: pd.Series) -> list[dict[str, float | None]]:
    """为序列中每个点计算「截至该日的滚动回报」。

    返回长度与 ``close_series`` 相同的 list；早期点窗口不足时
    相应字段为 ``None``。sector_rotation_service 通过查
    ``(sw_l1_code, trade_date)`` 直接拿历史回报，不必重新计算。
    """
    if close_series.empty:
        return []

    arr = close_series.to_numpy(dtype=float)
    n = len(arr)
    out: list[dict[str, float | None]] = []
    for i in range(n):
        latest = arr[i]
        row: dict[str, float | None] = {}
        for col, window in _LOOKBACK_TRADING_DAYS.items():
            if i >= window:
                past = arr[i - window]
                row[col] = (latest / past) - 1.0 if past else None
            else:
                row[col] = None
        out.append(row)
    return out


class SWIndustryIndexPipeline:
    """Phase 3 pipeline: 拉 31 个 SW2021 一级行业指数 → 算回报 → UPSERT。

    默认每周跑一次；首次会写 ~31 × 400 ≈ 12400 行 (PG UPSERT，几秒)。
    """

    job_name = "sw_industry_index_return"

    def __init__(self, db: Session) -> None:
        self.db = db
        self.provider = AkshareProvider()

    def run(self, lookback_days: int = 400) -> _Phase3Result:
        """执行全量刷新。返回简易 result，字段与 ETLResult 等价。"""
        result = _Phase3Result()
        log = self._create_log()
        try:
            codes = _load_sw_codes_from_db(self.db)
            result.metadata["codes_count"] = len(codes)
            if not codes:
                result.warnings.append(
                    "etf_info.sw_l1_code is empty; run backfill_a_share_sw first."
                )
                self._finalise_log(log, result)
                return result

            total_rows = 0
            for code in codes:
                symbol = code.split(".")[0]  # '801080.SI' → '801080'
                try:
                    bars = self.provider.fetch_sw_industry_index_daily(
                        symbol=symbol, lookback_days=lookback_days
                    )
                except Exception as exc:
                    logger.exception("fetch failed for %s: %s", symbol, exc)
                    result.errors.append(f"{symbol}: {exc}")
                    continue

                if not bars:
                    result.warnings.append(f"{symbol}: empty bars")
                    continue

# 按日期升序
                bars_sorted = sorted(bars, key=lambda b: b["date"])
                close_series = pd.Series([b["close"] for b in bars_sorted])
                returns_per_row = _rolling_returns(close_series)

                rows = []
                for b, ret in zip(bars_sorted, returns_per_row):
                    # 转纯 python float / None — psycopg2 不认 numpy.float64
                    rows.append(
                        {
                            "sw_l1_code": code,
                            "trade_date": b["date"],
                            "close": float(b["close"]),
                            "return_1w": (
                                float(ret["return_1w"])
                                if ret["return_1w"] is not None
                                else None
                            ),
                            "return_1m": (
                                float(ret["return_1m"])
                                if ret["return_1m"] is not None
                                else None
                            ),
                            "return_3m": (
                                float(ret["return_3m"])
                                if ret["return_3m"] is not None
                                else None
                            ),
                            "return_6m": (
                                float(ret["return_6m"])
                                if ret["return_6m"] is not None
                                else None
                            ),
                            "return_1y": (
                                float(ret["return_1y"])
                                if ret["return_1y"] is not None
                                else None
                            ),
                            "source": "akshare",
                        }
                    )

                try:
                    stmt = insert(SWIndustryIndexReturn).values(rows)
                    stmt = stmt.on_conflict_do_update(
                        index_elements=["sw_l1_code", "trade_date"],
                        set_={
                            "close": stmt.excluded.close,
                            "return_1w": stmt.excluded.return_1w,
                            "return_1m": stmt.excluded.return_1m,
                            "return_3m": stmt.excluded.return_3m,
                            "return_6m": stmt.excluded.return_6m,
                            "return_1y": stmt.excluded.return_1y,
                            "source": stmt.excluded.source,
                        },
                    )
                    self.db.execute(stmt)
                    self.db.commit()
                    total_rows += len(rows)
                    logger.info(
                        "sw_industry_index upsert code=%s rows=%d",
                        code,
                        len(rows),
                    )
                except Exception as exc:
                    self.db.rollback()
                    logger.exception("upsert failed for %s: %s", code, exc)
                    result.errors.append(f"{symbol} upsert: {exc}")

            result.records_processed = total_rows
            result.metadata["rows_written"] = total_rows
            logger.info(
                "sw_industry_index_refresh done codes=%d rows=%d errors=%d",
                len(codes),
                total_rows,
                len(result.errors),
            )
            self._finalise_log(log, result)
        except Exception as exc:
            logger.exception("sw_industry_index_refresh failed: %s", exc)
            log.status = "failed"
            log.error_msg = str(exc)[:500]
            log.end_time = datetime.now(timezone.utc)
            self.db.commit()
            result.errors.append(f"global: {exc}")
        return result

    # ----- ETLLog 集成 -----
    def _create_log(self) -> ETLLog:
        log = ETLLog(
            job_name=self.job_name,
            source=self.provider.name,
            status="running",
            start_time=datetime.now(timezone.utc),
        )
        self.db.add(log)
        self.db.commit()
        self.db.refresh(log)
        return log

    def _finalise_log(self, log: ETLLog, result: _Phase3Result) -> None:
        log.end_time = datetime.now(timezone.utc)
        log.status = "success" if not result.errors else "partial"
        log.records_count = result.records_processed
        if result.errors:
            log.error_msg = "\n".join(result.errors)[:500]
        self.db.commit()


def run_once(lookback_days: int = 400) -> _Phase3Result:
    """便捷入口：开 session 跑一次，返回 _Phase3Result。

    字段：``records_processed`` / ``errors`` / ``warnings`` / ``metadata``。
    """
    db = SessionLocal()
    try:
        return SWIndustryIndexPipeline(db).run(lookback_days=lookback_days)
    finally:
        db.close()


if __name__ == "__main__":  # pragma: no cover - manual smoke
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    out = run_once()
    print(
        f"rows={out.records_processed} errors={out.errors} warnings={out.warnings}"
    )
    sys.exit(0 if not out.errors else 1)