"""Tests for the FRED API provider.

We never hit the real network in unit tests — ``requests.get`` is
patched to return canned JSON.  The tests below cover:

  * URL construction (api_key, series_id, start/end dates all wired in)
  * The "value is missing" sentinel (".") is filtered out
  * Missing API key raises DataProviderError
  * HTTP 429 triggers a retry, not an immediate failure
"""

from unittest.mock import MagicMock, patch

import pytest

from app.core.exceptions import DataProviderError
from app.data.providers.fred_provider import FredProvider


def _ok_response(json_payload: dict) -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    resp.headers = {}
    resp.json.return_value = json_payload
    resp.raise_for_status.return_value = None
    resp.text = ""
    return resp


def _rate_limit_response() -> MagicMock:
    resp = MagicMock()
    resp.status_code = 429
    resp.headers = {"Retry-After": "0"}
    resp.text = "rate limited"
    return resp


def test_get_series_requires_api_key():
    """Without a key, calling get_series must raise DataProviderError."""
    with patch("app.data.providers.fred_provider.get_settings") as gs:
        gs.return_value.fred_api_key = ""
        provider = FredProvider(api_key="")
        with pytest.raises(DataProviderError, match="FRED_API_KEY not configured"):
            provider.get_series("CPIAUCSL")


def test_get_series_url_construction_and_parsing():
    """The provider must hit /fred/series/observations with the right params."""
    payload = {
        "observations": [
            {"date": "2026-06-30", "value": "321.5"},
            {"date": "2026-05-31", "value": "320.8"},
            {"date": "2026-04-30", "value": "."},   # missing
            {"date": "2026-03-31", "value": ""},    # empty
        ]
    }
    captured_urls: list[str] = []

    def fake_get(url, timeout):  # noqa: ARG001
        captured_urls.append(url)
        return _ok_response(payload)

    with patch("app.data.providers.fred_provider.get_settings") as gs:
        gs.return_value.fred_api_key = "fake-key"
        with patch("app.data.providers.fred_provider.requests.get", side_effect=fake_get):
            provider = FredProvider()
            obs = provider.get_series(
                "CPIAUCSL",
                start_date="2026-01-01",
                end_date="2026-06-30",
            )

    assert len(obs) == 2
    assert obs[0] == {"date": "2026-06-30", "value": 321.5}
    assert obs[1] == {"date": "2026-05-31", "value": 320.8}

    assert len(captured_urls) == 1
    url = captured_urls[0]
    assert url.startswith("https://api.stlouisfed.org/fred/series/observations?")
    assert "series_id=CPIAUCSL" in url
    assert "api_key=fake-key" in url
    assert "file_type=json" in url
    assert "observation_start=2026-01-01" in url
    assert "observation_end=2026-06-30" in url


def test_get_series_retries_on_429():
    """A single 429 followed by success should return the parsed data."""
    payload = {"observations": [{"date": "2026-06-30", "value": "1.23"}]}
    responses = [_rate_limit_response(), _ok_response(payload)]

    with patch("app.data.providers.fred_provider.get_settings") as gs:
        gs.return_value.fred_api_key = "fake-key"
        with patch(
            "app.data.providers.fred_provider.requests.get", side_effect=responses
        ), patch("app.data.providers.fred_provider.time.sleep") as sleep_mock:
            provider = FredProvider()
            obs = provider.get_series("DGS10")

    assert obs == [{"date": "2026-06-30", "value": 1.23}]
    # Sleep was called at least once (between the 429 and the retry).
    assert sleep_mock.called


def test_get_series_raises_after_exhausting_retries():
    """All-429 should surface as DataProviderError."""
    with patch("app.data.providers.fred_provider.get_settings") as gs:
        gs.return_value.fred_api_key = "fake-key"
        with patch(
            "app.data.providers.fred_provider.requests.get",
            side_effect=[_rate_limit_response()] * 5,
        ), patch("app.data.providers.fred_provider.time.sleep"):
            provider = FredProvider()
            with pytest.raises(DataProviderError, match="failed after"):
                provider.get_series("DGS10")


def test_get_series_info_returns_none_without_key():
    """No key → graceful None (used as a best-effort enrichment)."""
    with patch("app.data.providers.fred_provider.get_settings") as gs:
        gs.return_value.fred_api_key = ""
        provider = FredProvider(api_key="")
        assert provider.get_series_info("DGS10") is None