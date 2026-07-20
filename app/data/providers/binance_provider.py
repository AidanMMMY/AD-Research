"""Binance data provider for cryptocurrency daily bars.

Binance free tier (public REST endpoints):
  - No API key required for klines, ticker, exchangeInfo, ping
  - 1200 request weight per minute
  - Each kline/candlestick request = 1 weight for up to 500 candles
  - Each ticker/24hr request for multiple symbols = 40 weight

Rate limit: 0.1 s sleep per request (~10 req/s) leaves comfortable headroom.
"""

import json
import time
from datetime import date, datetime, timedelta, timezone

import pandas as pd
import requests

from app.core.exceptions import DataProviderError
from app.data.providers.base import DataProvider, ETFInfo, MarketHours

# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------
# Binance allows 1200 request weight per minute.
# At 10 req/s = 600 req/min, we are well within the limit.
_REQUEST_DELAY = 0.1  # seconds between requests


# ---------------------------------------------------------------------------
# Curated list of major spot trading pairs (all quoted in USDT)
# ---------------------------------------------------------------------------
_DEFAULT_CRYPTO = [
    ("BTC.US", "Bitcoin", "Layer1"),
    ("ETH.US", "Ethereum", "Layer1"),
    ("BNB.US", "BNB", "Exchange"),
    ("SOL.US", "Solana", "Layer1"),
    ("XRP.US", "XRP", "Payments"),
    ("DOGE.US", "Dogecoin", "Meme"),
    ("ADA.US", "Cardano", "Layer1"),
    ("AVAX.US", "Avalanche", "Layer1"),
    ("DOT.US", "Polkadot", "Layer1"),
    ("LINK.US", "Chainlink", "Oracle"),
    ("MATIC.US", "Polygon", "L2"),
    ("UNI.US", "Uniswap", "DeFi"),
    ("ATOM.US", "Cosmos", "Layer1"),
    ("LTC.US", "Litecoin", "Payments"),
    ("ETC.US", "Ethereum Classic", "Layer1"),
    ("FIL.US", "Filecoin", "Storage"),
    ("APT.US", "Aptos", "Layer1"),
    ("ARB.US", "Arbitrum", "L2"),
    ("OP.US", "Optimism", "L2"),
    ("NEAR.US", "NEAR Protocol", "Layer1"),
    ("INJ.US", "Injective", "DeFi"),
    ("SUI.US", "Sui", "Layer1"),
    ("PEPE.US", "Pepe", "Meme"),
    ("WIF.US", "dogwifhat", "Meme"),
    ("BONK.US", "Bonk", "Meme"),
]

# Minimal subset for faster initial tests
_DEFAULT_CRYPTO_TOP = _DEFAULT_CRYPTO[:10]


class BinanceProvider(DataProvider):
    @property
    def name(self) -> str:
        return "binance"

    """Binance data provider for cryptocurrency daily bars.

    Uses Binance's public REST API (no authentication required for the
    endpoints used in Phase 1).

    Internal instrument code convention: ``SYMBOL.US`` (e.g. ``BTC.US``).
    The provider maps this to Binance trading pair ``BTCUSDT``.
    """

    # Public REST hosts, tried in order. ``api.binance.com`` is geo-blocked
    # in some regions (e.g. mainland-China ECS where it returns HTTP 451 or
    # times out); ``data-api.binance.vision`` is Binance's official
    # market-data-only host serving the same public endpoints (klines,
    # ticker, exchangeInfo, ping) without geo restrictions.
    BASE_URLS = (
        "https://api.binance.com",
        "https://data-api.binance.vision",
    )
    BASE_URL = BASE_URLS[0]  # backwards-compatible alias

    # ------------------------------------------------------------------
    # HTTP helper
    # ------------------------------------------------------------------

    def _get(self, path: str, params: dict | None = None, timeout: int = 30):
        """GET a public endpoint, failing over across ``BASE_URLS``.

        Returns the parsed JSON body. Raises ``DataProviderError`` when
        every host fails, so callers can distinguish a real outage from
        an empty (but successful) response.
        """
        last_exc: Exception | None = None
        for base in self.BASE_URLS:
            try:
                resp = requests.get(f"{base}{path}", params=params, timeout=timeout)
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException as exc:
                last_exc = exc
                continue
        raise DataProviderError(f"Binance request {path} failed on all hosts: {last_exc}")

    # ------------------------------------------------------------------
    # DataProvider interface
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "binance"

    # ------------------------------------------------------------------
    # Symbol mapping
    # ------------------------------------------------------------------

    @staticmethod
    def to_binance_symbol(code: str) -> str:
        """Convert internal code to Binance trading pair.

        >>> BinanceProvider.to_binance_symbol("BTC.US")
        'BTCUSDT'
        >>> BinanceProvider.to_binance_symbol("ETH.US")
        'ETHUSDT'
        """
        if code.endswith(".US"):
            return code[:-3] + "USDT"
        return code + "USDT"

    @staticmethod
    def from_binance_symbol(symbol: str) -> str:
        """Convert Binance trading pair to internal code.

        >>> BinanceProvider.from_binance_symbol("BTCUSDT")
        'BTC.US'
        """
        if symbol.endswith("USDT"):
            return symbol[:-4] + ".US"
        return symbol + ".US"

    # ------------------------------------------------------------------
    # Instrument list
    # ------------------------------------------------------------------

    def fetch_etf_list(self) -> list[ETFInfo]:
        """Return a curated list of major crypto trading pairs.

        Uses a hard-coded list of top spot pairs.  Callers that need the
        full Binance exchange list can use ``fetch_exchange_info()``
        which returns every available spot trading pair.
        """
        instruments: list[ETFInfo] = []
        for code, name, category in _DEFAULT_CRYPTO:
            instruments.append(
                ETFInfo(
                    code=code,
                    name=name,
                    market="CRYPTO",
                    exchange="BINANCE",
                    category=category,
                    currency="USDT",
                    instrument_type="CRYPTO",
                )
            )
        return instruments

    def fetch_exchange_info(self) -> list[dict]:
        """Return available spot trading pairs from Binance exchangeInfo.

        Returns a list of dicts with keys: ``symbol``, ``baseAsset``,
        ``quoteAsset``, ``status``.
        """
        data = self._get("/api/v3/exchangeInfo")

        pairs: list[dict] = []
        for s in data.get("symbols", []):
            if s.get("status") == "TRADING" and s.get("quoteAsset") == "USDT":
                pairs.append(
                    {
                        "symbol": s["symbol"],
                        "baseAsset": s["baseAsset"],
                        "quoteAsset": s["quoteAsset"],
                        "status": s["status"],
                    }
                )
        return pairs

    # ------------------------------------------------------------------
    # Daily bars
    # ------------------------------------------------------------------

    def fetch_daily_bars(
        self,
        codes: list[str],
        start_date: date,
        end_date: date,
    ) -> pd.DataFrame:
        """Fetch daily klines (candlesticks) from Binance.

        Calls ``GET /api/v3/klines`` for each symbol individually because
        Binance does not provide a batch-kline endpoint.  Symbol-level
        failures are logged and skipped; the method returns whatever data
        was successfully retrieved, but raises ``DataProviderError`` when
        request-level failures left zero rows (i.e. the feed is down)
        instead of silently returning an empty frame.

        Args:
            codes: Internal instrument codes (e.g. ``["BTC.US", "ETH.US"]``).
            start_date: Inclusive start date.
            end_date: Inclusive end date.

        Returns:
            DataFrame with columns: ``etf_code``, ``trade_date``, ``open``,
            ``high``, ``low``, ``close``, ``volume``, ``amount``,
            ``change_pct``.  Empty DataFrame only when every request
            succeeded but Binance returned no candles.
        """
        COLUMNS = [
            "etf_code", "trade_date",
            "open", "high", "low", "close",
            "volume", "amount", "change_pct",
        ]

        # Binance timestamps are UTC ms since epoch. The daily kline's
        # open_time is 00:00:00 UTC. We extend end_date by one day so that
        # the target day's candle (open_time = target_date 00:00 UTC) is
        # included even when the container runs in Asia/Shanghai timezone.
        start_dt = datetime.combine(
            start_date, datetime.min.time(), tzinfo=timezone.utc
        )
        end_dt = datetime.combine(
            end_date + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc
        )
        start_ms = int(start_dt.timestamp() * 1000)
        end_ms = int(end_dt.timestamp() * 1000)

        rows: list[dict] = []
        failed_codes: list[str] = []
        for code in codes:
            symbol = self.to_binance_symbol(code)
            params = {
                "symbol": symbol,
                "interval": "1d",
                "startTime": start_ms,
                "endTime": end_ms,
                "limit": 1000,  # max per request; enough for 4 years of daily bars
            }

            try:
                candles = self._get("/api/v3/klines", params=params)
            except DataProviderError as exc:
                print(f"[BinanceProvider] Failed to fetch {code}: {exc}")
                failed_codes.append(code)
                time.sleep(_REQUEST_DELAY)
                continue

            if not isinstance(candles, list) or not candles:
                time.sleep(_REQUEST_DELAY)
                continue

            # Binance kline format (array of arrays):
            # [0] open_time_ms  [1] open   [2] high   [3] low
            # [4] close         [5] volume  [6] close_time_ms
            # [7] quote_volume  [8] trades [9] taker_buy_base_vol
            # [10] taker_buy_quote_vol  [11] ignore
            for candle in candles:
                try:
                    open_time_ms = candle[0]
                    # Binance daily candles open at 00:00:00 UTC; pin the
                    # conversion to UTC so the trade date does not depend
                    # on the container's local timezone.
                    trade_date_val = datetime.fromtimestamp(
                        open_time_ms / 1000, tz=timezone.utc
                    ).date()
                    open_px = float(candle[1])
                    close_px = float(candle[4])
                    rows.append(
                        {
                            "etf_code": code,
                            "trade_date": trade_date_val,
                            "open": open_px,
                            "high": float(candle[2]),
                            "low": float(candle[3]),
                            "close": close_px,
                            "volume": float(candle[5]),
                            "amount": float(candle[7]),   # quote volume in USDT
                            "change_pct": (
                                (close_px - open_px)
                                / open_px * 100
                                if open_px != 0
                                else 0
                            ),
                        }
                    )
                except (IndexError, ValueError, TypeError) as exc:
                    print(
                        f"[BinanceProvider] Skipping malformed candle "
                        f"for {code}: {exc}"
                    )
                    continue

            time.sleep(_REQUEST_DELAY)

        if not rows:
            if failed_codes:
                # Every request-level failure with zero rows landed means
                # the feed is down (geo-block, DNS, outage) — fail loudly
                # instead of returning an empty frame that downstream
                # pipelines would record as a fake "success".
                raise DataProviderError(
                    f"Binance klines failed for all {len(failed_codes)} "
                    f"symbol(s): {', '.join(failed_codes)}"
                )
            return pd.DataFrame(columns=COLUMNS)

        df = pd.DataFrame(rows)
        df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date
        return df

    # ------------------------------------------------------------------
    # Real-time quotes
    # ------------------------------------------------------------------

    def fetch_realtime_quotes(self, codes: list[str]) -> pd.DataFrame:
        """Fetch 24hr ticker statistics via ``GET /api/v3/ticker/24hr``.

        Binance's 24hr ticker endpoint accepts an optional ``symbols``
        parameter as a JSON array; a single request covers all symbols
        (weight = 2 per symbol, or 40 weight for all symbols).

        Returns:
            DataFrame with columns: ``etf_code``, ``price``,
            ``price_change_pct``, ``high``, ``low``, ``volume``, ``amount``.
        """
        COLUMNS = [
            "etf_code", "price", "price_change_pct",
            "high", "low", "volume", "amount",
        ]

        symbols = [self.to_binance_symbol(c) for c in codes]
        params = {"symbols": json.dumps(symbols, separators=(",", ":"))}

        data = self._get("/api/v3/ticker/24hr", params=params)

        if not isinstance(data, list):
            return pd.DataFrame(columns=COLUMNS)

        rows: list[dict] = []
        for ticker in data:
            internal_code = self.from_binance_symbol(ticker.get("symbol", ""))
            rows.append(
                {
                    "etf_code": internal_code,
                    "price": float(ticker.get("lastPrice", 0)),
                    "price_change_pct": float(
                        ticker.get("priceChangePercent", 0)
                    ),
                    "high": float(ticker.get("highPrice", 0)),
                    "low": float(ticker.get("lowPrice", 0)),
                    "volume": float(ticker.get("volume", 0)),
                    "amount": float(ticker.get("quoteVolume", 0)),
                }
            )

        return pd.DataFrame(rows)

    # ------------------------------------------------------------------
    # Market hours
    # ------------------------------------------------------------------

    def get_market_hours(self, code: str | None = None) -> MarketHours:
        """Crypto markets are open 24/7."""
        return MarketHours(
            open_time="00:00",
            close_time="23:59",
            timezone="UTC",
        )

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    def check_health(self) -> bool:
        """Check whether any Binance public host is accessible."""
        try:
            self._get("/api/v3/ping", timeout=10)
            return True
        except DataProviderError:
            return False
