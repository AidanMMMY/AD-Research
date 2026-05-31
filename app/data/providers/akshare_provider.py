import warnings
from datetime import date
from typing import List

import akshare as ak
import pandas as pd

from app.core.exceptions import DataProviderError
from app.data.providers.base import DataProvider, ETFInfo, MarketHours

warnings.filterwarnings("ignore")


class AkshareProvider(DataProvider):
    @property
    def name(self) -> str:
        return "akshare"

    def fetch_etf_list(self) -> List[ETFInfo]:
        """获取 A股场内 ETF 列表

        使用 ak.fund_etf_spot_em() 获取全部 ETF
        代码规则：5/51 开头 = 沪市(SH)，其他 = 深市(SZ)
        """
        try:
            df = ak.fund_etf_spot_em()
        except Exception as exc:
            raise DataProviderError(f"获取 ETF 列表失败: {exc}") from exc

        etf_list: List[ETFInfo] = []
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
        # Sina 接口没有 change_pct 和 turnover_rate，保留为 NaN
        for col in ["open", "high", "low", "close", "volume", "amount"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        df["change_pct"] = pd.NA
        df["turnover_rate"] = pd.NA
        return df

    def fetch_daily_bars(
        self, codes: List[str], start_date: date, end_date: date
    ) -> pd.DataFrame:
        """获取 A股ETF 日线数据

        优先使用 ak.fund_etf_hist_em (东方财富)，失败时回退到
        ak.fund_etf_hist_sina (新浪).

        返回 DataFrame 列：etf_code, trade_date, open, high, low, close,
                          volume, amount, change_pct, turnover_rate
        """
        all_frames: List[pd.DataFrame] = []
        for code in codes:
            pure_code = code.split(".")[0]
            df = pd.DataFrame()

            # 优先尝试 EM 接口
            try:
                df = self._fetch_daily_bars_em(code, pure_code, start_date, end_date)
            except Exception as exc:
                print(f"[WARN] EM 接口获取 {code} 失败，尝试 Sina 回退: {exc}")
                try:
                    df = self._fetch_daily_bars_sina(code, pure_code, start_date, end_date)
                except Exception as exc2:
                    print(f"[WARN] Sina 接口获取 {code} 也失败: {exc2}")
                    continue

            if df.empty:
                continue

            all_frames.append(df)

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

    def fetch_realtime_quotes(self, codes: List[str]) -> pd.DataFrame:
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

    def get_market_hours(self) -> MarketHours:
        return MarketHours(
            open_time="09:30", close_time="15:00", timezone="Asia/Shanghai"
        )
