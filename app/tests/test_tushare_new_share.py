"""Tests for Tushare ``new_share`` provider and free-tier fallback.

Covers:
- Helper utilities: derive_market / derive_board / compute_listing_status /
  _is_tushare_permission_error.
- ``TushareProvider.fetch_new_share`` happy path (returns list of dicts).
- ``fetch_new_share`` falls back to ``stock_basic`` when ``new_share`` raises
  a permission / 积分 error.
- ``fetch_new_share`` raises ``DataProviderError`` on non-permission errors.
- Empty DataFrame from ``new_share`` returns ``[]``.
- ``_fallback_recent_listings`` filters out rows whose ``list_date`` is older
  than the lookback window.
"""

from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from app.core.exceptions import DataProviderError
from app.data.providers.tushare_provider import (
    TushareProvider,
    _is_tushare_permission_error,
    compute_listing_status,
    derive_board,
    derive_market,
)


# ---------------------------------------------------------------------------
# Helper unit tests
# ---------------------------------------------------------------------------


class TestDeriveMarket:
    def test_sh_suffix(self):
        assert derive_market("600519.SH") == "SH"

    def test_sz_suffix(self):
        assert derive_market("001289.SZ") == "SZ"

    def test_bj_suffix(self):
        assert derive_market("830799.BJ") == "BJ"

    def test_full_exchange_alias(self):
        assert derive_market("600519.SSE") == "SH"
        assert derive_market("001289.SZSE") == "SZ"
        assert derive_market("830799.BSE") == "BJ"

    def test_unknown_suffix_passthrough(self):
        # Unknown suffix is returned uppercase for diagnostic visibility.
        assert derive_market("AAPL.O") == "O"

    def test_empty_or_invalid(self):
        assert derive_market("") == ""
        assert derive_market(None) == ""
        assert derive_market("nodot") == ""


class TestDeriveBoard:
    def test_main_board_sh(self):
        assert derive_board("600519.SH") == "主板"

    def test_main_board_sz(self):
        assert derive_board("001289.SZ") == "主板"

    def test_chinext(self):
        assert derive_board("300750.SZ") == "创业板"

    def test_star_market(self):
        assert derive_board("688981.SH") == "科创板"

    def test_bse_8_prefix(self):
        assert derive_board("830799.BJ") == "北交所"

    def test_bse_92_prefix(self):
        assert derive_board("920018.BJ") == "北交所"

    def test_bse_43_prefix(self):
        assert derive_board("430047.BJ") == "北交所"

    def test_empty_defaults_to_main_board(self):
        assert derive_board("") == "主板"


class TestComputeListingStatus:
    def test_listed(self):
        assert compute_listing_status(date(2025, 1, 1), date(2025, 1, 10), today=date(2025, 6, 1)) == "listed"

    def test_subscribing(self):
        assert compute_listing_status(date(2025, 5, 15), date(2025, 6, 15), today=date(2025, 5, 20)) == "subscribing"

    def test_upcoming(self):
        assert compute_listing_status(date(2025, 6, 15), date(2025, 6, 25), today=date(2025, 5, 20)) == "upcoming"

    def test_unknown_when_both_missing(self):
        assert compute_listing_status(None, None, today=date(2025, 6, 1)) == "unknown"

    def test_today_defaults_to_actual_today(self):
        # When today is unset, list_date == today should still be 'listed'.
        today = date.today()
        assert compute_listing_status(date.today() - timedelta(days=10), today, today) == "listed"


class TestPermissionErrorDetection:
    @pytest.mark.parametrize("msg", [
        "权限不足",
        "您没有该接口权限",
        "积分不足，请升级",
        "permission denied",
        "403 Forbidden",
        "401 Unauthorized",
    ])
    def test_detects_permission_markers(self, msg):
        assert _is_tushare_permission_error(msg) is True

    @pytest.mark.parametrize("msg", [
        "timeout",
        "Connection refused",
        "ValueError: bad data",
        "",
    ])
    def test_rejects_non_permission_messages(self, msg):
        assert _is_tushare_permission_error(msg) is False


# ---------------------------------------------------------------------------
# TushareProvider.fetch_new_share behavior tests
# ---------------------------------------------------------------------------


def _make_provider_with_pro(pro_mock: MagicMock) -> TushareProvider:
    """Build a TushareProvider whose ``self._pro`` is the given mock.

    Bypasses the ``__init__`` setup that requires a real token by injecting
    ``_pro`` directly.
    """
    provider = TushareProvider.__new__(TushareProvider)
    provider._pro = pro_mock
    # Disable rate limiter noise — tests run fast.
    provider._limiter = MagicMock()
    return provider


def _sample_new_share_df() -> pd.DataFrame:
    return pd.DataFrame([
        {
            "ts_code": "001289.SZ",
            "sub_code": "001289",
            "name": "Test Co A",
            "ipo_date": "20260115",
            "issue_date": "20260115",
            "list_date": "20260201",
            "price": 25.5,
            "pe": 22.3,
            "limit_amount": 10000.0,
            "funds": 50000.0,
            "market_amount": 20000.0,
            "industry": "电子",
            "sponsor": "Test Sponsor",
            "underwriter": "Test Underwriter",
        },
        {
            "ts_code": "688981.SH",
            "sub_code": "787981",
            "name": "Test Co B",
            "ipo_date": "20260120",
            "issue_date": "20260120",
            "list_date": "20260205",
            "price": 88.0,
            "pe": 45.2,
            "limit_amount": 5000.0,
            "funds": 300000.0,
            "market_amount": 10000.0,
            "industry": "信息技术",
            "sponsor": "Other Sponsor",
            "underwriter": "Other Underwriter",
        },
    ])


class TestFetchNewShareHappyPath:
    def test_returns_records_as_dicts(self):
        pro_mock = MagicMock()
        pro_mock.new_share.return_value = _sample_new_share_df()
        provider = _make_provider_with_pro(pro_mock)

        records = provider.fetch_new_share(start_date="20260101", end_date="20260301")

        assert isinstance(records, list)
        assert len(records) == 2
        first = records[0]
        assert first["ts_code"] == "001289.SZ"
        assert first["name"] == "Test Co A"
        assert first["price"] == 25.5

    def test_empty_dataframe_returns_empty_list(self):
        pro_mock = MagicMock()
        pro_mock.new_share.return_value = pd.DataFrame()
        provider = _make_provider_with_pro(pro_mock)

        records = provider.fetch_new_share()

        assert records == []


class TestFetchNewSharePermissionFallback:
    def test_falls_back_to_stock_basic_on_permission_error(self):
        pro_mock = MagicMock()
        pro_mock.new_share.side_effect = Exception("权限不足, 请升级积分")
        # stock_basic fallback returns one row from 5 days ago.
        recent_date = (date.today() - timedelta(days=5)).strftime("%Y%m%d")
        pro_mock.stock_basic.return_value = pd.DataFrame([
            {"ts_code": "600000.SH", "name": "Recent Co", "list_date": recent_date, "industry": "银行"},
        ])

        provider = _make_provider_with_pro(pro_mock)
        records = provider.fetch_new_share()

        assert len(records) == 1
        rec = records[0]
        assert rec["ts_code"] == "600000.SH"
        assert rec["name"] == "Recent Co"
        assert rec["list_date"] is not None
        pro_mock.stock_basic.assert_called_once()

    def test_falls_back_on_forbidden_marker(self):
        pro_mock = MagicMock()
        pro_mock.new_share.side_effect = Exception("HTTP 403 forbidden")
        pro_mock.stock_basic.return_value = pd.DataFrame(columns=["ts_code", "name", "list_date", "industry"])

        provider = _make_provider_with_pro(pro_mock)
        records = provider.fetch_new_share()

        assert records == []

    def test_fallback_silently_returns_empty_when_stock_basic_fails(self):
        pro_mock = MagicMock()
        pro_mock.new_share.side_effect = Exception("权限不足")
        pro_mock.stock_basic.side_effect = Exception("Network timeout")

        provider = _make_provider_with_pro(pro_mock)
        records = provider.fetch_new_share()

        assert records == []


class TestFetchNewShareNonPermissionErrors:
    def test_raises_data_provider_error_on_unrelated_exception(self):
        pro_mock = MagicMock()
        pro_mock.new_share.side_effect = Exception("Unexpected internal error")
        provider = _make_provider_with_pro(pro_mock)

        with pytest.raises(DataProviderError):
            provider.fetch_new_share()


class TestFallbackRecentListingsFiltering:
    def test_filters_out_old_listings(self):
        recent = (date.today() - timedelta(days=5)).strftime("%Y%m%d")
        old = (date.today() - timedelta(days=60)).strftime("%Y%m%d")
        pro_mock = MagicMock()
        pro_mock.stock_basic.return_value = pd.DataFrame([
            {"ts_code": "A.SZ", "name": "Recent", "list_date": recent, "industry": "X"},
            {"ts_code": "B.SZ", "name": "Old", "list_date": old, "industry": "Y"},
        ])
        provider = _make_provider_with_pro(pro_mock)

        records = provider._fallback_recent_listings(lookback_days=30)

        ts_codes = [r["ts_code"] for r in records]
        assert "A.SZ" in ts_codes
        assert "B.SZ" not in ts_codes

    def test_skips_rows_with_non_digit_list_date(self):
        pro_mock = MagicMock()
        pro_mock.stock_basic.return_value = pd.DataFrame([
            {"ts_code": "A.SZ", "name": "Bad", "list_date": "n/a", "industry": "X"},
        ])
        provider = _make_provider_with_pro(pro_mock)

        records = provider._fallback_recent_listings()

        assert records == []