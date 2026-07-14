"""综合资金信号 Provider (akshare 间接信号汇总)。

聚合 5 类间接资金信号：

* 融资融券 — ``ak.stock_margin_detail_sse`` (SSE 每日融资余额)
* 龙虎榜   — ``ak.stock_lhb_detail_em`` (按日，提取机构净买)
* 股东户数 — ``ak.stock_zh_a_gdhs(symbol='最新')`` (最新一期)
* AH 溢价  — ``ak.stock_zh_ah_spot()`` (实时，仅 A+H 同时上市)
* 大宗交易 — ``ak.stock_dzjy_mrtj(start, end)`` (按日)

每个方法都返回 ``list[dict]``，按 (ts_code, trade_date) 一一对应，
方便 Pipeline 合成 ``flow_signal`` 记录。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import pandas as pd

from app.data.providers.fund_flow_provider import (
    _MAX_RETRIES,
    _RateLimiter,
    _coerce_date,
    _coerce_float,
    _code_to_ts_code,
)

logger = logging.getLogger(__name__)


_API_DELAY = 0.3
_BATCH_DELAY = 1.0


@dataclass
class MarginChangeRow:
    """融资余额日变化 (推算)。"""

    ts_code: str
    trade_date: date
    margin_net_change: float | None  # financing_balance_today - yesterday


@dataclass
class LhbNetRow:
    """龙虎榜机构净买。"""

    ts_code: str
    trade_date: date
    lhb_net_buy: float | None  # 龙虎榜净买额 (akshare 原始字段)


@dataclass
class ShareholderRow:
    """股东户数变化。"""

    ts_code: str
    trade_date: date
    shareholder_count_change: float | None  # 股东户数环比 (户)


@dataclass
class AhPremiumRow:
    """AH 溢价 (H 股价格折算成 A 股口径)。"""

    ts_code: str
    trade_date: date
    ah_premium: float | None


@dataclass
class BlockTradeRow:
    """大宗交易净买。"""

    ts_code: str
    trade_date: date
    block_trade_net: float | None  # 成交价 × 成交量 = 总额；正值=买方主导


# ---------------------------------------------------------------------------
# Provider
# ---------------------------------------------------------------------------


class FlowSignalsProvider:
    """akshare 间接资金信号汇总。"""

    name = "akshare"

    def __init__(self, api_delay: float = _API_DELAY) -> None:
        self._limiter = _RateLimiter(api_delay)

    # ---- 融资 ----------------------------------------------------------------

    def fetch_margin_change(
        self, target_date: date | None = None
    ) -> list[dict[str, Any]]:
        """SSE 融资余额日变化 (ak.stock_margin_detail_sse)。

        通过查询 target_date 与 (target_date - 1) 两天的融资余额做差分
        得到 ``margin_net_change``。  SZSE 的 ``ak.stock_margin_underlying_info_szse``
        不返回余额数字，不参与。
        """
        import akshare as ak

        target = target_date or date.today()
        prev = target - timedelta(days=5)  # 5 天 buffer 覆盖周末/节假日

        def _fetch_fin_bal(d: date) -> dict[str, float]:
            """return {ts_code: financing_balance}。"""
            try:
                self._limiter.acquire()
                df = ak.stock_margin_detail_sse(date=d.strftime("%Y%m%d"))
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "[FlowSignalsProvider] margin_detail_sse(%s) failed: %s",
                    d, exc,
                )
                return {}
            if df is None or df.empty:
                return {}
            out: dict[str, float] = {}
            for _, row in df.iterrows():
                ts_code = _code_to_ts_code(row.get("标的证券代码"))
                bal = _coerce_float(row.get("融资余额"))
                if ts_code and bal is not None:
                    out[ts_code] = bal
            return out

        today_map = _fetch_fin_bal(target)
        prev_map = _fetch_fin_bal(prev)
        if not today_map:
            return []

        out: list[dict[str, Any]] = []
        for ts_code, cur_bal in today_map.items():
            prev_bal = prev_map.get(ts_code)
            change = cur_bal - prev_bal if prev_bal is not None else None
            out.append({
                "ts_code": ts_code,
                "trade_date": target,
                "margin_net_change": change,
            })
        return out

    # ---- 龙虎榜 --------------------------------------------------------------

    def fetch_lhb_net(self, target_date: date | None = None) -> list[dict[str, Any]]:
        """龙虎榜机构净买 (ak.stock_lhb_detail_em)。

        拉 [target-1, target] 共 3 天的明细，提取 ``龙虎榜净买额`` 字段。
        """
        import akshare as ak

        target = target_date or date.today()
        start = target - timedelta(days=1)
        start_str = start.strftime("%Y%m%d")
        end_str = target.strftime("%Y%m%d")

        try:
            self._limiter.acquire()
            df = ak.stock_lhb_detail_em(
                start_date=start_str, end_date=end_str
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "[FlowSignalsProvider] stock_lhb_detail_em failed: %s", exc
            )
            return []

        if df is None or df.empty:
            return []

        out: list[dict[str, Any]] = []
        for _, row in df.iterrows():
            ts_code = _code_to_ts_code(row.get("代码"))
            trade_date = _coerce_date(row.get("上榜日"))
            net_buy = _coerce_float(row.get("龙虎榜净买额"))
            if not (ts_code and trade_date and net_buy is not None):
                continue
            out.append({
                "ts_code": ts_code,
                "trade_date": trade_date,
                "lhb_net_buy": net_buy,
            })
        return out

    # ---- 股东户数 ------------------------------------------------------------

    def fetch_shareholder_count(
        self, target_date: date | None = None
    ) -> list[dict[str, Any]]:
        """最新一期股东户数 (ak.stock_zh_a_gdhs)。

        返回字段 ``shareholder_count_change`` = ``HOLDER_NUM_CHANGE`` (户数变化)。
        """
        import akshare as ak

        try:
            self._limiter.acquire()
            df = ak.stock_zh_a_gdhs(symbol="最新")
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "[FlowSignalsProvider] stock_zh_a_gdhs failed: %s", exc
            )
            return []

        if df is None or df.empty:
            return []

        out: list[dict[str, Any]] = []
        for _, row in df.iterrows():
            ts_code = _code_to_ts_code(row.get("SECURITY_CODE"))
            change = _coerce_float(row.get("HOLDER_NUM_CHANGE"))
            hold_notice = _coerce_date(row.get("HOLD_NOTICE_DATE"))
            if not (ts_code and change is not None):
                continue
            out.append({
                "ts_code": ts_code,
                "trade_date": target_date or hold_notice or date.today(),
                "shareholder_count_change": change,
            })
        return out

    # ---- AH 溢价 -------------------------------------------------------------

    def fetch_ah_premium(
        self, target_date: date | None = None
    ) -> list[dict[str, Any]]:
        """AH 溢价 (ak.stock_zh_ah_spot)。

        数据源是腾讯财经的实时快照，没有按日的历史；Pipeline 调用时仅
        标记"当日快照"语义。``ah_premium`` 字段保留给后续若能补历史的
        扩展点。
        """
        import akshare as ak

        try:
            self._limiter.acquire()
            df = ak.stock_zh_ah_spot()
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "[FlowSignalsProvider] stock_zh_ah_spot failed: %s", exc
            )
            return []

        if df is None or df.empty:
            return []

        target = target_date or date.today()
        out: list[dict[str, Any]] = []
        for _, row in df.iterrows():
            ts_code = _code_to_ts_code(row.get("代码"))
            if not ts_code:
                continue
            # 腾讯 AH 接口只给 A 股实时价；H 股价 / A 股价 = (1 - 折价)
            # 这里只是占位 — 真正的 AH 溢价需要跨市场汇率换算，
            # 当前为 None 让前端用 (name 字段) 自行提示。
            out.append({
                "ts_code": ts_code,
                "trade_date": target,
                "ah_premium": None,  # 占位；前端展示时按 name 标识
            })
        return out

    # ---- 大宗交易 ------------------------------------------------------------

    def fetch_block_trade(
        self, target_date: date | None = None
    ) -> list[dict[str, Any]]:
        """大宗交易每日统计 (ak.stock_dzjy_mrtj)。单日单只股票的总额。"""
        import akshare as ak

        target = target_date or date.today()
        end_str = target.strftime("%Y%m%d")
        start_str = (target - timedelta(days=1)).strftime("%Y%m%d")

        try:
            self._limiter.acquire()
            df = ak.stock_dzjy_mrtj(start_date=start_str, end_date=end_str)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "[FlowSignalsProvider] stock_dzjy_mrtj failed: %s", exc
            )
            return []

        if df is None or df.empty:
            return []

        out: list[dict[str, Any]] = []
        for _, row in df.iterrows():
            ts_code = _code_to_ts_code(row.get("证券代码"))
            trade_date = _coerce_date(row.get("交易日期"))
            amount = _coerce_float(row.get("成交总额"))
            premium = _coerce_float(row.get("折溢率"))
            if not (ts_code and trade_date and amount is not None):
                continue
            # 大宗交易本身没有明确的"买方/卖方"方向；约定：
            # 折价成交 (premium < 0) 视为卖方主导，net = -amount
            # 平价或溢价成交视为买方主导，net = +amount
            if premium is not None and premium < 0:
                net = -abs(amount)
            else:
                net = abs(amount)
            out.append({
                "ts_code": ts_code,
                "trade_date": trade_date,
                "block_trade_net": net,
            })
        return out
