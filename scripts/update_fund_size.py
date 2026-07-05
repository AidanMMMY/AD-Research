"""Update ETF fund_size (AUM) from akshare real-time data."""

import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

import akshare as ak
from sqlalchemy.orm import Session

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.core.database import SessionLocal
from app.models.etf import ETFInfo


def update_fund_size():
    """Fetch ETF fund size from akshare and update database."""
    print("Fetching ETF spot data from akshare...")
    df = ak.fund_etf_spot_em()

    # Build code -> total_market_value mapping
    # '总市值' column is fund size in CNY
    size_map = {}
    for _, row in df.iterrows():
        code = str(row["代码"]).strip()
        total_mv = row.get("总市值")
        if total_mv and total_mv > 0:
            size_map[code] = float(total_mv)

    print(f"Fetched {len(size_map)} ETFs with size data from akshare")

    db: Session = SessionLocal()
    try:
        etfs = db.query(ETFInfo.code, ETFInfo.name).all()
        updated = 0
        missing = []

        for etf in etfs:
            # Database codes have suffix like "159915.SZ", akshare codes are pure "159915"
            pure_code = etf.code.split('.')[0] if '.' in etf.code else etf.code
            if pure_code in size_map:
                db.query(ETFInfo).filter(ETFInfo.code == etf.code).update(
                    {"fund_size": size_map[pure_code]}
                )
                updated += 1
            else:
                missing.append(etf.code)

        db.commit()
        print(f"Updated {updated} ETFs with fund_size")

        if missing:
            print(f"Missing size data for {len(missing)} ETFs")
            print(f"Examples: {missing[:10]}")

        # Show summary
        count_with_size = db.query(ETFInfo).filter(ETFInfo.fund_size.isnot(None)).count()
        total = db.query(ETFInfo).count()
        print(f"\nSummary: {count_with_size}/{total} ETFs now have fund_size data")

        # Top 10 largest
        top = (
            db.query(ETFInfo.code, ETFInfo.name, ETFInfo.fund_size)
            .filter(ETFInfo.fund_size.isnot(None))
            .order_by(ETFInfo.fund_size.desc())
            .limit(10)
            .all()
        )
        print("\nTop 10 largest ETFs:")
        for e in top:
            size_yi = float(e.fund_size) / 1e8 if e.fund_size else 0
            print(f"  {e.code} {e.name}: {size_yi:.1f}亿")

    finally:
        db.close()


if __name__ == "__main__":
    update_fund_size()
