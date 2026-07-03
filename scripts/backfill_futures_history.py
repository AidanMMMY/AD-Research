#!/usr/bin/env python3
"""Backfill Chinese commodity futures contracts and daily bars.

This script is a one-time / catch-up tool for the futures tables:
  - futures_contracts   (main continuous contract metadata)
  - futures_daily_bars  (daily OHLCV + settlement + open interest)

It runs the same pipelines as the scheduler, but with an extended history
window so missed data can be filled in. The scheduler keeps only the last
30 days by default; this script defaults to 10 000 days (~27 years) which
is longer than the history returned by akshare's sina endpoints.

Usage:
    python scripts/backfill_futures_history.py
    python scripts/backfill_futures_history.py --history-days 365
    python scripts/backfill_futures_history.py --skip-discovery --history-days 30
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import date

# Make `app` importable when running from the scripts/ directory.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.data.pipelines.futures import (
    FuturesContractDiscoveryPipeline,
    FuturesDailyPipeline,
)
from app.models.futures import FuturesContract
from app.services.futures_service import FuturesService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def _print_stats(session: Session, label: str) -> None:
    service = FuturesService(session)
    stats = service.stats()
    logger.info(
        "[%s] main_contracts=%d total_bars=%d latest_trade_date=%s",
        label,
        stats["total_contracts"],
        stats["total_bars"],
        stats["latest_trade_date"],
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Backfill Chinese futures contracts and daily bars."
    )
    parser.add_argument(
        "--history-days",
        type=int,
        default=10000,
        help="Number of calendar days of daily bars to retain (default: 10000).",
    )
    parser.add_argument(
        "--target-date",
        type=date.fromisoformat,
        default=None,
        help="Optional target date (ISO format). Defaults to today.",
    )
    parser.add_argument(
        "--skip-discovery",
        action="store_true",
        help="Skip contract discovery; only backfill daily bars for existing contracts.",
    )
    parser.add_argument(
        "--max-attempts",
        type=int,
        default=2,
        help="Retry attempts per pipeline (default: 2).",
    )
    args = parser.parse_args()

    session = SessionLocal()
    try:
        _print_stats(session, "BEFORE")

        if not args.skip_discovery:
            logger.info("Starting futures contract discovery...")
            discovery = FuturesContractDiscoveryPipeline(session)
            discovery_result = discovery.run_with_retry(max_attempts=args.max_attempts)
            logger.info(
                "Contract discovery: success=%s records=%s",
                discovery_result.success,
                discovery_result.records,
            )
            if not discovery_result.success:
                logger.error(
                    "Contract discovery failed: %s", discovery_result.error
                )
                return 1
        else:
            contract_count = session.query(FuturesContract).count()
            if contract_count == 0:
                logger.error(
                    "--skip-discovery requested but futures_contracts is empty. "
                    "Run discovery first."
                )
                return 1
            logger.info("Skipping discovery; %d contracts in DB.", contract_count)

        logger.info(
            "Starting daily bar backfill (history_days=%d, target_date=%s)...",
            args.history_days,
            args.target_date,
        )
        daily = FuturesDailyPipeline(
            session,
            target_date=args.target_date,
            history_days=args.history_days,
        )
        daily_result = daily.run_with_retry(max_attempts=args.max_attempts)
        logger.info(
            "Daily bar backfill: success=%s records=%s",
            daily_result.success,
            daily_result.records,
        )
        if daily_result.warnings:
            for warning in daily_result.warnings:
                logger.warning("Backfill warning: %s", warning)
        if not daily_result.success:
            logger.error("Daily bar backfill failed: %s", daily_result.error)
            return 1

        _print_stats(session, "AFTER")
        return 0

    except Exception as exc:
        logger.exception("Backfill crashed: %s", exc)
        return 1
    finally:
        session.close()


if __name__ == "__main__":
    sys.exit(main())
