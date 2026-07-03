"""Tests for the East Money Chinese-name lookup provider.

We never hit the real network.  ``requests.Session.get`` is patched so we
can control the JSON payload, status, and exception path.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests

from app.data.providers.eastmoney_zh_provider import (
    EastMoneyZhProvider,
    _infer_us_market_id,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ok_response(json_payload: dict) -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    resp.headers = {}
    resp.json.return_value = json_payload
    resp.raise_for_status.return_value = None
    resp.text = ""
    return resp


def _empty_response() -> MagicMock:
    return _ok_response({"data": None})


# ---------------------------------------------------------------------------
# URL / secid heuristics
# ---------------------------------------------------------------------------

def test_infer_us_market_id_explicit_nasdaq():
    assert _infer_us_market_id("AAPL", "NASDAQ") == [106, 105]


def test_infer_us_market_id_explicit_nyse():
    assert _infer_us_market_id("SPY", "NYSE") == [105, 106]


def test_infer_us_market_id_falls_back_to_heuristic():
    # Five letter all-alpha -> NASDAQ first
    assert _infer_us_market_id("QQQ", None) == [105, 106]  # 3 chars -> NYSE first
    assert _infer_us_market_id("QQQMM", None) == [106, 105]  # 5 chars -> NASDAQ first
    assert _infer_us_market_id("SPY", None) == [105, 106]


# ---------------------------------------------------------------------------
# Provider behaviour
# ---------------------------------------------------------------------------

def test_fetch_chinese_name_returns_value_on_match():
    """secid=106 returns the right name -> provider returns it directly."""
    captured_params: list[dict] = []

    def fake_get(url, params=None, timeout=None):  # noqa: ARG001
        captured_params.append(params or {})
        return _ok_response({"data": {"f57": "AAPL", "f58": "苹果"}})

    provider = EastMoneyZhProvider()
    with patch.object(provider._session, "get", side_effect=fake_get):
        name = provider.fetch_chinese_name("AAPL", market="US", exchange="NASDAQ")

    assert name == "苹果"
    assert len(captured_params) == 1
    assert captured_params[0]["secid"] == "106.AAPL"


def test_fetch_chinese_name_falls_back_to_other_secid_on_mismatch():
    """If first secid returns the wrong f57, try the next prefix."""
    responses = [
        _ok_response({"data": {"f57": "AAPL", "f58": "苹果"}}),  # 106 hit
    ]

    provider = EastMoneyZhProvider()
    with patch.object(provider._session, "get", side_effect=responses):
        # Ask for NYSE first (105 -> 106).  The first call returns AAPL,
        # so we should be done after 1 round-trip.
        name = provider.fetch_chinese_name("AAPL", market="US", exchange="NYSE")
    assert name == "苹果"


def test_fetch_chinese_name_falls_back_when_first_secid_returns_empty():
    """First secid returns no data -> try the second."""
    responses = [
        _empty_response(),  # 105 miss
        _ok_response({"data": {"f57": "QQQ", "f58": "纳指100ETF"}}),  # 106 hit
    ]

    provider = EastMoneyZhProvider()
    with patch.object(provider._session, "get", side_effect=responses):
        # QQQ is 3 letters -> heuristic puts 105 first; we expect 2 round-trips.
        name = provider.fetch_chinese_name("QQQ", market="US")
    assert name == "纳指100ETF"


def test_fetch_chinese_name_returns_none_when_market_not_us():
    """Non-US markets are not yet wired up; provider short-circuits to None."""
    provider = EastMoneyZhProvider()
    with patch.object(provider._session, "get") as get_mock:
        name = provider.fetch_chinese_name("0700", market="HK")
    assert name is None
    get_mock.assert_not_called()


def test_fetch_chinese_name_returns_none_on_network_error():
    """Persistent network failure -> None, no exception bubbles out."""
    provider = EastMoneyZhProvider()
    with patch.object(
        provider._session,
        "get",
        side_effect=requests.ConnectionError("boom"),
    ):
        name = provider.fetch_chinese_name("AAPL", market="US", exchange="NASDAQ")
    assert name is None


def test_fetch_chinese_name_empty_symbol_returns_none():
    provider = EastMoneyZhProvider()
    with patch.object(provider._session, "get") as get_mock:
        assert provider.fetch_chinese_name("", market="US") is None
        assert provider.fetch_chinese_name("   ", market="US") is None
        get_mock.assert_not_called()


def test_fetch_chinese_name_uses_request_session_user_agent():
    """User-Agent header should be set on the session so requests aren't blocked."""
    provider = EastMoneyZhProvider()
    assert "Mozilla" in provider._session.headers.get("User-Agent", "")


def test_fetch_chinese_name_caches_positive_result():
    """A cached hit should not trigger a second network round-trip."""
    call_count = {"n": 0}

    def fake_get(url, params=None, timeout=None):  # noqa: ARG001
        call_count["n"] += 1
        return _ok_response({"data": {"f57": "AAPL", "f58": "苹果"}})

    provider = EastMoneyZhProvider()
    with patch.object(provider._session, "get", side_effect=fake_get):
        first = provider.fetch_chinese_name("AAPL", market="US", exchange="NASDAQ")
        second = provider.fetch_chinese_name("AAPL", market="US", exchange="NASDAQ")
        third = provider.fetch_chinese_name("aapl", market="US", exchange="NASDAQ")

    assert first == "苹果"
    assert second == "苹果"
    assert third == "苹果"
    # First call hit network; subsequent calls served from cache.
    assert call_count["n"] == 1


def test_fetch_chinese_name_caches_negative_result_for_short_window():
    """A miss should be cached too so retries within 5 min don't hit the API."""
    call_count = {"n": 0}

    def fake_get(url, params=None, timeout=None):  # noqa: ARG001
        call_count["n"] += 1
        return _empty_response()

    provider = EastMoneyZhProvider()
    with patch.object(provider._session, "get", side_effect=fake_get):
        first = provider.fetch_chinese_name("XXXX", market="US")
        second = provider.fetch_chinese_name("XXXX", market="US")

    assert first is None
    assert second is None
    # Negative cache -> only the first call walked the network for both
    # secid prefixes; the second call short-circuited via cache.
    assert call_count["n"] == 2


@pytest.mark.parametrize(
    "symbol, exchange, expected_first_param",
    [
        ("AAPL", "NASDAQ", "106.AAPL"),
        ("SPY", "NYSE", "105.SPY"),
        ("QQQ", None, "105.QQQ"),     # 3-char heuristic -> NYSE first
        ("QQQMM", None, "106.QQQMM"), # 5-char heuristic -> NASDAQ first
    ],
)
def test_fetch_chinese_name_first_secid_param(symbol, exchange, expected_first_param):
    """Make sure the URL parameter is exactly what we expect for the first attempt."""
    captured_params: list[dict] = []

    def fake_get(url, params=None, timeout=None):  # noqa: ARG001
        captured_params.append(params or {})
        return _empty_response()

    provider = EastMoneyZhProvider()
    with patch.object(provider._session, "get", side_effect=fake_get):
        provider.fetch_chinese_name(symbol, market="US", exchange=exchange)

    assert captured_params, "no request was made"
    assert captured_params[0]["secid"] == expected_first_param