import contextlib
import threading
import time
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date

import akshare as ak
import pandas as pd

from app.core.exceptions import DataProviderError
from app.data.providers.base import DataProvider, ETFInfo, MarketHours

warnings.filterwarnings("ignore")

# Rate limiting: minimum interval between API calls (seconds)
_API_DELAY = 0.3
# Delay between batches (seconds)
_BATCH_DELAY = 2.0
# Max retries per request
_MAX_RETRIES = 3
# Retry backoff base (seconds)
_RETRY_BACKOFF = 1.0
# Number of concurrent workers for historical bar fetching
_MAX_WORKERS = 5


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


class AkshareProvider(DataProvider):
    def __init__(self, prefer_sina: bool = False):
        self._prefer_sina = prefer_sina
        self._em_available = True  # Adaptive: set to False if EM keeps failing
        self._em_fail_count = 0
        self._em_fail_threshold = 2
        self._state_lock = threading.Lock()
        self._limiter = _RateLimiter(_API_DELAY)

    @property
    def name(self) -> str:
        return "akshare"

    def fetch_etf_list(self) -> list[ETFInfo]:
        """获取 A股场内 ETF 列表

        使用 ak.fund_etf_spot_em() 获取全部 ETF
        代码规则：5/51 开头 = 沪市(SH)，其他 = 深市(SZ)
        """
        try:
            df = ak.fund_etf_spot_em()
        except Exception as exc:
            raise DataProviderError(f"获取 ETF 列表失败: {exc}") from exc

        etf_list: list[ETFInfo] = []
        for _, row in df.iterrows():
            raw_code = str(row.get("代码", "")).strip()
            name = str(row.get("名称", "")).strip()

            if not raw_code or not name:
                continue

            if raw_code.startswith("5"):
                exchange = "SH"
            elif raw_code.startswith("1"):
                exchange = "SZ"
            else:
                continue

            full_code = f"{raw_code}.{exchange}"
            etf_list.append(
                ETFInfo(
                    code=full_code,
                    name=name,
                    exchange=exchange,
                    market="A股" if exchange in ("SH", "SZ") else "",
                )
            )

        return etf_list

    def _fetch_daily_bars_em(
        self, code: str, pure_code: str, start_date: date, end_date: date
    ) -> pd.DataFrame:
        """使用东方财富接口获取日线数据."""
        start_str = start_date.strftime("%Y%m%d")
        end_str = end_date.strftime("%Y%m%d")
        df = ak.fund_etf_hist_em(
            symbol=pure_code,
            period="daily",
            start_date=start_str,
            end_date=end_str,
            adjust="qfq",
            timeout=8,
        )
        if df.empty:
            return df

        # 中文列名 -> 英文列名
        rename_map = {
            "日期": "trade_date",
            "开盘": "open",
            "收盘": "close",
            "最高": "high",
            "最低": "low",
            "成交量": "volume",
            "成交额": "amount",
            "振幅": "amplitude",
            "涨跌幅": "change_pct",
            "涨跌额": "change_amount",
            "换手率": "turnover_rate",
        }
        df = df.rename(columns=rename_map)
        df["etf_code"] = code
        if "trade_date" in df.columns:
            df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date
        numeric_cols = ["open", "high", "low", "close", "volume", "amount", "change_pct", "turnover_rate"]
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        return df

    def _fetch_daily_bars_sina(
        self, code: str, pure_code: str, start_date: date, end_date: date
    ) -> pd.DataFrame:
        """使用新浪接口获取日线数据 (fallback)."""
        exchange = code.split(".")[1].lower()
        sina_symbol = f"{exchange}{pure_code}"
        df = ak.fund_etf_hist_sina(symbol=sina_symbol)
        if df.empty:
            return df

        # 过滤日期范围
        df = df[(df["date"] >= start_date) & (df["date"] <= end_date)].copy()
        if df.empty:
            return df

        df = df.rename(columns={"date": "trade_date"})
        df["etf_code"] = code
        # Sina 接口没有 turnover_rate，保留为 NaN；change_pct 从收盘价推导
        for col in ["open", "high", "low", "close", "volume", "amount"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        df = df.sort_values("trade_date").reset_index(drop=True)
        if "close" in df.columns and len(df) > 1:
            df["change_pct"] = df["close"].pct_change() * 100.0
        else:
            df["change_pct"] = pd.NA
        df["turnover_rate"] = pd.NA
        return df

    def _fetch_single_etf(
        self, code: str, start_date: date, end_date: date
    ) -> pd.DataFrame:
        """获取单个 ETF 的日线数据，带自适应限流.

        默认优先使用 EM 接口，检测到 EM 不可用时自动切换为 Sina.
        如果初始化时 prefer_sina=True，则优先使用 Sina 接口（更稳定，适合补跑）.
        """
        pure_code = code.split(".")[0]
        df = pd.DataFrame()

        # If prefer_sina, try Sina first
        if self._prefer_sina:
            self._limiter.acquire()
            try:
                df = self._fetch_daily_bars_sina(code, pure_code, start_date, end_date)
                if not df.empty:
                    return df
            except Exception:
                pass

        # Try EM interface (if still considered available)
        with self._state_lock:
            em_available = self._em_available

        if em_available:
            self._limiter.acquire()
            try:
                df = self._fetch_daily_bars_em(code, pure_code, start_date, end_date)
                if not df.empty:
                    with self._state_lock:
                        self._em_fail_count = 0
                    return df
                # Empty but no error - maybe no data for this period
                with self._state_lock:
                    self._em_fail_count = 0
            except Exception:
                with self._state_lock:
                    self._em_fail_count += 1
                    if self._em_fail_count >= self._em_fail_threshold:
                        self._em_available = False
                        print(
                            f"     [INFO] EM 接口连续失败 {self._em_fail_threshold} 次，"
                            "后续将直接使用 Sina 接口"
                        )

        # Fallback to Sina (or primary if EM is down)
        self._limiter.acquire()
        with contextlib.suppress(Exception):
            df = self._fetch_daily_bars_sina(code, pure_code, start_date, end_date)

        return df

    def fetch_daily_bars(
        self, codes: list[str], start_date: date, end_date: date
    ) -> pd.DataFrame:
        """获取 A股ETF 日线数据

        优先使用 ak.fund_etf_hist_em (东方财富)，失败时回退到
        ak.fund_etf_hist_sina (新浪).

        使用线程池并发请求，并通过全局限速器控制对数据源的总调用频率，
        在提升性能的同时避免触发平台限流.

        返回 DataFrame 列：etf_code, trade_date, open, high, low, close,
                          volume, amount, change_pct, turnover_rate
        """
        all_frames: list[pd.DataFrame] = []

        with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as executor:
            futures = {
                executor.submit(
                    self._fetch_single_etf, code, start_date, end_date
                ): code
                for code in codes
            }
            for future in as_completed(futures):
                code = futures[future]
                try:
                    df = future.result()
                    if not df.empty:
                        all_frames.append(df)
                except Exception as exc:
                    print(f"[AkshareProvider] 获取 {code} 日线数据失败: {exc}")

        if not all_frames:
            return pd.DataFrame()

        result = pd.concat(all_frames, ignore_index=True)

        # 统一列顺序
        ordered_cols = [
            "etf_code", "trade_date", "open", "high", "low", "close",
            "volume", "amount", "change_pct", "turnover_rate",
        ]
        existing_cols = [c for c in ordered_cols if c in result.columns]
        result = result[existing_cols]

        return result

    def fetch_realtime_quotes(self, codes: list[str]) -> pd.DataFrame:
        """获取实时行情"""
        try:
            df = ak.fund_etf_spot_em()
        except Exception as exc:
            raise DataProviderError(f"获取实时行情失败: {exc}") from exc

        if df.empty:
            return pd.DataFrame()

        df["完整代码"] = df["代码"].astype(str).apply(
            lambda c: f"{c}.SH" if c.startswith("5") else f"{c}.SZ"
        )
        mask = df["完整代码"].isin(codes)
        return df[mask].copy()

    def get_market_hours(self, code: str | None = None) -> MarketHours:
        return MarketHours(
            open_time="09:30", close_time="15:00", timezone="Asia/Shanghai"
        )
