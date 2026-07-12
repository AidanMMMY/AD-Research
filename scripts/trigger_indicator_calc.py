#!/usr/bin/env python3
"""Trigger A-share indicator calculation via Celery.

Usage:
    python3 scripts/trigger_indicator_calc.py
    python3 scripts/trigger_indicator_calc.py --full-history
    python3 scripts/trigger_indicator_calc.py --target-date 2026-07-10
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure project root is on sys.path.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from app.tasks.indicator import calculate_indicators


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--target-date",
        type=str,
        default=None,
        help="ISO date string (YYYY-MM-DD); default is None (latest available)",
    )
    parser.add_argument(
        "--full-history",
        action="store_true",
        help="Recalculate indicators for every historical trade date",
    )
    parser.add_argument(
        "--market",
        type=str,
        default="A股",
        help="Market filter (default: A股)",
    )
    args = parser.parse_args(argv)

    result = calculate_indicators.delay(
        target_date=args.target_date,
        full_history=args.full_history,
        market_filter=args.market,
    )
    print(f"Indicator calculation task submitted: task_id={result.id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
