"""Tests for the adj_factor source fix and ETF holdings unit normalization.

Covers the production incident where daily-increment bars written by the
Akshare EM/Sina paths reset ``adj_factor`` to 1.0 against stored Tushare
cumulative factors (seam corrupting returns for 237 ETFs), and the unit
mismatch where Eastmoney F10 / Akshare holdings were stored in 万股/万元
instead of raw shares / yuan.
"""

import datetime as _dt
import logging
from datetime import date

import pandas as pd
import pytest

from app.data.pipelines.a_share_stock_daily import AStockDailyPipeline
from app.data.providers import eastmoney_f10_provider
from app.data.providers.akshare_provider import AkshareProvider
from app.models.etf import InstrumentDailyBar


def _raw_em_df() -> pd.DataFrame:
    """Minimal Eastmoney raw-quote frame (Chinese columns)."""
    return pd.DataFrame(
        [
            {
                "日期": "2026-07-17",
                "开盘": 4.0,
                "收盘": 4.1,
                "最高": 4.2,
                "最低": 3.9,
                "成交量": 1000,
                "成交额": 4100.0,
                "振幅": 7.5,
                "涨跌幅": 2.5,
                "涨跌额": 0.1,
                "换手率": 1.2,
            }
        ]
    )


def test_em_daily_bars_leave_adj_factor_empty(monkeypatch):
    """The EM path must not write a window-derived factor (window end ~= 1.0)."""
    calls: list[str] = []

    def fake_fund_etf_hist_em(symbol, period, start_date, end_date, adjust):
        calls.append(adjust)
        return _raw_em_df() if adjust == "" else pd.DataFrame()

    monkeypatch.setattr(
        "app.data.providers.akshare_provider.ak.fund_etf_hist_em",
        fake_fund_etf_hist_em,
    )
    provider = AkshareProvider()
    df = provider._fetch_daily_bars_em("510300.SH", "510300", date(2026, 7, 17), date(2026, 7, 17))

    assert len(df) == 1
    # Only the raw-quote request is made — no qfq pull for factor derivation.
    assert calls == [""]
    # adj_factor stays NULL so the pipeline upsert preserves the stored factor.
    assert df["adj_factor"].isna().all()


def test_sina_daily_bars_leave_adj_factor_empty(monkeypatch):
    """The Sina fallback must not hardcode adj_factor = 1.0."""
    monkeypatch.setattr(
        "app.data.providers.akshare_provider.ak.fund_etf_hist_sina",
        lambda symbol: pd.DataFrame(
            [
                {
                    "date": date(2026, 7, 16),
                    "open": 4.0,
                    "high": 4.1,
                    "low": 3.9,
                    "close": 4.0,
                    "volume": 1000,
                    "amount": 4000.0,
                },
                {
                    "date": date(2026, 7, 17),
                    "open": 4.0,
                    "high": 4.2,
                    "low": 3.9,
                    "close": 4.1,
                    "volume": 1100,
                    "amount": 4510.0,
                },
            ]
        ),
    )
    provider = AkshareProvider()
    df = provider._fetch_daily_bars_sina(
        "510300.SH", "510300", date(2026, 7, 16), date(2026, 7, 17)
    )

    assert len(df) == 2
    assert df["adj_factor"].isna().all()


def test_akshare_holdings_normalized_to_shares_and_yuan(monkeypatch):
    """fund_portfolio_hold_em reports 万股/万元 — must be stored ×1e4."""

    def fake_fund_portfolio_hold_em(symbol, date):
        # The provider queries the current and previous year; only the
        # current year carries the Q1 frame.
        if str(date) != str(_dt.date.today().year):
            return pd.DataFrame()
        return pd.DataFrame(
            [
                {
                    "季度": f"{_dt.date.today().year}年1季度",
                    "股票代码": "600519",
                    "股票名称": "贵州茅台",
                    "占净值比例": 4.27,
                    "持股数": 12.5,  # 万股
                    "持仓市值": 20000.0,  # 万元
                }
            ]
        )

    monkeypatch.setattr(
        "app.data.providers.akshare_provider.ak.fund_portfolio_hold_em",
        fake_fund_portfolio_hold_em,
    )
    provider = AkshareProvider()
    df = provider.fetch_etf_holdings("510300.SH")

    assert len(df) == 1
    assert df.iloc[0]["shares"] == 12.5 * 1e4
    assert df.iloc[0]["market_value"] == 20000.0 * 1e4
    assert df.iloc[0]["weight"] == pytest.approx(0.0427)


def test_eastmoney_normalize_converts_wan_units():
    """Eastmoney jjcc 持股数(万股)/持仓市值(万元) → raw shares / yuan."""
    table = pd.DataFrame(
        [
            {
                "股票代码": "600519",
                "股票名称": "贵州茅台",
                "占净值比例": "4.27%",
                "持股数": "12.5",
                "持仓市值": "20000.0",
            }
        ]
    )
    df = eastmoney_f10_provider._normalize(table, "510300.SH", date(2026, 3, 31), 10)

    assert df is not None and len(df) == 1
    assert df.iloc[0]["shares"] == 12.5 * 1e4
    assert df.iloc[0]["market_value"] == 20000.0 * 1e4
    assert df.iloc[0]["weight"] == pytest.approx(0.0427)


def _prev_bar(db_session, code: str, adj_factor: float) -> None:
    db_session.add(
        InstrumentDailyBar(
            etf_code=code,
            trade_date=date(2026, 7, 17),
            close=10.0,
            pre_close=10.0,
            adj_factor=adj_factor,
        )
    )
    db_session.commit()


def _new_bar_df(code: str, adj_factor, close, pre_close) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "etf_code": code,
                "trade_date": date(2026, 7, 18),
                "close": close,
                "pre_close": pre_close,
                "adj_factor": adj_factor,
            }
        ]
    )


def _run_guardrail(db_session, df: pd.DataFrame, caplog) -> list[str]:
    pipeline = AStockDailyPipeline.__new__(AStockDailyPipeline)
    pipeline.db = db_session
    with caplog.at_level(logging.ERROR, logger="app.data.pipelines.a_share_stock_daily"):
        pipeline._check_adj_factor_continuity(df)
    return [r.getMessage() for r in caplog.records if r.levelno == logging.ERROR]


def test_guardrail_flags_baseline_seam(db_session, caplog):
    """Factor reset 10055.64 → 1.0 without a price gap must log ERROR."""
    _prev_bar(db_session, "600653.SH", 10055.64)
    errors = _run_guardrail(
        db_session, _new_bar_df("600653.SH", 1.0, close=10.0, pre_close=10.0), caplog
    )
    assert any("adj_factor discontinuity" in msg and "600653.SH" in msg for msg in errors)


def test_guardrail_quiet_on_continuous_factor(db_session, caplog):
    """A factor matching the previous bar must not alert."""
    _prev_bar(db_session, "600653.SH", 10055.64)
    errors = _run_guardrail(
        db_session,
        _new_bar_df("600653.SH", 10055.64, close=10.1, pre_close=10.0),
        caplog,
    )
    assert errors == []


def test_guardrail_quiet_on_genuine_corporate_action(db_session, caplog):
    """A 1:2 split (factor ×2, price ×0.5) is a matching gap — no alert."""
    _prev_bar(db_session, "600519.SH", 1.0)
    errors = _run_guardrail(
        db_session, _new_bar_df("600519.SH", 2.0, close=5.0, pre_close=10.0), caplog
    )
    assert errors == []
