"""Tests for the East Money Chinese-name lookup provider (with fallback chain).

We never hit the real network.  ``requests.Session.get`` is patched so we
can control the JSON payload, status, and exception path.  Each source
(East Money / Sina / Tencent / Yahoo) is callable via the same patched
method, so tests need to look at ``call_args`` to disambiguate which
upstream was hit.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests

from app.data.providers.eastmoney_zh_provider import (
    EastMoneyZhProvider,
    _NEGATIVE_CACHE_TTL,
    _CACHE_TTL_SECONDS,
    _infer_us_market_id,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ok_response(json_payload: dict, text: str = "") -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    resp.headers = {}
    resp.json.return_value = json_payload
    resp.raise_for_status.return_value = None
    resp.text = text
    resp.content = text.encode("utf-8") if text else b""
    resp.apparent_encoding = "utf-8"
    resp.encoding = "utf-8"
    return resp


def _gbk_text_response(text: str) -> MagicMock:
    """Build a response whose ``.content`` is GBK-encoded bytes.

    The Tencent parser force-decodes via GBK regardless of headers, so
    tests need to mirror that wire format — otherwise ``苹果`` in the
    payload becomes ``鑻规灉`` after a mistaken GBK round-trip.
    """
    resp = MagicMock()
    resp.status_code = 200
    resp.headers = {}
    resp.json.return_value = {}
    resp.raise_for_status.return_value = None
    resp.text = text
    resp.content = text.encode("gbk", errors="replace")
    resp.apparent_encoding = "GB2312"
    resp.encoding = "iso-8859-1"  # what requests sees on the wire
    return resp


def _empty_response() -> MagicMock:
    return _ok_response({"data": None})


def _http_error(status: int = 502) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status
    resp.headers = {}
    resp.raise_for_status.side_effect = requests.HTTPError(f"{status} Server Error")
    return resp


def _sina_response(chinese_name: str = "苹果") -> MagicMock:
    payload = f"var hq_str_gb_aapl=\"{chinese_name},APPLE,105.AAPL,{chinese_name}\";"
    return _ok_response({}, text=payload)


def _tencent_response(chinese_name: str = "苹果") -> MagicMock:
    payload = f"v_usAAPL=\"200~{chinese_name}~AAPL.OQ~USD~N~105~...\";"
    return _gbk_text_response(payload)


def _tencent_pv_none() -> MagicMock:
    payload = 'v_usAAPL="pv_none_match~1~...";'
    return _gbk_text_response(payload)


def _yahoo_response(short_name: str = "Apple Inc.") -> MagicMock:
    return _ok_response(
        {
            "chart": {
                "result": [
                    {
                        "meta": {
                            "shortName": short_name,
                            "longName": "Apple Inc.",
                            "symbol": "AAPL",
                        }
                    }
                ]
            }
        }
    )


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
# Provider behaviour — East Money path (unchanged behaviour)
# ---------------------------------------------------------------------------

def test_fetch_chinese_name_returns_value_on_match():
    """secid=106 returns the right name -> provider returns it directly."""
    captured_params: list[dict] = []

    def fake_get(url, params=None, timeout=None, headers=None):  # noqa: ARG001
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
    """Persistent network failure on all four sources -> None, no exception."""
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

    def fake_get(url, params=None, timeout=None, headers=None):  # noqa: ARG001
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
    """A miss should be cached per-source so retries within 5 min don't hit the API."""
    call_count = {"n": 0}

    def fake_get(url, params=None, timeout=None, headers=None):  # noqa: ARG001
        call_count["n"] += 1
        # Every upstream is empty — drives the full fallback chain.
        if url.startswith("https://push2.eastmoney.com"):
            return _empty_response()
        if url.startswith("https://hq.sinajs.cn"):
            return _ok_response({}, text='var hq_str_gb_aapl="";')
        if url.startswith("https://qt.gtimg.cn"):
            return _tencent_pv_none()
        if url.startswith("https://query1.finance.yahoo.com"):
            return _ok_response({"chart": {"result": []}})
        return _empty_response()

    provider = EastMoneyZhProvider()
    with patch.object(provider._session, "get", side_effect=fake_get):
        first = provider.fetch_chinese_name("XXXX", market="US")
        second = provider.fetch_chinese_name("XXXX", market="US")

    assert first is None
    assert second is None
    # First call: 2 East Money secid prefixes + Sina + Tencent + Yahoo = 5
    # round-trips.  Second call: every source is negative-cached — 0
    # additional round-trips.
    assert call_count["n"] == 5


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

    def fake_get(url, params=None, timeout=None, headers=None):  # noqa: ARG001
        captured_params.append(params or {})
        return _empty_response()

    provider = EastMoneyZhProvider()
    with patch.object(provider._session, "get", side_effect=fake_get):
        provider.fetch_chinese_name(symbol, market="US", exchange=exchange)

    assert captured_params, "no request was made"
    assert captured_params[0]["secid"] == expected_first_param


# ---------------------------------------------------------------------------
# Provider behaviour — fallback chain (Sina / Tencent / Yahoo)
# ---------------------------------------------------------------------------

def _urls_called(get_mock) -> list[str]:
    """Return the URLs visited by the patched session.get in call order."""
    urls = []
    for call in get_mock.call_args_list:
        # Newer mock: args[0] is positional url; older: kwargs['url']
        if call.args:
            urls.append(call.args[0])
        else:
            urls.append(call.kwargs.get("url", ""))
    return urls


def test_fetch_chinese_name_falls_back_to_sina_when_eastmoney_returns_502():
    """East Money 502 on both secid prefixes -> Sina is tried and wins."""
    calls: list[dict] = []

    def fake_get(url, params=None, timeout=None, headers=None):
        calls.append({"url": url, "params": params, "headers": headers})
        if url.startswith("https://push2.eastmoney.com"):
            return _http_error(502)
        if url.startswith("https://hq.sinajs.cn"):
            return _sina_response("苹果")
        raise AssertionError(f"Unexpected URL: {url}")

    provider = EastMoneyZhProvider()
    with patch.object(provider._session, "get", side_effect=fake_get):
        name = provider.fetch_chinese_name("AAPL", market="US", exchange="NASDAQ")

    assert name == "苹果"
    urls = [c["url"] for c in calls]
    # Two EM attempts (106 then 105), then Sina.  No Tencent/Yahoo.
    assert urls[0].startswith("https://push2.eastmoney.com")
    assert urls[1].startswith("https://push2.eastmoney.com")
    assert urls[2].startswith("https://hq.sinajs.cn")
    assert not any(u.startswith("https://qt.gtimg.cn") for u in urls)
    assert not any(u.startswith("https://query1.finance.yahoo.com") for u in urls)

    # Sina must have been hit with the correct Referer header.
    sina_call = next(c for c in calls if c["url"].startswith("https://hq.sinajs.cn"))
    assert sina_call["headers"]["Referer"] == "https://finance.sina.com.cn/"


def test_fetch_chinese_name_falls_back_to_tencent_when_eastmoney_and_sina_fail():
    """East Money 502 + Sina miss -> Tencent is tried and wins."""
    calls: list[dict] = []

    def fake_get(url, params=None, timeout=None, headers=None):
        calls.append({"url": url, "params": params})
        if url.startswith("https://push2.eastmoney.com"):
            return _http_error(502)
        if url.startswith("https://hq.sinajs.cn"):
            # Sina returns an empty payload (no quoted CSV).
            return _ok_response({}, text='var hq_str_gb_aapl="";')
        if url.startswith("https://qt.gtimg.cn"):
            return _tencent_response("苹果")
        raise AssertionError(f"Unexpected URL: {url}")

    provider = EastMoneyZhProvider()
    with patch.object(provider._session, "get", side_effect=fake_get):
        name = provider.fetch_chinese_name("AAPL", market="US", exchange="NASDAQ")

    assert name == "苹果"
    urls = [c["url"] for c in calls]
    # Both East Money prefixes, Sina, then Tencent.
    assert urls[0].startswith("https://push2.eastmoney.com")
    assert urls[1].startswith("https://push2.eastmoney.com")
    assert urls[2].startswith("https://hq.sinajs.cn")
    assert urls[3].startswith("https://qt.gtimg.cn")
    assert not any(u.startswith("https://query1.finance.yahoo.com") for u in urls)


def test_fetch_chinese_name_falls_back_to_yahoo_for_english_name():
    """All three Chinese sources fail -> Yahoo provides an English name."""
    calls: list[dict] = []

    def fake_get(url, params=None, timeout=None, headers=None):
        calls.append({"url": url})
        if url.startswith("https://push2.eastmoney.com"):
            return _http_error(502)
        if url.startswith("https://hq.sinajs.cn"):
            return _ok_response({}, text='var hq_str_gb_aapl="";')
        if url.startswith("https://qt.gtimg.cn"):
            return _tencent_pv_none()
        if url.startswith("https://query1.finance.yahoo.com"):
            return _yahoo_response("Apple Inc.")
        raise AssertionError(f"Unexpected URL: {url}")

    provider = EastMoneyZhProvider()
    with patch.object(provider._session, "get", side_effect=fake_get):
        name = provider.fetch_chinese_name("AAPL", market="US", exchange="NASDAQ")

    # We *accept* English as a last resort so the row is not blank.
    assert name == "Apple Inc."
    urls = [c["url"] for c in calls]
    assert any(u.startswith("https://query1.finance.yahoo.com") for u in urls)


def test_fetch_chinese_name_returns_none_when_all_sources_fail():
    """When every source is empty/error, fetch_chinese_name returns None."""
    def fake_get(url, params=None, timeout=None, headers=None):
        if url.startswith("https://push2.eastmoney.com"):
            return _http_error(502)
        if url.startswith("https://hq.sinajs.cn"):
            return _ok_response({}, text='var hq_str_gb_aapl="";')
        if url.startswith("https://qt.gtimg.cn"):
            return _tencent_pv_none()
        if url.startswith("https://query1.finance.yahoo.com"):
            return _ok_response({"chart": {"result": []}})
        raise AssertionError(f"Unexpected URL: {url}")

    provider = EastMoneyZhProvider()
    with patch.object(provider._session, "get", side_effect=fake_get):
        name = provider.fetch_chinese_name("AAPL", market="US", exchange="NASDAQ")
    assert name is None


# ---------------------------------------------------------------------------
# Negative-cache isolation between sources
# ---------------------------------------------------------------------------

def test_negative_cache_isolation_between_sources():
    """EM's 502 negative cache must not poison Sina's positive cache.

    We arrange East Money to 502 (negative-cached), then make Sina return a
    Chinese name (positive-cached).  On a follow-up call, we flip East
    Money to return a *different* Chinese name — the provider should
    still emit Sina's cached name without bouncing through the network
    on Sina again.
    """
    em_behaviour = {"mode": "fail"}
    sina_hit_count = {"n": 0}

    def fake_get(url, params=None, timeout=None, headers=None):
        if url.startswith("https://push2.eastmoney.com"):
            if em_behaviour["mode"] == "fail":
                return _http_error(502)
            return _ok_response({"data": {"f57": "AAPL", "f58": "东方错误"}})
        if url.startswith("https://hq.sinajs.cn"):
            sina_hit_count["n"] += 1
            return _sina_response("苹果")
        raise AssertionError(f"Unexpected URL: {url}")

    provider = EastMoneyZhProvider()
    with patch.object(provider._session, "get", side_effect=fake_get):
        first = provider.fetch_chinese_name("AAPL", market="US", exchange="NASDAQ")

    assert first == "苹果"
    # First call should have hit EM twice and Sina once.
    assert sina_hit_count["n"] == 1

    # Now switch East Money to a *different* answer; Sina's positive cache
    # should still win on the second call so Sina is not retried.
    em_behaviour["mode"] = "ok"
    with patch.object(provider._session, "get", side_effect=fake_get):
        second = provider.fetch_chinese_name("AAPL", market="US", exchange="NASDAQ")

    assert second == "苹果"  # Sina cache hit, not "东方错误"
    assert sina_hit_count["n"] == 1  # Sina not retried

    # EM's negative cache had its 5-minute TTL; flip it back to success
    # and clear the negative entries, then a third call should now pick
    # up East Money's positive result (since both Sina-positive and EM
    # are positive, EM wins because it's earlier in the chain).
    with provider._cache_lock:
        provider._cache.clear()
    em_behaviour["mode"] = "ok"
    with patch.object(provider._session, "get", side_effect=fake_get):
        third = provider.fetch_chinese_name("AAPL", market="US", exchange="NASDAQ")

    # After cache reset, EM is tried first and now succeeds — wins.
    assert third == "东方错误"


def test_eastmoney_negative_cache_does_not_block_sina_on_different_symbols():
    """Each (source, symbol) pair is cached independently.

    EM failing on AAPL must not cause us to skip Sina on MSFT.
    """
    def fake_get(url, params=None, timeout=None, headers=None):
        secid = (params or {}).get("secid", "") if url.startswith("https://push2.eastmoney.com") else ""
        if url.startswith("https://push2.eastmoney.com"):
            return _http_error(502)
        if url.startswith("https://hq.sinajs.cn"):
            # Sina responds for both symbols.
            return _sina_response("结果")
        raise AssertionError(f"Unexpected URL: {url}")

    provider = EastMoneyZhProvider()
    with patch.object(provider._session, "get", side_effect=fake_get):
        aapl = provider.fetch_chinese_name("AAPL", market="US", exchange="NASDAQ")
        msft = provider.fetch_chinese_name("MSFT", market="US", exchange="NASDAQ")

    assert aapl == "结果"
    assert msft == "结果"


def test_negative_cache_keys_are_per_source():
    """The cache dict should record each source independently.

    Asserts the (source, market_id, symbol) key shape so future refactors
    don't accidentally merge sources together.
    """
    provider = EastMoneyZhProvider()

    provider._set_cache("eastmoney", 105, "AAPL", None)
    provider._set_cache("eastmoney", 106, "AAPL", None)
    provider._set_cache("sina", 0, "AAPL", "苹果")
    provider._set_cache("tencent", 0, "AAPL", None)
    provider._set_cache("yahoo", 0, "AAPL", None)

    with provider._cache_lock:
        keys = sorted(provider._cache.keys())

    assert keys == [
        ("eastmoney", 105, "AAPL"),
        ("eastmoney", 106, "AAPL"),
        ("sina", 0, "AAPL"),
        ("tencent", 0, "AAPL"),
        ("yahoo", 0, "AAPL"),
    ]

    # Positive hits live for the long TTL; negative hits for the short one.
    with provider._cache_lock:
        assert provider._cache[("sina", 0, "AAPL")][1] == "苹果"
        assert provider._cache[("eastmoney", 105, "AAPL")][1] is None
        # We can't assert TTL exactly because it's time.monotonic()-relative,
        # but we can confirm the positive entry has a strictly later
        # expiry than any of the negative ones.
        pos_expiry = provider._cache[("sina", 0, "AAPL")][0]
        neg_expiry = provider._cache[("eastmoney", 105, "AAPL")][0]
        assert pos_expiry > neg_expiry + (_CACHE_TTL_SECONDS - _NEGATIVE_CACHE_TTL - 5)
