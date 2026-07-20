"""Finnhub data provider for US equity data.

Finnhub free tier: 60 requests/minute, real-time quotes, WebSocket,
news sentiment, basic fundamentals. Rate-limited to 1 req/sec for safety.

API docs: https://finnhub.io/docs/api
"""

import os
import re
import time
from datetime import date, timedelta
from typing import Any
from urllib.parse import urlencode

import pandas as pd
import requests

from app.core.exceptions import DataProviderError
from app.data.providers.base import DataProvider, ETFInfo, MarketHours


# ---------------------------------------------------------------------------
# Free tier rate limit: 60 requests/minute → safe at 1 request/second with
# a short sleep between calls.
# ---------------------------------------------------------------------------
_FREE_TIER_SAFE_DELAY = 1.1  # seconds


def _api_key() -> str:
    key = os.getenv("FINNHUB_API_KEY", "")
    if not key:
        raise DataProviderError(
            "FINNHUB_API_KEY environment variable is not set. "
            "Get a free key at https://finnhub.io/register"
        )
    return key


def _redact_api_key(message: object) -> str:
    """Mask API-key query params in URLs embedded in error messages.

    ``requests`` exceptions include the full request URL, and the Finnhub
    key travels as a ``token=`` query param — never propagate it raw.
    """
    return re.sub(r"(?i)(token|apikey|api_key)=[^&\s]+", r"\1=***", str(message))


def _get(endpoint: str, params: dict[str, Any] | None = None) -> dict:
    """Make a GET request to the Finnhub API."""
    url_params = params or {}
    url_params["token"] = _api_key()
    url = f"https://finnhub.io/api/v1{endpoint}?{urlencode(url_params)}"

    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict) and data.get("error"):
            raise DataProviderError(f"Finnhub API error: {data['error']}")
        return data
    except requests.RequestException as exc:
        raise DataProviderError(f"Finnhub request failed: {_redact_api_key(exc)}") from exc


# ---------------------------------------------------------------------------
# Known US ETF list — broad market, sector, factor, and thematic ETFs.
# These are the most liquid and widely traded US ETFs.
# ---------------------------------------------------------------------------
_US_ETF_LIST: list[dict[str, str]] = [
    # Broad market
    {"code": "SPY.US", "name": "SPDR S&P 500 ETF Trust", "category": "大盘", "exchange": "NYSE"},
    {"code": "IVV.US", "name": "iShares Core S&P 500 ETF", "category": "大盘", "exchange": "NYSE"},
    {"code": "VOO.US", "name": "Vanguard S&P 500 ETF", "category": "大盘", "exchange": "NYSE"},
    {"code": "VTI.US", "name": "Vanguard Total Stock Market ETF", "category": "大盘", "exchange": "NYSE"},
    {"code": "ITOT.US", "name": "iShares Core S&P Total US Stock Market ETF", "category": "大盘", "exchange": "NYSE"},
    {"code": "QQQ.US", "name": "Invesco QQQ Trust", "category": "大盘", "exchange": "NASDAQ"},
    {"code": "QQQM.US", "name": "Invesco NASDAQ 100 ETF", "category": "大盘", "exchange": "NASDAQ"},
    {"code": "DIA.US", "name": "SPDR Dow Jones Industrial Average ETF", "category": "大盘", "exchange": "NYSE"},
    {"code": "IWM.US", "name": "iShares Russell 2000 ETF", "category": "小盘", "exchange": "NYSE"},
    {"code": "IJR.US", "name": "iShares Core S&P Small-Cap ETF", "category": "小盘", "exchange": "NYSE"},
    {"code": "MDY.US", "name": "SPDR S&P MidCap 400 ETF", "category": "中盘", "exchange": "NYSE"},
    {"code": "IJH.US", "name": "iShares Core S&P Mid-Cap ETF", "category": "中盘", "exchange": "NYSE"},
    # International
    {"code": "EFA.US", "name": "iShares MSCI EAFE ETF", "category": "国际", "exchange": "NYSE"},
    {"code": "EEM.US", "name": "iShares MSCI Emerging Markets ETF", "category": "新兴市场", "exchange": "NYSE"},
    {"code": "VXUS.US", "name": "Vanguard Total International Stock ETF", "category": "国际", "exchange": "NASDAQ"},
    {"code": "VEA.US", "name": "Vanguard FTSE Developed Markets ETF", "category": "国际", "exchange": "NYSE"},
    {"code": "IEFA.US", "name": "iShares Core MSCI EAFE ETF", "category": "国际", "exchange": "NYSE"},
    {"code": "VWO.US", "name": "Vanguard FTSE Emerging Markets ETF", "category": "新兴市场", "exchange": "NYSE"},
    # Sector ETFs
    {"code": "XLK.US", "name": "Technology Select Sector SPDR Fund", "category": "科技", "exchange": "NYSE"},
    {"code": "XLF.US", "name": "Financial Select Sector SPDR Fund", "category": "金融", "exchange": "NYSE"},
    {"code": "XLV.US", "name": "Health Care Select Sector SPDR Fund", "category": "医疗", "exchange": "NYSE"},
    {"code": "XLE.US", "name": "Energy Select Sector SPDR Fund", "category": "能源", "exchange": "NYSE"},
    {"code": "XLI.US", "name": "Industrial Select Sector SPDR Fund", "category": "工业", "exchange": "NYSE"},
    {"code": "XLY.US", "name": "Consumer Discretionary Select Sector SPDR", "category": "消费", "exchange": "NYSE"},
    {"code": "XLP.US", "name": "Consumer Staples Select Sector SPDR", "category": "消费", "exchange": "NYSE"},
    {"code": "XLU.US", "name": "Utilities Select Sector SPDR Fund", "category": "公用事业", "exchange": "NYSE"},
    {"code": "XLRE.US", "name": "Real Estate Select Sector SPDR Fund", "category": "房地产", "exchange": "NYSE"},
    {"code": "XLB.US", "name": "Materials Select Sector SPDR Fund", "category": "材料", "exchange": "NYSE"},
    {"code": "SMH.US", "name": "VanEck Semiconductor ETF", "category": "半导体", "exchange": "NYSE"},
    {"code": "SOXX.US", "name": "iShares Semiconductor ETF", "category": "半导体", "exchange": "NASDAQ"},
    # Bonds
    {"code": "BND.US", "name": "Vanguard Total Bond Market ETF", "category": "债券", "exchange": "NASDAQ"},
    {"code": "AGG.US", "name": "iShares Core US Aggregate Bond ETF", "category": "债券", "exchange": "NYSE"},
    {"code": "TLT.US", "name": "iShares 20+ Year Treasury Bond ETF", "category": "债券", "exchange": "NASDAQ"},
    {"code": "LQD.US", "name": "iShares iBoxx $ Inv Grade Corporate Bond ETF", "category": "债券", "exchange": "NYSE"},
    {"code": "HYG.US", "name": "iShares iBoxx $ High Yield Corporate Bond ETF", "category": "债券", "exchange": "NYSE"},
    {"code": "SHY.US", "name": "iShares 1-3 Year Treasury Bond ETF", "category": "债券", "exchange": "NASDAQ"},
    {"code": "IEF.US", "name": "iShares 7-10 Year Treasury Bond ETF", "category": "债券", "exchange": "NASDAQ"},
    {"code": "TIP.US", "name": "iShares TIPS Bond ETF", "category": "债券", "exchange": "NYSE"},
    # Commodities
    {"code": "GLD.US", "name": "SPDR Gold Trust", "category": "黄金", "exchange": "NYSE"},
    {"code": "IAU.US", "name": "iShares Gold Trust", "category": "黄金", "exchange": "NYSE"},
    {"code": "SLV.US", "name": "iShares Silver Trust", "category": "贵金属", "exchange": "NYSE"},
    {"code": "USO.US", "name": "United States Oil Fund", "category": "原油", "exchange": "NYSE"},
    {"code": "UNG.US", "name": "United States Natural Gas Fund", "category": "天然气", "exchange": "NYSE"},
    {"code": "DBC.US", "name": "Invesco DB Commodity Index Tracking Fund", "category": "商品", "exchange": "NYSE"},
    # Real Estate
    {"code": "VNQ.US", "name": "Vanguard Real Estate ETF", "category": "房地产", "exchange": "NYSE"},
    {"code": "SCHH.US", "name": "Schwab US REIT ETF", "category": "房地产", "exchange": "NYSE"},
    # Thematic / Factor
    {"code": "ARKK.US", "name": "ARK Innovation ETF", "category": "创新", "exchange": "NYSE"},
    {"code": "ARKG.US", "name": "ARK Genomic Revolution ETF", "category": "基因", "exchange": "NYSE"},
    {"code": "ICLN.US", "name": "iShares Global Clean Energy ETF", "category": "清洁能源", "exchange": "NASDAQ"},
    {"code": "TAN.US", "name": "Invesco Solar ETF", "category": "太阳能", "exchange": "NYSE"},
    {"code": "LIT.US", "name": "Global X Lithium & Battery Tech ETF", "category": "锂电池", "exchange": "NYSE"},
    {"code": "BOTZ.US", "name": "Global X Robotics & Artificial Intelligence ETF", "category": "AI机器人", "exchange": "NASDAQ"},
    {"code": "AIQ.US", "name": "Global X Artificial Intelligence & Technology ETF", "category": "AI", "exchange": "NASDAQ"},
    {"code": "FINX.US", "name": "Global X FinTech ETF", "category": "金融科技", "exchange": "NASDAQ"},
    {"code": "IBB.US", "name": "iShares Biotechnology ETF", "category": "生物科技", "exchange": "NASDAQ"},
    {"code": "XBI.US", "name": "SPDR S&P Biotech ETF", "category": "生物科技", "exchange": "NYSE"},
    # Dividend / Income
    {"code": "SCHD.US", "name": "Schwab US Dividend Equity ETF", "category": "红利", "exchange": "NYSE"},
    {"code": "VYM.US", "name": "Vanguard High Dividend Yield ETF", "category": "红利", "exchange": "NYSE"},
    {"code": "DVY.US", "name": "iShares Select Dividend ETF", "category": "红利", "exchange": "NASDAQ"},
    {"code": "JEPI.US", "name": "JPMorgan Equity Premium Income ETF", "category": "收入", "exchange": "NYSE"},
    # Leveraged / Inverse
    {"code": "TQQQ.US", "name": "ProShares UltraPro QQQ", "category": "杠杆", "exchange": "NASDAQ"},
    {"code": "SQQQ.US", "name": "ProShares UltraPro Short QQQ", "category": "反向", "exchange": "NASDAQ"},
    {"code": "UPRO.US", "name": "ProShares UltraPro S&P500", "category": "杠杆", "exchange": "NYSE"},
    {"code": "SPXU.US", "name": "ProShares UltraPro Short S&P500", "category": "反向", "exchange": "NYSE"},
    {"code": "TMF.US", "name": "Direxion Daily 20+ Year Treasury Bull 3X", "category": "杠杆", "exchange": "NYSE"},
    {"code": "SOXL.US", "name": "Direxion Daily Semiconductor Bull 3X", "category": "杠杆", "exchange": "NYSE"},
    {"code": "UVXY.US", "name": "ProShares Ultra VIX Short-Term Futures ETF", "category": "波动率", "exchange": "NYSE"},
    # Volatility
    {"code": "VXX.US", "name": "iPath Series B S&P 500 VIX Short-Term Futures ETN", "category": "波动率", "exchange": "NYSE"},
    {"code": "VIXY.US", "name": "ProShares VIX Short-Term Futures ETF", "category": "波动率", "exchange": "NYSE"},
]


class FinnhubProvider(DataProvider):
    """Finnhub data provider for US equity data.

    Free tier: 60 requests/minute, real-time US quotes, company news,
    basic fundamentals, WebSocket streaming.
    """

    @property
    def name(self) -> str:
        return "finnhub"

    def _to_finnhub_symbol(self, code: str) -> str:
        """Convert internal code to Finnhub symbol.

        Finnhub uses plain ticker symbols (e.g. AAPL, SPY) without suffix.
        Strips .US/.HK/.JP suffixes.
        """
        if code.endswith(".US"):
            return code[:-3]
        return code

    # ------------------------------------------------------------------
    # ETF List
    # ------------------------------------------------------------------

    def fetch_etf_list(self) -> list[ETFInfo]:
        """Return a curated list of US ETFs.

        Uses hard-coded list of ~70 highly liquid US ETFs across
        broad market, sector, factor, bond, and commodity categories.
        This avoids burning Finnhub API calls on ETF discovery which
        is rate-limited on the free tier.

        For dynamic ETF discovery, use USStockDiscoveryPipeline
        (FMPProvider) which has higher free tier limits.
        """
        result = []
        for item in _US_ETF_LIST:
            result.append(
                ETFInfo(
                    code=item["code"],
                    name=item["name"],
                    market="US",
                    exchange=item["exchange"],
                    category=item["category"],
                    currency="USD",
                )
            )
        return result

    # ------------------------------------------------------------------
    # Daily OHLCV Bars
    # ------------------------------------------------------------------

    def fetch_daily_bars(
        self, codes: list[str], start_date: date, end_date: date
    ) -> pd.DataFrame:
        """Fetch daily OHLCV bars via Finnhub's stock/candle endpoint.

        Finnhub free tier provides historical candles at daily resolution.

        Returns a DataFrame with columns:
          etf_code, trade_date, open, high, low, close, volume, amount
        """
        from_timestamp = int(
            __import__("datetime").datetime.combine(
                start_date, __import__("datetime").datetime.min.time()
            ).timestamp()
        )
        to_timestamp = int(
            __import__("datetime").datetime.combine(
                end_date, __import__("datetime").datetime.min.time()
            ).timestamp()
        )

        rows = []
        for code in codes:
            symbol = self._to_finnhub_symbol(code)
            try:
                data = _get(
                    "/stock/candle",
                    {
                        "symbol": symbol,
                        "resolution": "D",
                        "from": str(from_timestamp),
                        "to": str(to_timestamp),
                    },
                )
            except DataProviderError as exc:
                print(f"[FinnhubProvider] Failed to fetch {code}: {exc}")
                continue

            if data.get("s") != "ok" or not data.get("t"):
                continue

            timestamps = data["t"]
            opens = data["o"]
            highs = data["h"]
            lows = data["l"]
            closes = data["c"]
            volumes = data["v"]

            for i, ts in enumerate(timestamps):
                trade_date_val = date.fromtimestamp(ts)
                close_price = float(closes[i]) if closes[i] else 0.0
                volume_val = int(volumes[i]) if volumes[i] else 0
                rows.append(
                    {
                        "etf_code": code,
                        "trade_date": trade_date_val,
                        "open": float(opens[i]) if opens[i] else 0.0,
                        "high": float(highs[i]) if highs[i] else 0.0,
                        "low": float(lows[i]) if lows[i] else 0.0,
                        "close": close_price,
                        "volume": volume_val,
                        "amount": volume_val * close_price,
                    }
                )

            # Respect free tier rate limit
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
    # Real-time Quotes
    # ------------------------------------------------------------------

    def fetch_realtime_quotes(self, codes: list[str]) -> pd.DataFrame:
        """Fetch latest quotes via Finnhub's /quote endpoint.

        Returns a DataFrame with columns: etf_code, price, volume,
        open, high, low, prev_close, change_pct.
        """
        rows = []
        for code in codes:
            symbol = self._to_finnhub_symbol(code)
            try:
                data = _get("/quote", {"symbol": symbol})
            except DataProviderError as exc:
                print(f"[FinnhubProvider] Failed quote for {code}: {exc}")
                continue

            current = float(data.get("c", 0) or 0)
            prev = float(data.get("pc", 0) or 0)
            change_pct = ((current - prev) / prev * 100) if prev else 0.0

            rows.append(
                {
                    "etf_code": code,
                    "price": current,
                    "volume": int(data.get("v", 0) or 0),
                    "open": float(data.get("o", 0) or 0),
                    "high": float(data.get("h", 0) or 0),
                    "low": float(data.get("l", 0) or 0),
                    "prev_close": prev,
                    "change_pct": round(change_pct, 4),
                }
            )
            time.sleep(_FREE_TIER_SAFE_DELAY)

        return pd.DataFrame(rows)

    # ------------------------------------------------------------------
    # Company News (for sentiment analysis - Phase 3)
    # ------------------------------------------------------------------

    def fetch_company_news(
        self, code: str, from_date: date, to_date: date
    ) -> list[dict[str, Any]]:
        """Fetch company news articles from Finnhub.

        Free tier includes company news with headline and summary.
        Returns list of article dicts with: headline, summary, url,
        datetime, source, category.
        """
        symbol = self._to_finnhub_symbol(code)
        try:
            data = _get(
                "/company-news",
                {
                    "symbol": symbol,
                    "from": from_date.isoformat(),
                    "to": to_date.isoformat(),
                },
            )
        except DataProviderError as exc:
            print(f"[FinnhubProvider] Failed news for {code}: {exc}")
            return []

        if not isinstance(data, list):
            return []

        return [
            {
                "headline": item.get("headline", ""),
                "summary": item.get("summary", ""),
                "url": item.get("url", ""),
                "datetime": item.get("datetime"),
                "source": item.get("source", ""),
                "category": item.get("category", ""),
            }
            for item in data
        ]

    # ------------------------------------------------------------------
    # Company Profile
    # ------------------------------------------------------------------

    def fetch_company_profile(self, code: str) -> dict[str, Any] | None:
        """Fetch company profile from Finnhub.

        Returns dict with: name, country, currency, exchange, ipo,
        market_cap, share_outstanding, industry, sector, logo, weburl.
        """
        symbol = self._to_finnhub_symbol(code)
        try:
            data = _get("/stock/profile2", {"symbol": symbol})
        except DataProviderError:
            return None

        if not data or not data.get("name"):
            return None

        return {
            "name": data.get("name", ""),
            "country": data.get("country", ""),
            "currency": data.get("currency", ""),
            "exchange": data.get("exchange", ""),
            "ipo": data.get("ipo"),
            "market_cap": data.get("marketCapitalization"),
            "share_outstanding": data.get("shareOutstanding"),
            "sector": data.get("finnhubIndustry", ""),
            "industry": data.get("finnhubIndustry", ""),
            "logo": data.get("logo", ""),
            "weburl": data.get("weburl", ""),
        }

    # ------------------------------------------------------------------
    # Market Hours
    # ------------------------------------------------------------------

    def get_market_hours(self, code: str | None = None) -> MarketHours:
        """Return US market hours (NYSE/NASDAQ): 09:30-16:00 ET."""
        return MarketHours(
            open_time="09:30",
            close_time="16:00",
            timezone="America/New_York",
        )

    # ------------------------------------------------------------------
    # Health Check
    # ------------------------------------------------------------------

    def check_health(self) -> bool:
        """Check Finnhub API is accessible."""
        try:
            _get("/quote", {"symbol": "SPY"})
            return True
        except DataProviderError:
            return False
