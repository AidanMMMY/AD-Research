"""资金流信号链修复的回归测试 (2026-07-20)。

覆盖：
1. ``_compute_composite`` 按有效权重归一 + breakdown 记录 coverage
2. 股东户数 provider 中英列名兼容 (akshare 列名从英文改中文)
3. AH 溢价占位源禁用 (恒返回空，不再产生六分量全 NULL 的垃圾行)
4. ``MarketFundFlowPipeline._derive_sh_sz_records`` 调用
   ``_aggregate_individual`` (原潜伏 NameError)
"""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

import pandas as pd

from app.data.pipelines.fund_flow import WEIGHTS, _compute_composite
from app.data.pipelines.market_fund_flow import MarketFundFlowPipeline
from app.data.providers.flow_signals_provider import FlowSignalsProvider


class TestComputeComposite:
    """composite_score 按有效权重归一，缺失分量不再按 0 拉低量程。"""

    def test_full_components_still_full_scale(self) -> None:
        parts = {
            "main": 1e8,
            "margin": 5e7,
            "lhb": 5e7,
            "shareholder": 1e4,
            "ah": 50.0,
            "block": 5e7,
        }
        score, breakdown = _compute_composite(parts)
        assert score == 100.0
        assert breakdown["coverage"] == 1.0

    def test_missing_components_normalized_by_effective_weight(self) -> None:
        # 只有主力分量 (weight 0.40) 且打满 → 归一后应为 +100 而非 40
        score, breakdown = _compute_composite({"main": 1e8})
        assert score == 100.0
        assert breakdown["coverage"] == WEIGHTS["main"]
        assert breakdown["margin"] == 0.0

    def test_partial_components_keep_full_range_negative(self) -> None:
        # 主力 -1 倍阈值 (weight 0.40) + 融资 +1 倍阈值 (weight 0.20)
        # raw = -40 + 20 = -20, Σ有效权重 = 0.60 → -20 / 0.60 = -33.3333
        score, breakdown = _compute_composite({"main": -1e8, "margin": 5e7})
        assert score == round(-20.0 / 0.6, 4)
        assert breakdown["coverage"] == round(WEIGHTS["main"] + WEIGHTS["margin"], 4)

    def test_all_missing_returns_zero_with_zero_coverage(self) -> None:
        score, breakdown = _compute_composite({})
        assert score == 0.0
        assert breakdown["coverage"] == 0.0


class TestShareholderColumns:
    """股东户数：akshare 列名英文→中文后的兼容映射。"""

    def test_chinese_columns(self, monkeypatch) -> None:
        df = pd.DataFrame(
            [
                {
                    "代码": "600519",
                    "股东户数-增减": -1234.0,
                    "公告日期": "2026-07-15",
                }
            ]
        )
        import akshare as ak

        monkeypatch.setattr(ak, "stock_zh_a_gdhs", lambda symbol="最新": df)
        rows = FlowSignalsProvider(api_delay=0).fetch_shareholder_count(date(2026, 7, 17))
        assert len(rows) == 1
        assert rows[0]["ts_code"] == "600519.SH"
        assert rows[0]["shareholder_count_change"] == -1234.0
        assert rows[0]["trade_date"] == date(2026, 7, 17)

    def test_english_columns_still_supported(self, monkeypatch) -> None:
        df = pd.DataFrame(
            [
                {
                    "SECURITY_CODE": "000001",
                    "HOLDER_NUM_CHANGE": 500.0,
                    "HOLD_NOTICE_DATE": "2026-07-15",
                }
            ]
        )
        import akshare as ak

        monkeypatch.setattr(ak, "stock_zh_a_gdhs", lambda symbol="最新": df)
        rows = FlowSignalsProvider(api_delay=0).fetch_shareholder_count()
        assert len(rows) == 1
        assert rows[0]["ts_code"] == "000001.SZ"
        assert rows[0]["shareholder_count_change"] == 500.0
        # 未传 target_date 时回落到公告日期
        assert rows[0]["trade_date"] == date(2026, 7, 15)


class TestAhPremiumDisabled:
    """AH 溢价占位源禁用：恒返回空，不再污染 flow_signal 并集。"""

    def test_returns_empty(self) -> None:
        provider = FlowSignalsProvider(api_delay=0)
        assert provider.fetch_ah_premium(date(2026, 7, 17)) == []


class TestDeriveShSzRecords:
    """_derive_sh_sz_records 必须调用 _aggregate_individual (NameError 回归)。"""

    def _make_pipeline(self) -> MarketFundFlowPipeline:
        return MarketFundFlowPipeline(MagicMock(), target_date=date(2026, 7, 17))

    def test_aggregates_sh_sz(self, monkeypatch) -> None:
        pipeline = self._make_pipeline()
        sums = {
            "main_net_inflow": 1.0,
            "super_large_net": 2.0,
            "large_net": 3.0,
            "medium_net": 4.0,
            "small_net": 5.0,
        }
        monkeypatch.setattr(pipeline, "_aggregate_individual", lambda td, suffix: sums)
        td = date(2026, 7, 17)
        meta = {
            td: {
                "sh_close": 3000.0,
                "sh_pct_change": 0.5,
                "sz_close": 9000.0,
                "sz_pct_change": -0.3,
            }
        }
        records = pipeline._derive_sh_sz_records({td}, meta)
        assert len(records) == 2
        assert {r["market"] for r in records} == {"SH", "SZ"}
        sh = next(r for r in records if r["market"] == "SH")
        assert sh["main_net_inflow"] == 1.0
        assert sh["close_price"] == 3000.0
        assert sh["pct_change"] == 0.5
        assert sh["source"] == "derived"

    def test_empty_aggregate_skipped_without_error(self, monkeypatch) -> None:
        pipeline = self._make_pipeline()
        monkeypatch.setattr(pipeline, "_aggregate_individual", lambda td, suffix: None)
        records = pipeline._derive_sh_sz_records({date(2026, 7, 17)}, {})
        assert records == []
