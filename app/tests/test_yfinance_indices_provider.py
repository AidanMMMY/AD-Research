"""Tests for the yfinance-based macro indicators provider.

Covers the new Phase 6a additions on top of the existing stock-index
fetcher:

  * ``GLOBAL_FOREX_REGISTRY``   — FX tickers (CNY=X, EUR=X, JPY=X, DX-Y.NYB)
  * ``GLOBAL_RATES_REGISTRY``   — US Treasury yields (^TNX, ^TYX)
  * ``GLOBAL_COMMODITY_REGISTRY``— Crude futures (CL=F, BZ=F)
  * ``fetch_yfinance_macro_latest`` — batch fetcher that returns rows
    grouped by region so the orchestrator can upsert each region
    separately and share the (code, region) key with FRED rows.
  * FX inversion (``IndexMeta.invert_value``) — the 1/val flip on
    EUR=X / JPY=X so yfinance values match FRED's convention for the
    same internal code.

The yfinance HTTP layer is patched out — we never touch the network.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from app.data.providers import yfinance_indices_provider as yip


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fake_history_frame(dates, closes):
    """Build a yfinance-shaped DataFrame: tz-naive date index + Close column."""
    idx = pd.to_datetime(dates)
    return pd.DataFrame({"Close": closes}, index=idx)


def _patch_yf_history(monkeypatch, frame):
    """Replace ``yf.Ticker(...).history`` with a stub returning ``frame``."""
    ticker = MagicMock()
    ticker.history.return_value = frame
    fake = MagicMock()
    fake.Ticker.return_value = ticker
    monkeypatch.setattr(yip, "yf", fake)
    return ticker


# ---------------------------------------------------------------------------
# Registry — shape sanity
# ---------------------------------------------------------------------------


def test_forex_registry_has_expected_codes():
    """The four FRED-only FX codes must be present with matching codes."""
    codes = {m.code for m in yip.GLOBAL_FOREX_REGISTRY}
    expected = {"usd_cny", "usd_eur", "global_dxy", "global_usdjpy"}
    assert expected.issubset(codes), (
        f"Missing FX codes: {expected - codes}; "
        f"have: {sorted(codes)}"
    )


def test_rates_registry_has_expected_codes():
    codes = {m.code for m in yip.GLOBAL_RATES_REGISTRY}
    expected = {"us_dgs10", "us_dgs30"}
    assert expected.issubset(codes), (
        f"Missing rate codes: {expected - codes}; have: {sorted(codes)}"
    )


def test_commodity_registry_has_expected_codes():
    codes = {m.code for m in yip.GLOBAL_COMMODITY_REGISTRY}
    expected = {"global_brent", "global_wti"}
    assert expected.issubset(codes), (
        f"Missing commodity codes: {expected - codes}; have: {sorted(codes)}"
    )


def test_forex_registry_codes_match_fred_codes():
    """The yfinance codes must be identical to FRED's so latest_snapshot
    can pick the newer source on the (code, region) tie-break."""
    from app.services.macro.fred_service import (
        SERIES_REGISTRY,
        _GLOBAL_SERIES,
    )
    fred_us_codes = {m.code for m in SERIES_REGISTRY}
    fred_global_codes = {m.code for m in _GLOBAL_SERIES}
    fred_codes = fred_us_codes | fred_global_codes

    yf_codes = {m.code for m in yip.GLOBAL_FOREX_REGISTRY}
    # Every yfinance FX code MUST also exist in FRED's registry, with
    # the same string, so the snapshot can pick between them.
    assert yf_codes.issubset(fred_codes), (
        f"yfinance FX codes not in FRED registry: {yf_codes - fred_codes}"
    )


def test_indexmeta_has_invert_and_region_fields():
    """The optional fields on IndexMeta must exist and have correct defaults."""
    meta = yip.IndexMeta("^GSPC", "global_sp500", "标普500", "S&P 500")
    # Default for stock indices: no inversion, region='global'.
    assert meta.invert_value is False
    assert meta.region == "global"


def test_us_region_macro_codes_match_us_fred_codes():
    """The yfinance FX / rates codes we tag ``region='us'`` MUST exist in
    FRED's US registry under the same name — that's the only way the
    (code, region) key stays consistent across sources."""
    from app.services.macro.fred_service import SERIES_REGISTRY
    fred_us_codes = {m.code for m in SERIES_REGISTRY}
    us_region_codes = {
        m.code for m in (
            list(yip.GLOBAL_FOREX_REGISTRY)
            + list(yip.GLOBAL_RATES_REGISTRY)
        )
        if m.region == "us"
    }
    assert us_region_codes, "expected at least one region='us' macro code"
    assert us_region_codes.issubset(fred_us_codes), (
        f"region='us' macro codes not in FRED US registry: "
        f"{us_region_codes - fred_us_codes}"
    )


# ---------------------------------------------------------------------------
# FX inversion — IndexMeta.invert_value flips value + prev_close
# ---------------------------------------------------------------------------


def test_fetch_yfinance_index_inverts_when_meta_flag_set(monkeypatch):
    """EUR=X-style tickers must be inverted (1/val) before being stored."""
    frame = _fake_history_frame(
        dates=["2026-07-01", "2026-07-02", "2026-07-03"],
        closes=[1.0, 1.10, 1.20],  # "USD per EUR"
    )
    _patch_yf_history(monkeypatch, frame)

    meta = yip.IndexMeta(
        "EUR=X", "usd_eur", "美元/欧元", "USD/EUR", "EUR/USD",
        invert_value=True, region="us",
    )
    rows = yip.fetch_yfinance_index(meta)

    assert len(rows) == 3
    # First row: prev_close is None; value is 1/1.0 = 1.0.
    assert rows[0]["value"] == pytest.approx(1.0)
    assert rows[0]["prev_close"] is None
    # Second row: value = 1/1.10 ≈ 0.9091, prev_close = 1/1.0 = 1.0.
    assert rows[1]["value"] == pytest.approx(1.0 / 1.10)
    assert rows[1]["prev_close"] == pytest.approx(1.0)
    # Third row: value = 1/1.20 ≈ 0.8333, prev_close = 1/1.10.
    assert rows[2]["value"] == pytest.approx(1.0 / 1.20)
    assert rows[2]["prev_close"] == pytest.approx(1.0 / 1.10)


def test_fetch_yfinance_index_does_not_invert_by_default(monkeypatch):
    """For stock indices (and CNY=X / DXY / ^TNX / CL=F / BZ=F) the
    close is passed through verbatim."""
    frame = _fake_history_frame(
        dates=["2026-07-01", "2026-07-02"],
        closes=[100.0, 101.5],
    )
    _patch_yf_history(monkeypatch, frame)

    meta = yip.IndexMeta("^GSPC", "global_sp500", "标普500", "S&P 500")
    rows = yip.fetch_yfinance_index(meta)

    assert rows[0]["value"] == pytest.approx(100.0)
    assert rows[0]["prev_close"] is None
    assert rows[1]["value"] == pytest.approx(101.5)
    assert rows[1]["prev_close"] == pytest.approx(100.0)


def test_maybe_invert_skips_zero_to_avoid_divbyzero():
    """A zero close is a feed glitch — propagate as-is rather than raise."""
    assert yip._maybe_invert(0.0, invert=True) == 0.0
    assert yip._maybe_invert(None, invert=True) is None
    assert yip._maybe_invert(2.0, invert=False) == 2.0
    assert yip._maybe_invert(2.0, invert=True) == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# fetch_yfinance_macro_latest — batched, region-grouped
# ---------------------------------------------------------------------------


def test_macro_latest_returns_region_grouped_dict(monkeypatch):
    """All three registries must be walked; rows must be grouped by region."""
    # Stub yfinance so every ticker returns a single deterministic row.
    fake = MagicMock()

    def _make_ticker(t):
        t_obj = MagicMock()
        t_obj.history.return_value = _fake_history_frame(
            dates=["2026-07-01"], closes=[1.0],
        )
        return t_obj

    fake.Ticker.side_effect = _make_ticker
    monkeypatch.setattr(yip, "yf", fake)

    out = yip.fetch_yfinance_macro_latest()

    # us_region_codes: usd_cny (CNY=X, no invert), usd_eur (EUR=X, invert),
    # us_dgs10 (^TNX), us_dgs30 (^TYX).
    assert "us" in out, "expected region='us' in macro output"
    # global: global_dxy (DX-Y.NYB), global_usdjpy (JPY=X, invert),
    # global_brent (BZ=F), global_wti (CL=F).
    assert "global" in out, "expected region='global' in macro output"

    us_codes = {r["code"] for r in out["us"]}
    global_codes = {r["code"] for r in out["global"]}

    assert {"usd_cny", "usd_eur", "us_dgs10", "us_dgs30"}.issubset(us_codes)
    assert {"global_dxy", "global_usdjpy", "global_brent", "global_wti"}.issubset(
        global_codes
    )

    # Per-ticker failures should not have aborted the batch.
    assert len(out["us"]) >= 4
    assert len(out["global"]) >= 4


def test_macro_latest_handles_per_ticker_failure(monkeypatch):
    """A single ticker raising must not crash the batch — only that ticker
    is dropped, the rest still come through."""
    fake = MagicMock()

    def _make_ticker(ticker_str):
        t_obj = MagicMock()
        if ticker_str == "CNY=X":
            t_obj.history.side_effect = RuntimeError("simulated network error")
        else:
            t_obj.history.return_value = _fake_history_frame(
                dates=["2026-07-01"], closes=[1.0],
            )
        return t_obj

    fake.Ticker.side_effect = _make_ticker
    monkeypatch.setattr(yip, "yf", fake)

    out = yip.fetch_yfinance_macro_latest()

    # All non-CNY tickers must still produce at least one row.
    all_codes = {r["code"] for v in out.values() for r in v}
    assert "usd_cny" not in all_codes, "CNY=X should have failed"
    assert {"usd_eur", "us_dgs10", "us_dgs30"}.issubset(all_codes)
    assert {"global_dxy", "global_usdjpy", "global_brent", "global_wti"}.issubset(
        all_codes
    )


def test_macro_latest_forwards_start_end_kwargs(monkeypatch):
    """When ``start`` / ``end`` are provided, they must be forwarded to
    ``yf.Ticker.history`` so the scheduler can backfill a precise window."""
    fake = MagicMock()
    ticker = MagicMock()
    ticker.history.return_value = _fake_history_frame(
        dates=["2026-07-01"], closes=[1.0],
    )
    fake.Ticker.return_value = ticker
    monkeypatch.setattr(yip, "yf", fake)

    yip.fetch_yfinance_macro_latest(start="2026-06-01", end="2026-07-01")

    # At least one call to history() must have been made with the kwargs.
    kwargs_seen = [
        call.kwargs for call in ticker.history.call_args_list
    ]
    assert any(
        kw.get("start") == "2026-06-01" and kw.get("end") == "2026-07-01"
        for kw in kwargs_seen
    ), f"start/end not forwarded: {kwargs_seen[:3]}"


def test_macro_latest_inverts_eur_only():
    """Spot-check that the registry flags are wired correctly:
    EUR=X inverts (yfinance returns "EUR per USD" ~0.87; FRED DEXUSEU
    is "USD per EUR" ~1.14 — needs invert); CNY=X, JPY=X, ^TNX, CL=F
    do not (yfinance already returns FRED's convention)."""
    by_code = {m.code: m for m in (
        list(yip.GLOBAL_FOREX_REGISTRY)
        + list(yip.GLOBAL_RATES_REGISTRY)
        + list(yip.GLOBAL_COMMODITY_REGISTRY)
    )}
    # EUR=X: yfinance convention differs from FRED — invert needed.
    assert by_code["usd_eur"].invert_value is True
    # CNY=X, JPY=X, DXY: yfinance already matches FRED's convention.
    assert by_code["usd_cny"].invert_value is False
    assert by_code["global_usdjpy"].invert_value is False
    assert by_code["global_dxy"].invert_value is False
    # Rates + commodities: same unit as FRED, no inversion.
    assert by_code["us_dgs10"].invert_value is False
    assert by_code["us_dgs30"].invert_value is False
    assert by_code["global_brent"].invert_value is False
    assert by_code["global_wti"].invert_value is False


def test_macro_latest_uses_default_period_when_no_dates(monkeypatch):
    """When no start/end are provided, yfinance.history must be called with
    the default ``_HISTORY_PERIOD``."""
    fake = MagicMock()
    ticker = MagicMock()
    ticker.history.return_value = _fake_history_frame(
        dates=["2026-07-01"], closes=[1.0],
    )
    fake.Ticker.return_value = ticker
    monkeypatch.setattr(yip, "yf", fake)

    yip.fetch_yfinance_macro_latest()

    kwargs_seen = [call.kwargs for call in ticker.history.call_args_list]
    assert any(
        kw.get("period") == yip._HISTORY_PERIOD for kw in kwargs_seen
    ), f"default period not used: {kwargs_seen[:3]}"


# ---------------------------------------------------------------------------
# Orchestrator (global_indices_fetcher) integration — verify the new
# fetcher is wired into the refresh path with per-region upserts.
# ---------------------------------------------------------------------------


def test_refresh_calls_macro_fetcher(monkeypatch):
    """``run_global_indices_refresh`` must invoke ``fetch_macro_fx_rates_commodities``
    and upsert each region returned by it."""
    from app.services.macro import global_indices_fetcher as gif

    monkeypatch.setattr(gif, "fetch_a_share_indices", lambda: [])
    monkeypatch.setattr(gif, "fetch_international_indices", lambda: [])

    macro_calls = {"n": 0}

    def fake_macro():
        macro_calls["n"] += 1
        return {
            "us": [
                {
                    "code": "usd_cny", "period": "2026-07-01",
                    "value": 7.25, "prev_close": 7.24,
                    "name_zh": "美元/人民币", "name_en": "USD/CNY",
                    "unit": "CNY/USD",
                },
            ],
            "global": [
                {
                    "code": "global_brent", "period": "2026-07-01",
                    "value": 82.5, "prev_close": 82.0,
                    "name_zh": "布伦特原油", "name_en": "Brent Crude",
                    "unit": "USD/桶",
                },
            ],
        }

    monkeypatch.setattr(gif, "fetch_macro_fx_rates_commodities", fake_macro)

    upsert_calls: list[dict] = []

    class _FakeService:
        def __init__(self, db):  # noqa: ARG002
            pass

        def upsert_observations(self, region, source, observations):
            upsert_calls.append({
                "region": region, "source": source,
                "n": len(observations),
                "codes": [o["code"] for o in observations],
            })
            return len(observations)

    monkeypatch.setattr(gif, "MacroDataService", _FakeService)
    monkeypatch.setattr(gif, "SessionLocal", lambda: MagicMock())

    result = gif.run_global_indices_refresh()

    # The new fetcher must have been called.
    assert macro_calls["n"] == 1

    # Two region upserts (us, global) with the right codes.
    regions = {c["region"] for c in upsert_calls}
    assert {"us", "global"}.issubset(regions), (
        f"Missing region upserts: {regions}; all calls: {upsert_calls}"
    )

    # The macro upserts went through source='yfinance'.
    macro_calls_by_region = {
        c["region"]: c for c in upsert_calls if c["region"] in {"us", "global"}
    }
    assert macro_calls_by_region["us"]["source"] == "yfinance"
    assert macro_calls_by_region["global"]["source"] == "yfinance"
    assert "usd_cny" in macro_calls_by_region["us"]["codes"]
    assert "global_brent" in macro_calls_by_region["global"]["codes"]

    # Per-source counts are surfaced in the result so the scheduler log
    # can report what happened.
    per_source = result["per_source"]
    assert per_source["yfinance_macro_us"]["written"] == 1
    assert per_source["yfinance_macro_global"]["written"] == 1


def test_refresh_survives_empty_macro(monkeypatch):
    """Empty macro batch must not blow up — and must record 0s in per_source."""
    from app.services.macro import global_indices_fetcher as gif

    monkeypatch.setattr(gif, "fetch_a_share_indices", lambda: [])
    monkeypatch.setattr(gif, "fetch_international_indices", lambda: [])
    monkeypatch.setattr(
        gif, "fetch_macro_fx_rates_commodities",
        lambda: {"us": [], "global": []},
    )

    class _FakeService:
        def __init__(self, db):  # noqa: ARG002
            pass

        def upsert_observations(self, region, source, observations):  # noqa: ARG002
            return len(observations)

    monkeypatch.setattr(gif, "MacroDataService", _FakeService)
    monkeypatch.setattr(gif, "SessionLocal", lambda: MagicMock())

    result = gif.run_global_indices_refresh()

    assert result["per_source"]["yfinance_macro_us"] == {"fetched": 0, "written": 0}
    assert result["per_source"]["yfinance_macro_global"] == {
        "fetched": 0, "written": 0,
    }