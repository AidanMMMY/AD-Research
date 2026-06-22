"""手动触发全市场 ETF 扫描.

可独立运行，也可被 update_daily_data.py 调用.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import get_settings
from app.services.etf_scanner_service import ETFScannerService

settings = get_settings()
engine = create_engine(settings.database_url)
Session = sessionmaker(bind=engine)


def main():
    db = Session()
    try:
        print("🔍 Running ETF market scan...")
        service = ETFScannerService(db)
        result = service.scan_market()

        new = len(result.get("new", []))
        delisted = len(result.get("delisted", []))
        changed = len(result.get("changed", []))
        total = new + delisted + changed

        print(f"   New: {new}")
        print(f"   Delisted: {delisted}")
        print(f"   Changed: {changed}")
        print(f"   Total changes: {total}")

        if total == 0:
            print("✅ No changes detected")
        else:
            print("✅ Scan complete")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    main()
