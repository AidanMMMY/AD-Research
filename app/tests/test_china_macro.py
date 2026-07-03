"""Tests for the China macro indicator pipeline.

Covers three layers:

1. ``AkshareProvider`` macro fetch methods return dicts shaped as the
   scheduler expects, using mocked upstream responses.
2. ``MacroDataService`` upserts observations idempotently via the
   unique constraint on (code, region, period, source).
3. The HTTP API returns paginated list / latest snapshot / codes.

The provider tests mock akshare so they don't hit the network; the
service tests use a SQLite in-memory DB; the API tests use the same
in-memory DB with FastAPI dependency overrides.
"""

from __future__ import annotations

import math
from datetime import date
from unittest.mock import patch

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import deps as api_deps
from app.api.v1 import macro as macro_api
from app.core.database import Base
from app.data.providers.akshare_provider import AkshareProvider
from app.main import app
from app.models.macro import MacroIndicator
from app.services.macro_service import MacroDataService


# ---------------------------------------------------------------------------
# Provider tests — mock akshare
# ---------------------------------------------------------------------------


def _make_gdp_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "商品": ["中国GDP年率报告"],
            "日期": ["2025-01-17"],
            "今值": [5.0],
            "预测值": [4.9],
            "前值": [5.2],
        }
    )


def _make_cpi_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "商品": ["中国CPI月率报告"],
            "日期": ["2025-05-09"],
            "今值": [0.1],
            "预测值": [0.2],
            "前值": [0.0],
        }
    )


def _make_ppi_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "月份": ["2025年05月份"],
            "当月": [103.9],
            "当月同比增长": [-1.5],
            "累计": [101.0],
        }
    )


def _make_m2_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "商品": ["中国M2货币供应年率报告"],
            "日期": ["2025-05-13"],
            "今值": [8.0],
            "预测值": [8.5],
            "前值": [7.2],
        }
    )


def _make_pmi_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "商品": ["中国官方制造业PMI"],
            "日期": ["2025-05-31"],
            "今值": [49.5],
            "预测值": [50.0],
            "前值": [50.1],
        }
    )


def _make_shibor_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "日期": ["2025-05-08"],
            "O/N-定价": [1.42],
            "O/N-涨跌幅": [None],
            "1W-定价": [1.55],
            "1W-涨跌幅": [None],
            "2W-定价": [1.65],
            "2W-涨跌幅": [None],
            "1M-定价": [1.80],
            "1M-涨跌幅": [None],
            "3M-定价": [1.90],
            "3M-涨跌幅": [None],
            "6M-定价": [2.00],
            "6M-涨跌幅": [None],
            "9M-定价": [2.05],
            "9M-涨跌幅": [None],
            "1Y-定价": [2.10],
            "1Y-涨跌幅": [None],
        }
    )


def _make_rrr_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "公布时间": ["2025年05月07日"],
            "生效时间": ["2025年05月15日"],
            "大型金融机构-调整前": [9.5],
            "大型金融机构-调整后": [9.0],
            "大型金融机构-调整幅度": [-0.5],
            "中小金融机构-调整前": [6.5],
            "中小金融机构-调整后": [6.0],
            "中小金融机构-调整幅度": [-0.5],
            "消息公布次日指数涨跌-上证": [0.5],
            "消息公布次日指数涨跌-深证": [0.9],
            "备注": ["降准 0.5 个百分点"],
        }
    )


@pytest.fixture
def provider():
    """AkshareProvider instance."""
    return AkshareProvider()


def test_fetch_china_macro_gdp_returns_dicts(provider):
    with patch("app.data.providers.akshare_provider.ak.macro_china_gdp_yearly", return_value=_make_gdp_df()):
        result = provider.fetch_china_macro_gdp()
    assert len(result) == 1
    row = result[0]
    assert row["code"] == "gdp_yoy"
    assert row["period"] == "2025-01-17"
    assert row["value"] == 5.0
    assert row["unit"] == "%"
    assert row["name_zh"] == "GDP 年率"


def test_fetch_china_macro_cpi_returns_dicts(provider):
    with patch("app.data.providers.akshare_provider.ak.macro_china_cpi_monthly", return_value=_make_cpi_df()):
        result = provider.fetch_china_macro_cpi()
    assert result[0]["code"] == "cpi_yoy"
    assert result[0]["period"] == "2025-05-09"
    assert result[0]["value"] == 0.1


def test_fetch_china_macro_ppi_parses_chinese_period(provider):
    with patch("app.data.providers.akshare_provider.ak.macro_china_ppi", return_value=_make_ppi_df()):
        result = provider.fetch_china_macro_ppi()
    assert result[0]["code"] == "ppi_yoy"
    assert result[0]["period"] == "2025-05-01"
    assert result[0]["value"] == -1.5


def test_fetch_china_macro_m2(provider):
    with patch("app.data.providers.akshare_provider.ak.macro_china_m2_yearly", return_value=_make_m2_df()):
        result = provider.fetch_china_macro_m2()
    assert result[0]["code"] == "m2_yoy"
    assert result[0]["value"] == 8.0


def test_fetch_china_macro_pmi(provider):
    with patch("app.data.providers.akshare_provider.ak.macro_china_pmi_yearly", return_value=_make_pmi_df()):
        result = provider.fetch_china_macro_pmi()
    assert result[0]["code"] == "pmi_manufacturing"
    assert result[0]["value"] == 49.5


def test_fetch_china_macro_shibor_emits_eight_tenors(provider):
    with patch("app.data.providers.akshare_provider.ak.macro_china_shibor_all", return_value=_make_shibor_df()):
        result = provider.fetch_china_macro_shibor()
    codes = {r["code"] for r in result}
    assert codes == {
        "shibor_on", "shibor_1w", "shibor_2w", "shibor_1m",
        "shibor_3m", "shibor_6m", "shibor_9m", "shibor_1y",
    }
    # O/N value present
    on_row = next(r for r in result if r["code"] == "shibor_on")
    assert on_row["value"] == 1.42


def test_fetch_china_macro_rrr_splits_large_and_small(provider):
    with patch(
        "app.data.providers.akshare_provider.ak.macro_china_reserve_requirement_ratio",
        return_value=_make_rrr_df(),
    ):
        result = provider.fetch_china_macro_rrr()
    codes = {r["code"] for r in result}
    assert codes == {"rrr_large", "rrr_small"}
    large = next(r for r in result if r["code"] == "rrr_large")
    small = next(r for r in result if r["code"] == "rrr_small")
    assert large["value"] == 9.0
    assert small["value"] == 6.0
    assert large["period"] == "2025-05-15"


def test_provider_returns_empty_on_exception(provider):
    with patch(
        "app.data.providers.akshare_provider.ak.macro_china_cpi_monthly",
        side_effect=RuntimeError("rate limit"),
    ):
        result = provider.fetch_china_macro_cpi()
    assert result == []


def test_provider_returns_empty_on_empty_df(provider):
    empty_df = pd.DataFrame(columns=["商品", "日期", "今值", "预测值", "前值"])
    with patch(
        "app.data.providers.akshare_provider.ak.macro_china_cpi_monthly",
        return_value=empty_df,
    ):
        result = provider.fetch_china_macro_cpi()
    assert result == []


# ---------------------------------------------------------------------------
# Service tests — in-memory SQLite
# ---------------------------------------------------------------------------


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session_ = sessionmaker(bind=engine)
    session = Session_()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_upsert_inserts_new_observations(db_session):
    svc = MacroDataService(db_session)
    written = svc.upsert_observations(
        region="cn",
        source="akshare",
        observations=[
            {
                "code": "gdp_yoy",
                "period": "2025-01-17",
                "value": 5.0,
                "name_zh": "GDP 年率",
                "unit": "%",
            },
            {
                "code": "cpi_yoy",
                "period": "2025-05-09",
                "value": 0.1,
                "name_zh": "CPI 月率",
                "unit": "%",
            },
        ],
    )
    assert written == 2
    rows = db_session.query(MacroIndicator).all()
    assert len(rows) == 2
    assert {r.code for r in rows} == {"gdp_yoy", "cpi_yoy"}


def test_upsert_is_idempotent(db_session):
    svc = MacroDataService(db_session)
    obs = {
        "code": "gdp_yoy",
        "period": "2025-01-17",
        "value": 5.0,
        "name_zh": "GDP 年率",
        "unit": "%",
    }
    svc.upsert_observations(region="cn", source="akshare", observations=[obs])
    svc.upsert_observations(region="cn", source="akshare", observations=[obs])
    svc.upsert_observations(
        region="cn",
        source="akshare",
        observations=[{**obs, "value": 5.4, "name_zh": "GDP 年率 (修订)"}],
    )
    rows = db_session.query(MacroIndicator).all()
    assert len(rows) == 1
    assert rows[0].value == 5.4
    assert rows[0].name_zh == "GDP 年率 (修订)"


def test_list_indicators_filters_and_paginates(db_session):
    svc = MacroDataService(db_session)
    svc.upsert_observations(
        region="cn",
        source="akshare",
        observations=[
            {"code": "gdp_yoy", "period": "2025-01-17", "value": 5.0, "name_zh": "GDP", "unit": "%"},
            {"code": "gdp_yoy", "period": "2024-01-17", "value": 5.2, "name_zh": "GDP", "unit": "%"},
            {"code": "cpi_yoy", "period": "2025-05-09", "value": 0.1, "name_zh": "CPI", "unit": "%"},
        ],
    )
    result = svc.list_indicators(code="gdp_yoy", page=1, page_size=10)
    assert result["total"] == 2
    assert {row["code"] for row in result["items"]} == {"gdp_yoy"}
    # Default ordering is period desc.
    assert result["items"][0]["period"] >= result["items"][1]["period"]


def test_latest_snapshot_returns_one_row_per_code(db_session):
    svc = MacroDataService(db_session)
    svc.upsert_observations(
        region="cn",
        source="akshare",
        observations=[
            {"code": "gdp_yoy", "period": "2024-01-17", "value": 5.2, "name_zh": "GDP", "unit": "%"},
            {"code": "gdp_yoy", "period": "2025-01-17", "value": 5.0, "name_zh": "GDP", "unit": "%"},
            {"code": "cpi_yoy", "period": "2025-05-09", "value": 0.1, "name_zh": "CPI", "unit": "%"},
        ],
    )
    snapshot = svc.latest_snapshot(region="cn")
    by_code = {item["code"]: item for item in snapshot["items"]}
    assert set(by_code.keys()) == {"gdp_yoy", "cpi_yoy"}
    assert by_code["gdp_yoy"]["value"] == 5.0
    assert by_code["gdp_yoy"]["period"] == "2025-01-17"
    assert by_code["cpi_yoy"]["value"] == 0.1


def test_list_codes_returns_distinct_codes_with_latest(db_session):
    svc = MacroDataService(db_session)
    svc.upsert_observations(
        region="cn",
        source="akshare",
        observations=[
            {"code": "gdp_yoy", "period": "2024-01-17", "value": 5.2, "name_zh": "GDP", "unit": "%"},
            {"code": "gdp_yoy", "period": "2025-01-17", "value": 5.0, "name_zh": "GDP", "unit": "%"},
            {"code": "cpi_yoy", "period": "2025-05-09", "value": 0.1, "name_zh": "CPI", "unit": "%"},
        ],
    )
    codes = svc.list_codes(region="cn")
    by_code = {c["code"]: c for c in codes}
    assert set(by_code.keys()) == {"gdp_yoy", "cpi_yoy"}
    assert by_code["gdp_yoy"]["latest_period"] == date(2025, 1, 17)
    assert by_code["gdp_yoy"]["latest_value"] == 5.0
    assert math.isclose(by_code["cpi_yoy"]["latest_value"], 0.1)


# ---------------------------------------------------------------------------
# API tests — in-memory SQLite + FastAPI dependency overrides
# ---------------------------------------------------------------------------


@pytest.fixture
def client(db_session):
    """TestClient with DB / auth overrides."""

    def _override_user():
        from app.schemas.auth import UserResponse

        return UserResponse(id=1, username="tester", role="user")

    def _get_db_override():
        try:
            yield db_session
        finally:
            pass

    def _macro_service_override():
        return MacroDataService(db_session)

    app.dependency_overrides[api_deps.get_db] = _get_db_override
    app.dependency_overrides[macro_api._macro_service] = _macro_service_override
    app.dependency_overrides[macro_api.get_current_user] = _override_user

    with patch("app.api.v1.macro.SessionLocal", return_value=db_session), TestClient(app) as c:
        try:
            yield c
        finally:
            app.dependency_overrides.clear()


def _seed(db, rows):
    for r in rows:
        db.add(MacroIndicator(**r))
    db.commit()


def _macro_row(
    code: str,
    *,
    region: str = "cn",
    name_zh: str = "测试",
    unit: str = "%",
    period: date | None = None,
    value: float = 1.0,
    source: str = "akshare",
):
    return {
        "code": code,
        "region": region,
        "name_zh": name_zh,
        "unit": unit,
        "period": period or date(2025, 1, 1),
        "value": value,
        "source": source,
    }


def test_api_list_returns_paginated_items(client, db_session):
    _seed(
        db_session,
        [
            _macro_row("gdp_yoy", period=date(2025, 1, 17), value=5.0),
            _macro_row("gdp_yoy", period=date(2024, 1, 17), value=5.2),
            _macro_row("cpi_yoy", period=date(2025, 5, 9), value=0.1),
        ],
    )
    resp = client.get("/api/v1/macro/indicators-list?page=1&page_size=2")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3
    assert body["page"] == 1
    assert body["page_size"] == 2
    assert len(body["items"]) == 2


def test_api_list_filter_by_code(client, db_session):
    _seed(
        db_session,
        [
            _macro_row("gdp_yoy", period=date(2025, 1, 17), value=5.0),
            _macro_row("cpi_yoy", period=date(2025, 5, 9), value=0.1),
        ],
    )
    resp = client.get("/api/v1/macro/indicators-list?code=gdp_yoy")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["code"] == "gdp_yoy"


def test_api_latest_returns_one_row_per_code(client, db_session):
    _seed(
        db_session,
        [
            _macro_row("gdp_yoy", period=date(2024, 1, 17), value=5.2),
            _macro_row("gdp_yoy", period=date(2025, 1, 17), value=5.0),
            _macro_row("cpi_yoy", period=date(2025, 5, 9), value=0.1),
        ],
    )
    resp = client.get("/api/v1/macro/latest?region=cn")
    assert resp.status_code == 200
    body = resp.json()
    assert body["region"] == "cn"
    by_code = {item["code"]: item for item in body["items"]}
    assert set(by_code.keys()) == {"gdp_yoy", "cpi_yoy"}
    assert by_code["gdp_yoy"]["value"] == 5.0


def test_api_codes_returns_distinct_codes(client, db_session):
    _seed(
        db_session,
        [
            _macro_row("gdp_yoy", period=date(2025, 1, 17), value=5.0, name_zh="GDP"),
            _macro_row("cpi_yoy", period=date(2025, 5, 9), value=0.1, name_zh="CPI"),
        ],
    )
    resp = client.get("/api/v1/macro/codes?region=cn")
    assert resp.status_code == 200
    body = resp.json()
    codes = {item["code"] for item in body["items"]}
    assert codes == {"gdp_yoy", "cpi_yoy"}
    gdp = next(item for item in body["items"] if item["code"] == "gdp_yoy")
    assert gdp["latest_value"] == 5.0
    assert gdp["name_zh"] == "GDP"


def test_api_indicators_for_cn_returns_latest_per_code(client, db_session):
    """The legacy /macro/indicators endpoint must also surface China data."""
    _seed(
        db_session,
        [
            _macro_row("gdp_yoy", period=date(2024, 1, 17), value=5.2, name_zh="GDP"),
            _macro_row("gdp_yoy", period=date(2025, 1, 17), value=5.0, name_zh="GDP"),
            _macro_row("cpi_yoy", period=date(2025, 5, 9), value=0.1, name_zh="CPI"),
        ],
    )
    resp = client.get("/api/v1/macro/indicators?region=cn")
    assert resp.status_code == 200
    body = resp.json()
    by_code = {item["code"]: item for item in body}
    assert set(by_code.keys()) == {"gdp_yoy", "cpi_yoy"}
    assert by_code["gdp_yoy"]["value"] == 5.0
    assert by_code["gdp_yoy"]["period"] == "2025-01-17"
    assert by_code["cpi_yoy"]["value"] == 0.1


def test_api_requires_auth(db_session):
    """Without auth override the endpoint must reject the request."""

    def _get_db_override():
        try:
            yield db_session
        finally:
            pass

    def _macro_service_override():
        return MacroDataService(db_session)

    app.dependency_overrides[api_deps.get_db] = _get_db_override
    app.dependency_overrides[macro_api._macro_service] = _macro_service_override
    try:
        with patch("app.api.v1.macro.SessionLocal", return_value=db_session), TestClient(app) as c:
            resp = c.get("/api/v1/macro/indicators-list")
        assert resp.status_code in (401, 403)
    finally:
        app.dependency_overrides.clear()
