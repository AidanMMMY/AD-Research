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

# ---------------------------------------------------------------------------
# EastMoney push2delay fallback (direct HTTP)
# ---------------------------------------------------------------------------
#
# Since ~2026-07-17 eastmoney's edge drops API calls on the canonical
# ``push2.eastmoney.com`` / ``push2his.eastmoney.com`` hosts used by akshare
# (TLS handshake succeeds, then the connection is closed without response;
# clist returns 502). The ``push2delay.eastmoney.com`` host serves the same
# qt endpoints and stays reachable, so each akshare-based fetch below falls
# back to a direct push2delay call when akshare fails. Caveat: push2delay's
# fflow daykline only carries the latest trading day (no history), which is
# still enough for the daily ETL.

_EM_DELAY_BASE = "https://push2delay.eastmoney.com/api/qt"
_EM_UT = "b2884a393a59ad64002292a3e90d46a5"
_EM_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
_EM_REFERER = "https://quote.eastmoney.com/"
_EM_PAGE_SIZE = 100
_EM_MAX_PAGES = 200


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
        akshare 失败时降级 push2delay 直连 (仅支持 "今日")。
        """
        rows = self._fetch_individual_rank_akshare(indicator)
        if not rows:
            rows = self._fetch_individual_rank_delay(indicator)
        return rows

    def _fetch_individual_rank_akshare(self, indicator: str) -> list[dict[str, Any]]:
        """akshare 主路径：全市场个股资金流排行。"""
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
        akshare 失败时降级 push2delay 直连 (仅支持 "今日")。
        """
        rows = self._fetch_sector_rank_akshare(sector_type, indicator)
        if not rows:
            rows = self._fetch_sector_rank_delay(sector_type, indicator)
        return rows

    def _fetch_sector_rank_akshare(
        self, sector_type: str, indicator: str
    ) -> list[dict[str, Any]]:
        """akshare 主路径：板块资金流排行。"""
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
        """大盘整体资金流 (ak.stock_market_fund_flow)。返回最近 ``days`` 日。

        akshare 失败时降级 push2delay 直连 (只有最新一个交易日)。
        """
        rows = self._fetch_market_fund_flow_akshare(days)
        if not rows:
            rows = self._fetch_market_fund_flow_delay()
        return rows

    def _fetch_market_fund_flow_akshare(self, days: int) -> list[dict[str, Any]]:
        """akshare 主路径：大盘整体资金流。"""
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


    # ---- push2delay 直连 fallback ------------------------------------------

    def _em_get(self, path: str, params: dict[str, Any]) -> dict[str, Any] | None:
        """GET a push2delay qt endpoint; returns parsed JSON or None."""
        import requests

        for attempt in range(_MAX_RETRIES):
            try:
                self._limiter.acquire()
                resp = requests.get(
                    f"{_EM_DELAY_BASE}{path}",
                    params=params,
                    headers={"User-Agent": _EM_UA, "Referer": _EM_REFERER},
                    timeout=15,
                )
                resp.raise_for_status()
                return resp.json()
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "[FundFlowProvider] push2delay %s attempt %d failed: %s",
                    path, attempt + 1, exc,
                )
                if attempt == _MAX_RETRIES - 1:
                    return None
                time.sleep(1.0)
        return None

    def _em_clist(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        """Paginated ``clist/get`` via push2delay; returns raw ``diff`` rows."""
        out: list[dict[str, Any]] = []
        total: int | None = None
        for page in range(1, _EM_MAX_PAGES + 1):
            payload = self._em_get(
                "/clist/get",
                {**params, "pn": str(page), "pz": str(_EM_PAGE_SIZE)},
            )
            data = payload.get("data") if isinstance(payload, dict) else None
            if not isinstance(data, dict):
                break
            if total is None:
                total = int(data.get("total") or 0)
            diff = data.get("diff") or []
            if not diff:
                break
            out.extend(diff)
            if len(out) >= total:
                break
        return out

    def _fetch_individual_rank_delay(self, indicator: str) -> list[dict[str, Any]]:
        """push2delay fallback for ``fetch_individual_rank`` ("今日" only)."""
        if indicator != "今日":
            return []
        rows = self._em_clist({
            "fid": "f62",
            "po": "1",
            "np": "1",
            "fltt": "2",
            "invt": "2",
            "ut": _EM_UT,
            "fs": (
                "m:0+t:6+f:!2,m:0+t:13+f:!2,m:0+t:80+f:!2,"
                "m:1+t:2+f:!2,m:1+t:23+f:!2,m:0+t:7+f:!2,m:1+t:3+f:!2"
            ),
            "fields": "f12,f14,f2,f3,f62,f184,f66,f69,f72,f75,f78,f81,f84,f87",
        })
        out: list[dict[str, Any]] = []
        for row in rows:
            ts_code = _code_to_ts_code(row.get("f12"))
            if not ts_code:
                continue
            out.append({
                "ts_code": ts_code,
                "trade_date": date.today(),
                "main_net_inflow": _coerce_float(row.get("f62")),
                "main_net_pct": _coerce_float(row.get("f184")),
                "super_large_net": _coerce_float(row.get("f66")),
                "super_large_pct": _coerce_float(row.get("f69")),
                "large_net": _coerce_float(row.get("f72")),
                "large_pct": _coerce_float(row.get("f75")),
                "medium_net": _coerce_float(row.get("f78")),
                "medium_pct": _coerce_float(row.get("f81")),
                "small_net": _coerce_float(row.get("f84")),
                "small_pct": _coerce_float(row.get("f87")),
                "source": "push2delay",
            })
        if out:
            logger.info(
                "[FundFlowProvider] individual rank via push2delay fallback: %d rows",
                len(out),
            )
        return out

    def _fetch_sector_rank_delay(
        self, sector_type: str, indicator: str
    ) -> list[dict[str, Any]]:
        """push2delay fallback for ``fetch_sector_rank`` ("今日" only)."""
        if indicator != "今日":
            return []
        # fs 板块代码 + 统一映射类型 (与 akshare sector_type_map 一致)
        type_map = {
            "行业资金流": ("2", "行业"),
            "概念资金流": ("3", "概念"),
            "地域资金流": ("1", "地域"),
        }
        mapped = type_map.get(sector_type)
        if not mapped:
            return []
        fs_code, mapped_type = mapped
        rows = self._em_clist({
            "fid0": "f62",
            "po": "1",
            "np": "1",
            "fltt": "2",
            "invt": "2",
            "ut": _EM_UT,
            "fs": f"m:90 t:{fs_code}",
            "stat": "1",
            "fields": "f12,f14,f2,f3,f62,f184,f66,f69,f72,f75,f78,f81,f84,f87,f204,f205,f124",
            "rt": "52975239",
        })
        out: list[dict[str, Any]] = []
        for row in rows:
            name = str(row.get("f14") or "").strip()
            if not name:
                continue
            out.append({
                "sector_name": name,
                "sector_type": mapped_type,
                "trade_date": date.today(),
                "main_net_inflow": _coerce_float(row.get("f62")),
                "main_net_pct": _coerce_float(row.get("f184")),
                "super_large_net": _coerce_float(row.get("f66")),
                "large_net": _coerce_float(row.get("f72")),
                "leading_stock": str(row.get("f204") or "").strip() or None,
            })
        if out:
            logger.info(
                "[FundFlowProvider] sector rank(%s) via push2delay fallback: %d rows",
                sector_type, len(out),
            )
        return out

    def _fetch_market_fund_flow_delay(self) -> list[dict[str, Any]]:
        """push2delay fallback for ``fetch_market_fund_flow`` (latest day only)."""
        payload = self._em_get(
            "/stock/fflow/daykline/get",
            {
                "lmt": "0",
                "klt": "101",
                "secid": "1.000001",
                "secid2": "0.399001",
                "fields1": "f1,f2,f3,f7",
                "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65",
                "ut": _EM_UT,
            },
        )
        data = payload.get("data") if isinstance(payload, dict) else None
        klines = data.get("klines") if isinstance(data, dict) else None
        if not klines:
            return []
        # kline 字段顺序与 akshare stock_market_fund_flow 的 15 列一致
        parts = str(klines[-1]).split(",")
        if len(parts) < 15:
            return []
        trade_date = _coerce_date(parts[0])
        if not trade_date:
            return []
        logger.info("[FundFlowProvider] market fund flow via push2delay fallback")
        return [{
            "trade_date": trade_date,
            "sh_close": _coerce_float(parts[11]),
            "sh_pct_change": _coerce_float(parts[12]),
            "sz_close": _coerce_float(parts[13]),
            "sz_pct_change": _coerce_float(parts[14]),
            "main_net_inflow": _coerce_float(parts[1]),
            "main_net_pct": _coerce_float(parts[6]),
            "super_large_net": _coerce_float(parts[5]),
            "large_net": _coerce_float(parts[4]),
            "medium_net": _coerce_float(parts[3]),
            "small_net": _coerce_float(parts[2]),
        }]
