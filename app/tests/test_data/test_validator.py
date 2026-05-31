"""Tests for the four-layer data validator."""

import pandas as pd
import pytest

from app.data.transformers.validator import validate_all


def test_validate_valid_data():
    """Normal data should pass all validations with is_valid=True and no errors."""
    df = pd.DataFrame({
        "etf_code": ["510300"],
        "trade_date": [pd.Timestamp("2024-01-01")],
        "open": [3.5],
        "high": [3.6],
        "low": [3.4],
        "close": [3.55],
        "volume": [1000000],
        "change_pct": [1.5],
    })
    result = validate_all(df)
    assert result.is_valid is True
    assert result.errors == []


def test_validate_high_less_than_low():
    """high < low should fail L2 business validation with is_valid=False."""
    df = pd.DataFrame({
        "etf_code": ["510300"],
        "trade_date": [pd.Timestamp("2024-01-01")],
        "open": [3.5],
        "high": [3.3],
        "low": [3.4],
        "close": [3.35],
        "volume": [1000000],
        "change_pct": [1.5],
    })
    result = validate_all(df)
    assert result.is_valid is False
    assert any("high < low" in e for e in result.errors)


def test_validate_extreme_change():
    """change_pct > 20%% should pass validation but produce warnings."""
    df = pd.DataFrame({
        "etf_code": ["510300"],
        "trade_date": [pd.Timestamp("2024-01-01")],
        "open": [3.5],
        "high": [3.6],
        "low": [3.4],
        "close": [3.55],
        "volume": [1000000],
        "change_pct": [25.0],
    })
    result = validate_all(df)
    assert result.is_valid is True
    assert len(result.warnings) > 0
    assert any("25.00" in w for w in result.warnings)
