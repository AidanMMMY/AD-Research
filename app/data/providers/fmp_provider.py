"""Financial Modeling Prep (FMP) data provider.

FMP free tier: 250 requests/day, US stocks only, EOD quotes,
basic financial statements, key ratios, earnings data.

Used as the primary source for stock discovery and fundamentals.
API docs: https://site.financialmodelingprep.com/developer/docs
"""

import os
import time
from datetime import date, timedelta
from typing import Any

import pandas as pd
import requests

from app.core.exceptions import DataProviderError
from app.data.providers.base import DataProvider, ETFInfo, MarketHours

# Free tier: 250 requests/day → safe at ~1 request every 8 seconds
# for a daily batch of ~250 symbols. For stock discovery (once/week),
# we can afford 1 request per second.
_FREE_TIER_SAFE_DELAY = 1.2  # seconds


def _api_key() -> str:
    key = os.getenv("FMP_API_KEY", "")
    if not key:
        raise DataProviderError(
            "FMP_API_KEY environment variable is not set. "
            "Get a free key at https://site.financialmodelingprep.com/register"
        )
    return key


def _get(endpoint: str, params: dict[str, Any] | None = None) -> Any:
    """Make a GET request to the FMP API."""
    url_params = params or {}
    url_params["apikey"] = _api_key()
    qs = "&".join(f"{k}={v}" for k, v in url_params.items())
    url = f"https://financialmodelingprep.com/api/v3{endpoint}?{qs}"

    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict) and data.get("Error Message"):
            raise DataProviderError(f"FMP API error: {data['Error Message']}")
        return data
    except requests.RequestException as exc:
        raise DataProviderError(f"FMP request failed: {exc}") from exc


_SP500_CSV_URL = (
    "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/"
    "main/data/constituents.csv"
)


def _fetch_sp500_from_public_csv() -> list[ETFInfo]:
    """Fallback S&P 500 source when FMP legacy endpoints are unavailable.

    FMP no longer allows new free API keys to access legacy endpoints such as
    /sp500_constituent. This public dataset is updated regularly and provides
    the current S&P 500 constituent list together with GICS sector data.
    """
    try:
        resp = requests.get(_SP500_CSV_URL, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise DataProviderError(f"Failed to fetch S&P 500 CSV: {exc}") from exc

    df = pd.read_csv(pd.io.common.StringIO(resp.text))
    required = {"Symbol", "Security"}
    if not required.issubset(df.columns):
        raise DataProviderError("S&P 500 CSV has unexpected format")

    result = []
    for _, row in df.iterrows():
        symbol = str(row.get("Symbol", "")).strip().upper()
        name = str(row.get("Security", "")).strip()
        sector = str(row.get("GICS Sector", "")).strip() or None
        industry = str(row.get("GICS Sub-Industry", "")).strip() or None
        if not symbol or not name:
            continue
        result.append(
            ETFInfo(
                code=f"{symbol}.US",
                name=name,
                market="US",
                exchange="NYSE",
                category=sector,
                sector=sector,
                industry=industry,
                currency="USD",
                instrument_type="STOCK",
            )
        )

    result.sort(key=lambda x: x.code)
    return result


# ---------------------------------------------------------------------------
# S&P 500 constituent tickers fetched once and cached. We fetch the full
# list on pipeline init and store it locally to avoid repeated API calls.
# ---------------------------------------------------------------------------

class FMPProvider(DataProvider):
    """Financial Modeling Prep data provider.

    Primary for: US stock discovery (S&P 500 constituents),
    company profiles (sector, industry, market cap),
    financial statements, and key metrics.

    Free tier: 250 requests/day, US stocks only.
    """

    @property
    def name(self) -> str:
        return "fmp"

    # ------------------------------------------------------------------
    # Stock Discovery
    # ------------------------------------------------------------------

    def fetch_etf_list(self) -> list[ETFInfo]:
        """Return empty; use fetch_sp500_list() for stock discovery."""
        return []

    def fetch_sp500_list(self) -> list[ETFInfo]:
        """Fetch S&P 500 constituent list.

        Tries FMP first, then falls back to a public S&P 500 CSV dataset
        because FMP legacy endpoints are no longer available to new free keys.

        Each stock is mapped to ETFInfo with:
          code = TICKER.US, market = US, instrument_type = STOCK

        Returns a list of ETFInfo dataclass instances.
        """
        # Try FMP legacy endpoint first
        try:
            data = _get("/sp500_constituent")
            if isinstance(data, list) and data:
                result = []
                for item in data:
                    symbol = str(item.get("symbol", "")).upper()
                    name = str(item.get("name", "") or item.get("companyName", ""))
                    exchange = str(
                        item.get("exchangeShortName", "") or item.get("exchange", "")
                    )
                    if not symbol or not name:
                        continue
                    result.append(
                        ETFInfo(
                            code=f"{symbol}.US",
                            name=name,
                            market="US",
                            exchange=exchange or "NYSE",
                            currency="USD",
                            instrument_type="STOCK",
                        )
                    )
                result.sort(key=lambda x: x.code)
                return result
        except DataProviderError as exc:
            print(f"[FMPProvider] FMP S&P 500 failed: {exc}")
            print("[FMPProvider] Falling back to public S&P 500 CSV...")

        # Fallback to public CSV
        try:
            return _fetch_sp500_from_public_csv()
        except DataProviderError as exc:
            print(f"[FMPProvider] Fallback CSV failed: {exc}")
            return []

    def fetch_company_profile(self, code: str) -> dict[str, Any] | None:
        """Fetch detailed company profile for a single stock.

        Returns dict with: name, sector, industry, market_cap, exchange,
        currency, country, ipo_date, description, website, employees, ceo.
        """
        symbol = code
        if code.endswith(".US"):
            symbol = code[:-3]

        try:
            data = _get(f"/profile/{symbol}")
        except DataProviderError:
            return None

        if not isinstance(data, list) or not data:
            return None

        item = data[0]
        return {
            "name": item.get("companyName", ""),
            "sector": item.get("sector", ""),
            "industry": item.get("industry", ""),
            "market_cap": item.get("mktCap"),
            "exchange": item.get("exchangeShortName", ""),
            "currency": item.get("currency", "USD"),
            "country": item.get("country", ""),
            "ipo_date": item.get("ipoDate"),
            "description": item.get("description", ""),
            "website": item.get("website", ""),
            "employees": item.get("fullTimeEmployees"),
            "ceo": item.get("ceo", ""),
        }

    # ------------------------------------------------------------------
    # Daily OHLCV Bars (fallback for yfinance/Tiingo)
    # ------------------------------------------------------------------

    def fetch_daily_bars(
        self, codes: list[str], start_date: date, end_date: date
    ) -> pd.DataFrame:
        """Fetch EOD bars from FMP's historical-price-full endpoint.

        FMP provides up to 30 years of history. Free tier limited to
        US stocks. One API call per ticker.

        Returns DataFrame with columns:
          etf_code, trade_date, open, high, low, close, volume, amount
        """
        rows = []
        for code in codes:
            symbol = code[:-3] if code.endswith(".US") else code
            try:
                data = _get(
                    f"/historical-price-full/{symbol}",
                    {
                        "from": start_date.isoformat(),
                        "to": end_date.isoformat(),
                    },
                )
            except DataProviderError as exc:
                print(f"[FMPProvider] Failed to fetch {code}: {exc}")
                continue

            if not isinstance(data, dict):
                continue

            historical = data.get("historical", [])
            if not historical:
                continue

            for item in historical:
                trade_date_val = date.fromisoformat(item.get("date", ""))
                if trade_date_val < start_date or trade_date_val > end_date:
                    continue

                close_price = float(item.get("close", 0) or 0)
                volume_val = int(item.get("volume", 0) or 0)
                rows.append(
                    {
                        "etf_code": code,
                        "trade_date": trade_date_val,
                        "open": float(item.get("open", 0) or 0),
                        "high": float(item.get("high", 0) or 0),
                        "low": float(item.get("low", 0) or 0),
                        "close": close_price,
                        "volume": volume_val,
                        "amount": volume_val * close_price,
                    }
                )

            time.sleep(_FREE_TIER_SAFE_DELAY)

        if not rows:
            return pd.DataFrame(
                columns=[
                    "etf_code", "trade_date", "open", "high", "low",
                    "close", "volume", "amount",
                ]
            )

        df = pd.DataFrame(rows)
        df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date
        return df

    # ------------------------------------------------------------------
    # Financial Statements (Phase 3: AI earnings analysis)
    # ------------------------------------------------------------------

    def fetch_income_statement(
        self, code: str, limit: int = 4
    ) -> list[dict[str, Any]]:
        """Fetch quarterly income statements."""
        symbol = code[:-3] if code.endswith(".US") else code
        try:
            data = _get(
                f"/income-statement/{symbol}",
                {"period": "quarter", "limit": str(limit)},
            )
        except DataProviderError:
            return []
        return data if isinstance(data, list) else []

    def fetch_balance_sheet(
        self, code: str, limit: int = 4
    ) -> list[dict[str, Any]]:
        """Fetch quarterly balance sheets."""
        symbol = code[:-3] if code.endswith(".US") else code
        try:
            data = _get(
                f"/balance-sheet-statement/{symbol}",
                {"period": "quarter", "limit": str(limit)},
            )
        except DataProviderError:
            return []
        return data if isinstance(data, list) else []

    def fetch_cash_flow(
        self, code: str, limit: int = 4
    ) -> list[dict[str, Any]]:
        """Fetch quarterly cash flow statements."""
        symbol = code[:-3] if code.endswith(".US") else code
        try:
            data = _get(
                f"/cash-flow-statement/{symbol}",
                {"period": "quarter", "limit": str(limit)},
            )
        except DataProviderError:
            return []
        return data if isinstance(data, list) else []

    def fetch_key_metrics(self, code: str) -> dict[str, Any] | None:
        """Fetch key financial ratios and metrics (TTM)."""
        symbol = code[:-3] if code.endswith(".US") else code
        try:
            data = _get(f"/key-metrics-ttm/{symbol}")
        except DataProviderError:
            return None
        if isinstance(data, list) and data:
            return data[0]
        return None

    def fetch_earnings_calendar(
        self, code: str
    ) -> list[dict[str, Any]]:
        """Fetch upcoming and historical earnings dates."""
        symbol = code[:-3] if code.endswith(".US") else code
        try:
            data = _get(f"/historical/earning_calendar/{symbol}", {"limit": "8"})
        except DataProviderError:
            return []
        return data if isinstance(data, list) else []

    # ------------------------------------------------------------------
    # Real-time Quotes & Market Hours
    # ------------------------------------------------------------------

    def fetch_realtime_quotes(self, codes: list[str]) -> pd.DataFrame:
        """Fetch latest quotes from FMP's quote endpoint.

        Batch endpoint supports multiple symbols: /quote/AAPL,SPY,QQQ
        """
        symbols = [c[:-3] if c.endswith(".US") else c for c in codes]
        symbol_str = ",".join(symbols)
        try:
            data = _get(f"/quote/{symbol_str}")
        except DataProviderError as exc:
            raise DataProviderError(f"FMP quote fetch failed: {exc}") from exc

        if not isinstance(data, list):
            return pd.DataFrame()

        rows = []
        for item in data:
            symbol = str(item.get("symbol", ""))
            code = f"{symbol}.US"
            current = float(item.get("price", 0) or 0)
            prev = float(item.get("previousClose", 0) or 0)
            change_pct = float(item.get("changesPercentage", 0) or 0)

            rows.append(
                {
                    "etf_code": code,
                    "price": current,
                    "volume": int(item.get("volume", 0) or 0),
                    "open": float(item.get("open", 0) or 0),
                    "high": float(item.get("dayHigh", 0) or 0),
                    "low": float(item.get("dayLow", 0) or 0),
                    "prev_close": prev,
                    "change_pct": round(change_pct, 4),
                }
            )

        return pd.DataFrame(rows)

    def get_market_hours(self, code: str | None = None) -> MarketHours:
        return MarketHours(
            open_time="09:30",
            close_time="16:00",
            timezone="America/New_York",
        )

    def check_health(self) -> bool:
        """Check FMP API is accessible."""
        try:
            data = _get("/quote/AAPL")
            return isinstance(data, list) and len(data) > 0
        except DataProviderError:
            return False
