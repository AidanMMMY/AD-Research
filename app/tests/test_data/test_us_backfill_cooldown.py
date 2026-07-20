"""Tests for the US backfill failure cooldown and share-class symbol mapping.

Regression coverage for the production incident where unfetchable codes
(BF.B.US / BRK.B.US) blocked the rotation: ``_select_batch`` always
prioritized missing-data codes, so the two permanently-failing tickers
were re-fetched every run and the Redis rotation offset never advanced.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd
import pytest

from app.data.pipelines import us_backfill
from app.data.pipelines.us_backfill import (
    _COOLDOWN_KEY,
    _FAIL_COUNT_KEY,
    _MAX_CONSECUTIVE_FAILURES,
    _OFFSET_KEY,
    USHistoricalBackfillPipeline,
)
from app.data.providers.tiingo_provider import TiingoProvider
from app.data.providers.yfinance_provider import YFinanceProvider


class FakeRedis:
    """Minimal in-memory Redis stand-in for the backfill cooldown keys."""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    def get(self, key: str) -> Any | None:
        return self.store.get(key)

    def set(self, key: str, value: Any, ex: int | None = None) -> bool:
        self.store[key] = str(value)
        return True

    def delete(self, *keys: str) -> int:
        n = 0
        for k in keys:
            if k in self.store:
                del self.store[k]
                n += 1
        return n

    def exists(self, key: str) -> int:
        return 1 if key in self.store else 0

    def incr(self, key: str) -> int:
        v = int(self.store.get(key, "0")) + 1
        self.store[key] = str(v)
        return v


# Codes with price data sort before the failing ones so the rotation batch
# never contains them once cooldown kicks in.
CODES_WITH_DATA = [f"AAA{i:02d}.US" for i in range(18)]
FAILING_CODES = ["BF.B.US", "BRK.B.US"]
ALL_CODES = sorted(CODES_WITH_DATA + FAILING_CODES)


@pytest.fixture
def pipeline(db_session, monkeypatch) -> USHistoricalBackfillPipeline:
    """Pipeline wired to an in-memory Redis and stubbed code listings."""
    fake_redis = FakeRedis()
    monkeypatch.setattr(us_backfill, "get_redis_client", lambda: fake_redis)
    pipe = USHistoricalBackfillPipeline(db_session)
    monkeypatch.setattr(pipe, "_get_active_us_codes", lambda: ALL_CODES)
    monkeypatch.setattr(pipe, "_get_codes_with_price_data", lambda: set(CODES_WITH_DATA))
    return pipe


def _stub_empty_providers(pipe: USHistoricalBackfillPipeline, monkeypatch) -> list[list[str]]:
    """Make every provider return nothing; record requested batches."""
    requested: list[list[str]] = []

    def fake_fetch(codes, start_date, end_date):
        requested.append(list(codes))
        return pd.DataFrame()

    monkeypatch.setattr(pipe.provider, "fetch_daily_bars", fake_fetch)
    monkeypatch.setattr(pipe, "_try_yfinance_fallback", lambda *a, **k: pd.DataFrame())
    return requested


def _bars_df(codes: list[str]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "etf_code": codes,
            "trade_date": [date.today()] * len(codes),
            "close": [1.0] * len(codes),
        }
    )


class TestShareClassSymbolMapping:
    """Request-side mapping: BRK.B.US -> BRK-B (DB code stays unchanged)."""

    def test_tiingo_maps_share_class_dots_to_dashes(self):
        provider = TiingoProvider()
        assert provider._to_tiingo_symbol("BRK.B.US") == "BRK-B"
        assert provider._to_tiingo_symbol("BF.B.US") == "BF-B"
        assert provider._to_tiingo_symbol("SPY.US") == "SPY"

    def test_yfinance_maps_share_class_dots_to_dashes(self):
        provider = YFinanceProvider()
        assert provider._to_ticker("BRK.B.US") == "BRK-B"
        assert provider._to_ticker("BF.B.US") == "BF-B"
        # Non-share-class mappings stay untouched.
        assert provider._to_ticker("AAPL.US") == "AAPL"
        assert provider._to_ticker("1321.JP") == "1321.T"


class TestFailureCooldown:
    def test_rotation_advances_after_repeated_failures(self, pipeline, monkeypatch):
        """Missing codes failing 3 consecutive runs enter cooldown and the
        batch selection falls through to the normal rotation, persisting
        the offset so the rest of the universe finally gets processed."""
        redis = pipeline.redis
        requested = _stub_empty_providers(pipeline, monkeypatch)

        for _ in range(_MAX_CONSECUTIVE_FAILURES):
            pipeline.extract()
            # While under the failure threshold the failing codes still get
            # prioritized and the rotation offset is never persisted.
            assert redis.get(_OFFSET_KEY) is None
        assert requested[-1] == FAILING_CODES

        # Both codes are now cooled down.
        for code in FAILING_CODES:
            assert redis.exists(_COOLDOWN_KEY.format(code=code))
            assert redis.get(_FAIL_COUNT_KEY.format(code=code)) is None

        # Next run rotates through the full list and advances the offset.
        pipeline.extract()
        assert requested[-1] == ALL_CODES[: us_backfill._BATCH_SIZE]
        assert int(redis.get(_OFFSET_KEY)) == us_backfill._BATCH_SIZE % len(ALL_CODES)

    def test_success_resets_failure_counter(self, pipeline, monkeypatch):
        """A code that returns data clears its counter, so only truly
        persistent failures accumulate toward the cooldown."""
        redis = pipeline.redis
        _stub_empty_providers(pipeline, monkeypatch)

        pipeline.extract()
        pipeline.extract()
        assert int(redis.get(_FAIL_COUNT_KEY.format(code="BF.B.US"))) == 2

        # Both failing codes suddenly return data: counters reset.
        monkeypatch.setattr(
            pipeline.provider,
            "fetch_daily_bars",
            lambda codes, s, e: _bars_df(list(codes)),
        )
        pipeline.extract()
        for code in FAILING_CODES:
            assert redis.get(_FAIL_COUNT_KEY.format(code=code)) is None
            assert not redis.exists(_COOLDOWN_KEY.format(code=code))
