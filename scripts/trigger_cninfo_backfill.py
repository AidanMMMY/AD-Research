#!/usr/bin/env python3
"""Trigger cninfo periodic-report backfill via Celery.

Usage:
    python3 scripts/trigger_cninfo_backfill.py
    python3 scripts/trigger_cninfo_backfill.py --shard-size 500
    python3 scripts/trigger_cninfo_backfill.py --years 1 --type annual
    python3 scripts/trigger_cninfo_backfill.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Ensure project root is on sys.path.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from app.tasks.cninfo import backfill_cninfo_reports

_ORG_IDS_PATH = _PROJECT_ROOT / "app" / "data" / "static" / "cninfo_org_ids.json"


def _load_ts_codes() -> list[str]:
    if not _ORG_IDS_PATH.exists():
        raise RuntimeError(f"org_id mapping not found at {_ORG_IDS_PATH}")
    data = json.loads(_ORG_IDS_PATH.read_text(encoding="utf-8"))
    return sorted(k for k in data if not k.startswith("_"))


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--shard-size",
        type=int,
        default=500,
        help="Number of stocks per Celery task (default: 500)",
    )
    parser.add_argument(
        "--years",
        type=int,
        default=5,
        help="How many years back from today to fetch (default: 5)",
    )
    parser.add_argument(
        "--type",
        choices=("annual", "semi", "q1", "q3", "all"),
        default="all",
        help="Report type to fetch (default: all)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print shards without submitting tasks",
    )
    args = parser.parse_args(argv)

    all_codes = _load_ts_codes()
    total = len(all_codes)
    shard_size = args.shard_size

    if shard_size <= 0:
        print("ERROR: --shard-size must be positive", file=sys.stderr)
        return 1

    tasks: list[tuple[int, int]] = []
    for offset in range(0, total, shard_size):
        limit = min(shard_size, total - offset)
        tasks.append((offset, limit))

    print(f"Total stocks: {total}, shard size: {shard_size}, tasks: {len(tasks)}")

    if args.dry_run:
        for offset, limit in tasks:
            print(f"DRY-RUN shard [{offset}:{offset + limit}]")
        return 0

    submitted = 0
    for offset, limit in tasks:
        result = backfill_cninfo_reports.delay(
            offset=offset,
            limit=limit,
            years=args.years,
            report_type=args.type,
        )
        print(f"Submitted shard [{offset}:{offset + limit}] task_id={result.id}")
        submitted += 1

    print(f"Done. Submitted {submitted} tasks.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
