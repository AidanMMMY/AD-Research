"""A 股免费资金流 ETL Pipeline (方案 C)。

日频调度入口 ``run_daily()`` 拉 4 类资金流数据并 UPSERT：

1. 个股主力/超大/大/中/小单 (ak.fund_etf_spot_em + 个股历史) → ``individual_fund_flow``
2. 行业 / 概念 / 地域 板块资金流 (ak.stock_sector_fund_flow_rank)     → ``sector_fund_flow``
3. ETF 现价 + 份额差分 (ak.fund_etf_spot_em + fund_etf_fund_daily_em)  → ``etf_fund_flow``
4. 综合资金信号 (主力 + 融资 + 龙虎榜 + 股东户数 + AH + 大宗)         → ``flow_signal``

调度时间：A 股收盘后 17:30 Asia/Shanghai (避免与 18:30 microstructure 冲突)。

每类数据独立 try/except 保护，单源失败不阻塞其他数据源。
"""

from __future__ import annotations

import logging
import math
from datetime import date, datetime
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.data.pipelines.base import ETLPipeline, ETLResult
from app.data.providers.etf_flow_provider import EtfFlowProvider
from app.data.providers.flow_signals_provider import FlowSignalsProvider
from app.data.providers.fund_flow_provider import FundFlowProvider
from app.models.fund_flow import (
    EtfFundFlow,
    FlowSignal,
    IndividualFundFlow,
    SectorFundFlow,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 综合评分权重 — composite_score = sum(score_i * weight_i)  ∈ [-100, +100]
# ---------------------------------------------------------------------------
#
# 每个分量先归一化到 [-1, +1] 区间 (按绝对阈值 / 资金量级)，
# 再乘以权重 (权重之和 = 1.0)，最后 ×100 输出。
#
# 设计思路：主力资金是直接信号，权重最高 (40%)；融资 + 龙虎榜是
# 强机构信号 (各 20%)；股东户数 + AH + 大宗是弱信号 (各 5-10%)。

WEIGHTS: dict[str, float] = {
    "main": 0.40,           # 主力净流入
    "margin": 0.20,         # 融资净变化
    "lhb": 0.20,            # 龙虎榜机构净买
    "shareholder": 0.05,    # 股东户数变化 (反向)
    "ah": 0.05,             # AH 溢价
    "block": 0.10,          # 大宗交易
}
assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9, "weights must sum to 1.0"

# 归一化阈值 (单位：元) — 当日量级超过此值 → score = 1.0；低于负值 → score = -1.0
NORM_THRESHOLDS: dict[str, float] = {
    "main": 1e8,            # 1 亿
    "margin": 5e7,          # 5 千万
    "lhb": 5e7,             # 5 千万
    "shareholder": 1e4,     # 1 万户
    "ah": 50.0,             # 50 个百分点
    "block": 5e7,           # 5 千万
}


def _norm(x: float | None, threshold: float) -> float:
    """sigmoid 风格的归一化到 [-1, +1]。"""
    if x is None or threshold <= 0:
        return 0.0
    # 简单线性 + clip — 避免 0 附近过于敏感
    ratio = x / threshold
    return max(-1.0, min(1.0, ratio))


def _compute_composite(parts: dict[str, float | None]) -> tuple[float, dict[str, float]]:
    """计算 composite_score + 各分量贡献 (raw, 0-100 范围)。"""
    breakdown: dict[str, float] = {}
    score = 0.0
    for name, weight in WEIGHTS.items():
        x = parts.get(name)
        norm = _norm(x, NORM_THRESHOLDS[name])
        contrib = norm * weight * 100.0
        breakdown[name] = round(contrib, 4)
        score += contrib
    return round(score, 4), breakdown


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _df_to_records(df: pd.DataFrame | None) -> list[dict[str, Any]]:
    if df is None or df.empty:
        return []
    df = df.replace({pd.NA: None, float("nan"): None})
    return df.to_dict("records")


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


class FundFlowPipeline(ETLPipeline):
    """资金流日终 ETL Pipeline (4 个 sub-task 独立容错)。"""

    job_name = "fund_flow_daily"

    def __init__(self, db: Session, target_date: date | None = None) -> None:
        # base class requires a provider; we don't use it for OHLCV flow.
        from app.data.providers.akshare_provider import AkshareProvider

        super().__init__(provider=AkshareProvider(), db=db)
        self.target_date = target_date or date.today()
        self._ff_provider = FundFlowProvider()
        self._etf_provider = EtfFlowProvider()
        self._signals_provider = FlowSignalsProvider()
        # Per-sub-task counts (populated during run())
        self.sub_task_counts: dict[str, int] = {
            "individual": 0, "sector": 0, "etf": 0, "signals": 0,
        }

    def run(self) -> ETLResult:
        """Run 4 sub-tasks independently with try/except guards."""
        result = ETLResult()
        self._create_log()

        results: dict[str, int] = {}
        sub_tasks = (
            ("individual", self._run_individual),
            ("sector", self._run_sector),
            ("etf", self._run_etf),
            ("signals", self._run_signals),
        )

        any_success = False
        try:
            for name, fn in sub_tasks:
                try:
                    written = fn()
                    results[name] = written
                    self.sub_task_counts[name] = written
                    if written > 0:
                        any_success = True
                    logger.info(
                        "FundFlowPipeline[%s]: upserted %d rows", name, written
                    )
                except Exception as exc:
                    logger.exception("FundFlowPipeline[%s] failed: %s", name, exc)
                    result.warnings.append(f"{name}: {exc}")
                    results[name] = 0
                    self.sub_task_counts[name] = 0
                    # Rollback any in-flight transaction from the failed
                    # sub-task so the next sub-task starts on a clean session.
                    try:
                        self.db.rollback()
                    except Exception:  # noqa: BLE001
                        pass

            result.records = sum(results.values())
            result.success = any_success or all(v == 0 for v in results.values())
            try:
                self._update_log(
                    status="success" if result.success else "partial",
                    records=result.records,
                    error=None if result.success else "; ".join(result.warnings)
                    or "all sub-tasks empty",
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("etl_log update failed: %s", exc)
                try:
                    self.db.rollback()
                except Exception:  # noqa: BLE001
                    pass
        except Exception as exc:
            error_msg = str(exc)
            result.success = False
            result.error = error_msg
            try:
                self._update_log(status="failed", error=error_msg)
            except Exception:  # noqa: BLE001
                logger.warning("etl_log update failed: %s", exc)
                try:
                    self.db.rollback()
                except Exception:  # noqa: BLE001
                    pass
            logger.exception("FundFlowPipeline crashed: %s", exc)

        return result

    # base class declares extract() and load() as abstract — stub them
    def extract(self) -> pd.DataFrame:  # pragma: no cover - unused
        raise NotImplementedError("FundFlowPipeline uses run() override")

    def load(self, data: pd.DataFrame) -> int:  # pragma: no cover - unused
        raise NotImplementedError("FundFlowPipeline uses run() override")

    # -----------------------------------------------------------------
    # Sub-tasks
    # -----------------------------------------------------------------

    def _run_individual(self) -> int:
        """个股主力资金流 (ak.fund_etf_spot_em 不行时改用 stock_individual_fund_flow_rank)。"""
        rows = self._ff_provider.fetch_individual_rank(indicator="今日")
        if not rows:
            return 0
        # 补 trade_date (Pipeline 显式以 target_date 写入)
        for r in rows:
            r["trade_date"] = self.target_date
        return self._upsert_individual(rows)

    def _run_sector(self) -> int:
        """行业 + 概念 + 地域 板块资金流。"""
        rows: list[dict[str, Any]] = []
        for st in ("行业资金流", "概念资金流", "地域资金流"):
            sub = self._ff_provider.fetch_sector_rank(
                sector_type=st, indicator="今日"
            )
            for r in sub:
                r["trade_date"] = self.target_date
            rows.extend(sub)
        if not rows:
            return 0
        return self._upsert_sector(rows)

    def _run_etf(self) -> int:
        """ETF 现价 + 折溢价 + 份额差分 → etf_fund_flow。"""
        spot = self._ff_provider if False else None  # 静态 lint
        spot_rows = self._etf_provider.fetch_etf_spot()
        fund_daily_rows = self._etf_provider.fetch_etf_fund_daily()

        # merge: spot 提供 shares_outstanding + turnover; fund_daily 提供更准的 net_value
        price_map: dict[str, dict[str, Any]] = {
            r["ts_code"]: r for r in spot_rows if r.get("ts_code")
        }
        for r in fund_daily_rows:
            ts = r.get("ts_code")
            if not ts:
                continue
            if ts in price_map:
                # 用 fund_daily 的 net_value / premium_rate 覆盖 (更准)
                if r.get("net_value") is not None:
                    price_map[ts]["net_value"] = r["net_value"]
                if r.get("premium_rate") is not None:
                    price_map[ts]["premium_rate"] = r["premium_rate"]
                # 用 fund_daily 的 price 覆盖 (收盘价)
                if r.get("price") is not None:
                    price_map[ts]["price"] = r["price"]
            else:
                price_map[ts] = r

        merged = list(price_map.values())
        if not merged:
            return 0

        # 拉昨日的 shares_outstanding 做差分
        prev_shares_map = self._fetch_prev_shares_map(self.target_date)
        merged = self._etf_provider.compute_shares_change_and_inflow(
            merged, [{"ts_code": k, "shares_outstanding": v} for k, v in prev_shares_map.items()]
        )

        for r in merged:
            r["trade_date"] = self.target_date

        return self._upsert_etf(merged)

    def _run_signals(self) -> int:
        """综合资金信号 (聚合多源)。"""
        # 1) 主力 — 从 individual_fund_flow 读 (今天写入的)
        main_map = self._fetch_main_map(self.target_date)

        # 2) 融资
        margin_rows = self._signals_provider.fetch_margin_change(self.target_date)
        margin_map = {r["ts_code"]: r["margin_net_change"] for r in margin_rows}

        # 3) 龙虎榜
        lhb_rows = self._signals_provider.fetch_lhb_net(self.target_date)
        lhb_map: dict[str, float] = {}
        for r in lhb_rows:
            ts = r["ts_code"]
            lhb_map[ts] = (lhb_map.get(ts) or 0.0) + float(r["lhb_net_buy"] or 0.0)

        # 4) 股东户数
        sh_rows = self._signals_provider.fetch_shareholder_count(self.target_date)
        sh_map = {r["ts_code"]: r["shareholder_count_change"] for r in sh_rows}

        # 5) AH 溢价
        ah_rows = self._signals_provider.fetch_ah_premium(self.target_date)
        ah_map = {r["ts_code"]: r["ah_premium"] for r in ah_rows}

        # 6) 大宗
        bt_rows = self._signals_provider.fetch_block_trade(self.target_date)
        bt_map: dict[str, float] = {}
        for r in bt_rows:
            ts = r["ts_code"]
            bt_map[ts] = (bt_map.get(ts) or 0.0) + float(r["block_trade_net"] or 0.0)

        # 7) 合并：union of all ts_codes that have any signal
        all_codes = set(main_map) | set(margin_map) | set(lhb_map) | set(sh_map) | set(ah_map) | set(bt_map)
        if not all_codes:
            return 0

        out: list[dict[str, Any]] = []
        for ts_code in all_codes:
            main = main_map.get(ts_code)
            margin = margin_map.get(ts_code)
            lhb = lhb_map.get(ts_code)
            sh = sh_map.get(ts_code)
            ah = ah_map.get(ts_code)
            bt = bt_map.get(ts_code)
            # 股东户数反向 (负=集中) → 乘 -1 后归一化
            sh_for_score = -float(sh) if sh is not None else None
            score, breakdown = _compute_composite({
                "main": main,
                "margin": margin,
                "lhb": lhb,
                "shareholder": sh_for_score,
                "ah": ah,
                "block": bt,
            })
            out.append({
                "ts_code": ts_code,
                "trade_date": self.target_date,
                "main_net_inflow": main,
                "margin_net_change": margin,
                "lhb_net_buy": lhb,
                "shareholder_count_change": sh,
                "ah_premium": ah,
                "block_trade_net": bt,
                "composite_score": score,
                "score_breakdown": breakdown,
            })

        return self._upsert_signal(out)

    # -----------------------------------------------------------------
    # Reads (cross-sub-task)
    # -----------------------------------------------------------------

    def _fetch_main_map(self, target_date: date) -> dict[str, float]:
        """从 individual_fund_flow 读当日的 main_net_inflow 字典。"""
        stmt = select(
            IndividualFundFlow.ts_code, IndividualFundFlow.main_net_inflow
        ).where(IndividualFundFlow.trade_date == target_date)
        out: dict[str, float] = {}
        for row in self.db.execute(stmt).all():
            ts, main = row
            if ts and main is not None:
                out[ts] = float(main)
        return out

    def _fetch_prev_shares_map(self, target_date: date) -> dict[str, float]:
        """读 ETF 上一交易日的 shares_outstanding。"""
        # 找最近的 trade_date < target_date 且有 shares_outstanding 的行
        stmt = (
            select(EtfFundFlow.ts_code, EtfFundFlow.shares_outstanding, EtfFundFlow.trade_date)
            .where(EtfFundFlow.trade_date < target_date)
            .where(EtfFundFlow.shares_outstanding.isnot(None))
            .order_by(EtfFundFlow.trade_date.desc())
            .limit(2000)
        )
        rows = self.db.execute(stmt).all()
        # 取每个 ts_code 的最新一条
        latest: dict[str, float] = {}
        for ts, shares, _d in rows:
            if ts and ts not in latest and shares is not None:
                latest[ts] = float(shares)
        return latest

    # -----------------------------------------------------------------
    # Upsert helpers
    # -----------------------------------------------------------------

    def _upsert_individual(self, records: list[dict[str, Any]]) -> int:
        if not records:
            return 0
        stmt = insert(IndividualFundFlow).values(records)
        excluded = insert(IndividualFundFlow).excluded
        stmt = stmt.on_conflict_do_update(
            index_elements=["ts_code", "trade_date"],
            set_={
                "main_net_inflow": excluded.main_net_inflow,
                "main_net_pct": excluded.main_net_pct,
                "super_large_net": excluded.super_large_net,
                "super_large_pct": excluded.super_large_pct,
                "large_net": excluded.large_net,
                "large_pct": excluded.large_pct,
                "medium_net": excluded.medium_net,
                "medium_pct": excluded.medium_pct,
                "small_net": excluded.small_net,
                "small_pct": excluded.small_pct,
                "source": excluded.source,
            },
        )
        self.db.execute(stmt)
        self.db.commit()
        return len(records)

    def _upsert_sector(self, records: list[dict[str, Any]]) -> int:
        if not records:
            return 0
        stmt = insert(SectorFundFlow).values(records)
        excluded = insert(SectorFundFlow).excluded
        stmt = stmt.on_conflict_do_update(
            index_elements=["sector_name", "sector_type", "trade_date"],
            set_={
                "main_net_inflow": excluded.main_net_inflow,
                "main_net_pct": excluded.main_net_pct,
                "super_large_net": excluded.super_large_net,
                "large_net": excluded.large_net,
                "leading_stock": excluded.leading_stock,
            },
        )
        self.db.execute(stmt)
        self.db.commit()
        return len(records)

    def _upsert_etf(self, records: list[dict[str, Any]]) -> int:
        if not records:
            return 0
        # Dedupe on (ts_code, trade_date) before insert (defensive)
        seen: set[tuple[str, date]] = set()
        deduped: list[dict[str, Any]] = []
        for r in records:
            key = (r.get("ts_code"), r.get("trade_date"))
            if key in seen:
                continue
            seen.add(key)
            deduped.append(r)

        # ETF 子任务合并了两个数据源：spot 提供 shares_outstanding/turnover，
        # fund_daily 只提供 price/net_value/premium_rate。SQLAlchemy 的多行
        # insert().values([...]) 要求每个字典拥有相同的键，尤其是在 ON CONFLICT
        # 的 set_ 中引用 excluded.<col> 时；否则会出现 CompileError：
        # "INSERT value for column shares_outstanding is explicitly rendered as a
        # boundparameter..." 这里统一补缺失键为 None。
        columns = {
            "ts_code",
            "trade_date",
            "price",
            "net_value",
            "premium_rate",
            "shares_outstanding",
            "shares_change",
            "turnover",
            "inferred_net_inflow",
        }
        normalized = [{col: r.get(col) for col in columns} for r in deduped]

        stmt = insert(EtfFundFlow).values(normalized)
        excluded = insert(EtfFundFlow).excluded
        stmt = stmt.on_conflict_do_update(
            index_elements=["ts_code", "trade_date"],
            set_={
                "price": excluded.price,
                "net_value": excluded.net_value,
                "premium_rate": excluded.premium_rate,
                "shares_outstanding": excluded.shares_outstanding,
                "shares_change": excluded.shares_change,
                "turnover": excluded.turnover,
                "inferred_net_inflow": excluded.inferred_net_inflow,
            },
        )
        self.db.execute(stmt)
        self.db.commit()
        return len(deduped)

    def _upsert_signal(self, records: list[dict[str, Any]]) -> int:
        if not records:
            return 0
        # Pydantic JSON-serializable — score_breakdown is a dict
        stmt = insert(FlowSignal).values(records)
        excluded = insert(FlowSignal).excluded
        stmt = stmt.on_conflict_do_update(
            index_elements=["ts_code", "trade_date"],
            set_={
                "main_net_inflow": excluded.main_net_inflow,
                "margin_net_change": excluded.margin_net_change,
                "lhb_net_buy": excluded.lhb_net_buy,
                "shareholder_count_change": excluded.shareholder_count_change,
                "ah_premium": excluded.ah_premium,
                "block_trade_net": excluded.block_trade_net,
                "composite_score": excluded.composite_score,
                "score_breakdown": excluded.score_breakdown,
            },
        )
        self.db.execute(stmt)
        self.db.commit()
        return len(records)


# ---------------------------------------------------------------------------
# Top-level entry (used by scheduler + ad-hoc trigger)
# ---------------------------------------------------------------------------


def run_daily(trade_date: date | None = None) -> dict[str, Any]:
    """日终调度入口：拉所有资金流数据并 UPSERT。

    Args:
        trade_date: 目标交易日；为 None 时取 ``date.today()``。

    Returns:
        ``{"individual": N, "sector": N, "etf": N, "signals": N, "success": bool, "warnings": [...]}``
    """
    from app.core.database import SessionLocal

    target = trade_date or date.today()
    db = SessionLocal()
    try:
        pipeline = FundFlowPipeline(db, target_date=target)
        result = pipeline.run()
        return {
            **pipeline.sub_task_counts,
            "success": result.success,
            "warnings": result.warnings,
        }
    finally:
        db.close()
