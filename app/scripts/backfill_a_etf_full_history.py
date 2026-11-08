"""A 股 ETF 全史一次性回填（2026-11-04，Phase 1.1）。

2,296 只 A 股 ETF 用 akshare ``fund_etf_hist_em``（东财、无配额）补到
各自成立日。复用 AShareETLPipeline 的幂等 upsert 口径（不覆盖非空、
冲突跳过）。akshare 无 SLA、上游改版漂移 → 失败清单化，可重跑续跑。

用法（容器内）：
    python scripts/backfill_a_etf_full_history.py --dry-run
    python scripts/backfill_a_etf_full_history.py --limit 20     # 小批试跑
    python scripts/backfill_a_etf_full_history.py                # 全量（≈1h）

「待补」定义：该 ETF 现有最早 bar 晚于其上市/成立日 30 天以上（与
覆盖评估报告口径一致），或完全无 bar。
"""

import argparse
import logging
import sys
import time
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, "/app")  # Docker 容器惯例（与 crypto 回填脚本一致）

from sqlalchemy import func  # noqa: E402

from app.core.database import SessionLocal  # noqa: E402
from app.core.redis_client import get_redis_client  # noqa: E402
from app.data.pipelines.a_share import AShareETLPipeline  # noqa: E402
from app.models.etf import ETFInfo, InstrumentDailyBar  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("backfill_a_etf")

LOCK_KEY = "ad:backfill:a_etf_full_history"
GAP_DAYS = 30
REQ_DELAY = 1.2  # akshare 无配额但对上游礼貌限速


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=None, help="只跑前 N 只（试跑用）")
    parser.add_argument("--codes", nargs="*", default=None)
    args = parser.parse_args()

    r = get_redis_client()
    if r is not None and r.set(LOCK_KEY, "1", nx=True, ex=14400) is None:
        raise SystemExit("已有回填在跑（Redis 锁），退出。")

    db = SessionLocal()
    try:
        pipe = AShareETLPipeline(db=db, target_date=None, prefer_sina=False)
        provider = pipe.provider  # AkShareProvider

        q = db.query(ETFInfo).filter(ETFInfo.market == "A股").filter(ETFInfo.status == "active")
        etfs = q.all()
        logger.info("A股 active 标的: %d（含个股与 ETF）", len(etfs))

        first_bar = dict(
            db.query(InstrumentDailyBar.etf_code, func.min(InstrumentDailyBar.trade_date))
            .group_by(InstrumentDailyBar.etf_code)
            .all()
        )

        def is_etf(code: str) -> bool:
            # A股 ETF 代码特征：沪 51/56/58、深 15/16 开头；库存格式带
            # 交易所后缀（如 158000.SZ / 510300.SH），先剥后缀再判前缀。
            pure = code.split(".")[0]
            return len(pure) == 6 and pure[:2] in {"51", "56", "58", "15", "16"}

        todo, skipped = [], []
        for e in etfs:
            code = e.code
            if not is_etf(code):
                continue
            if args.codes and code not in args.codes:
                continue
            cur = first_bar.get(code)
            listing = e.list_date
            if listing is None:
                listing = date(2004, 12, 30)  # 无上市日 → 尽量往前补
            if cur is not None and cur <= listing + timedelta(days=GAP_DAYS):
                skipped.append(code)
            else:
                todo.append((code, listing, cur))

        logger.info("ETF 已完整 %d 只；待补 %d 只", len(skipped), len(todo))
        if args.limit:
            todo = todo[: args.limit]
            logger.info("limit=%d，本轮只跑 %d 只", args.limit, len(todo))

        if args.dry_run:
            for code, listing, cur in todo[:30]:
                logger.info("  %s: 现 min=%s 上市=%s", code, cur, listing)
            logger.info("…（共 %d 只）dry-run 结束，未写库。", len(todo))
            return

        end = date.today() - timedelta(days=1)
        failed, done = [], 0
        for i, (code, listing, _cur) in enumerate(todo, 1):
            try:
                df = provider.fetch_daily_bars([code], listing, end)
                if df is None or df.empty:
                    logger.warning("[%d/%d] %s: 空，跳过", i, len(todo), code)
                    failed.append(code)
                    time.sleep(REQ_DELAY)
                    continue
                n = pipe.load(df)
                done += n
                logger.info(
                    "[%d/%d] %s: +%d 行（%s ~ %s）",
                    i,
                    len(todo),
                    code,
                    n,
                    df["trade_date"].min(),
                    df["trade_date"].max(),
                )
            except Exception:
                logger.exception("[%d/%d] %s: 失败", i, len(todo), code)
                failed.append(code)
            time.sleep(REQ_DELAY)

        logger.info("完成：写入 %d 行；失败 %d 只: %s", done, len(failed), failed[:50] or "无")
    finally:
        db.close()
        if r is not None:
            r.delete(LOCK_KEY)


if __name__ == "__main__":
    main()
