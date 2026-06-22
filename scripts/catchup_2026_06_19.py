#!/usr/bin/env python3
"""Catch up 2026-06-19 data: bars, indicators, scores, signals."""

import sys
from datetime import date

sys.path.insert(0, "/Users/aidanliu/Documents/vibe-trading/etf-research-platform")

from app.core.scheduler import (
    run_a_share_etl,
    run_indicator_calculation,
    run_score_calculation,
    run_signal_generation,
)

TARGET = date(2026, 6, 19)

if __name__ == "__main__":
    print(f"=== Catching up data for {TARGET} ===")
    run_a_share_etl(target_date=TARGET, prefer_sina=True)
    run_indicator_calculation(target_date=TARGET)
    run_score_calculation(target_date=TARGET)
    run_signal_generation(target_date=TARGET)
    print("=== Done ===")
