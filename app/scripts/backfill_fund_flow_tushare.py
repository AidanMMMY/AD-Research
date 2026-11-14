"""A 股资金流历史回填（Tushare moneyflow，2026-11-15）。

背景：akshare 东财资金流接口从 ECS 时灵时不灵，individual/sector 两表
近六周只有零星交易日有全量数据。Tushare ``moneyflow`` / ``moneyflow_ind_dc``
（东财同源）探针实测：个股 5,580 行/日、行业 1,058 行/日，稳定可用。

口径对齐（与 akshare 东财路径一致）：
- 主力 = 超大单 + 大单；Tushare 金额单位万元 → 库内元（×10^4）
- 净占比 = 净额 / 当日成交额 × 100（成交额取自 instrument_daily_bar）
- 残卷日（<1000 行个股 / <300 行行业）先清后补，避免 upsert 覆盖半截数据

用法（容器内）：
    python scripts/backfill_fund_flow_tushare.py --dry-run   # 只列缺口
    python scripts/backfill_fund_flow_tushare.py             # 补全部缺口
    python scripts/backfill_fund_flow_tushare.py --start 2026-10-01 --end 2026-11-13
"""

import argparse
import logging
import sys
import time
from datetime import date, timedelta
from pathlib import Path

_THIS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_THIS_DIR.parents[1]))
sys.path.insert(0, "/app")

import os  # noqa: E402

import tushare as ts  # noqa: E402
from sqlalchemy import func  # noqa: E402

from app.core.database import SessionLocal  # noqa: E402
from app.core.redis_client import get_redis_client  # noqa: E402
from app.data.pipelines.fund_flow import FundFlowPipeline  # noqa: E402
from app.models.etf import InstrumentDailyBar  # noqa: E402
from app.models.fund_flow import IndividualFundFlow, SectorFundFlow  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("backfill_fundflow")

LOCK_KEY = "ad:backfill:fund_flow_tushare"
IND_FULL = 1000  # 个股全量约 5,3xx；低于此视为残卷
SEC_FULL = 300  # 行业全量 1,05x


def _w(yuan_wan):
    """万元 → 元；None 透传。"""
    if yuan_wan is None:
        return None
    return float(yuan_wan) * 10_000


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=date.fromisoformat, default=date(2026, 10, 1))
    parser.add_argument("--end", type=date.fromisoformat, default=date.today() - timedelta(days=1))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    r = get_redis_client()
    if r is not None and r.set(LOCK_KEY, "1", nx=True, ex=7200) is None:
        raise SystemExit("已有回填在跑（Redis 锁），退出。")

    db = SessionLocal()
    try:
        pro = ts.pro_api(os.environ["TUSHARE_TOKEN"])
        pipe = FundFlowPipeline(db=db)

        # 交易日历取自日线（A股大盘日历，天然准确）
        trading_days = [
            d
            for (d,) in db.query(InstrumentDailyBar.trade_date)
            .filter(
                InstrumentDailyBar.trade_date >= args.start,
                InstrumentDailyBar.trade_date <= args.end,
            )
            .distinct()
            .order_by(InstrumentDailyBar.trade_date)
            .all()
        ]

        ind_counts = dict(
            db.query(IndividualFundFlow.trade_date, func.count())
            .filter(IndividualFundFlow.trade_date >= args.start)
            .group_by(IndividualFundFlow.trade_date)
            .all()
        )
        sec_counts = dict(
            db.query(SectorFundFlow.trade_date, func.count())
            .filter(SectorFundFlow.trade_date >= args.start)
            .group_by(SectorFundFlow.trade_date)
            .all()
        )

        todo = [
            d
            for d in trading_days
            if ind_counts.get(d, 0) < IND_FULL or sec_counts.get(d, 0) < SEC_FULL
        ]
        logger.info(
            "区间 %s ~ %s：交易日 %d，缺口日 %d", args.start, args.end, len(trading_days), len(todo)
        )
        for d in todo:
            logger.info("  %s: ind=%d sec=%d", d, ind_counts.get(d, 0), sec_counts.get(d, 0))
        if args.dry_run:
            logger.info("dry-run 结束，未写库。")
            return

        # 当日成交额（元）用于净占比换算
        total_written = 0
        for i, d in enumerate(todo, 1):
            dstr = d.strftime("%Y%m%d")
            try:
                amount_map = dict(
                    db.query(InstrumentDailyBar.etf_code, InstrumentDailyBar.amount)
                    .filter(InstrumentDailyBar.trade_date == d)
                    .all()
                )

                # ── 个股 ──
                if ind_counts.get(d, 0) < IND_FULL:
                    df = pro.moneyflow(trade_date=dstr)
                    time.sleep(0.4)
                    if df is not None and not df.empty:
                        if ind_counts.get(d, 0) > 0:  # 清残卷
                            db.query(IndividualFundFlow).filter(
                                IndividualFundFlow.trade_date == d
                            ).delete()
                            db.commit()
                        recs = []

                        def _net(row, buy_k, sell_k):
                            b, sl = row.get(buy_k), row.get(sell_k)
                            if b is None or sl is None:
                                return None
                            return _w(b) - _w(sl)

                        for _, row in df.iterrows():
                            ts_code = row.get("ts_code")
                            elg_n = _net(row, "buy_elg_amount", "sell_elg_amount")
                            lg_n = _net(row, "buy_lg_amount", "sell_lg_amount")
                            md_n = _net(row, "buy_md_amount", "sell_md_amount")
                            sm_n = _net(row, "buy_sm_amount", "sell_sm_amount")
                            main_n = (
                                elg_n + lg_n if elg_n is not None and lg_n is not None else None
                            )
                            # bar 表 code 无后缀；净占比 = 净额/成交额×100
                            amt = amount_map.get(ts_code.split(".")[0]) if ts_code else None

                            def _pct(v):
                                return round(v / amt * 100, 2) if (v is not None and amt) else None

                            recs.append(
                                {
                                    "ts_code": ts_code,
                                    "trade_date": d,
                                    "main_net_inflow": main_n,
                                    "main_net_pct": _pct(main_n),
                                    "super_large_net": elg_n,
                                    "super_large_pct": _pct(elg_n),
                                    "large_net": lg_n,
                                    "large_pct": _pct(lg_n),
                                    "medium_net": md_n,
                                    "medium_pct": _pct(md_n),
                                    "small_net": sm_n,
                                    "small_pct": _pct(sm_n),
                                    "source": "tushare_backfill",
                                }
                            )
                        n = pipe._upsert_individual(recs)
                        total_written += n
                        logger.info("[%d/%d] %s 个股 +%d", i, len(todo), d, n)
                    else:
                        logger.warning("[%d/%d] %s 个股：Tushare 返回空", i, len(todo), d)

                # ── 行业（东财同源）──
                if sec_counts.get(d, 0) < SEC_FULL:
                    df2 = pro.moneyflow_ind_dc(trade_date=dstr)
                    time.sleep(0.4)
                    if df2 is not None and not df2.empty:
                        if sec_counts.get(d, 0) > 0:
                            db.query(SectorFundFlow).filter(SectorFundFlow.trade_date == d).delete()
                            db.commit()
                        recs2 = []
                        for _, row in df2.iterrows():
                            net = _w(row.get("net_amount"))
                            recs2.append(
                                {
                                    "sector_name": row.get("name") or row.get("industry"),
                                    "sector_type": "行业",
                                    "trade_date": d,
                                    "main_net_inflow": net,
                                    "main_net_pct": row.get("net_amount_rate"),
                                    "leading_stock": row.get("lead_stock"),
                                }
                            )
                        n2 = pipe._upsert_sector(recs2)
                        total_written += n2
                        logger.info("[%d/%d] %s 行业 +%d", i, len(todo), d, n2)
                    else:
                        logger.warning("[%d/%d] %s 行业：Tushare 返回空", i, len(todo), d)
            except Exception:
                logger.exception("[%d/%d] %s 失败，继续下一日", i, len(todo), d)
                db.rollback()

        logger.info("完成：共写入 %d 行。", total_written)
    finally:
        db.close()
        if r is not None:
            r.delete(LOCK_KEY)


if __name__ == "__main__":
    main()
