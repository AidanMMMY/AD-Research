"""End-to-end test for ScreeningService.

Verifies multi-condition ETF screening on a seeded universe.
"""

from __future__ import annotations

import math

import pytest

from app.services.screening_service import ScreeningService


# ---------------------------------------------------------------------------
# Multi-condition screen
# ---------------------------------------------------------------------------


def test_screening_filters_by_sharpe_and_return(db_session, seeded_etf_universe):
    """Screen with sharpe_min + return_1m_min should exclude weak ETFs."""
    svc = ScreeningService(db_session)

    # 510500.SH (sharpe 1.4, return_1m 5.0) and 510300.SH (sharpe 2.0, return_1m 8.0)
    # and 513500.SH (sharpe 1.6, return_1m 3.0) and 512760.SH (sharpe 1.8, return_1m 10.0)
    # 511010.SH (sharpe 0.9, return_1m 0.5) should be excluded by sharpe>=1.2.
    result = svc.screen(
        market="E2E_SH",
        sharpe_min=1.2,
        return_1m_min=2.0,
        sort_by="sharpe_1y",
        sort_order="desc",
        limit=20,
    )

    # Shape
    assert isinstance(result, dict)
    for key in ("items", "count", "offset", "limit"):
        assert key in result, f"Missing key {key} in screen() result"
    assert isinstance(result["items"], list)
    assert isinstance(result["count"], int)
    assert result["count"] >= 1, "Expected at least one ETF to pass the filter"

    # Excluded: 511010.SH (treasury, sharpe 0.9, return 0.5%)
    codes = {item["code"] for item in result["items"]}
    assert "511010.SH" not in codes, "Treasury ETF should be filtered out by sharpe/return"

    # All returned rows must satisfy the filter
    for item in result["items"]:
        sharpe = item["sharpe_1y"]
        return_1m = item["return_1m"]
        if sharpe is not None:
            assert sharpe >= 1.2, f"ETF {item['code']} has sharpe {sharpe} < 1.2"
        if return_1m is not None:
            assert return_1m >= 2.0, f"ETF {item['code']} has return_1m {return_1m} < 2.0"


def test_screening_sort_order_desc(db_session, seeded_etf_universe):
    """sort_order=desc should put highest sharpe first."""
    svc = ScreeningService(db_session)
    result = svc.screen(
        market="E2E_SH",
        sort_by="sharpe_1y",
        sort_order="desc",
        limit=10,
    )
    items = result["items"]
    assert len(items) >= 2
    sharpes = [it["sharpe_1y"] for it in items if it["sharpe_1y"] is not None]
    # Non-increasing
    for a, b in zip(sharpes, sharpes[1:]):
        assert a >= b, f"Sharpe sequence not descending: {sharpes}"


def test_screening_preset_high_sharpe_low_vol(db_session, seeded_etf_universe):
    """The 'high_sharpe_low_vol' preset should apply sharpe_min + volatility_max."""
    svc = ScreeningService(db_session)
    result = svc.screen_by_preset("high_sharpe_low_vol", limit=20)
    assert "preset" in result
    assert result["preset"]["key"] == "high_sharpe_low_vol"
    for item in result["items"]:
        sharpe = item["sharpe_1y"]
        vol = item["volatility_20d"]
        if sharpe is not None:
            assert sharpe >= 1.0, f"Sharpe {sharpe} < 1.0 in preset result"
        if vol is not None:
            assert vol <= 20.0, f"Volatility {vol} > 20% in preset result"


def test_screening_get_presets_returns_four(db_session):
    """get_presets() returns the four documented preset configurations."""
    svc = ScreeningService(db_session)
    presets = svc.get_presets()
    assert isinstance(presets, list)
    assert len(presets) >= 4
    keys = {p["key"] for p in presets}
    assert "high_sharpe_low_vol" in keys
    assert "trend_strong" in keys
    assert "value_pit" in keys
    assert "liquidity_sufficient" in keys


def test_screening_get_categories(db_session, seeded_etf_universe):
    """get_categories should aggregate active ETFs by category."""
    svc = ScreeningService(db_session)
    categories = svc.get_categories(market="E2E_SH")
    assert isinstance(categories, list)
    # Seeded universe has 3 distinct categories (股票型 x3, 债券型 x1, 商品型 x1)
    assert len(categories) == 3
    # Each entry has a count > 0
    for cat in categories:
        assert cat["count"] > 0
    # The 股票型 category should have 3 ETFs
    by_cat = {c["category"]: c["count"] for c in categories}
    assert by_cat["股票型"] == 3
    assert by_cat["债券型"] == 1
    assert by_cat["商品型"] == 1


def test_screening_pagination(db_session, seeded_etf_universe):
    """Limit + offset should paginate correctly."""
    svc = ScreeningService(db_session)
    page1 = svc.screen(market="E2E_SH", sort_by="sharpe_1y", sort_order="desc", offset=0, limit=2)
    page2 = svc.screen(market="E2E_SH", sort_by="sharpe_1y", sort_order="desc", offset=2, limit=2)
    assert len(page1["items"]) == 2
    assert len(page2["items"]) >= 1
    # No overlap
    page1_codes = {it["code"] for it in page1["items"]}
    page2_codes = {it["code"] for it in page2["items"]}
    assert page1_codes.isdisjoint(page2_codes)
