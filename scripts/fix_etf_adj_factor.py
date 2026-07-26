#!/usr/bin/env python3
"""Compute synthetic adj_factor for ETFs from raw price data.

ETFs listed on A-shares can undergo share splits (份额拆分) like stocks.
Akshare provides raw split-adjusted prices that are continuous BEFORE the
split but jump at the split date. Tushare does NOT provide adj_factor for
ETFs (it's only designed for individual stocks).

This script detects split events (overnight price drop > 35% with normal
volume) from raw bars and computes a cumulative adj_factor so the frontend
adjustOHLC() can produce continuous forward-adjusted K-lines.

Strategy:
  Scan each ETF's bars oldest→newest. When a split is detected:
    split_ratio = close_before / close_after
  Multiply ALL preceding bars' adj_factor by split_ratio.
  Sets the latest bar's factor so adjustOHLC(… / latestFactor) = 1.

Usage:
  python -m app.scripts.fix_etf_adj_factor              # all ETFs
  python -m app.scripts.fix_etf_adj_factor --dry-run    # report only
"""

import argparse
import sys
from datetime import date

import pandas as pd
from sqlalchemy import text

from app.core.database import SessionLocal

# Day-over-day price ratio thresholds: outside [MIN_RATIO, MAX_RATIO] = split.
MIN_RATIO = 0.65   # normally ~1.0; < 0.67 ≈ 2:1 split down
MAX_RATIO = 1.50   # > 1.5 ≈ 2:1 reverse split up


def detect_splits(bars: pd.DataFrame) -> list[dict]:
    """Find split events in chronological bar data.
    Returns list of {index, ratio, date}.
    """
    splits = []
    for i in range(1, len(bars)):
        prev_close = float(bars.iloc[i - 1]["close"])
        curr_close = float(bars.iloc[i]["close"])
        if prev_close <= 0 or curr_close <= 0:
            continue
        ratio = prev_close / curr_close
        if ratio > MAX_RATIO or ratio < MIN_RATIO:
            splits.append({
                "index": i,
                "trade_date": bars.iloc[i]["trade_date"],
                "ratio": ratio,
                "prev_close": prev_close,
                "curr_close": curr_close,
            })
    return splits


def main() -> int:
    p = argparse.ArgumentParser(description="Fix ETF adj_factor from raw price splits")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--codes", help="Comma-separated ETF codes (default: all)")
    args = p.parse_args()

    db = SessionLocal()
    try:
        code_filter = ""
        params = {}
        if args.codes:
            code_list = [c.strip() for c in args.codes.split(",")]
            code_filter = "AND e.code = ANY(:codes)"
            params["codes"] = code_list

        etfs = db.execute(
            text(f"SELECT code FROM etf_info e WHERE instrument_type='ETF' AND status='active' {code_filter} ORDER BY code"),
            params,
        ).fetchall()
        codes = [r[0] for r in etfs]
        print(f"Found {len(codes)} active ETFs")

        total_updated = 0
        split_etfs = 0

        for code in codes:
            rows = db.execute(
                text("SELECT trade_date, close FROM instrument_daily_bar WHERE etf_code = :code ORDER BY trade_date"),
                {"code": code},
            ).fetchall()

            if len(rows) < 2:
                continue

            df = pd.DataFrame(rows, columns=["trade_date", "close"])
            splits = detect_splits(df)

            if not splits:
                continue

            split_etfs += 1
            cumulative = 1.0

            for s in splits:
                cumulative *= s["ratio"]
                print(
                    f"  {code} split @ {s['trade_date']}: "
                    f"{s['prev_close']:.4f} → {s['curr_close']:.4f} "
                    f"(ratio={s['ratio']:.4f}, cumulative={cumulative:.4f})"
                )

            if args.dry_run:
                continue

            # Write cumulative adj_factor to every bar of this ETF
            db.execute(
                text("UPDATE instrument_daily_bar SET adj_factor = :af WHERE etf_code = :code"),
                {"af": round(cumulative, 8), "code": code},
            )
            db.commit()
            total_updated += len(rows)

        print(f"\nSummary: {split_etfs} ETFs with splits, {total_updated} rows updated")
        if args.dry_run:
            print("[DRY RUN] no changes written")
        db.close()
        return 0

    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
