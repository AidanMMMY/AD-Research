#!/usr/bin/env python3
"""初始化 ETF 列表数据到数据库"""

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert

from app.core.database import SessionLocal
from app.data.providers.akshare_provider import AkshareProvider
from app.models.etf import ETFInfo


def init_etfs():
    db = SessionLocal()
    try:
        provider = AkshareProvider()
        etfs = provider.fetch_etf_list()
        print(f"Fetched {len(etfs)} ETFs from akshare")

        records = []
        for etf in etfs:
            records.append({
                "code": etf.code,
                "name": etf.name,
                "market": etf.market,
                "exchange": etf.exchange,
                "currency": etf.currency,
                "is_qdii": etf.is_qdii,
                "status": "active",
            })

        # UPSERT
        stmt = insert(ETFInfo).values(records)
        stmt = stmt.on_conflict_do_update(
            index_elements=["code"],
            set_={
                "name": stmt.excluded.name,
                "market": stmt.excluded.market,
                "exchange": stmt.excluded.exchange,
                "updated_at": func.now(),
            },
        )
        db.execute(stmt)
        db.commit()
        print(f"Upserted {len(records)} ETFs")
    finally:
        db.close()


if __name__ == "__main__":
    init_etfs()
