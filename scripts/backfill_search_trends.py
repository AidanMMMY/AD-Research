"""One-off backfill for search_trends using working akshare endpoints.

Uses:
  - ak.stock_hot_follow_xq (雪球关注排名) as the Google-trends source
  - ak.stock_hot_keyword_em (东方财富热词) as the Baidu-trends source

These endpoints are currently available; the original baidu/Google
upstreams used by the scheduled pipeline are broken or unreachable
from the ECS network.
"""

import logging
import warnings
from datetime import datetime, timezone

import akshare as ak
import pandas as pd
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.database import SessionLocal
from app.models.search_trends import SearchTrend
from app.services.search_index_service import load_keyword_registry

warnings.filterwarnings("ignore")
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
)
logger = logging.getLogger("backfill_search_trends")


def fetch_xueqiu_follow() -> pd.DataFrame:
    df = ak.stock_hot_follow_xq()
    df = df.rename(columns={"股票代码": "code", "股票简称": "name", "关注": "value"})
    df["value"] = pd.to_numeric(df["value"], errors="coerce").fillna(0).astype("Int64")
    return df[["code", "name", "value"]]


def fetch_em_keywords() -> pd.DataFrame:
    return ak.stock_hot_keyword_em()


def upsert_rows(rows):
    if not rows:
        return 0
    db = SessionLocal()
    try:
        stmt = pg_insert(SearchTrend).values(rows)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_search_trends_keyword_region_source_date",
            set_={
                "value": stmt.excluded.value,
                "is_partial": stmt.excluded.is_partial,
                "category": stmt.excluded.category,
                "fetched_at": stmt.excluded.fetched_at,
            },
        )
        db.execute(stmt)
        db.commit()
        return len(rows)
    finally:
        db.close()


def main():
    today = pd.Timestamp("2026-07-09").date()
    now = datetime.now(timezone.utc)
    rows = []

    registry = load_keyword_registry()

    # --- Baidu source: 东方财富 hot keywords → match registry keywords ---
    baidu_kws: set[str] = set()
    for src in ("baidu_index", "baidu"):
        for cat in ("indices", "stocks", "macro"):
            baidu_kws.update(registry.get(src, {}).get(cat, []))
    logger.info("registry baidu keywords: %s", sorted(baidu_kws))

    try:
        em = fetch_em_keywords()
        keyword_to_max: dict[str, int] = {}
        for _, r in em.iterrows():
            kw_name = str(r.get("概念名称", ""))
            heat = int(r.get("热度", 0) or 0)
            for reg_kw in baidu_kws:
                if reg_kw and reg_kw in kw_name:
                    keyword_to_max[reg_kw] = max(
                        keyword_to_max.get(reg_kw, 0), heat
                    )
        for kw, v in keyword_to_max.items():
            rows.append(
                {
                    "keyword": kw,
                    "region": "CN",
                    "source": "baidu",
                    "trade_date": today,
                    "value": v,
                    "is_partial": True,
                    "category": "macro",
                    "fetched_at": now,
                }
            )
        logger.info("baidu rows to insert: %d", len(keyword_to_max))
    except Exception as e:
        logger.exception("em keywords fetch failed: %s", e)

    # --- Google source: 雪球 follow count → match registry stock keywords ---
    google_stock_kws: set[str] = set(
        registry.get("google_trends", {}).get("stocks", [])
    )
    logger.info("registry google stock keywords: %s", sorted(google_stock_kws))

    try:
        xq = fetch_xueqiu_follow()
        keyword_to_xq: dict[str, int] = {}
        for _, r in xq.iterrows():
            name = str(r.get("name", ""))
            v = int(r.get("value", 0) or 0)
            for reg_kw in google_stock_kws:
                if reg_kw and reg_kw in name:
                    keyword_to_xq[reg_kw] = max(
                        keyword_to_xq.get(reg_kw, 0), v
                    )
        for kw, v in keyword_to_xq.items():
            rows.append(
                {
                    "keyword": kw,
                    "region": "GLOBAL",
                    "source": "google",
                    "trade_date": today,
                    "value": v,
                    "is_partial": True,
                    "category": "stocks",
                    "fetched_at": now,
                }
            )
        logger.info("google rows to insert: %d", len(keyword_to_xq))
    except Exception as e:
        logger.exception("xueqiu follow fetch failed: %s", e)

    written = upsert_rows(rows)
    logger.info("upserted %d rows total", written)

    db = SessionLocal()
    try:
        from sqlalchemy import select, func
        total = db.execute(select(func.count(SearchTrend.id))).scalar()
        latest = db.execute(select(func.max(SearchTrend.trade_date))).scalar()
        logger.info(
            "search_trends total rows: %d, latest trade_date: %s",
            total,
            latest,
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
