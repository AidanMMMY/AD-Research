"""CRYPTO 全史一次性回填（2026-11-04，Phase 0.3）。

25 币补到各自上线日（BTC≈2017-08）。Binance klines 公开端点（无鉴权、
1000 根/页、provider 内部已限速 0.1s/req）→ 复用 CryptoDailyPipeline 的
幂等 upsert（instrument_daily_bar，冲突不覆盖非空）。

用法（容器内）：
    python scripts/backfill_crypto_full_history.py --dry-run   # 只打印缺口
    python scripts/backfill_crypto_full_history.py             # 真跑（幂等可续）

验收：每币 min(trade_date) ≤ 上线后 7 天；指标/评分由既有 chunked 补算跟进。
"""

import argparse
import logging
from datetime import date, timedelta

from sqlalchemy import func

from app.core.database import SessionLocal
from app.core.redis_client import get_redis_client
from app.data.pipelines.crypto_daily import CryptoDailyPipeline
from app.models.etf import ETFInfo, InstrumentDailyBar

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("backfill_crypto")

LOCK_KEY = "ad:backfill:crypto_full_history"
# 上线锚点：目标下限（上线后 7 天内视为完整；取保守的已知上线月）
_LISTING_ANCHOR = {
    "BTC.US": date(2017, 8, 17),
    "ETH.US": date(2017, 8, 17),
    "BNB.US": date(2017, 11, 16),
    "SOL.US": date(2020, 8, 11),
    "DOGE.US": date(2020, 7, 10),
    "ADA.US": date(2018, 4, 17),
    "AVAX.US": date(2020, 9, 22),
    "DOT.US": date(2020, 8, 19),
    "LINK.US": date(2019, 1, 14),
    "LTC.US": date(2017, 12, 13),
}


def _listing_of(code: str) -> date:
    return _LISTING_ANCHOR.get(code, date(2023, 1, 1))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--codes", nargs="*", default=None, help="只跑指定币（默认全部）")
    args = parser.parse_args()

    r = get_redis_client()
    if r is not None and r.set(LOCK_KEY, "1", nx=True, ex=7200) is None:
        raise SystemExit("已有回填在跑（Redis 锁），退出。")

    db = SessionLocal()
    try:
        # CryptoDailyPipeline 内部自建 BinanceProvider（含限速与多 host 回退）
        pipe = CryptoDailyPipeline(db=db, target_date=None)
        provider = pipe.provider

        q = db.query(ETFInfo).filter(ETFInfo.market == "CRYPTO", ETFInfo.status == "active")
        if args.codes:
            q = q.filter(ETFInfo.code.in_(args.codes))
        cryptos = [c.code for c in q.all()]
        logger.info("待检币数: %d", len(cryptos))

        first_bar = dict(
            db.query(InstrumentDailyBar.etf_code, func.min(InstrumentDailyBar.trade_date))
            .filter(InstrumentDailyBar.etf_code.in_(cryptos))
            .group_by(InstrumentDailyBar.etf_code)
            .all()
        )

        todo, skipped = [], []
        for code in cryptos:
            anchor = _listing_of(code)
            current_min = first_bar.get(code)
            if current_min is not None and current_min <= anchor + timedelta(days=7):
                skipped.append(code)
            else:
                todo.append((code, anchor, current_min))

        logger.info("已完整 %d 只；待补 %d 只", len(skipped), len(todo))
        for code, anchor, cur in todo:
            logger.info("  %s: 现 min=%s → 目标 %s", code, cur, anchor)

        if args.dry_run:
            logger.info("dry-run 结束，未写库。")
            return

        end = date.today() - timedelta(days=1)
        failed = []
        for code, anchor, _cur in todo:
            try:
                df = provider.fetch_daily_bars([code], anchor, end)
                if df.empty:
                    logger.warning("%s: 返回空，跳过", code)
                    failed.append(code)
                    continue
                n = pipe.load(df)
                logger.info(
                    "%s: 写入 %d 行（%s ~ %s）",
                    code,
                    n,
                    df["trade_date"].min(),
                    df["trade_date"].max(),
                )
            except Exception:
                logger.exception("%s: 失败", code)
                failed.append(code)

        logger.info("完成。失败 %d: %s", len(failed), failed or "无")
    finally:
        db.close()
        if r is not None:
            r.delete(LOCK_KEY)


if __name__ == "__main__":
    main()
