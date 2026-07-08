"""Measure the new bulk Tushare pull against the real 1527-ETF universe."""
import sys
import time

from app.core.database import SessionLocal
from app.data.providers.tushare_provider import TushareProvider
from app.models.etf import ETFHoldingUnavailable, ETFInfo


def main() -> int:
    period = sys.argv[1] if len(sys.argv) > 1 else "20250331"
    db = SessionLocal()
    try:
        # 1. List of 1527 active A-share ETFs
        etfs = (
            db.query(ETFInfo)
            .filter(
                ETFInfo.market == "A股",
                ETFInfo.instrument_type == "ETF",
                ETFInfo.status == "active",
            )
            .all()
        )
        # 2. Skip blacklisted (33 structurally-unavailable)
        blacklisted = {
            r.etf_code
            for r in db.query(ETFHoldingUnavailable.etf_code).all()
        }
        etf_codes = [e.code for e in etfs if e.code not in blacklisted]
        print(f"== bulk pull against {len(etf_codes)} ETFs (period={period}) ==")
        print(f"   ({len(etfs)} total active A-share ETFs, {len(blacklisted)} blacklisted)")

        # 3. The bulk call
        provider = TushareProvider()
        t0 = time.time()
        mapping, missing = provider.fetch_etf_holdings_batch(
            ts_codes=etf_codes, period=period,
        )
        elapsed = time.time() - t0

        # 4. Report
        total_rows = sum(len(df) for df in mapping.values())
        covered_count = len(etf_codes) - len(missing)
        all_funds_in_response = len(mapping)
        print(f"  elapsed:        {elapsed:.2f}s ({elapsed/60:.2f} min)")
        print(f"  covered:        {covered_count}/{len(etf_codes)} of OUR ETFs")
        print(f"  total funds:    {all_funds_in_response} in Tushare response (incl. .OF)")
        print(f"  missing:        {len(missing)} (will Akshare-fallback)")
        print(f"  total rows:     {total_rows}")
        print()
        print("Legacy baseline: 31.5 minutes (1527 sequential calls)")
        print(f"Speedup:         {31.5*60 / elapsed:.1f}x")
        print(f"Sample missing:  {missing[:10]}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
