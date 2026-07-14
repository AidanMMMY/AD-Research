"""ETF 资金流 Provider (akshare)。

两个核心接口：

* ``ak.fund_etf_spot_em()``         — 全部 ETF 现价 + 最新份额 + 成交额
                                       (差分可推申赎代理变量)
* ``ak.fund_etf_fund_daily_em()``   — 当日所有场内交易基金净值/折溢价

``premium_rate = (price - net_value) / net_value * 100``
``shares_change = shares_outstanding_today - shares_outstanding_yesterday``
``inferred_net_inflow = shares_change × price``
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from datetime import date
from typing import Any

import pandas as pd

from app.data.providers.fund_flow_provider import (
    _RateLimiter,
    _coerce_date,
    _coerce_float,
)

logger = logging.getLogger(__name__)


_API_DELAY = 0.3
_MAX_RETRIES = 2


@dataclass
class EtfFlowRow:
    """单只 ETF 当日资金流。"""

    ts_code: str
    trade_date: date
    price: float | None = None
    net_value: float | None = None
    premium_rate: float | None = None
    shares_outstanding: float | None = None
    shares_change: float | None = None
    turnover: float | None = None
    inferred_net_inflow: float | None = None


# ---------------------------------------------------------------------------
# Provider
# ---------------------------------------------------------------------------


class EtfFlowProvider:
    """akshare ETF 资金流 Provider。"""

    name = "akshare"

    def __init__(self, api_delay: float = _API_DELAY) -> None:
        self._limiter = _RateLimiter(api_delay)

    def fetch_etf_spot(self) -> list[dict[str, Any]]:
        """全部 ETF 实时快照 (ak.fund_etf_spot_em)。

        字段映射: ``代码`` → ``ts_code``，``最新价`` → ``price``，``最新份额``
        → ``shares_outstanding``，``成交额`` → ``turnover``，``IOPV实时估值``
        → ``net_value``，``基金折价率`` → ``premium_rate``。
        """
        import akshare as ak

        for attempt in range(_MAX_RETRIES):
            try:
                self._limiter.acquire()
                df = ak.fund_etf_spot_em()
                break
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "[EtfFlowProvider] fund_etf_spot_em attempt %d failed: %s",
                    attempt + 1, exc,
                )
                if attempt == _MAX_RETRIES - 1:
                    return []
                time.sleep(1.0)
        else:
            return []

        if df is None or df.empty:
            return []

        out: list[dict[str, Any]] = []
        for _, row in df.iterrows():
            raw_code = str(row.get("代码", "")).strip()
            if not raw_code:
                continue

            if raw_code.startswith("5"):
                ts_code = f"{raw_code}.SH"
            elif raw_code.startswith("1"):
                ts_code = f"{raw_code}.SZ"
            elif raw_code.startswith(("15", "16", "18")):
                ts_code = f"{raw_code}.SZ"
            else:
                continue

            price = _coerce_float(row.get("最新价"))
            net_value = _coerce_float(row.get("IOPV实时估值"))
            # akshare 字段: 基金折价率 已经是百分数形式 (e.g. -0.42 表示 -0.42%)
            # 如果没有 IOPV，则用 1 + 折价率 推算 (市价/净值 - 1)
            premium_rate = _coerce_float(row.get("基金折价率"))
            if premium_rate is None and price and net_value and net_value != 0:
                premium_rate = (price - net_value) / net_value * 100.0

            out.append({
                "ts_code": ts_code,
                "trade_date": date.today(),
                "price": price,
                "net_value": net_value,
                "premium_rate": premium_rate,
                "shares_outstanding": _coerce_float(row.get("最新份额")),
                "turnover": _coerce_float(row.get("成交额")),
            })
        return out

    def fetch_etf_fund_daily(self) -> list[dict[str, Any]]:
        """当日所有场内交易基金净值/折溢价 (ak.fund_etf_fund_daily_em)。

        返回字段: ``ts_code`` / ``trade_date`` / ``price`` / ``net_value`` /
        ``premium_rate``。
        """
        import akshare as ak

        for attempt in range(_MAX_RETRIES):
            try:
                self._limiter.acquire()
                df = ak.fund_etf_fund_daily_em()
                break
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "[EtfFlowProvider] fund_etf_fund_daily_em attempt %d failed: %s",
                    attempt + 1, exc,
                )
                if attempt == _MAX_RETRIES - 1:
                    return []
                time.sleep(1.0)
        else:
            return []

        if df is None or df.empty:
            return []

        out: list[dict[str, Any]] = []
        for _, row in df.iterrows():
            raw_code = str(row.get("基金代码", "")).strip()
            if not raw_code or not raw_code.isdigit():
                continue
            if raw_code.startswith("5"):
                ts_code = f"{raw_code}.SH"
            elif raw_code.startswith("1"):
                ts_code = f"{raw_code}.SZ"
            else:
                continue

            price = _coerce_float(row.get("市价"))
            # 单位净值列名带日期前缀 — 取第二个单位净值 (今日)
            # 实际上 ak 输出列名是 f"{show_day[0]}-单位净值" (昨日) 和
            # f"{show_day[2]}-单位净值" (今日)，我们用 "单位净值" 后缀匹配
            net_value: float | None = None
            for col_name in row.index:
                if isinstance(col_name, str) and col_name.endswith("-单位净值"):
                    # 第二个 (今日) 优先；index 倒序匹配
                    val = _coerce_float(row.get(col_name))
                    if val is not None and val > 0:
                        net_value = val
                        # continue; let last match win (today's column is later)
            if net_value is None:
                net_value = _coerce_float(row.get("单位净值"))
            premium_rate = _coerce_float(row.get("折价率"))
            if premium_rate is None and price and net_value and net_value != 0:
                premium_rate = (price - net_value) / net_value * 100.0

            out.append({
                "ts_code": ts_code,
                "trade_date": date.today(),
                "price": price,
                "net_value": net_value,
                "premium_rate": premium_rate,
            })
        return out

    # ---- 计算 shares_change + inferred_net_inflow -----------------------------

    @staticmethod
    def compute_shares_change_and_inflow(
        today: list[dict[str, Any]],
        yesterday: list[dict[str, Any]] | None,
    ) -> list[dict[str, Any]]:
        """差分昨日份额 → ``shares_change``，再乘以 price 推算 ``inferred_net_inflow``。

        ``yesterday`` 可为 None；为 None 时 shares_change / inferred_net_inflow 都填 None。
        """
        if not yesterday:
            for row in today:
                row["shares_change"] = None
                row["inferred_net_inflow"] = None
            return today

        prev_map: dict[str, float] = {
            str(r.get("ts_code")): r.get("shares_outstanding")  # type: ignore[arg-type]
            for r in yesterday
            if r.get("ts_code") and r.get("shares_outstanding") is not None
        }

        for row in today:
            ts_code = row.get("ts_code")
            cur_shares = row.get("shares_outstanding")
            price = row.get("price")
            if ts_code in prev_map and cur_shares is not None:
                delta = float(cur_shares) - float(prev_map[ts_code])
                row["shares_change"] = delta
                if price is not None:
                    row["inferred_net_inflow"] = delta * float(price)
                else:
                    row["inferred_net_inflow"] = None
            else:
                row["shares_change"] = None
                row["inferred_net_inflow"] = None
        return today
