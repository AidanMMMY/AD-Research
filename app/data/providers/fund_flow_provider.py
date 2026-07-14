"""免费资金流 akshare Provider (方案 C)。

封装 akshare 的 4 个资金流接口：

* ``stock_individual_fund_flow_rank`` — 个股主力/超大/大/中/小单 资金流
* ``stock_sector_fund_flow_rank``    — 行业 / 概念 / 地域 板块资金流
* ``stock_market_fund_flow``         — 大盘整体 (上证/深证) 资金流
* ``stock_individual_fund_flow``     — 单只股票近 100 日资金流历史

所有方法都使用 ``_RateLimiter`` 限速（akshare 后端常出现 JSONDecodeError /
Connection aborted，单次失败不抛异常，返回 None 让上层兜底）。

约定：返回 list[dict]，每条 dict 的 schema 与 ORM 模型字段保持一致
(``ts_code`` / ``sector_name`` / ``trade_date`` / 数值字段)，方便
Pipeline 直接 list 化入库。
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 限速器 (与 akshare_provider 保持同样的 0.3s 间隔)
# ---------------------------------------------------------------------------


_API_DELAY = 0.3
_BATCH_DELAY = 1.5
_MAX_RETRIES = 2


class _RateLimiter:
    """线程安全的最小间隔限速器。"""

    def __init__(self, min_interval: float) -> None:
        self.min_interval = min_interval
        self._last = 0.0
        self._lock = threading.Lock()

    def acquire(self) -> None:
        with self._lock:
            now = time.monotonic()
            elapsed = now - self._last
            if elapsed < self.min_interval:
                time.sleep(self.min_interval - elapsed)
                now = time.monotonic()
            self._last = now


# ---------------------------------------------------------------------------
# 类型定义
# ---------------------------------------------------------------------------


@dataclass
class IndividualFundFlowRow:
    """单只股票的资金流一行 (今日/历史通用)。"""

    ts_code: str
    trade_date: date
    main_net_inflow: float | None = None
    main_net_pct: float | None = None
    super_large_net: float | None = None
    super_large_pct: float | None = None
    large_net: float | None = None
    large_pct: float | None = None
    medium_net: float | None = None
    medium_pct: float | None = None
    small_net: float | None = None
    small_pct: float | None = None


@dataclass
class SectorFundFlowRow:
    """板块资金流一行。"""

    sector_name: str
    sector_type: str  # '行业' / '概念' / '地域'
    trade_date: date
    main_net_inflow: float | None = None
    main_net_pct: float | None = None
    super_large_net: float | None = None
    large_net: float | None = None
    leading_stock: str | None = None


@dataclass
class MarketFundFlowRow:
    """大盘资金流一行 (ak.stock_market_fund_flow 单日单行)。"""

    trade_date: date
    sh_close: float | None = None
    sh_pct_change: float | None = None
    sz_close: float | None = None
    sz_pct_change: float | None = None
    main_net_inflow: float | None = None
    main_net_pct: float | None = None
    super_large_net: float | None = None
    large_net: float | None = None
    medium_net: float | None = None
    small_net: float | None = None


# ---------------------------------------------------------------------------
# 辅助
# ---------------------------------------------------------------------------


def _coerce_date(value: Any) -> date | None:
    """Best-effort 转换 akshare 日期字段。"""
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y%m%d"):
            try:
                return datetime.strptime(s, fmt).date()
            except (ValueError, TypeError):
                continue
    try:
        return pd.to_datetime(value).date()  # type: ignore[arg-type]
    except Exception:  # noqa: BLE001
        return None


def _coerce_float(value: Any) -> float | None:
    """Best-effort 转换 akshare 数值字段。"""
    if value is None:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    if isinstance(value, str):
        s = value.strip().replace(",", "").replace("%", "")
        if not s:
            return None
        try:
            return float(s)
        except (ValueError, TypeError):
            return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _code_to_ts_code(code: Any) -> str | None:
    """裸 6 位数字代码 → ts_code (与 microstructure 同样的映射规则)。"""
    if code is None:
        return None
    s = str(code).strip()
    if not s or not s.isdigit() or len(s) not in (5, 6):
        return None
    s = s.split(".")[0]
    if s.startswith("6") or s.startswith("5") or s.startswith("9"):
        return f"{s}.SH"
    if s.startswith(("0", "30", "1", "2")):
        return f"{s}.SZ"
    if s.startswith(("8", "92", "43")):
        return f"{s}.BJ"
    return f"{s}.SH"


# ---------------------------------------------------------------------------
# Provider
# ---------------------------------------------------------------------------


class FundFlowProvider:
    """akshare 资金流 Provider。

    限速策略：单次调用间隔 0.3s，连续请求间 1.5s 间隔 (历史逐只股票拉取时)。
    所有方法都做 2 次重试，每次 1s 退避；最终失败返回 None，不抛异常。
    """

    name = "akshare"

    def __init__(self, api_delay: float = _API_DELAY) -> None:
        self._limiter = _RateLimiter(api_delay)

    # ---- 个股 --------------------------------------------------------------

    def fetch_individual_rank(self, indicator: str = "今日") -> list[dict[str, Any]]:
        """全市场个股资金流排行 (ak.stock_individual_fund_flow_rank)。

        indicator: "今日" / "3日" / "5日" / "10日"
        返回 list[dict]，每条 dict 的字段与 ``IndividualFundFlow`` ORM 一致。
        """
        import akshare as ak

        for attempt in range(_MAX_RETRIES):
            try:
                self._limiter.acquire()
                df = ak.stock_individual_fund_flow_rank(indicator=indicator)
                break
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "[FundFlowProvider] stock_individual_fund_flow_rank(indicator=%s) "
                    "attempt %d failed: %s",
                    indicator, attempt + 1, exc,
                )
                if attempt == _MAX_RETRIES - 1:
                    return []
                time.sleep(1.0)
        else:
            return []

        if df is None or df.empty:
            return []

        # 字段映射：akshare '今日' 列名带 '今日' 前缀
        prefix = "今日" if indicator == "今日" else indicator
        out: list[dict[str, Any]] = []
        for _, row in df.iterrows():
            ts_code = _code_to_ts_code(row.get("代码"))
            if not ts_code:
                continue
            out.append({
                "ts_code": ts_code,
                "trade_date": date.today(),  # 当日；历史数据靠 stock_individual_fund_flow 拉
                "main_net_inflow": _coerce_float(row.get(f"{prefix}主力净流入-净额")),
                "main_net_pct": _coerce_float(row.get(f"{prefix}主力净流入-净占比")),
                "super_large_net": _coerce_float(row.get(f"{prefix}超大单净流入-净额")),
                "super_large_pct": _coerce_float(row.get(f"{prefix}超大单净流入-净占比")),
                "large_net": _coerce_float(row.get(f"{prefix}大单净流入-净额")),
                "large_pct": _coerce_float(row.get(f"{prefix}大单净流入-净占比")),
                "medium_net": _coerce_float(row.get(f"{prefix}中单净流入-净额")),
                "medium_pct": _coerce_float(row.get(f"{prefix}中单净流入-净占比")),
                "small_net": _coerce_float(row.get(f"{prefix}小单净流入-净额")),
                "small_pct": _coerce_float(row.get(f"{prefix}小单净流入-净占比")),
                "source": "akshare",
            })
        return out

    def fetch_individual_history(
        self, ts_code: str, days: int = 30
    ) -> list[dict[str, Any]]:
        """单只股票近 ``days`` 日资金流历史 (ak.stock_individual_fund_flow)。

        返回 list[dict]，按 trade_date 升序。``ts_code`` 形如 "600519.SH"。
        """
        import akshare as ak

        pure_code = ts_code.split(".")[0]
        suffix = ts_code.split(".")[-1].lower() if "." in ts_code else "sh"
        # akshare 的 market 参数: "sh" / "sz" / "bj"
        if suffix in ("sh", "ss"):
            market = "sh"
        elif suffix in ("sz", "szse"):
            market = "sz"
        elif suffix in ("bj", "bse"):
            market = "bj"
        else:
            market = "sh"

        end_str = date.today().strftime("%Y%m%d")
        start_str = (date.today() - timedelta(days=days * 2)).strftime("%Y%m%d")

        for attempt in range(_MAX_RETRIES):
            try:
                self._limiter.acquire()
                df = ak.stock_individual_fund_flow(
                    stock=pure_code, market=market
                )
                break
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "[FundFlowProvider] stock_individual_fund_flow(%s, %s) "
                    "attempt %d failed: %s",
                    pure_code, market, attempt + 1, exc,
                )
                if attempt == _MAX_RETRIES - 1:
                    return []
                time.sleep(1.0)
        else:
            return []

        if df is None or df.empty:
            return []

        # 保留最近 days 行
        if len(df) > days:
            df = df.tail(days).reset_index(drop=True)

        out: list[dict[str, Any]] = []
        for _, row in df.iterrows():
            trade_date = _coerce_date(row.get("日期"))
            if not trade_date:
                continue
            out.append({
                "ts_code": ts_code,
                "trade_date": trade_date,
                "main_net_inflow": _coerce_float(row.get("主力净流入-净额")),
                "main_net_pct": _coerce_float(row.get("主力净流入-净占比")),
                "super_large_net": _coerce_float(row.get("超大单净流入-净额")),
                "super_large_pct": _coerce_float(row.get("超大单净流入-净占比")),
                "large_net": _coerce_float(row.get("大单净流入-净额")),
                "large_pct": _coerce_float(row.get("大单净流入-净占比")),
                "medium_net": _coerce_float(row.get("中单净流入-净额")),
                "medium_pct": _coerce_float(row.get("中单净流入-净占比")),
                "small_net": _coerce_float(row.get("小单净流入-净额")),
                "small_pct": _coerce_float(row.get("小单净流入-净占比")),
                "source": "akshare",
            })
        return out

    # ---- 板块 --------------------------------------------------------------

    def fetch_sector_rank(
        self, sector_type: str = "行业资金流", indicator: str = "今日"
    ) -> list[dict[str, Any]]:
        """板块资金流排行 (ak.stock_sector_fund_flow_rank)。

        sector_type: '行业资金流' / '概念资金流' / '地域资金流'
        返回 list[dict]，``sector_type`` 字段统一映射成 行业/概念/地域。
        """
        import akshare as ak

        type_map = {
            "行业资金流": "行业",
            "概念资金流": "概念",
            "地域资金流": "地域",
        }
        mapped_type = type_map.get(sector_type, sector_type)

        for attempt in range(_MAX_RETRIES):
            try:
                self._limiter.acquire()
                df = ak.stock_sector_fund_flow_rank(
                    indicator=indicator, sector_type=sector_type
                )
                break
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "[FundFlowProvider] stock_sector_fund_flow_rank(%s, %s) "
                    "attempt %d failed: %s",
                    sector_type, indicator, attempt + 1, exc,
                )
                if attempt == _MAX_RETRIES - 1:
                    return []
                time.sleep(1.0)
        else:
            return []

        if df is None or df.empty:
            return []

        prefix = "今日" if indicator == "今日" else indicator
        out: list[dict[str, Any]] = []
        for _, row in df.iterrows():
            name = str(row.get("名称", "")).strip()
            if not name:
                continue
            out.append({
                "sector_name": name,
                "sector_type": mapped_type,
                "trade_date": date.today(),
                "main_net_inflow": _coerce_float(row.get(f"{prefix}主力净流入-净额")),
                "main_net_pct": _coerce_float(row.get(f"{prefix}主力净流入-净占比")),
                "super_large_net": _coerce_float(row.get(f"{prefix}超大单净流入-净额")),
                "large_net": _coerce_float(row.get(f"{prefix}大单净流入-净额")),
                "leading_stock": str(row.get(f"{prefix}主力净流入最大股", "") or "").strip() or None,
            })
        return out

    # ---- 大盘 --------------------------------------------------------------

    def fetch_market_fund_flow(self, days: int = 60) -> list[dict[str, Any]]:
        """大盘整体资金流 (ak.stock_market_fund_flow)。返回最近 ``days`` 日。"""
        import akshare as ak

        for attempt in range(_MAX_RETRIES):
            try:
                self._limiter.acquire()
                df = ak.stock_market_fund_flow()
                break
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "[FundFlowProvider] stock_market_fund_flow attempt %d failed: %s",
                    attempt + 1, exc,
                )
                if attempt == _MAX_RETRIES - 1:
                    return []
                time.sleep(1.0)
        else:
            return []

        if df is None or df.empty:
            return []

        if len(df) > days:
            df = df.tail(days).reset_index(drop=True)

        out: list[dict[str, Any]] = []
        for _, row in df.iterrows():
            trade_date = _coerce_date(row.get("日期"))
            if not trade_date:
                continue
            out.append({
                "trade_date": trade_date,
                "sh_close": _coerce_float(row.get("上证-收盘价")),
                "sh_pct_change": _coerce_float(row.get("上证-涨跌幅")),
                "sz_close": _coerce_float(row.get("深证-收盘价")),
                "sz_pct_change": _coerce_float(row.get("深证-涨跌幅")),
                "main_net_inflow": _coerce_float(row.get("主力净流入-净额")),
                "main_net_pct": _coerce_float(row.get("主力净流入-净占比")),
                "super_large_net": _coerce_float(row.get("超大单净流入-净额")),
                "large_net": _coerce_float(row.get("大单净流入-净额")),
                "medium_net": _coerce_float(row.get("中单净流入-净额")),
                "small_net": _coerce_float(row.get("小单净流入-净额")),
            })
        return out
