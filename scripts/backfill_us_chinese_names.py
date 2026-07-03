#!/usr/bin/env python3
"""Backfill Chinese display names for US instruments.

Iterates ``etf_info`` rows where ``market='US'`` and ``name_zh`` is NULL,
asks East Money for each symbol's Chinese name via the
``EastMoneyZhProvider``, and writes the result back.  Idempotent —
re-running on a fully-populated table is a no-op.

Usage
-----
    # 1) Dry-run — print what *would* be updated, no DB writes.
    python scripts/backfill_us_chinese_names.py --dry-run

    # 2) Commit — actually update rows.
    python scripts/backfill_us_chinese_names.py --commit

    # 3) Commit with a smaller batch and slower pacing.
    python scripts/backfill_us_chinese_names.py --commit \\
        --batch-size 25 --sleep 0.6

Notes
-----
* The provider caches each (secid, symbol) for 24h, so duplicate symbols
  (rare) don't hit the network twice.
* Throttled to one request per ``--sleep`` seconds to stay well below
  East Money's free-tier limits.
* Run on a single backend / scheduler pod.  Do not parallelize across
  workers without external coordination.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.data.providers.eastmoney_zh_provider import EastMoneyZhProvider
from app.models.etf import ETFInfo


logger = logging.getLogger("backfill_us_zh")


def _select_targets(db: Session) -> list[ETFInfo]:
    """Return US instruments that still need a Chinese name."""
    stmt = (
        select(ETFInfo)
        .where(ETFInfo.market == "US")
        .where(ETFInfo.name_zh.is_(None))
        .order_by(ETFInfo.code)
    )
    return list(db.scalars(stmt).all())


def _symbol_of(code: str) -> str:
    """Strip the ``.US`` suffix to get the raw ticker for East Money."""
    return code.split(".", 1)[0] if "." in code else code


def _run(
    *,
    commit: bool,
    batch_size: int,
    sleep_seconds: float,
    max_rows: int | None,
) -> None:
    db = SessionLocal()
    provider = EastMoneyZhProvider()
    targets = _select_targets(db)
    if max_rows is not None:
        targets = targets[:max_rows]

    total = len(targets)
    logger.info(
        "Found %d US instruments needing name_zh (commit=%s, batch=%d, sleep=%.2fs)",
        total, commit, batch_size, sleep_seconds,
    )
    if total == 0:
        db.close()
        return

    updated = 0
    skipped = 0
    failed = 0

    try:
        for idx, row in enumerate(targets, start=1):
            symbol = _symbol_of(row.code)
            try:
                name_zh = provider.fetch_chinese_name(
                    symbol, market="US", exchange=row.exchange,
                )
            except Exception as exc:  # noqa: BLE001 — defensive: provider already swallows
                failed += 1
                logger.warning("provider raised for %s: %s", row.code, exc)
                name_zh = None

            if not name_zh:
                skipped += 1
                logger.debug("no name_zh for %s (exchange=%s)", row.code, row.exchange)
            else:
                row.name_zh = name_zh
                updated += 1
                logger.info("[%d/%d] %s -> %s", idx, total, row.code, name_zh)

            # Persist in batches so a long run can checkpoint progress.
            if commit and (idx % batch_size == 0 or idx == total):
                db.commit()
                logger.info("checkpoint: committed up to %d/%d", idx, total)

            # Pace ourselves between API calls.  Skip the sleep on the
            # final iteration.
            if sleep_seconds > 0 and idx < total:
                time.sleep(sleep_seconds)

        if not commit:
            logger.info(
                "Dry-run complete: would update %d rows, skip %d, fail %d",
                updated, skipped, failed,
            )
            db.rollback()
        else:
            db.commit()
            logger.info(
                "Backfill complete: updated %d rows, skipped %d, failed %d",
                updated, skipped, failed,
            )
    finally:
        db.close()


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    g = parser.add_mutually_exclusive_group()
    g.add_argument(
        "--commit",
        action="store_true",
        help="Persist updates to the database (default is dry-run).",
    )
    g.add_argument(
        "--dry-run",
        action="store_true",
        help="Explicitly do a dry run.  This is the default if neither flag is set.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=50,
        help="Commit after every N successful updates (default 50).",
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=0.3,
        help="Seconds to sleep between API calls (default 0.3).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional cap on number of rows processed (for debugging).",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable debug-level logging.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    _run(
        commit=args.commit,
        batch_size=args.batch_size,
        sleep_seconds=args.sleep,
        max_rows=args.limit,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())