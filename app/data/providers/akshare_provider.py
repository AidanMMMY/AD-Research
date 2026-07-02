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


def _coerce_date(value) -> str | None:
    """Coerce a value to a YYYY-MM-DD string, returning None on failure.

    Accepts pandas Timestamp, datetime.date, datetime.datetime, and
    ISO-format strings.
    """
    if value is None:
        return None
    if isinstance(value, str):
        try:
            return pd.to_datetime(value).strftime("%Y-%m-%d")
        except Exception:
            return None
    try:
        return pd.to_datetime(value).strftime("%Y-%m-%d")
    except Exception:
        return None


def _coerce_float(value) -> float | None:
    """Coerce a value to float, returning None on failure or NaN."""
    if value is None:
        return None
    try:
        result = float(value)
        import math
        if math.isnan(result):
            return None
        return result
    except (TypeError, ValueError):
        return None


def _coerce_ppi_month(value) -> str | None:
    """Parse PPI 'YYYY年MM月份' strings to YYYY-MM-01."""
    if value is None:
        return None
    if not isinstance(value, str):
        return _coerce_date(value)
    import re
    match = re.match(r"(\d{4})年(\d{1,2})月份", value.strip())
    if not match:
        return _coerce_date(value)
    year, month = match.group(1), match.group(2).zfill(2)
    return f"{year}-{month}-01"


def _coerce_chinese_date(value) -> str | None:
    """Parse 'YYYY年MM月DD日' strings to YYYY-MM-DD."""
    if value is None or not isinstance(value, str):
        return _coerce_date(value)
    import re
    match = re.match(r"(\d{4})年(\d{1,2})月(\d{1,2})日", value.strip())
    if not match:
        return _coerce_date(value)
    y, m, d = match.groups()
    return f"{y}-{int(m):02d}-{int(d):02d}"

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

        df = df.rename(columns={"date": "trade_date"})
        df["etf_code"] = code
        # Sina 接口没有 turnover_rate，保留为 NaN；change_pct 从收盘价推导
        for col in ["open", "high", "low", "close", "volume", "amount"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        df = df.sort_values("trade_date").reset_index(drop=True)
        # Compute change_pct on the FULL sorted DataFrame BEFORE filtering by date range
        if "close" in df.columns and len(df) > 1:
            df["change_pct"] = df["close"].pct_change() * 100.0
        else:
            df["change_pct"] = pd.NA
        df["turnover_rate"] = pd.NA

        # 过滤日期范围
        df = df[(df["trade_date"] >= start_date) & (df["trade_date"] <= end_date)].copy()
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
                    # 单个 ETF 最多等 60 秒，避免某只 ETF 网络请求 hang 死拖垮整批
                    df = future.result(timeout=60)
                    if not df.empty:
                        all_frames.append(df)
                except TimeoutError:
                    print(f"[AkshareProvider] 获取 {code} 日线数据超时，跳过")
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

    # ------------------------------------------------------------------
    # China macro indicators (akshare ``macro_china_*`` family).
    #
    # Each method returns ``list[dict]`` shaped as:
    #     [{"code", "period": YYYY-MM-DD, "value", "name_zh", "unit"}, ...]
    # The fetch is best-effort: if the upstream endpoint changes shape,
    # is rate-limited, or returns no data, the method logs and returns
    # an empty list so the scheduler job can keep running.
    # ------------------------------------------------------------------

    def fetch_china_macro_gdp(self) -> list[dict]:
        """GDP 年率报告 (%). akshare: macro_china_gdp_yearly."""
        try:
            df = ak.macro_china_gdp_yearly()
        except Exception as exc:
            print(f"[AkshareProvider] fetch_china_macro_gdp failed: {exc}")
            return []

        if df is None or df.empty:
            return []

        out: list[dict] = []
        for _, row in df.iterrows():
            period = _coerce_date(row.get("日期"))
            value = _coerce_float(row.get("今值"))
            if period is None or value is None:
                continue
            out.append({
                "code": "gdp_yoy",
                "period": period,
                "value": value,
                "name_zh": "GDP 年率",
                "unit": "%",
            })
        return out

    def fetch_china_macro_cpi(self) -> list[dict]:
        """CPI 月率报告 (%). akshare: macro_china_cpi_monthly."""
        try:
            df = ak.macro_china_cpi_monthly()
        except Exception as exc:
            print(f"[AkshareProvider] fetch_china_macro_cpi failed: {exc}")
            return []

        if df is None or df.empty:
            return []

        out: list[dict] = []
        for _, row in df.iterrows():
            period = _coerce_date(row.get("日期"))
            value = _coerce_float(row.get("今值"))
            if period is None or value is None:
                continue
            out.append({
                "code": "cpi_yoy",
                "period": period,
                "value": value,
                "name_zh": "CPI 月率",
                "unit": "%",
            })
        return out

    def fetch_china_macro_ppi(self) -> list[dict]:
        """PPI 月度同比增长 (%). akshare: macro_china_ppi (当月同比增长)."""
        try:
            df = ak.macro_china_ppi()
        except Exception as exc:
            print(f"[AkshareProvider] fetch_china_macro_ppi failed: {exc}")
            return []

        if df is None or df.empty:
            return []

        out: list[dict] = []
        for _, row in df.iterrows():
            period = _coerce_ppi_month(row.get("月份"))
            value = _coerce_float(row.get("当月同比增长"))
            if period is None or value is None:
                continue
            out.append({
                "code": "ppi_yoy",
                "period": period,
                "value": value,
                "name_zh": "PPI 同比增长",
                "unit": "%",
            })
        return out

    def fetch_china_macro_m2(self) -> list[dict]:
        """M2 货币供应年率 (%). akshare: macro_china_m2_yearly."""
        try:
            df = ak.macro_china_m2_yearly()
        except Exception as exc:
            print(f"[AkshareProvider] fetch_china_macro_m2 failed: {exc}")
            return []

        if df is None or df.empty:
            return []

        out: list[dict] = []
        for _, row in df.iterrows():
            period = _coerce_date(row.get("日期"))
            value = _coerce_float(row.get("今值"))
            if period is None or value is None:
                continue
            out.append({
                "code": "m2_yoy",
                "period": period,
                "value": value,
                "name_zh": "M2 货币供应年率",
                "unit": "%",
            })
        return out

    def fetch_china_macro_pmi(self) -> list[dict]:
        """官方制造业 PMI. akshare: macro_china_pmi_yearly."""
        try:
            df = ak.macro_china_pmi_yearly()
        except Exception as exc:
            print(f"[AkshareProvider] fetch_china_macro_pmi failed: {exc}")
            return []

        if df is None or df.empty:
            return []

        out: list[dict] = []
        for _, row in df.iterrows():
            period = _coerce_date(row.get("日期"))
            value = _coerce_float(row.get("今值"))
            if period is None or value is None:
                continue
            out.append({
                "code": "pmi_manufacturing",
                "period": period,
                "value": value,
                "name_zh": "官方制造业 PMI",
                "unit": "",
            })
        return out

    def fetch_china_macro_shibor(self) -> list[dict]:
        """SHIBOR 各期限 (%). akshare: macro_china_shibor_all.

        Each tenor (O/N, 1W, 2W, 1M, 3M, 6M, 9M, 1Y) becomes its own
        indicator code so the frontend can plot them independently.
        """
        try:
            df = ak.macro_china_shibor_all()
        except Exception as exc:
            print(f"[AkshareProvider] fetch_china_macro_shibor failed: {exc}")
            return []

        if df is None or df.empty:
            return []

        tenors = [
            ("O/N", "shibor_on", "SHIBOR 隔夜"),
            ("1W", "shibor_1w", "SHIBOR 1周"),
            ("2W", "shibor_2w", "SHIBOR 2周"),
            ("1M", "shibor_1m", "SHIBOR 1月"),
            ("3M", "shibor_3m", "SHIBOR 3月"),
            ("6M", "shibor_6m", "SHIBOR 6月"),
            ("9M", "shibor_9m", "SHIBOR 9月"),
            ("1Y", "shibor_1y", "SHIBOR 1年"),
        ]
        out: list[dict] = []
        for _, row in df.iterrows():
            period = _coerce_date(row.get("日期"))
            if period is None:
                continue
            for prefix, code, name_zh in tenors:
                value = _coerce_float(row.get(f"{prefix}-定价"))
                if value is None:
                    continue
                out.append({
                    "code": code,
                    "period": period,
                    "value": value,
                    "name_zh": name_zh,
                    "unit": "%",
                })
        return out

    def fetch_china_macro_rrr(self) -> list[dict]:
        """存款准备金率 - 大型/中小金融机构 (%). akshare: macro_china_reserve_requirement_ratio."""
        try:
            df = ak.macro_china_reserve_requirement_ratio()
        except Exception as exc:
            print(f"[AkshareProvider] fetch_china_macro_rrr failed: {exc}")
            return []

        if df is None or df.empty:
            return []

        out: list[dict] = []
        for _, row in df.iterrows():
            period = _coerce_date(row.get("生效时间"))
            if period is None:
                period = _coerce_chinese_date(row.get("生效时间"))
            large = _coerce_float(row.get("大型金融机构-调整后"))
            small = _coerce_float(row.get("中小金融机构-调整后"))
            if period is None:
                continue
            if large is not None:
                out.append({
                    "code": "rrr_large",
                    "period": period,
                    "value": large,
                    "name_zh": "存款准备金率 大型机构",
                    "unit": "%",
                })
            if small is not None:
                out.append({
                    "code": "rrr_small",
                    "period": period,
                    "value": small,
                    "name_zh": "存款准备金率 中小机构",
                    "unit": "%",
                })
        return out
