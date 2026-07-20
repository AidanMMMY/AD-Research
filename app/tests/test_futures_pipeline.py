"""Tests for the futures ETL pipelines.

Focuses on:
- ``_symbol_root`` extracts alphabetic root from continuous contract codes.
- ``_classify_product`` maps (exchange, symbol_root) to product category.
- ``_coerce_date`` / ``_coerce_int`` / ``_coerce_float`` helpers.
- DCE fetcher (``_fetch_dce_via_main_sina`` / ``_dce_main_contracts``) maps
  sina's Chinese-column response into the canonical English schema and trims
  to the requested window, with the rest of the pipeline downstream.
- ``FuturesContractDiscoveryPipeline`` upserts main contracts derived from
  per-exchange akshare data, including product classification.
- ``FuturesDailyPipeline`` extracts, transforms and loads daily bars from
  per-exchange akshare endpoints into the DB (mocked), with cache
  invalidation.
- ``scheduler.run_futures_daily`` (the cron-driven entry at 16:30 Asia/Shanghai)
  delegates to ``FuturesDailyPipeline`` and ultimately exercises the DCE branch
  inside ``fetch_all_markets``.
"""

from datetime import date
from decimal import Decimal
from unittest.mock import patch

import pandas as pd
import pytest

from app.core import scheduler as core_scheduler
from app.data.pipelines.futures import (
    FuturesContractDiscoveryPipeline,
    FuturesDailyPipeline,
    _classify_product,
    _coerce_date,
    _coerce_float,
    _coerce_int,
    _dce_main_contracts,
    _fetch_dce_via_main_sina,
    _pick_main_per_day,
    _symbol_root,
    fetch_all_markets,
)
from app.models.futures import FuturesContract, FuturesDailyBar


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


class TestSymbolRoot:
    @pytest.mark.parametrize("symbol,expected", [
        ("CU0", "CU"),
        ("M0", "M"),
        ("IF0", "IF"),
        ("AU2506", "AU"),
        ("TA2509", "TA"),
        ("PTA2606", "PTA"),
        ("V2606", "V"),
    ])
    def test_extracts_alphabetic_prefix(self, symbol, expected):
        assert _symbol_root(symbol) == expected


class TestClassifyProduct:
    @pytest.mark.parametrize("exchange,symbol_root,expected", [
        ("SHFE", "CU", "金属"),
        ("DCE", "M", "农产品"),
        ("CZCE", "SR", "农产品"),
        ("CFFEX", "IF", "金融期货"),
        ("INE", "SC", "能源化工"),
        ("GFEX", "SI", "金属"),
        ("SHFE", "UNKNOWN", "其他"),  # falls back
    ])
    def test_classifies_by_exchange_and_root(self, exchange, symbol_root, expected):
        assert _classify_product(exchange, symbol_root) == expected


class TestCoerceDate:
    @pytest.mark.parametrize("value,expected", [
        ("2026-07-01", date(2026, 7, 1)),
        ("2026/07/01", date(2026, 7, 1)),
        (date(2026, 7, 1), date(2026, 7, 1)),
        (None, None),
    ])
    def test_parses_supported_formats(self, value, expected):
        assert _coerce_date(value) == expected

    def test_returns_none_for_unparseable(self):
        assert _coerce_date("not-a-date") is None


class TestCoerceInt:
    def test_int_passthrough(self):
        assert _coerce_int(42) == 42

    def test_float_string(self):
        assert _coerce_int("100") == 100

    def test_nan_returns_none(self):
        assert _coerce_int(float("nan")) is None

    def test_none_returns_none(self):
        assert _coerce_int(None) is None

    def test_invalid_string_returns_none(self):
        assert _coerce_int("not-a-number") is None


class TestCoerceFloat:
    def test_float_passthrough(self):
        assert _coerce_float(3.14) == 3.14

    def test_int_to_float(self):
        assert _coerce_float(5) == 5.0

    def test_string(self):
        assert _coerce_float("1.23") == 1.23

    def test_nan_returns_none(self):
        assert _coerce_float(float("nan")) is None

    def test_none_returns_none(self):
        assert _coerce_float(None) is None


# ---------------------------------------------------------------------------
# Main-contract pick helper
# ---------------------------------------------------------------------------


class TestPickMainPerDay:
    def test_picks_highest_open_interest_per_variety_day(self):
        df = pd.DataFrame(
            [
                {"date": "2026-07-01", "variety": "CU", "symbol": "CU2607",
                 "open_interest": 44610, "open": 100.0, "close": 101.0},
                {"date": "2026-07-01", "variety": "CU", "symbol": "CU2608",
                 "open_interest": 154212, "open": 102.0, "close": 103.0},
                {"date": "2026-07-01", "variety": "AU", "symbol": "AU2608",
                 "open_interest": 50000, "open": 200.0, "close": 201.0},
                {"date": "2026-07-02", "variety": "CU", "symbol": "CU2608",
                 "open_interest": 150000, "open": 102.0, "close": 103.0},
            ]
        )
        out = _pick_main_per_day(df)
        assert len(out) == 3  # one row per (date, variety)
        cu_0701 = out[(out["date"] == "2026-07-01") & (out["variety"] == "CU")]
        assert cu_0701.iloc[0]["symbol"] == "CU2608"
        au_0701 = out[(out["date"] == "2026-07-01") & (out["variety"] == "AU")]
        assert au_0701.iloc[0]["symbol"] == "AU2608"

    def test_returns_empty_for_empty_frame(self):
        assert _pick_main_per_day(pd.DataFrame()).empty


# ---------------------------------------------------------------------------
# DCE fetcher (uses ak.futures_main_sina under the hood)
# ---------------------------------------------------------------------------


def _fake_main_sina(symbol: str) -> pd.DataFrame:
    """Build a small fake sina response with Chinese column names."""

    dates = ["2026-07-06", "2026-07-07", "2026-07-08"]
    if symbol == "M0":
        opens = [3030.0, 3039.0, 3045.0]
        highs = [3055.0, 3046.0, 3059.0]
        lows = [3025.0, 3030.0, 3027.0]
        closes = [3040.0, 3045.0, 3051.0]
        volumes = [1000000, 1017070, 993980]
        oi = [1900000, 1893351, 1915914]
        settle = [3038.0, 3038.0, 3045.0]
    else:
        opens = [100.0, 101.0, 102.0]
        highs = [101.0, 102.0, 103.0]
        lows = [99.0, 100.0, 101.0]
        closes = [100.5, 101.5, 102.5]
        volumes = [1000, 2000, 3000]
        oi = [5000, 5500, 6000]
        settle = [100.4, 101.4, 102.4]
    return pd.DataFrame(
        {
            "日期": dates,
            "开盘价": opens,
            "最高价": highs,
            "最低价": lows,
            "收盘价": closes,
            "成交量": volumes,
            "持仓量": oi,
            "动态结算价": settle,
        }
    )


_FAKE_DISPLAY_DCE = pd.DataFrame(
    {
        "symbol": ["M0", "JD0", "I0", "V0", "BB0"],
        "exchange": ["dce", "dce", "dce", "dce", "dce"],
        "name": ["豆粕连续", "鸡蛋连续", "铁矿石连续", "PVC连续", "胶合板连续"],
    }
)


class TestDCEFetcher:
    """Mocks akshare endpoints to verify the DCE path produces rows.

    Real ``ak.futures_main_sina`` is exercised in production; here we just
    confirm the column-mapping and window-trim logic.
    """

    def test_dce_main_contracts_filters_to_tracked_varieties(self):
        with patch(
            "app.data.pipelines.futures.ak.futures_display_main_sina",
            return_value=_FAKE_DISPLAY_DCE,
        ):
            syms = _dce_main_contracts()
        # M/JD/I/V/BB are all in _PRODUCT_MAP for DCE; the helper only
        # trims to map presence (suspended varieties like BB0 will simply
        # return zero bars when we fetch history).
        assert set(syms) == {"M0", "JD0", "I0", "V0", "BB0"}

    def test_dce_main_contracts_empty_on_display_error(self):
        with patch(
            "app.data.pipelines.futures.ak.futures_display_main_sina",
            side_effect=Exception("network"),
        ):
            assert _dce_main_contracts() == []

    def test_fetch_dce_via_main_sina_renames_columns_and_trims_window(self):
        def _display():
            return _FAKE_DISPLAY_DCE

        def _main(symbol):
            return _fake_main_sina(symbol)

        with patch(
            "app.data.pipelines.futures.ak.futures_display_main_sina",
            side_effect=_display,
        ), patch(
            "app.data.pipelines.futures.ak.futures_main_sina",
            side_effect=_main,
        ):
            df = _fetch_dce_via_main_sina(
                date(2026, 7, 7), date(2026, 7, 8)
            )

        # 5 tracked DCE contracts (M/JD/I/V/BB) × 2 days inside window
        # (the 2026-07-06 day is dropped by the window trim).
        assert len(df) == 10
        # Columns the rest of the pipeline expects are present and have
        # correct English names.
        for col in (
            "date", "open", "high", "low", "close",
            "volume", "open_interest", "settle",
            "symbol", "variety", "exchange",
        ):
            assert col in df.columns, f"missing column {col!r}"
        # Chinese column names should be gone.
        assert "日期" not in df.columns
        # Exchange tag is DCE for every row.
        assert (df["exchange"] == "DCE").all()
        # All 5 varieties are represented.
        assert set(df["variety"].unique()) == {"M", "JD", "I", "V", "BB"}
        # Dates are date objects inside the window.
        assert df["date"].between(
            date(2026, 7, 7), date(2026, 7, 8)
        ).all()

    def test_fetch_dce_via_main_sina_skips_varieties_with_errors(self):
        def _display():
            return _FAKE_DISPLAY_DCE

        def _main(symbol):
            if symbol == "JD0":
                raise Exception("upstream 500")
            return _fake_main_sina(symbol)

        with patch(
            "app.data.pipelines.futures.ak.futures_display_main_sina",
            side_effect=_display,
        ), patch(
            "app.data.pipelines.futures.ak.futures_main_sina",
            side_effect=_main,
        ):
            df = _fetch_dce_via_main_sina(
                date(2026, 7, 7), date(2026, 7, 8)
            )

        # Only JD0 failed; the other 4 tracked varieties came back.
        # 4 varieties × 2 days inside window = 8 rows.
        assert set(df["variety"].unique()) == {"M", "I", "V", "BB"}
        assert len(df) == 8

    def test_fetch_dce_via_main_sina_empty_when_no_contracts(self):
        with patch(
            "app.data.pipelines.futures.ak.futures_display_main_sina",
            return_value=pd.DataFrame(columns=["symbol", "exchange", "name"]),
        ):
            df = _fetch_dce_via_main_sina(
                date(2026, 7, 7), date(2026, 7, 8)
            )
        assert df.empty


# ---------------------------------------------------------------------------
# Contract discovery pipeline
# ---------------------------------------------------------------------------


def _build_market_frame(exchange: str, rows: list[dict]) -> pd.DataFrame:
    """Helper to build a per-exchange per-contract frame.

    Mimics the shape returned by ``ak.get_futures_daily(market=...)``:
      symbol / date / open / high / low / close / volume / open_interest /
      turnover / settle / pre_settle / variety
    """
    df = pd.DataFrame(rows)
    df["exchange"] = exchange
    return df


SAMPLE_SHFE = _build_market_frame(
    "SHFE",
    [
        # day 1: CU2608 is the leader (highest OI)
        {"symbol": "CU2607", "date": "2026-07-01", "variety": "CU",
         "open": 100.0, "high": 102.0, "low": 99.0, "close": 101.0,
         "volume": 15210, "open_interest": 44610, "turnover": 1.0,
         "settle": 102.1, "pre_settle": 102.34},
        {"symbol": "CU2608", "date": "2026-07-01", "variety": "CU",
         "open": 102.0, "high": 104.0, "low": 101.0, "close": 103.0,
         "volume": 84616, "open_interest": 154212, "turnover": 4.0,
         "settle": 102.5, "pre_settle": 102.49},
        # day 1: also have an AU contract (the second variety in this frame)
        {"symbol": "AU2607", "date": "2026-07-01", "variety": "AU",
         "open": 205.0, "high": 207.0, "low": 204.0, "close": 206.0,
         "volume": 2000, "open_interest": 80000, "turnover": 4.0,
         "settle": 206.5, "pre_settle": 206.6},
        # day 2 (latest): AU2608 is the leader
        {"symbol": "AU2607", "date": "2026-07-02", "variety": "AU",
         "open": 200.0, "high": 202.0, "low": 199.0, "close": 201.0,
         "volume": 1000, "open_interest": 5000, "turnover": 2.0,
         "settle": 200.5, "pre_settle": 200.6},
        {"symbol": "AU2608", "date": "2026-07-02", "variety": "AU",
         "open": 210.0, "high": 212.0, "low": 209.0, "close": 211.0,
         "volume": 9000, "open_interest": 90000, "turnover": 9.0,
         "settle": 210.5, "pre_settle": 210.6},
        # day 2 also: CU2608 still the leader
        {"symbol": "CU2607", "date": "2026-07-02", "variety": "CU",
         "open": 102.0, "high": 104.0, "low": 101.0, "close": 103.0,
         "volume": 15000, "open_interest": 44000, "turnover": 1.5,
         "settle": 103.0, "pre_settle": 102.1},
        {"symbol": "CU2608", "date": "2026-07-02", "variety": "CU",
         "open": 103.0, "high": 105.0, "low": 102.0, "close": 104.0,
         "volume": 80000, "open_interest": 150000, "turnover": 4.2,
         "settle": 103.5, "pre_settle": 102.5},
    ],
)


SAMPLE_CFFEX = _build_market_frame(
    "CFFEX",
    [
        {"symbol": "IF2607", "date": "2026-07-02", "variety": "IF",
         "open": 4000.0, "high": 4050.0, "low": 3990.0, "close": 4040.0,
         "volume": 50000, "open_interest": 100000, "turnover": 200.0,
         "settle": 4040.0, "pre_settle": 4030.0},
    ],
)


SAMPLE_DCE = _build_market_frame(
    "DCE",
    [
        {"symbol": "M2509", "date": "2026-07-02", "variety": "M",
         "open": 3000.0, "high": 3010.0, "low": 2990.0, "close": 3005.0,
         "volume": 10000, "open_interest": 200000, "turnover": 30.0,
         "settle": 3005.0, "pre_settle": 3000.0},
    ],
)


def _patch_fetch_all_markets(payload: dict[str, pd.DataFrame] | None):
    """Patch ``fetch_all_markets`` so discovery/daily extract don't hit the network.

    Pass ``None`` to simulate a fully failed fetch (all empty DataFrames).
    """
    if payload is None:
        return patch(
            "app.data.pipelines.futures.fetch_all_markets",
            return_value={
                "SHFE": pd.DataFrame(),
                "CZCE": pd.DataFrame(),
                "CFFEX": pd.DataFrame(),
                "INE": pd.DataFrame(),
                "GFEX": pd.DataFrame(),
                "DCE": pd.DataFrame(),
            },
        )
    # Fill in empty frames for the exchanges not in the payload.
    full = {ex: pd.DataFrame() for ex in
            ("SHFE", "CZCE", "CFFEX", "INE", "GFEX", "DCE")}
    full.update(payload)
    return patch("app.data.pipelines.futures.fetch_all_markets", return_value=full)


def test_discovery_pipeline_extracts_one_row_per_variety(db_session):
    with _patch_fetch_all_markets({"SHFE": SAMPLE_SHFE}):
        pipeline = FuturesContractDiscoveryPipeline(db_session)
        rows = pipeline.extract()
    # SHFE day 2 has CU + AU = 2 main contracts
    assert len(rows) == 2
    codes = set(rows["code"].tolist())
    assert codes == {"CU0", "AU0"}
    # Underlying instruments should be the highest-OI contract on the latest date
    by_code = {r["code"]: r for _, r in rows.iterrows()}
    assert by_code["CU0"]["underlying_instrument"] == "CU2608"
    assert by_code["AU0"]["underlying_instrument"] == "AU2608"


def test_discovery_pipeline_classifies_products(db_session):
    payload = {
        "SHFE": SAMPLE_SHFE,
        "CFFEX": SAMPLE_CFFEX,
        "DCE": SAMPLE_DCE,
    }
    with _patch_fetch_all_markets(payload):
        pipeline = FuturesContractDiscoveryPipeline(db_session)
        rows = pipeline.extract()

    by_code = {r["code"]: r for _, r in rows.iterrows()}
    assert by_code["CU0"]["product"] == "金属"
    assert by_code["AU0"]["product"] == "金属"
    assert by_code["IF0"]["product"] == "金融期货"
    assert by_code["M0"]["product"] == "农产品"


def test_discovery_pipeline_load_writes_rows(db_session):
    with _patch_fetch_all_markets({"SHFE": SAMPLE_SHFE}):
        pipeline = FuturesContractDiscoveryPipeline(db_session)
        df = pipeline.extract()
        n = pipeline.load(df)

    assert n == 2
    rows = db_session.query(FuturesContract).all()
    assert len(rows) == 2


def test_discovery_pipeline_is_idempotent(db_session):
    with _patch_fetch_all_markets({"SHFE": SAMPLE_SHFE}):
        pipeline = FuturesContractDiscoveryPipeline(db_session)
        pipeline.load(pipeline.extract())

    with _patch_fetch_all_markets({"SHFE": SAMPLE_SHFE}):
        pipeline2 = FuturesContractDiscoveryPipeline(db_session)
        pipeline2.load(pipeline2.extract())

    # Upsert on `code` keeps row count at 2
    assert db_session.query(FuturesContract).count() == 2


def test_discovery_pipeline_handles_empty_response(db_session):
    with _patch_fetch_all_markets(None):
        pipeline = FuturesContractDiscoveryPipeline(db_session)
        df = pipeline.extract()
        n = pipeline.load(df)
    assert df.empty
    assert n == 0


def test_discovery_pipeline_handles_akshare_exception(db_session):
    """If the upstream call raises, extract returns an empty DataFrame (no crash)."""
    with patch(
        "app.data.pipelines.futures.fetch_all_markets",
        side_effect=Exception("network error"),
    ):
        pipeline = FuturesContractDiscoveryPipeline(db_session)
        df = pipeline.extract()
        n = pipeline.load(df)
    assert df.empty
    assert n == 0


def test_discovery_pipeline_run_succeeds_without_ohlcv_validation(db_session):
    """run() must bypass the ETF OHLCV validator (which expects trade_date/open/...)."""
    with _patch_fetch_all_markets({"SHFE": SAMPLE_SHFE}):
        pipeline = FuturesContractDiscoveryPipeline(db_session)
        result = pipeline.run()
    assert result.success is True
    assert result.records == 2
    assert db_session.query(FuturesContract).count() == 2


# ---------------------------------------------------------------------------
# Daily bar pipeline
# ---------------------------------------------------------------------------


def _seed_main_contract(db, code="CU0", exchange="SHFE", product="金属"):
    db.add(
        FuturesContract(
            code=code,
            name=f"{code}主力",
            exchange=exchange,
            product=product,
            is_main=True,
            source="akshare",
        )
    )


def test_daily_pipeline_extract_picks_highest_oi_per_day(db_session):
    _seed_main_contract(db_session, code="CU0", exchange="SHFE", product="金属")
    _seed_main_contract(db_session, code="AU0", exchange="SHFE", product="金属")
    db_session.commit()

    with _patch_fetch_all_markets({"SHFE": SAMPLE_SHFE}):
        pipeline = FuturesDailyPipeline(db_session)
        out = pipeline.extract()

    # Two varieties × two days = 4 rows
    assert len(out) == 4
    # Every row's symbol must be the leading contract (CU2608 / AU2608)
    assert set(out["etf_code"].tolist()) == {"CU0", "AU0"}
    # The CU bar on day 2 should reflect CU2608's close (104.0)
    cu_day2 = out[(out["etf_code"] == "CU0") & (out["trade_date"] == date(2026, 7, 2))]
    assert float(cu_day2.iloc[0]["close"]) == 104.0


def test_daily_pipeline_pre_settle_inherited_when_symbol_unchanged(db_session):
    """Same picked contract two days running → pre_settle = previous day's settle."""
    _seed_main_contract(db_session, code="CU0", exchange="SHFE", product="金属")
    _seed_main_contract(db_session, code="AU0", exchange="SHFE", product="金属")
    db_session.commit()

    with _patch_fetch_all_markets({"SHFE": SAMPLE_SHFE}):
        pipeline = FuturesDailyPipeline(db_session)
        out = pipeline.extract()

    # CU2608 leads on both days: day2 pre_settle must equal day1 settle (102.5).
    cu_day2 = out[(out["etf_code"] == "CU0") & (out["trade_date"] == date(2026, 7, 2))]
    assert float(cu_day2.iloc[0]["pre_settle"]) == 102.5


def test_daily_pipeline_pre_settle_none_on_main_contract_roll(db_session):
    """On a main-contract roll the previous settle belongs to the old contract.

    Carrying it over distorts the daily change (production incident: CFFEX
    delivery-day roll showed -3.44% instead of -1.18%), so pre_settle must
    be left empty and the front end shows "-".
    """
    _seed_main_contract(db_session, code="CU0", exchange="SHFE", product="金属")
    db_session.commit()

    rolled = _build_market_frame(
        "SHFE",
        [
            # day 1: CU2607 leads on open interest
            {"symbol": "CU2607", "date": "2026-07-01", "variety": "CU",
             "open": 100.0, "high": 102.0, "low": 99.0, "close": 101.0,
             "volume": 50000, "open_interest": 200000, "turnover": 1.0,
             "settle": 100.0, "pre_settle": 99.0},
            {"symbol": "CU2608", "date": "2026-07-01", "variety": "CU",
             "open": 110.0, "high": 112.0, "low": 109.0, "close": 111.0,
             "volume": 30000, "open_interest": 100000, "turnover": 1.0,
             "settle": 110.0, "pre_settle": 109.0},
            # day 2: roll — CU2608 takes over the lead
            {"symbol": "CU2608", "date": "2026-07-02", "variety": "CU",
             "open": 111.0, "high": 113.0, "low": 110.0, "close": 112.0,
             "volume": 60000, "open_interest": 250000, "turnover": 1.0,
             "settle": 111.0, "pre_settle": 110.0},
            {"symbol": "CU2607", "date": "2026-07-02", "variety": "CU",
             "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0,
             "volume": 10000, "open_interest": 50000, "turnover": 1.0,
             "settle": 100.5, "pre_settle": 100.0},
        ],
    )

    with _patch_fetch_all_markets({"SHFE": rolled}):
        pipeline = FuturesDailyPipeline(db_session)
        out = pipeline.extract()

    day2 = out[out["trade_date"] == date(2026, 7, 2)]
    assert len(day2) == 1
    # The old contract's settle (100.0) must NOT leak into day2's pre_settle,
    # and the upstream per-contract pre_settle must not resurrect it either.
    assert pd.isna(day2.iloc[0]["pre_settle"])


def test_daily_pipeline_extract_respects_history_window(db_session):
    _seed_main_contract(db_session)
    db_session.commit()

    # Build 20 days of data so the 5-day cutoff must trim them.
    rows = []
    for d in range(20):
        iso = (date(2026, 7, 8) - __import__("datetime").timedelta(days=d)).isoformat()
        rows.append(
            {"symbol": "CU2608", "date": iso, "variety": "CU",
             "open": 100.0, "high": 102.0, "low": 99.0, "close": 101.0,
             "volume": 1000, "open_interest": 2000, "turnover": 1.0,
             "settle": 100.5, "pre_settle": 100.0}
        )
    shfe_long = _build_market_frame("SHFE", rows)

    with _patch_fetch_all_markets({"SHFE": shfe_long}):
        # history_days=5 → only keep the last 5 days
        pipeline = FuturesDailyPipeline(
            db_session, history_days=5, target_date=date(2026, 7, 8)
        )
        out = pipeline.extract()

    # 5 days kept (target_date included)
    assert len(out) == 5


def test_daily_pipeline_extract_skips_when_no_contracts(db_session):
    with _patch_fetch_all_markets({"SHFE": SAMPLE_SHFE}):
        pipeline = FuturesDailyPipeline(db_session)
        df = pipeline.extract()
    assert df.empty


def test_daily_pipeline_load_writes_and_invalidates_cache(db_session):
    _seed_main_contract(db_session, code="CU0", exchange="SHFE", product="金属")
    _seed_main_contract(db_session, code="AU0", exchange="SHFE", product="金属")
    db_session.commit()

    with _patch_fetch_all_markets({"SHFE": SAMPLE_SHFE}), patch(
        "app.data.pipelines.futures.cache_invalidate_pattern", return_value=0
    ) as mock_invalidate:
        pipeline = FuturesDailyPipeline(db_session)
        extracted = pipeline.extract()
        n = pipeline.load(extracted)

    # 2 varieties × 2 days = 4 rows
    assert n == 4
    bars = db_session.query(FuturesDailyBar).filter_by(code="CU0").all()
    assert len(bars) == 2
    # Cache invalidated with the futures:* pattern
    mock_invalidate.assert_called_once()
    assert "futures:" in str(mock_invalidate.call_args)


def test_daily_pipeline_load_is_upsert(db_session):
    """Re-running with same (code, date) should not duplicate rows."""
    _seed_main_contract(db_session, code="CU0", exchange="SHFE", product="金属")
    _seed_main_contract(db_session, code="AU0", exchange="SHFE", product="金属")
    db_session.commit()

    with _patch_fetch_all_markets({"SHFE": SAMPLE_SHFE}), patch(
        "app.data.pipelines.futures.cache_invalidate_pattern", return_value=0
    ):
        pipeline = FuturesDailyPipeline(db_session)
        pipeline.load(pipeline.extract())

    with _patch_fetch_all_markets({"SHFE": SAMPLE_SHFE}), patch(
        "app.data.pipelines.futures.cache_invalidate_pattern", return_value=0
    ):
        pipeline = FuturesDailyPipeline(db_session)
        pipeline.load(pipeline.extract())

    # 2 varieties × 2 days = 4 distinct (code, date) rows
    assert db_session.query(FuturesDailyBar).count() == 4


def test_daily_pipeline_extract_handles_empty_response(db_session):
    """If every exchange returns empty, the pipeline returns empty (no crash)."""
    _seed_main_contract(db_session)
    db_session.commit()

    with _patch_fetch_all_markets(None):
        pipeline = FuturesDailyPipeline(db_session)
        out = pipeline.extract()
    assert out.empty


def test_daily_pipeline_extract_handles_akshare_exception(db_session):
    """If the upstream call raises, the pipeline returns empty (no crash)."""
    _seed_main_contract(db_session)
    db_session.commit()

    with patch(
        "app.data.pipelines.futures.fetch_all_markets",
        side_effect=Exception("network error"),
    ):
        pipeline = FuturesDailyPipeline(db_session)
        out = pipeline.extract()
    assert out.empty


def test_daily_pipeline_run_succeeds_with_light_validation(db_session):
    """run() must work end-to-end and write bars without the strict ETF L2 validator."""
    _seed_main_contract(db_session, code="CU0", exchange="SHFE", product="金属")
    _seed_main_contract(db_session, code="AU0", exchange="SHFE", product="金属")
    db_session.commit()

    with _patch_fetch_all_markets({"SHFE": SAMPLE_SHFE}), patch(
        "app.data.pipelines.futures.cache_invalidate_pattern", return_value=0
    ):
        pipeline = FuturesDailyPipeline(db_session)
        result = pipeline.run()

    assert result.success is True
    assert result.records == 4
    assert db_session.query(FuturesDailyBar).count() == 4


def test_daily_pipeline_run_drops_rows_with_invalid_high_low(db_session):
    """Rows where high < low should be dropped rather than aborting the batch."""
    _seed_main_contract(db_session, code="CU0", exchange="SHFE", product="金属")
    _seed_main_contract(db_session, code="AU0", exchange="SHFE", product="金属")
    db_session.commit()

    bad_rows = list(SAMPLE_SHFE.to_dict("records"))
    # Inject a bad row (high < low) for the latest AU day. Give it the
    # highest OI on that day so it wins the per-(date, variety) pick;
    # the high<low filter should then drop it instead of writing it.
    bad_rows.append(
        {"symbol": "AU2608", "date": "2026-07-02", "variety": "AU",
         "open": 100.0, "high": 99.0, "low": 103.0, "close": 102.0,
         "volume": 0, "open_interest": 999999, "turnover": 0.0,
         "settle": 100.0, "pre_settle": 100.0}
    )
    shfe_bad = _build_market_frame("SHFE", bad_rows)

    with _patch_fetch_all_markets({"SHFE": shfe_bad}), patch(
        "app.data.pipelines.futures.cache_invalidate_pattern", return_value=0
    ):
        pipeline = FuturesDailyPipeline(db_session)
        result = pipeline.run()

    assert result.success is True
    # 4 valid picks before filtering (CU0×2 days, AU0×2 days).
    # The injected bad AU row wins the OI pick on day2 but is dropped
    # by the high<low filter, so 3 valid rows are written and a warning
    # is added to the result.
    assert result.records == 3
    assert any("invalid high/low" in w for w in result.warnings)


# ---------------------------------------------------------------------------
# Scheduler-level wiring: the 16:30 cron entry must reach the DCE branch.
# ---------------------------------------------------------------------------


class TestSchedulerFuturesDaily:
    """The 16:30 Asia/Shanghai cron entry is ``app.core.scheduler.run_futures_daily``.

    It must (a) invoke ``FuturesDailyPipeline.run_with_retry`` and (b) trigger
    ``fetch_all_markets`` which itself must call ``_fetch_dce_via_main_sina``
    — the only DCE source that works from the ECS IP.
    """

    def test_fetch_all_markets_invokes_dce_main_sina_branch(self):
        """``fetch_all_markets`` must call ``_fetch_dce_via_main_sina`` for DCE."""
        with patch(
            "app.data.pipelines.futures._fetch_dce_via_main_sina",
            wraps=_fetch_dce_via_main_sina,
        ) as spy_dce, patch(
            "app.data.pipelines.futures._fetch_market_range",
            return_value=pd.DataFrame(),
        ):
            out = fetch_all_markets(date(2026, 7, 8), date(2026, 7, 8))
        # The DCE branch is wired in: it produces an entry in the result
        # (possibly empty if mocked) and the spy observed exactly one call.
        assert "DCE" in out
        spy_dce.assert_called_once()

    def test_run_futures_daily_scheduler_entry_runs_pipeline(self, db_session):
        """``run_futures_daily`` must call ``FuturesDailyPipeline.run_with_retry``.

        We patch ``FuturesDailyPipeline`` so the test stays offline, but the
        assertion that ``run_with_retry`` was awaited proves the scheduler
        wiring is intact.
        """
        captured: dict = {}

        class _StubPipeline:
            def __init__(self, db, target_date=None, **kwargs):
                captured["db"] = db
                captured["target_date"] = target_date

            def run_with_retry(self, max_attempts=2):
                captured["max_attempts"] = max_attempts
                from app.data.pipelines.base import ETLResult
                captured["result"] = ETLResult(success=True, records=7)
                return captured["result"]

        with patch.object(core_scheduler, "FuturesDailyPipeline", _StubPipeline), \
             patch.object(core_scheduler, "SessionLocal", return_value=db_session), \
             patch.object(core_scheduler, "redis_lock") as mock_lock:
            mock_lock.return_value.__enter__.return_value = True
            core_scheduler.run_futures_daily()

        # The cron entry constructed the pipeline through SessionLocal() —
        # i.e. it did NOT call the pipeline with target_date=session (a
        # regression we already saw via signature mismatches).
        assert captured.get("db") is db_session
        assert captured.get("target_date") is None
        assert captured.get("max_attempts") == 2
        assert captured.get("result").records == 7

    def test_run_futures_daily_skips_when_lock_busy(self, db_session):
        """If another worker already holds the ``futures_daily`` lock, exit cleanly."""
        with patch.object(core_scheduler, "redis_lock") as mock_lock, \
             patch.object(core_scheduler, "FuturesDailyPipeline") as mock_pipe:
            mock_lock.return_value.__enter__.return_value = False
            core_scheduler.run_futures_daily()
        # Pipeline must NOT have been constructed when the lock failed.
        mock_pipe.assert_not_called()