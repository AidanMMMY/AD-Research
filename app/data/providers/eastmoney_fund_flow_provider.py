"""东方财富 push2 直连 Provider (备用 + 实时资金流)。

覆盖 akshare 不可用时的兜底路径；与
``app/data/providers/eastmoney_zh_provider.py`` 同样的 session +
Referer 范式。

主要接口：

* ``https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get``
  — 个股资金流历史 (近 100 日 K 线)
* ``https://push2.eastmoney.com/api/qt/stock/get``
  — 个股实时资金流 (单只)
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import date
from typing import Any

import requests

logger = logging.getLogger(__name__)


_BASE_URL_FFLOW = "https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get"
_BASE_URL_REALTIME = "https://push2.eastmoney.com/api/qt/stock/get"
_HIS_BASE = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
_REFERER = "https://quote.eastmoney.com/"
_TIMEOUT = 8.0
_MAX_RETRIES = 2


@dataclass
class EastMoneyFundFlowRow:
    """单只股票资金流一行 (历史 K 线)。"""

    ts_code: str
    trade_date: date
    main_net_inflow: float | None = None
    main_net_pct: float | None = None
    super_large_net: float | None = None
    large_net: float | None = None
    medium_net: float | None = None
    small_net: float | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _coerce_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        for fmt in ("%Y-%m-%d", "%Y%m%d"):
            try:
                from datetime import datetime

                return datetime.strptime(s, fmt).date()
            except (ValueError, TypeError):
                continue
    return None


def _coerce_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        v = float(value)
        if v != v:  # NaN
            return None
        return v
    except (TypeError, ValueError):
        return None


def _secid_for_ts_code(ts_code: str) -> str | None:
    """ts_code → eastmoney secid (1.xxxxxx=SH, 0.xxxxxx=SZ, 0.xxxxxx=BJ)。"""
    if not ts_code or "." not in ts_code:
        return None
    pure, suffix = ts_code.split(".", 1)
    if not pure.isdigit():
        return None
    if suffix.upper() in ("SH", "SS"):
        return f"1.{pure}"
    if suffix.upper() in ("SZ", "SZSE"):
        return f"0.{pure}"
    if suffix.upper() in ("BJ", "BSE"):
        return f"0.{pure}"  # BJ 实际 0.8xxxxx，东财也能识别
    return f"1.{pure}"


# ---------------------------------------------------------------------------
# Provider
# ---------------------------------------------------------------------------


class EastMoneyFundFlowProvider:
    """东方财富 push2 直连 — 个股资金流历史 K 线 / 实时。"""

    name = "eastmoney"

    def __init__(self, session: requests.Session | None = None) -> None:
        self._session = session or requests.Session()
        self._session.headers.setdefault("User-Agent", _USER_AGENT)
        self._session.headers.setdefault("Referer", _REFERER)

    def fetch_history(self, ts_code: str, days: int = 100) -> list[dict[str, Any]]:
        """单只股票近 ``days`` 日的资金流 K 线 (push2his fflow/daykline)。"""
        secid = _secid_for_ts_code(ts_code)
        if not secid:
            return []

        params = {
            "lmt": str(days),
            "klt": "101",  # 日 K
            "secid": secid,
            "fields1": "f1,f2,f3,f7",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65",
            "ut": "b2884a393a59ad64002292a3e90d46a5",
        }

        for attempt in range(_MAX_RETRIES):
            try:
                resp = self._session.get(
                    _BASE_URL_FFLOW, params=params, timeout=_TIMEOUT
                )
                resp.raise_for_status()
                payload = resp.json()
                break
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "[EastMoneyFundFlowProvider] fetch_history(%s) attempt %d failed: %s",
                    ts_code, attempt + 1, exc,
                )
                if attempt == _MAX_RETRIES - 1:
                    return []
                time.sleep(0.5)
        else:
            return []

        data = payload.get("data") if isinstance(payload, dict) else None
        if not data or not isinstance(data, dict):
            return []
        klines = data.get("klines") or []
        if not klines:
            return []

        out: list[dict[str, Any]] = []
        for line in klines:
            # 字段顺序: 日期,主力净流入,小单,中单,大单,超大单,主力占比,小单占比,中单占比,大单占比,超大单占比,...
            parts = line.split(",")
            if len(parts) < 11:
                continue
            trade_date = _coerce_date(parts[0])
            if not trade_date:
                continue
            out.append({
                "ts_code": ts_code,
                "trade_date": trade_date,
                "main_net_inflow": _coerce_float(parts[1]),
                "small_net": _coerce_float(parts[2]),
                "medium_net": _coerce_float(parts[3]),
                "large_net": _coerce_float(parts[4]),
                "super_large_net": _coerce_float(parts[5]),
                "main_net_pct": _coerce_float(parts[6]),
                "source": "eastmoney",
            })
        return out

    def fetch_realtime_quote(self, ts_code: str) -> dict[str, Any] | None:
        """个股实时行情 (push2 stock/get) — 主要用作 fallback 验证。"""
        secid = _secid_for_ts_code(ts_code)
        if not secid:
            return None

        params = {
            "secid": secid,
            "fields": "f12,f14,f2,f3,f62,f184,f66,f69,f72,f75,f78,f81,f84,f87",
            "invt": "2",
        }
        try:
            resp = self._session.get(
                _BASE_URL_REALTIME, params=params, timeout=_TIMEOUT
            )
            resp.raise_for_status()
            payload = resp.json()
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "[EastMoneyFundFlowProvider] fetch_realtime_quote(%s) failed: %s",
                ts_code, exc,
            )
            return None

        data = payload.get("data") if isinstance(payload, dict) else None
        if not data or not isinstance(data, dict):
            return None
        return {
            "ts_code": ts_code,
            "name": data.get("f14"),
            "price": _coerce_float(data.get("f2")),
            "pct_change": _coerce_float(data.get("f3")),
            "main_net_inflow": _coerce_float(data.get("f62")),
            "main_net_pct": _coerce_float(data.get("f184")),
            "super_large_net": _coerce_float(data.get("f66")),
            "large_net": _coerce_float(data.get("f72")),
            "medium_net": _coerce_float(data.get("f78")),
            "small_net": _coerce_float(data.get("f84")),
            "source": "eastmoney",
        }
