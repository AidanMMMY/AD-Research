"""Run the full ETFHoldingsPipeline against the production DB.

Measures wall-clock time of the new bulk-pull strategy vs the
legacy 31.5 min per-ETF loop.
"""
import sys
import time
from datetime import datetime

from app.core.database import SessionLocal
from app.data.pipelines.etf_holdings import ETFHoldingsPipeline


def main() -> int:
    period = sys.argv[1] if len(sys.argv) > 1 else "20250331"
    print(f"== full pipeline run (period={period}) ==")
    db = SessionLocal()
    try:
        t0 = time.time()
        pipeline = ETFHoldingsPipeline(db)
        result = pipeline.run()
        elapsed = time.time() - t0
        print(f"  total elapsed:  {elapsed:.2f}s ({elapsed/60:.2f} min)")
        print(f"  status:         {result.status if hasattr(result, 'status') else result.success}")
        print(f"  records:        {result.records}")
        if result.warnings:
            print(f"  warnings:       {result.warnings}")
        if result.error:
            print(f"  error:          {result.error}")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
