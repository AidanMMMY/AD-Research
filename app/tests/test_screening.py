"""Tests for ETF screening service and API.

Covers ScreeningService initialization, presets, category queries,
and the main screen() method with various filter combinations.
"""

from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.etf import ETFIndicator, ETFInfo
from app.models.scoring import ETFScore, ScoreTemplate
from app.services.screening_service import ScreeningService


def _clear_screening_cache():
    """Wipe screening-related Redis keys to prevent stale cache pollution.

    The screening cache key includes ``template_id`` but only the
    caller-supplied value (not the auto-resolved default), so tests that
    rely on auto-resolved templates can otherwise see stale entries
    cached by tests that didn't seed a default template.

    Note: screening_service.screen() calls cache_get/cache_set with the
    raw key (no etf: prefix), so we must scan ``screen:*`` rather than
    ``etf:screen:*`` to actually hit its entries.
    """
    try:
        from app.core.redis_client import get_redis_client

        client = get_redis_client()
        for pattern in ("screen:*", "etf:categories*"):
            for key in client.scan_iter(match=pattern):
                client.delete(key)
    except Exception:
        # Redis unavailable in this test environment — silently skip.
        pass


@pytest.fixture(autouse=True)
def _auto_clear_screening_cache():
    """Auto-clear the screening cache before AND after each test."""
    _clear_screening_cache()
    yield
    _clear_screening_cache()


@pytest.fixture
def db_session():
    """Create an in-memory SQLite database session for testing."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    session_maker = sessionmaker(bind=engine)
    session = session_maker()
    yield session
    session.close()


@pytest.fixture
def sample_etfs_and_indicators(db_session):
    """Create sample ETFs and their latest indicators for screening tests."""
    # Create ETFs
    etfs = [
        ETFInfo(code="510300", name="沪深300ETF", market="SH", category="股票型", status="active"),
        ETFInfo(code="510500", name="中证500ETF", market="SH", category="股票型", status="active"),
        ETFInfo(code="159915", name="创业板ETF", market="SZ", category="股票型", status="active"),
        ETFInfo(code="518880", name="黄金ETF", market="SH", category="商品型", status="active"),
        ETFInfo(code="511010", name="国债ETF", market="SH", category="债券型", status="active"),
    ]
    for etf in etfs:
        db_session.add(etf)
    db_session.commit()

    # Create indicators (latest date).
    # Volatility / returns / max_drawdown are stored as DECIMALS (0.15 ≈ 15%)
    # since the 2026-07-01 risk-unit unification.
    latest_date = date(2024, 6, 1)
    indicators = [
        ETFIndicator(
            etf_code="510300",
            trade_date=latest_date,
            sharpe_1y=1.5,
            volatility_20d=0.15,
            rsi14=55.0,
            return_1m=0.03,
            return_3m=0.08,
            return_1y=0.25,
            max_drawdown_1y=-0.10,
        ),
        ETFIndicator(
            etf_code="510500",
            trade_date=latest_date,
            sharpe_1y=0.8,
            volatility_20d=0.22,
            rsi14=65.0,
            return_1m=0.015,
            return_3m=0.05,
            return_1y=0.15,
            max_drawdown_1y=-0.18,
        ),
        ETFIndicator(
            etf_code="159915",
            trade_date=latest_date,
            sharpe_1y=1.2,
            volatility_20d=0.25,
            rsi14=72.0,
            return_1m=0.04,
            return_3m=0.12,
            return_1y=0.30,
            max_drawdown_1y=-0.20,
        ),
        ETFIndicator(
            etf_code="518880",
            trade_date=latest_date,
            sharpe_1y=0.5,
            volatility_20d=0.12,
            rsi14=45.0,
            return_1m=0.005,
            return_3m=0.02,
            return_1y=0.08,
            max_drawdown_1y=-0.05,
        ),
        ETFIndicator(
            etf_code="511010",
            trade_date=latest_date,
            sharpe_1y=0.3,
            volatility_20d=0.05,
            rsi14=40.0,
            return_1m=0.002,
            return_3m=0.01,
            return_1y=0.04,
            max_drawdown_1y=-0.02,
        ),
    ]
    for ind in indicators:
        db_session.add(ind)
    db_session.commit()

    return etfs, indicators


# ---------------------------------------------------------------------------
# Service initialization tests
# ---------------------------------------------------------------------------


def test_screening_service_initialization(db_session):
    """ScreeningService should initialize with DB session and presets."""
    service = ScreeningService(db_session)

    assert service.db is db_session
    assert hasattr(service, "PRESETS")
    assert len(service.PRESETS) == 4
    assert "high_sharpe_low_vol" in service.PRESETS
    assert "trend_strong" in service.PRESETS
    assert "value_pit" in service.PRESETS
    assert "liquidity_sufficient" in service.PRESETS


def test_screening_service_sort_field_map(db_session):
    """SORT_FIELD_MAP should contain expected sortable fields."""
    service = ScreeningService(db_session)

    expected_fields = {
        "composite_score",
        "sharpe_1y",
        "volatility_20d",
        "return_1m",
        "return_3m",
        "return_1y",
        "rsi14",
        "rank_overall",
        "rank_category",
        "score_return",
        "score_risk",
        "score_sharpe",
        "score_liquidity",
        "score_trend",
    }
    assert set(service.SORT_FIELD_MAP.keys()) == expected_fields


# ---------------------------------------------------------------------------
# Preset tests
# ---------------------------------------------------------------------------


def test_get_presets(db_session):
    """get_presets should return all 4 presets with correct structure."""
    service = ScreeningService(db_session)
    presets = service.get_presets()

    assert len(presets) == 4

    # Check structure of each preset
    for preset in presets:
        assert "key" in preset
        assert "name" in preset
        assert "description" in preset
        assert "filters" in preset
        assert "sort_by" in preset
        assert "sort_order" in preset

    # Verify specific preset
    high_sharpe = next(p for p in presets if p["key"] == "high_sharpe_low_vol")
    assert high_sharpe["name"] == "高夏普低波动"
    assert high_sharpe["filters"]["sharpe_min"] == 1.0
    assert high_sharpe["filters"]["volatility_max"] == 20.0


def test_preset_filters_structure(db_session):
    """Each preset should have valid filter values."""
    service = ScreeningService(db_session)

    # High sharpe low vol
    preset = service.PRESETS["high_sharpe_low_vol"]
    assert preset["filters"]["sharpe_min"] == 1.0
    assert preset["filters"]["volatility_max"] == 20.0
    assert preset["sort_by"] == "sharpe_1y"
    assert preset["sort_order"] == "desc"

    # Trend strong
    preset = service.PRESETS["trend_strong"]
    assert preset["filters"]["rsi_min"] == 50.0
    assert preset["filters"]["rsi_max"] == 80.0
    assert preset["filters"]["return_1m_min"] == 2.0
    assert preset["sort_by"] == "return_1m"
    assert preset["sort_order"] == "desc"

    # Value pit
    preset = service.PRESETS["value_pit"]
    assert preset["filters"]["sharpe_min"] == 0.5
    assert preset["sort_by"] == "return_1y"
    assert preset["sort_order"] == "asc"

    # Liquidity sufficient
    preset = service.PRESETS["liquidity_sufficient"]
    assert preset["filters"]["volatility_min"] == 10.0
    assert preset["filters"]["return_1m_min"] == 0.0
    assert preset["sort_by"] == "volatility_20d"
    assert preset["sort_order"] == "desc"


# ---------------------------------------------------------------------------
# Screen method tests
# ---------------------------------------------------------------------------


def test_screen_no_filters(db_session, sample_etfs_and_indicators):
    """screen() with no filters should return all ETFs with latest indicators."""
    service = ScreeningService(db_session)
    result = service.screen()

    assert result["count"] == 5
    assert len(result["items"]) == 5
    assert result["offset"] == 0
    assert result["limit"] == 50


def test_screen_by_market(db_session, sample_etfs_and_indicators):
    """screen() should filter by market."""
    service = ScreeningService(db_session)
    result = service.screen(market="SH")

    assert result["count"] == 4  # 510300, 510500, 518880, 511010
    codes = {item["code"] for item in result["items"]}
    assert "510300" in codes
    assert "510500" in codes
    assert "518880" in codes
    assert "511010" in codes
    assert "159915" not in codes  # SZ


def test_screen_by_category(db_session, sample_etfs_and_indicators):
    """screen() should filter by category."""
    service = ScreeningService(db_session)
    result = service.screen(category="股票型")

    assert result["count"] == 3  # 510300, 510500, 159915
    codes = {item["code"] for item in result["items"]}
    assert "510300" in codes
    assert "510500" in codes
    assert "159915" in codes


def test_screen_by_sharpe_range(db_session, sample_etfs_and_indicators):
    """screen() should filter by Sharpe ratio range."""
    service = ScreeningService(db_session)
    result = service.screen(sharpe_min=1.0)

    assert result["count"] == 2  # 510300 (1.5), 159915 (1.2)
    codes = {item["code"] for item in result["items"]}
    assert "510300" in codes
    assert "159915" in codes


def test_screen_by_volatility_range(db_session, sample_etfs_and_indicators):
    """screen() should filter by volatility range.

    The service API accepts percentage thresholds (e.g. 16.0 = 16%),
    and the service internally divides by 100 to compare against the
    decimal values stored in the DB.
    """
    service = ScreeningService(db_session)
    # 16% threshold catches 15%, 12%, 5% (all the SH + 商品型/股票型).
    result = service.screen(volatility_max=16.0)

    assert result["count"] == 3  # 510300 (15%), 518880 (12%), 511010 (5%)
    codes = {item["code"] for item in result["items"]}
    assert "510300" in codes
    assert "518880" in codes
    assert "511010" in codes


def test_screen_by_rsi_range(db_session, sample_etfs_and_indicators):
    """screen() should filter by RSI range."""
    service = ScreeningService(db_session)
    result = service.screen(rsi_min=50.0, rsi_max=70.0)

    assert result["count"] == 2  # 510300 (55), 510500 (65)
    codes = {item["code"] for item in result["items"]}
    assert "510300" in codes
    assert "510500" in codes


def test_screen_by_return_ranges(db_session, sample_etfs_and_indicators):
    """screen() should filter by return ranges.

    The service API accepts percentage thresholds; the service converts
    to decimal internally before comparing against the DB.
    """
    service = ScreeningService(db_session)

    # 1-month return — 2% threshold catches 3% and 4%.
    result = service.screen(return_1m_min=2.0)
    assert result["count"] == 2  # 510300 (3%), 159915 (4%)

    # 1-year return — 20% threshold catches 25% and 30%.
    result = service.screen(return_1y_min=20.0)
    assert result["count"] == 2  # 510300 (25%), 159915 (30%)


def test_screen_combined_filters(db_session, sample_etfs_and_indicators):
    """screen() should apply multiple filters together."""
    service = ScreeningService(db_session)
    result = service.screen(
        market="SH",
        category="股票型",
        sharpe_min=1.0,
        volatility_max=20.0,  # 20% threshold (service divides by 100)
    )

    # SH + 股票型 + sharpe >= 1.0 + vol <= 20%
    # 510300: SH, 股票型, sharpe=1.5, vol=15% -> matches
    # 510500: SH, 股票型, sharpe=0.8 -> fails sharpe
    # 159915: SZ -> fails market
    assert result["count"] == 1
    assert result["items"][0]["code"] == "510300"


def test_screen_sorting(db_session, sample_etfs_and_indicators):
    """screen() should support dynamic sorting."""
    service = ScreeningService(db_session)

    # Sort by sharpe desc
    result = service.screen(sort_by="sharpe_1y", sort_order="desc")
    codes = [item["code"] for item in result["items"]]
    assert codes[0] == "510300"  # sharpe 1.5

    # Sort by volatility asc
    result = service.screen(sort_by="volatility_20d", sort_order="asc")
    codes = [item["code"] for item in result["items"]]
    assert codes[0] == "511010"  # vol 5.0

    # Sort by return_1y desc
    result = service.screen(sort_by="return_1y", sort_order="desc")
    codes = [item["code"] for item in result["items"]]
    assert codes[0] == "159915"  # return 30.0


def test_screen_pagination(db_session, sample_etfs_and_indicators):
    """screen() should support pagination."""
    service = ScreeningService(db_session)

    result = service.screen(offset=0, limit=2)
    assert len(result["items"]) == 2
    assert result["count"] == 5

    result = service.screen(offset=2, limit=2)
    assert len(result["items"]) == 2

    result = service.screen(offset=4, limit=2)
    assert len(result["items"]) == 1


def test_screen_empty_result(db_session, sample_etfs_and_indicators):
    """screen() should return empty items when no matches."""
    service = ScreeningService(db_session)
    result = service.screen(sharpe_min=5.0)

    assert result["count"] == 0
    assert result["items"] == []


def test_screen_by_preset_high_sharpe(db_session, sample_etfs_and_indicators):
    """screen_by_preset should apply preset filters correctly."""
    service = ScreeningService(db_session)
    result = service.screen_by_preset("high_sharpe_low_vol")

    # sharpe >= 1.0 AND vol <= 20
    # 510300: sharpe=1.5, vol=15 -> matches
    # 159915: sharpe=1.2, vol=25 -> fails vol
    # 510500: sharpe=0.8 -> fails
    assert result["count"] == 1
    assert result["items"][0]["code"] == "510300"
    assert result["preset"]["name"] == "高夏普低波动"


def test_screen_by_preset_trend_strong(db_session, sample_etfs_and_indicators):
    """screen_by_preset trend_strong should filter by RSI and return."""
    service = ScreeningService(db_session)
    result = service.screen_by_preset("trend_strong")

    # rsi 50-80 AND return_1m >= 2.0
    # 510300: rsi=55, return_1m=3.0 -> matches
    # 510500: rsi=65, return_1m=1.5 -> fails return
    # 159915: rsi=72, return_1m=4.0 -> matches
    assert result["count"] == 2
    codes = {item["code"] for item in result["items"]}
    assert "510300" in codes
    assert "159915" in codes


def test_screen_by_preset_invalid(db_session):
    """screen_by_preset with invalid key should return empty results."""
    service = ScreeningService(db_session)
    result = service.screen_by_preset("nonexistent")

    assert result["items"] == []
    assert result["count"] == 0
    assert result["preset"] is None


# ---------------------------------------------------------------------------
# Category tests
# ---------------------------------------------------------------------------


def test_get_categories(db_session, sample_etfs_and_indicators):
    """get_categories should return categories with counts."""
    service = ScreeningService(db_session)
    categories = service.get_categories()

    assert len(categories) == 3  # 股票型, 商品型, 债券型

    cat_map = {c["category"]: c["count"] for c in categories}
    assert cat_map["股票型"] == 3
    assert cat_map["商品型"] == 1
    assert cat_map["债券型"] == 1


def test_get_categories_with_market_filter(db_session, sample_etfs_and_indicators):
    """get_categories should filter by market and update counts."""
    service = ScreeningService(db_session)
    categories = service.get_categories(market="SH")

    cat_map = {c["category"]: c["count"] for c in categories}
    assert cat_map["股票型"] == 2
    assert cat_map["商品型"] == 1
    assert cat_map["债券型"] == 1


def test_get_categories_with_empty_market_filter(db_session, sample_etfs_and_indicators):
    """get_categories with a non-matching market should return empty list."""
    service = ScreeningService(db_session)
    categories = service.get_categories(market="US")
    assert categories == []


# ---------------------------------------------------------------------------
# Score filtering tests
# ---------------------------------------------------------------------------


def test_screen_with_score_filter(db_session, sample_etfs_and_indicators):
    """screen() should support score-based filtering when template_id is provided."""
    # Create a template and scores
    template = ScoreTemplate(
        name="Test Template",
        weights={"return": 0.3, "risk": 0.3, "sharpe": 0.4},
    )
    db_session.add(template)
    db_session.commit()

    latest_date = date(2024, 6, 1)
    scores = [
        ETFScore(
            etf_code="510300",
            trade_date=latest_date,
            template_id=template.id,
            composite_score=85.0,
            rank_overall=1,
        ),
        ETFScore(
            etf_code="510500",
            trade_date=latest_date,
            template_id=template.id,
            composite_score=70.0,
            rank_overall=2,
        ),
        ETFScore(
            etf_code="159915",
            trade_date=latest_date,
            template_id=template.id,
            composite_score=75.0,
            rank_overall=3,
        ),
    ]
    for s in scores:
        db_session.add(s)
    db_session.commit()

    service = ScreeningService(db_session)
    result = service.screen(template_id=template.id, score_min=75.0)

    assert result["count"] == 2  # 510300 (85), 159915 (75)
    for item in result["items"]:
        assert item["composite_score"] is not None
        assert item["composite_score"] >= 75.0


def test_screen_with_score_sorting(db_session, sample_etfs_and_indicators):
    """screen() should support sorting by score fields with template_id."""
    # Create a template and scores
    template = ScoreTemplate(
        name="Sort Template",
        weights={"return": 0.3, "risk": 0.3, "sharpe": 0.4},
    )
    db_session.add(template)
    db_session.commit()

    latest_date = date(2024, 6, 1)
    scores = [
        ETFScore(
            etf_code="510300",
            trade_date=latest_date,
            template_id=template.id,
            composite_score=85.0,
            rank_overall=1,
        ),
        ETFScore(
            etf_code="510500",
            trade_date=latest_date,
            template_id=template.id,
            composite_score=70.0,
            rank_overall=2,
        ),
        ETFScore(
            etf_code="159915",
            trade_date=latest_date,
            template_id=template.id,
            composite_score=75.0,
            rank_overall=3,
        ),
    ]
    for s in scores:
        db_session.add(s)
    db_session.commit()

    service = ScreeningService(db_session)
    result = service.screen(
        template_id=template.id,
        sort_by="composite_score",
        sort_order="desc",
    )

    scores_list = [item["composite_score"] for item in result["items"] if item["composite_score"] is not None]
    assert scores_list == sorted(scores_list, reverse=True)


# ---------------------------------------------------------------------------
# Result structure tests
# ---------------------------------------------------------------------------


def test_screen_result_structure(db_session, sample_etfs_and_indicators):
    """screen() result items should have expected structure."""
    service = ScreeningService(db_session)
    result = service.screen(limit=1)

    assert "items" in result
    assert "count" in result
    assert "offset" in result
    assert "limit" in result

    item = result["items"][0]
    expected_keys = {
        "code", "name", "market", "category", "trade_date",
        "sharpe_1y", "volatility_20d", "rsi14",
        "return_1m", "return_3m", "return_1y", "max_drawdown_1y",
    }
    assert expected_keys.issubset(set(item.keys()))


# ---------------------------------------------------------------------------
# B13: Auto-default-template score population tests
# ---------------------------------------------------------------------------


def _seed_default_template_with_scores(db_session, scores_by_code: dict[str, float]):
    """Create a default ScoreTemplate plus ETFScore rows for the test ETFs."""
    template = ScoreTemplate(
        name="Default B13 Template",
        weights={"return": 0.3, "risk": 0.3, "sharpe": 0.4},
        is_default=True,
    )
    db_session.add(template)
    db_session.commit()

    latest_date = date(2024, 6, 1)
    for code, score in scores_by_code.items():
        db_session.add(
            ETFScore(
                etf_code=code,
                trade_date=latest_date,
                template_id=template.id,
                composite_score=score,
                rank_overall=1,
            )
        )
    db_session.commit()
    return template


def test_screen_populates_composite_score_without_template_id(
    db_session, sample_etfs_and_indicators
):
    """B13 fix: screen(market=None, sort_by="composite_score") with no
    template_id supplied should auto-resolve the default template and
    populate composite_score on every returned item."""
    _seed_default_template_with_scores(
        db_session,
        {
            "510300": 85.0,
            "510500": 70.0,
            "159915": 75.0,
            "518880": 60.0,
            "511010": 50.0,
        },
    )

    service = ScreeningService(db_session)
    result = service.screen(market=None, sort_by="composite_score")

    assert result["count"] == 5
    assert len(result["items"]) == 5
    for item in result["items"]:
        assert item["composite_score"] is not None, (
            f"composite_score missing for {item['code']} — B13 regression"
        )


def test_screen_populates_composite_score_with_indicator_sort_by(
    db_session, sample_etfs_and_indicators
):
    """B13 fix: screen() should populate composite_score even when sorting
    by an indicator field (e.g. sharpe_1y, rsi14, return_1m). The old code
    only triggered template resolution for score-based sort fields, so
    Full Market Screener with default sort dropped all score columns."""
    _seed_default_template_with_scores(
        db_session,
        {
            "510300": 85.0,
            "510500": 70.0,
            "159915": 75.0,
            "518880": 60.0,
            "511010": 50.0,
        },
    )

    service = ScreeningService(db_session)

    # sharpe_1y was the originally-reported failing case
    result = service.screen(sort_by="sharpe_1y")
    assert result["count"] == 5
    for item in result["items"]:
        assert item["composite_score"] is not None

    # Other indicator sort fields should also auto-populate scores
    for sort_field in ("rsi14", "return_1m", "return_1y", "volatility_20d"):
        result = service.screen(sort_by=sort_field)
        assert result["count"] == 5
        for item in result["items"]:
            assert item["composite_score"] is not None, (
                f"{sort_field}: composite_score missing for {item['code']}"
            )


def test_screen_by_preset_trend_strong_returns_composite_score(
    db_session, sample_etfs_and_indicators
):
    """B13 fix: screen_by_preset("trend_strong") should populate
    composite_score on returned rows via auto-default template resolution,
    even though the preset itself only sets indicator filters."""
    _seed_default_template_with_scores(
        db_session,
        {
            "510300": 85.0,
            "159915": 75.0,
        },
    )

    service = ScreeningService(db_session)
    result = service.screen_by_preset("trend_strong")

    # rsi 50-80 AND return_1m >= 2.0:
    # 510300: rsi=55, return_1m=3.0 -> matches
    # 159915: rsi=72, return_1m=4.0 -> matches
    assert result["count"] == 2
    assert result["preset"]["key"] == "trend_strong"

    for item in result["items"]:
        assert item["composite_score"] is not None, (
            f"composite_score missing for preset item {item['code']} — B13 regression"
        )


def test_screen_uses_db_default_template_not_hardcoded_id(
    db_session, sample_etfs_and_indicators
):
    """B13 fix: the default template should be resolved via
    ScoringService.get_default_template() (which filters on is_default=True),
    not hardcoded to id=2. Marking a different template as default should
    make screen() pull scores for that template."""
    # Two templates; only the second one is the default
    non_default = ScoreTemplate(
        name="Old Template",
        weights={"return": 0.5, "risk": 0.5},
        is_default=False,
    )
    db_session.add(non_default)
    db_session.commit()

    default_tmpl = ScoreTemplate(
        name="Brand-New Default",
        weights={"return": 0.3, "risk": 0.3, "sharpe": 0.4},
        is_default=True,
    )
    db_session.add(default_tmpl)
    db_session.commit()

    latest_date = date(2024, 6, 1)
    # Score 510300 differently under each template
    db_session.add(ETFScore(
        etf_code="510300", trade_date=latest_date,
        template_id=non_default.id, composite_score=10.0,
    ))
    db_session.add(ETFScore(
        etf_code="510300", trade_date=latest_date,
        template_id=default_tmpl.id, composite_score=99.0,
    ))
    db_session.commit()

    service = ScreeningService(db_session)
    result = service.screen(market=None, sort_by="composite_score")

    item_510300 = next(i for i in result["items"] if i["code"] == "510300")
    # Must pull 99.0 (the default template's score), not 10.0
    assert item_510300["composite_score"] == 99.0


def test_screen_cache_key_isolates_presets(
    db_session, sample_etfs_and_indicators
):
    """Different presets must produce different cache keys so that preset A's
    cached response never serves preset B's view (B13 follow-up)."""
    _seed_default_template_with_scores(
        db_session,
        {"510300": 85.0, "159915": 75.0},
    )

    service = ScreeningService(db_session)

    r_trend = service.screen_by_preset("trend_strong")
    r_high_sharpe = service.screen_by_preset("high_sharpe_low_vol")

    # Each preset returns the items it should — not a leaked view
    assert r_trend["count"] == 2  # 510300 + 159915
    assert r_high_sharpe["count"] == 1  # only 510300 (sharpe>=1, vol<=20%)
    assert {i["code"] for i in r_trend["items"]} == {"510300", "159915"}
    assert {i["code"] for i in r_high_sharpe["items"]} == {"510300"}

    # And the preset metadata is still attached
    assert r_trend["preset"]["key"] == "trend_strong"
    assert r_high_sharpe["preset"]["key"] == "high_sharpe_low_vol"
