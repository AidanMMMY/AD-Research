#!/usr/bin/env python3
"""One-shot US ETF metadata initialization / repair.

Upserts the curated US ETF list from Finnhub into etf_info.  This is
useful for:
  - Initial seeding of US ETFs on a fresh database.
  - Repairing category metadata that was lost or never populated.
  - Manual synchronization outside of the weekly scheduled discovery job.

Usage:
    docker exec etf-backend python3 app/scripts/init_us_etfs.py
"""

from app.core.database import SessionLocal
from app.data.pipelines.us_etf_discovery import USEtfDiscoveryPipeline


def init_us_etfs():
    db = SessionLocal()
    try:
        pipeline = USEtfDiscoveryPipeline(db)
        result = pipeline.run()
        print(
            f"USEtfDiscoveryPipeline: success={result.success}, "
            f"records={result.records}, warnings={result.warnings}, "
            f"error={result.error}"
        )
    finally:
        db.close()


if __name__ == "__main__":
    init_us_etfs()
