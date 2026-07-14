#!/usr/bin/env python3
"""Trigger cninfo PDF download + text-extraction via Celery.

Usage:
    poetry run python scripts/trigger_cninfo_pdf_download.py
    poetry run python scripts/trigger_cninfo_pdf_download.py --start-date 2026-01-01
    poetry run python scripts/trigger_cninfo_pdf_download.py --report-type annual
    poetry run python scripts/trigger_cninfo_pdf_download.py --shard-size 100 --no-extract
    poetry run python scripts/trigger_cninfo_pdf_download.py --dry-run

Defaults: start_date=2026-01-01, all 4 report types, download+extract,
shard_size=200 stocks per Celery task.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Ensure project root is on sys.path so ``app.*`` resolves when the script
# is invoked from anywhere.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from app.tasks.cninfo_pdf import download_cninfo_pdfs  # noqa: E402

_ORG_IDS_PATH = _PROJECT_ROOT / "app" / "data" / "static" / "cninfo_org_ids.json"


def _load_ts_codes() -> list[str]:
    if not _ORG_IDS_PATH.exists():
        raise RuntimeError(f"org_id mapping not found at {_ORG_IDS_PATH}")
    data = json.loads(_ORG_IDS_PATH.read_text(encoding="utf-8"))
    return sorted(k for k in data if not k.startswith("_"))


def _validate_date(s: str) -> str:
    """ISO date — raise early so a typo doesn't queue 5400 broken tasks."""
    from datetime import date as _date

    _date.fromisoformat(s)
    return s


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--start-date",
        type=_validate_date,
        default="2026-01-01",
        help="ISO date; only announcement_time >= this (default: 2026-01-01)",
    )
    parser.add_argument(
        "--report-type",
        choices=("annual", "semi", "q1", "q3", "all"),
        default="all",
        help="Report type filter (default: all)",
    )
    parser.add_argument(
        "--shard-size",
        type=int,
        default=200,
        help="Number of stocks per Celery task (default: 200)",
    )
    parser.add_argument(
        "--no-extract",
        action="store_true",
        help="Skip text extraction; only download PDFs.",
    )
    parser.add_argument(
        "--no-download",
        action="store_true",
        help="Skip PDF download; only extract text from existing file_path rows.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print shards without submitting tasks.",
    )
    args = parser.parse_args(argv)

    if args.no_extract and args.no_download:
        print("ERROR: --no-extract and --no-download are mutually exclusive (would do nothing).", file=sys.stderr)
        return 1
    if args.shard_size <= 0:
        print("ERROR: --shard-size must be positive", file=sys.stderr)
        return 1

    all_codes = _load_ts_codes()
    total = len(all_codes)
    shard_size = args.shard_size

    shards: list[tuple[int, int]] = []
    for offset in range(0, total, shard_size):
        limit = min(shard_size, total - offset)
        shards.append((offset, limit))

    print(
        f"Total stocks: {total}, shard size: {shard_size}, tasks: {len(shards)}\n"
        f"  start_date   = {args.start_date}\n"
        f"  report_type  = {args.report_type}\n"
        f"  download     = {not args.no_download}\n"
        f"  extract_text = {not args.no_extract}"
    )

    if args.dry_run:
        for offset, limit in shards:
            print(f"DRY-RUN shard [{offset}:{offset + limit}]")
        return 0

    submitted = 0
    for offset, limit in shards:
        result = download_cninfo_pdfs.delay(
            offset=offset,
            limit=limit,
            start_date=args.start_date,
            report_type=args.report_type,
            download=not args.no_download,
            extract_text=not args.no_extract,
        )
        print(f"Submitted shard [{offset}:{offset + limit}] task_id={result.id}")
        submitted += 1

    print(f"Done. Submitted {submitted} tasks.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
