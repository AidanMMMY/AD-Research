#!/usr/bin/env python3
"""Generate snapshots for all ETF pools."""

import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal
from app.models.pool import ETFPools
from app.services.pool_enhancement_service import PoolEnhancementService


def main():
    db = SessionLocal()
    try:
        service = PoolEnhancementService(db)
        pools = db.query(ETFPools).all()
        print(f"=== Generating snapshots for {len(pools)} pools ===")
        snapshot_date = date(2026, 6, 18)
        for pool in pools:
            result = service.create_snapshot(pool.id, snapshot_date=snapshot_date)
            print(f"  Pool {pool.id} ({pool.name}): {result}")
        print("=== Done ===")
    finally:
        db.close()


if __name__ == "__main__":
    main()
