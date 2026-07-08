"""Verify the legacy single-ETF code path still works after refactor."""
import time
from app.data.providers.tushare_provider import TushareProvider

p = TushareProvider()
for code in ["510300.SH", "159919.SZ", "512880.SH"]:
    t0 = time.time()
    df = p.fetch_etf_holdings(ts_code=code)
    elapsed = time.time() - t0
    print(f"  {code}: {elapsed:.2f}s, {len(df)} rows")
    if not df.empty:
        print(df[["etf_code", "holding_code", "weight", "market_value", "holdings_as_of_date"]].head(3).to_string(index=False))
        print()
