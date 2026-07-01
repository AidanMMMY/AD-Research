"""Tushare Pro data provider for China A-share individual stocks.

Tushare Pro is the primary data source for A-share individual stock data:
stock list, daily OHLCV, valuation metrics (PE/PB/market cap),
and financial statements.

API docs: https://tushare.pro  积分与频次说明: https://tushare.pro/document/1?doc_id=31

Free tier (注册即可):
  - stock_basic: 5000 stocks × 1 point = ~5000 points (one-time)
  - daily: ~5000 stocks × 2 points = ~10000 points/day
  - daily_basic: ~5000 stocks × 0.2 points = ~1000 points/day

Rate limit: free tier allows ~200 req/min with 5000 points/day cap.
We use a conservative delay to stay well within limits.
"""

import contextlib
import logging
import threading
import time
from datetime import date, datetime
from typing import Any

import pandas as pd
import tushare as ts

from app.config import get_settings
from app.core.exceptions import DataProviderError
from app.data.providers.base import DataProvider, ETFInfo, MarketHours

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Rate limiting constants
# ---------------------------------------------------------------------------
_API_DELAY = 0.5  # seconds between API calls
_BATCH_DELAY = 3.0  # seconds between batches (after every ~200 calls)
_MAX_WORKERS = 5  # max concurrent workers for batch fetching
_RETRIES = 2

# Tushare daily() returns at most ~5000 rows per call (entire market).
# We stay well within the 200 req/min rate limit with _API_DELAY=0.5.


# Strings that indicate the user's Tushare tier lacks permission for a
# particular endpoint (e.g. ``new_share`` requires higher 积分).
_PERMISSION_ERROR_MARKERS = (
    "权限不足",
    "无权限",
    "权限",  # generic catch-all: "您没有该接口权限", "无访问权限", etc.
    "积分",
    "permission",
    "forbidden",
    "401",
    "403",
)


def _is_tushare_permission_error(message: str) -> bool:
    """Heuristic check for Tushare permission / quota errors."""
    lowered = message.lower()
    return any(marker.lower() in lowered for marker in _PERMISSION_ERROR_MARKERS)


def derive_market(ts_code: str | None) -> str:
    """Derive internal market code (SH/SZ/BJ) from a Tushare ``ts_code``."""
    if not ts_code or "." not in ts_code:
        return ""
    suffix = ts_code.split(".")[-1].upper()
    if suffix in ("SH", "SZ", "BJ"):
        return suffix
    if suffix == "SSE":
        return "SH"
    if suffix == "SZSE":
        return "SZ"
    if suffix == "BSE":
        return "BJ"
    return suffix


def derive_board(ts_code: str | None) -> str:
    """Derive A-share board from a Tushare ``ts_code`` prefix.

    Mapping:
      * 60xxxx / 00xxxx -> 主板
      * 30xxxx          -> 创业板
      * 68xxxx          -> 科创板
      * 8xxxxx / 92xxxx -> 北交所
    """
    if not ts_code:
        return "主板"
    code = ts_code.split(".")[0]
    market = derive_market(ts_code)
    if market == "BJ":
        if code.startswith(("8", "92", "43")):
            return "北交所"
        return "主板"
    if code.startswith("68"):
        return "科创板"
    if code.startswith("30"):
        return "创业板"
    return "主板"


def compute_listing_status(
    issue_date: date | None,
    list_date: date | None,
    today: date | None = None,
) -> str:
    """Compute the listing event status given the two key dates."""
    if today is None:
        today = date.today()
    if list_date and list_date <= today:
        return "listed"
    if issue_date and issue_date <= today:
        return "subscribing"
    if list_date or issue_date:
        return "upcoming"
    return "unknown"



class _RateLimiter:
    """Thread-safe rate limiter enforcing a minimum interval between acquires."""

    def __init__(self, min_interval: float):
        self.min_interval = min_interval
        self._last_acquire = 0.0
        self._lock = threading.Lock()

    def acquire(self) -> None:
        """Block until at least ``min_interval`` seconds have passed since last acquire."""
        with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_acquire
            if elapsed < self.min_interval:
                time.sleep(self.min_interval - elapsed)
                now = time.monotonic()
            self._last_acquire = now


# Mapping: Tushare exchange codes to our internal format
_EXCHANGE_MAP: dict[str, str] = {
    "SSE": "SH",
    "SZSE": "SZ",
    "BSE": "BJ",
}


def _to_internal_code(ts_code: str) -> str:
    """Convert Tushare ts_code (000001.SZ) to internal code (000001.SZ).

    Both Tushare ts_code and our internal code use SH/SZ/BJ suffixes,
    so this is a passthrough. We keep it for clarity and future compatibility.
    """
    return ts_code


def _to_ts_code(internal_code: str) -> str:
    """Convert internal code (000001.SZ) to Tushare ts_code (000001.SZ).

    Both Tushare ts_code and our internal code use SH/SZ/BJ suffixes,
    so this is a passthrough.
    """
    return internal_code


class TushareProvider(DataProvider):
    """Tushare Pro data provider for A-share individual stocks.

    Primary data source for:
      - A-share stock discovery (stock_basic)
      - Daily OHLCV bars (daily)
      - Valuation metrics (daily_basic): PE, PB, market cap, turnover
      - Financial statements (income_vip, balancesheet_vip)
    """

    def __init__(self):
        token = get_settings().tushare_token
        if not token:
            raise DataProviderError(
                "TUSHARE_TOKEN is not configured. Set it in .env file. "
                "Get a token at https://tushare.pro/register"
            )
        self._pro = ts.pro_api(token)
        self._limiter = _RateLimiter(_API_DELAY)

    @property
    def name(self) -> str:
        return "tushare"

    # ------------------------------------------------------------------
    # Health Check
    # ------------------------------------------------------------------

    def check_health(self) -> bool:
        """Verify Tushare API connectivity with a lightweight call."""
        try:
            self._limiter.acquire()
            df = self._pro.stock_basic(
                exchange="", list_status="L",
                fields="ts_code", limit=1,
            )
            return isinstance(df, pd.DataFrame) and not df.empty
        except Exception:
            logger.exception("Tushare health check failed")
            return False

    # ------------------------------------------------------------------
    # Stock Discovery — fetch A-share stock list from Tushare
    # ------------------------------------------------------------------

    def fetch_etf_list(self) -> list[ETFInfo]:
        """Fetch A-share stock list from Tushare stock_basic.

        Returns stocks as ETFInfo with instrument_type implicitly set to "STOCK"
        by the caller (pipeline). The provider only deals with raw data.

        Markets covered: SSE (SH), SZSE (SZ), BSE (BJ).
        Only L-listed (正常上市) stocks are included.
        """

        all_stocks: list[ETFInfo] = []
        exchanges_map: dict[str, str] = {
            "SSE": "SH",
            "SZSE": "SZ",
            "BSE": "BJ",
        }

        for ts_exchange, internal_exchange in exchanges_map.items():
            try:
                self._limiter.acquire()
                df = self._pro.stock_basic(
                    exchange=ts_exchange,
                    list_status="L",
                    fields="ts_code,symbol,name,area,industry,list_date,market",
                )
            except Exception as exc:
                raise DataProviderError(
                    f"Tushare stock_basic({ts_exchange}) failed: {exc}"
                ) from exc

            if df is None or df.empty:
                continue

            for _, row in df.iterrows():
                ts_code = str(row.get("ts_code", ""))
                name = str(row.get("name", ""))
                area = str(row.get("area", ""))
                industry = str(row.get("industry", ""))
                list_date_val = row.get("list_date")

                if not ts_code or not name:
                    continue

                internal_code = _to_internal_code(ts_code)

                # Parse listing date (Tushare returns YYYYMMDD as string or int)
                inception_date: date | None = None
                if list_date_val and str(list_date_val).isdigit():
                    try:
                        inception_date = datetime.strptime(
                            str(list_date_val), "%Y%m%d"
                        ).date()
                    except (ValueError, TypeError):
                        pass

                all_stocks.append(
                    ETFInfo(
                        code=internal_code,
                        name=name,
                        market="A股",
                        exchange=internal_exchange,
                        category=industry,  # industry as category for compatibility
                        industry=industry or None,
                        inception_date=inception_date,
                        list_date=inception_date,
                        instrument_type="STOCK",
                    )
                )

            # Small delay between exchanges
            time.sleep(0.5)

        logger.info(
            "[TushareProvider] Fetched %d A-share stocks from stock_basic",
            len(all_stocks),
        )
        return all_stocks

    # ------------------------------------------------------------------
    # Listing / IPO — fetch upcoming and recently-listed A-share IPO events
    # ------------------------------------------------------------------

    def fetch_new_share(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch IPO / listing events from Tushare ``new_share``.

        Args:
            start_date: Optional ``YYYYMMDD`` start of issue_date window.
            end_date: Optional ``YYYYMMDD`` end of issue_date window.

        Returns:
            List of raw record dicts from ``new_share``. Each dict is in
            Tushare's native format. The pipeline is responsible for
            mapping to the ``listing_events`` table.

        Free-tier fallback: ``new_share`` requires Tushare积分. If the call
        raises a permission / 积分 error, transparently fall back to
        ``stock_basic`` with ``list_date`` in the recent 30-day window.
        Returns ``[]`` if both endpoints return no rows.
        """
        params: dict[str, Any] = {}
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date

        try:
            self._limiter.acquire()
            df = self._pro.new_share(**params)
        except Exception as exc:
            error_text = str(exc) or exc.__class__.__name__
            if _is_tushare_permission_error(error_text):
                logger.warning(
                    "[TushareProvider] new_share denied (积分/权限), "
                    "falling back to stock_basic: %s",
                    error_text,
                )
                return self._fallback_recent_listings(lookback_days=30)
            raise DataProviderError(
                f"Tushare new_share({params}) failed: {exc}"
            ) from exc

        if df is None or df.empty:
            return []

        records: list[dict[str, Any]] = []
        for _, row in df.iterrows():
            record: dict[str, Any] = {}
            for col in df.columns:
                val = row[col]
                if val is None:
                    record[col] = None
                elif hasattr(val, "isoformat"):
                    record[col] = val
                else:
                    record[col] = val
            records.append(record)
        return records

    def _fallback_recent_listings(self, lookback_days: int = 30) -> list[dict[str, Any]]:
        """Fallback: fetch recently-listed stocks from stock_basic.

        Returns rows with the same shape as ``new_share`` so the pipeline
        can process them uniformly. ``issue_date`` and ``list_date`` are
        set to the same value (the actual list_date).
        """
        try:
            self._limiter.acquire()
            df = self._pro.stock_basic(
                list_status="L",
                fields="ts_code,name,list_date,industry",
            )
        except Exception as exc:
            logger.warning(
                "[TushareProvider] stock_basic fallback also failed: %s",
                exc,
            )
            return []

        if df is None or df.empty:
            return []

        cutoff = (date.today() - pd.Timedelta(days=lookback_days))
        records: list[dict[str, Any]] = []
        for _, row in df.iterrows():
            raw_list_date = row.get("list_date")
            if not raw_list_date or not str(raw_list_date).isdigit():
                continue
            try:
                parsed = datetime.strptime(str(raw_list_date), "%Y%m%d").date()
            except (ValueError, TypeError):
                continue
            if parsed < cutoff:
                continue
            records.append({
                "ts_code": row.get("ts_code"),
                "sub_code": None,
                "name": row.get("name"),
                "ipo_date": parsed,
                "issue_date": parsed,
                "list_date": parsed,
                "price": None,
                "pe": None,
                "limit_amount": None,
                "funds": None,
                "market_amount": None,
                "industry": row.get("industry"),
                "sponsor": None,
                "underwriter": None,
            })
        return records

    def fetch_adj_factor(
        self,
        ts_code: str | None = None,
        trade_date: date | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> pd.DataFrame:
        """Fetch cumulative adjustment factors from Tushare ``adj_factor()``.

        Returns a DataFrame with columns:
          etf_code, trade_date, adj_factor

        The adjustment factor is cumulative front-adjusted:
          adj_close = close * adj_factor
        """
        params: dict[str, Any] = {}
        if ts_code:
            params["ts_code"] = _to_ts_code(ts_code)
        if trade_date is not None:
            params["trade_date"] = trade_date.strftime("%Y%m%d")
        if start_date is not None:
            params["start_date"] = start_date.strftime("%Y%m%d")
        if end_date is not None:
            params["end_date"] = end_date.strftime("%Y%m%d")

        try:
            self._limiter.acquire()
            df = self._pro.adj_factor(**params)
        except Exception as exc:
            raise DataProviderError(
                f"Tushare adj_factor({params}) failed: {exc}"
            ) from exc

        if df is None or df.empty:
            return pd.DataFrame(columns=["etf_code", "trade_date", "adj_factor"])

        df = df.rename(columns={"ts_code": "etf_code"})
        df["etf_code"] = df["etf_code"].apply(_to_internal_code)
        if "trade_date" in df.columns:
            df["trade_date"] = pd.to_datetime(
                df["trade_date"], format="%Y%m%d"
            ).dt.date
        if "adj_factor" in df.columns:
            df["adj_factor"] = pd.to_numeric(df["adj_factor"], errors="coerce")

        return df

    # ------------------------------------------------------------------
    # Daily OHLCV Bars
    # ------------------------------------------------------------------

    def fetch_daily_bars(
        self, codes: list[str], start_date: date, end_date: date
    ) -> pd.DataFrame:
        """Fetch daily OHLCV bars for A-share stocks.

        Uses Tushare daily() which supports batch fetching by trade date range.
        Returns DataFrame with standard columns:
          etf_code, trade_date, open, high, low, close, volume, amount,
          pre_close, change_pct, turnover_rate, adj_factor
        """

        if not codes:
            return pd.DataFrame()

        all_frames: list[pd.DataFrame] = []

        # Convert dates to Tushare format (YYYYMMDD)
        start_str = start_date.strftime("%Y%m%d")
        end_str = end_date.strftime("%Y%m%d")

        # Fetch in batches to handle large date ranges efficiently
        # Tushare daily() with ts_code filter fetches per stock; we loop
        for code in codes:
            ts_code = _to_ts_code(code)
            df_daily: pd.DataFrame | None = None
            for attempt in range(_RETRIES + 1):
                try:
                    self._limiter.acquire()
                    df_daily = self._pro.daily(
                        ts_code=ts_code,
                        start_date=start_str,
                        end_date=end_str,
                        fields="ts_code,trade_date,open,high,low,close,vol,amount,"
                               "pre_close,pct_chg,turnover_rate,turnover_rate_f",
                    )
                    break  # success, exit retry loop
                except Exception as exc:
                    if attempt < _RETRIES:
                        logger.warning(
                            "Tushare daily(%s) retry %d/%d: %s",
                            ts_code, attempt + 1, _RETRIES, exc,
                        )
                        time.sleep(1.0 * (attempt + 1))
                    else:
                        logger.error(
                            "Tushare daily(%s) failed after %d retries: %s",
                            ts_code, _RETRIES, exc,
                        )

            if df_daily is None or df_daily.empty:
                continue

            # Standardize column names
            df_daily = df_daily.rename(
                columns={
                    "ts_code": "etf_code",
                    "vol": "volume",
                    "pct_chg": "change_pct",
                }
            )
            df_daily["etf_code"] = df_daily["etf_code"].apply(_to_internal_code)

            # Convert types
            if "trade_date" in df_daily.columns:
                df_daily["trade_date"] = pd.to_datetime(
                    df_daily["trade_date"], format="%Y%m%d"
                ).dt.date

            numeric_cols = [
                "open", "high", "low", "close", "volume", "amount",
                "pre_close", "change_pct", "turnover_rate",
            ]
            for col in numeric_cols:
                if col in df_daily.columns:
                    df_daily[col] = pd.to_numeric(df_daily[col], errors="coerce")

            # Tushare daily_basic has turnover_rate_f (free float),
            # daily() has turnover_rate. Prefer turnover_rate_f if present.
            if "turnover_rate_f" in df_daily.columns:
                mask = df_daily["turnover_rate"].isna()
                df_daily.loc[mask, "turnover_rate"] = df_daily.loc[
                    mask, "turnover_rate_f"
                ]
                df_daily = df_daily.drop(columns=["turnover_rate_f"])

            # Merge adjustment factor for this stock
            try:
                adj_df = self.fetch_adj_factor(
                    ts_code=code, start_date=start_date, end_date=end_date
                )
                if not adj_df.empty:
                    df_daily = df_daily.merge(
                        adj_df, on=["etf_code", "trade_date"], how="left"
                    )
            except Exception:
                logger.warning(
                    "Failed to fetch adj_factor for %s, defaulting to 1.0", code
                )
            df_daily["adj_factor"] = df_daily.get("adj_factor", pd.Series()).fillna(1.0)

            all_frames.append(df_daily)

        if not all_frames:
            return pd.DataFrame(
                columns=[
                    "etf_code", "trade_date", "open", "high", "low", "close",
                    "volume", "amount", "pre_close", "change_pct", "turnover_rate",
                    "adj_factor",
                ]
            )

        result = pd.concat(all_frames, ignore_index=True)

        # Sort by code and trade date
        result = result.sort_values(["etf_code", "trade_date"]).reset_index(drop=True)

        # Keep only the date range requested
        result = result[
            (result["trade_date"] >= start_date) & (result["trade_date"] <= end_date)
        ]

        return result

    # ------------------------------------------------------------------
    # Bulk Daily — single API call for entire market on one date
    # ------------------------------------------------------------------

    def fetch_daily_all_market(self, trade_date: date) -> pd.DataFrame:
        """Fetch daily OHLCV for ALL A-share stocks on a single trade date.

        Uses the Tushare daily() endpoint **without** ts_code, which returns
        the entire market in one API call (~5000+ stocks).  This is 5000×
        more efficient than per-stock looping.

        Tushare daily() with only trade_date:
          - Returns all listed stocks for that date
          - ~5000 rows × 2 pts/row ≈ 10000 pts (free tier = 5000 pts/day)
          - For bulk backfill, spread across multiple days

        Returns DataFrame with standard columns:
          etf_code, trade_date, open, high, low, close, volume, amount,
          pre_close, change_pct, turnover_rate, adj_factor
        """
        trade_date_str = trade_date.strftime("%Y%m%d")

        try:
            self._limiter.acquire()
            df = self._pro.daily(
                trade_date=trade_date_str,
                fields="ts_code,trade_date,open,high,low,close,vol,amount,"
                       "pre_close,pct_chg,turnover_rate,turnover_rate_f",
            )
        except Exception as exc:
            raise DataProviderError(
                f"Tushare daily(all market, {trade_date}) failed: {exc}"
            ) from exc

        if df is None or df.empty:
            return pd.DataFrame(
                columns=[
                    "etf_code", "trade_date", "open", "high", "low", "close",
                    "volume", "amount", "pre_close", "change_pct", "turnover_rate",
                    "adj_factor",
                ]
            )

        # Standardize column names
        df = df.rename(
            columns={
                "ts_code": "etf_code",
                "vol": "volume",
                "pct_chg": "change_pct",
            }
        )
        df["etf_code"] = df["etf_code"].apply(_to_internal_code)

        # Convert types
        if "trade_date" in df.columns:
            df["trade_date"] = pd.to_datetime(
                df["trade_date"], format="%Y%m%d"
            ).dt.date

        numeric_cols = [
            "open", "high", "low", "close", "volume", "amount",
            "pre_close", "change_pct", "turnover_rate",
        ]
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        # Prefer turnover_rate_f (free-float) if present
        if "turnover_rate_f" in df.columns:
            mask = df["turnover_rate"].isna()
            df.loc[mask, "turnover_rate"] = df.loc[mask, "turnover_rate_f"]
            df = df.drop(columns=["turnover_rate_f"])

        # Merge adjustment factors for the entire market on this date
        try:
            adj_df = self.fetch_adj_factor(trade_date=trade_date)
            if not adj_df.empty:
                df = df.merge(adj_df, on=["etf_code", "trade_date"], how="left")
        except Exception:
            logger.warning(
                "Failed to fetch adj_factor for %s, defaulting to 1.0", trade_date
            )
        df["adj_factor"] = df.get("adj_factor", pd.Series()).fillna(1.0)

        logger.info(
            "[TushareProvider] fetch_daily_all_market(%s): %d rows",
            trade_date_str, len(df),
        )
        return df

    # ------------------------------------------------------------------
    # ETF metadata enrichment (fund_basic)
    # ------------------------------------------------------------------

    def fetch_etf_metadata(self) -> pd.DataFrame:
        """Fetch A-share ETF metadata from Tushare ``fund_basic()``.

        Returns a DataFrame with standardized columns suitable for updating
        ``ETFInfo``:
          code, name, manager, category, sub_category, underlying_index,
          inception_date, list_date, fund_size
        """
        try:
            self._limiter.acquire()
            df = self._pro.fund_basic(market="E", status="L")
        except Exception as exc:
            raise DataProviderError(
                f"Tushare fund_basic failed: {exc}"
            ) from exc

        if df is None or df.empty:
            return pd.DataFrame(
                columns=[
                    "code", "name", "manager", "category", "sub_category",
                    "underlying_index", "inception_date", "list_date", "fund_size",
                ]
            )

        column_map = {
            "ts_code": "code",
            "name": "name",
            "management": "manager",
            "fund_type": "category",
            "invest_type": "sub_category",
            "benchmark": "underlying_index",
            "found_date": "inception_date",
            "list_date": "list_date",
            "issue_amount": "fund_size",
        }
        df = df.rename(columns=column_map)
        df["code"] = df["code"].apply(_to_internal_code)

        for col in ("inception_date", "list_date"):
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], format="%Y%m%d", errors="coerce").dt.date

        if "fund_size" in df.columns:
            df["fund_size"] = pd.to_numeric(df["fund_size"], errors="coerce")

        return df

    # ------------------------------------------------------------------
    # Valuation / Market Data (daily_basic)
    # ------------------------------------------------------------------

    def fetch_daily_basic(
        self, ts_code: str | None = None, trade_date: date | None = None,
        start_date: date | None = None, end_date: date | None = None,
    ) -> pd.DataFrame:
        """Fetch daily basic financial indicators for A-share stocks.

        Returns: pe_ttm, pb, total_mv, float_mv, volume_ratio, turnover_rate_f,
                 total_share, float_share, free_share, circ_mv

        Tushare daily_basic supports:
          - Single stock: ts_code + trade_date
          - Market-wide: trade_date only (fetches ALL stocks for that date)
          - Range: start_date + end_date

        Prefer market-wide fetch for efficiency when processing many stocks.
        """
        params: dict[str, Any] = {}

        if ts_code:
            params["ts_code"] = _to_ts_code(ts_code)
        if trade_date is not None:
            params["trade_date"] = trade_date.strftime("%Y%m%d")
        if start_date is not None:
            params["start_date"] = start_date.strftime("%Y%m%d")
        if end_date is not None:
            params["end_date"] = end_date.strftime("%Y%m%d")

        try:
            self._limiter.acquire()
            df = self._pro.daily_basic(**params)
        except Exception as exc:
            raise DataProviderError(
                f"Tushare daily_basic failed: {exc}"
            ) from exc

        if df is None or df.empty:
            return pd.DataFrame(
                columns=[
                    "ts_code", "trade_date", "pe_ttm", "pb", "total_mv",
                    "float_mv", "volume_ratio", "turnover_rate_f",
                    "total_share", "float_share", "free_share", "circ_mv",
                ]
            )

        # Standardize
        df["etf_code"] = df["ts_code"].apply(_to_internal_code)
        if "trade_date" in df.columns:
            df["trade_date"] = pd.to_datetime(df["trade_date"], format="%Y%m%d").dt.date

        return df

    def fetch_daily_basic_batch(
        self, codes: list[str], trade_date: date
    ) -> pd.DataFrame:
        """Fetch daily_basic for a batch of stocks on a given date.

        Uses the market-wide endpoint (trade_date only, no ts_code) which is
        much more efficient than per-stock calls. Then filters to requested codes.
        """
        try:
            df = self.fetch_daily_basic(trade_date=trade_date)
        except DataProviderError:
            logger.exception(
                "Tushare daily_basic batch fetch failed for %s", trade_date
            )
            return pd.DataFrame()

        if df is None or df.empty:
            return df

        # Filter to our codes
        df = df[df["etf_code"].isin(codes)].copy()
        return df

    # ------------------------------------------------------------------
    # Financial Statements
    # ------------------------------------------------------------------

    def fetch_income_vip(
        self, ts_code: str, start_date: date | None = None,
        end_date: date | None = None, limit: int = 4,
    ) -> pd.DataFrame:
        """Fetch income statement (利润表) for a single A-share stock.

        Uses income_vip (VIP endpoint) which returns normalized quarterly data.
        Free tier access depends on Tushare credit score.

        Key fields: total_revenue, revenue_yoy, n_income, basic_eps,
                    operate_profit, total_profit, grossprofit_margin, netprofit_margin
        """
        params: dict[str, Any] = {
            "ts_code": _to_ts_code(ts_code),
            "limit": str(limit),
        }
        if start_date:
            params["start_date"] = start_date.strftime("%Y%m%d")
        if end_date:
            params["end_date"] = end_date.strftime("%Y%m%d")

        try:
            self._limiter.acquire()
            df = self._pro.income_vip(**params)
        except Exception as exc:
            raise DataProviderError(
                f"Tushare income_vip({ts_code}) failed: {exc}"
            ) from exc

        if df is None or df.empty:
            return pd.DataFrame()

        df["etf_code"] = df["ts_code"].apply(_to_internal_code)
        if "end_date" in df.columns:
            df["end_date"] = pd.to_datetime(df["end_date"], format="%Y%m%d").dt.date

        return df

    def fetch_balancesheet_vip(
        self, ts_code: str, start_date: date | None = None,
        end_date: date | None = None, limit: int = 4,
    ) -> pd.DataFrame:
        """Fetch balance sheet (资产负债表) for a single A-share stock.

        Uses balancesheet_vip endpoint.

        Key fields: total_assets, total_liab, total_hldr_eqy_exc_min_int,
                    current_ratio, debt_to_assets
        """
        params: dict[str, Any] = {
            "ts_code": _to_ts_code(ts_code),
            "limit": str(limit),
        }
        if start_date:
            params["start_date"] = start_date.strftime("%Y%m%d")
        if end_date:
            params["end_date"] = end_date.strftime("%Y%m%d")

        try:
            self._limiter.acquire()
            df = self._pro.balancesheet_vip(**params)
        except Exception as exc:
            raise DataProviderError(
                f"Tushare balancesheet_vip({ts_code}) failed: {exc}"
            ) from exc

        if df is None or df.empty:
            return pd.DataFrame()

        df["etf_code"] = df["ts_code"].apply(_to_internal_code)
        if "end_date" in df.columns:
            df["end_date"] = pd.to_datetime(df["end_date"], format="%Y%m%d").dt.date

        return df

    # ------------------------------------------------------------------
    # Real-time Quotes & Market Hours
    # ------------------------------------------------------------------

    def fetch_realtime_quotes(self, codes: list[str]) -> pd.DataFrame:
        """Fetch real-time quotes (NA for Tushare — not supported on free tier).

        Free Tushare does not have real-time data. Returns empty DataFrame.
        """
        return pd.DataFrame(
            columns=[
                "etf_code", "price", "volume", "open", "high", "low",
                "prev_close", "change_pct",
            ]
        )

    def get_market_hours(self, code: str | None = None) -> MarketHours:
        """A-share market hours: 09:30–15:00 CST (Asia/Shanghai)."""
        return MarketHours(
            open_time="09:30",
            close_time="15:00",
            timezone="Asia/Shanghai",
        )
