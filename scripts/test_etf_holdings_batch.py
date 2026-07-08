"""Smoke test for fetch_etf_holdings_batch (Phase 2)."""
import sys
import time

from app.data.providers.tushare_provider import TushareProvider


def main() -> int:
    p = TushareProvider()
    sample = [
        "510300.SH",  # 华泰柏瑞沪深300ETF
        "510500.SH",  # 南方中证500ETF
        "159919.SZ",  # 嘉实沪深300ETF
        "512880.SH",  # 国泰中证全指证券公司ETF
        "588200.SH",  # 科创50ETF
        "510880.SH",  # 华泰柏瑞红利ETF
        "159915.SZ",  # 易方达创业板ETF
        "510050.SH",  # 华夏上证50ETF
        "159995.SZ",  # 华夏国证半导体芯片ETF
        "512760.SH",  # 国泰CES半导体芯片ETF
    ]
    period = sys.argv[1] if len(sys.argv) > 1 else "20250331"
    print(f"== fetch_etf_holdings_batch (period={period}) ==")
    t0 = time.time()
    mapping, missing = p.fetch_etf_holdings_batch(ts_codes=sample, period=period)
    elapsed = time.time() - t0
    print(f"  elapsed:        {elapsed:.2f}s")
    print(f"  covered:        {len(mapping)}/{len(sample)}")
    print(f"  missing:        {missing}")
    if mapping:
        etf = next(iter(mapping))
        df = mapping[etf]
        print(f"  sample etf {etf}: {len(df)} rows")
        cols = [c for c in ["etf_code", "holding_code", "weight", "market_value", "holdings_as_of_date"] if c in df.columns]
        print(df[cols].head(5).to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
