"""全球速览指数详情页（Batch A 数据层 + Batch B API）测试.

覆盖四层：

1. ``GlobalIndexBarService.upsert_bars`` 幂等（同批插两次行数不变、值更新）。
2. ``_frame_to_bars`` 的 OHLCV 提取：volume=0/NaN → None、open NaN → None、
   invert_value=True 时全字段取倒数且 high/low 互换。
3. ``get_detail`` 双分支：有 bars 走 OHLC；无 bars 回退 macro_indicator
   折线；未知 code 返回 None。
4. HTTP API：200 / 404 / limit 截断 / 时间窗过滤。

数据库用 SQLite in-memory（与 test_fred_service / test_china_macro
同一套 fixture 惯例）；API 测试用 FastAPI dependency overrides。
"""

from __future__ import annotations

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
from app.data.providers.yfinance_indices_provider import (
    IndexMeta,
    _frame_to_bars,
)
from app.main import app
from app.models.global_index_bar import GlobalIndexDailyBar
from app.models.macro import MacroIndicator
from app.services.macro.global_index_bar_service import (
    GlobalIndexBarService,
    _infer_category,
)

# ---------------------------------------------------------------------------
# Fixtures
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


def _bars(code: str, closes: list[float], start: date = date(2026, 7, 27)):
    """构造连续交易日的 bars dict（open/high/low 围绕 close 生成）."""
    out = []
    for i, c in enumerate(closes):
        d = date.fromordinal(start.toordinal() + i)
        out.append({
            "code": code,
            "trade_date": d.isoformat(),
            "open": c - 1.0,
            "high": c + 2.0,
            "low": c - 2.0,
            "close": c,
            "volume": 1000 + i,
            "source": "yfinance",
        })
    return out


def _macro_row(code: str, period: date, value: float, **kw):
    row = {
        "code": code,
        "region": "us",
        "name_zh": "美国10年期国债收益率",
        "name_en": "10-Year Treasury Rate",
        "unit": "%",
        "period": period,
        "value": value,
        "source": "fred",
    }
    row.update(kw)
    return row


# ---------------------------------------------------------------------------
# 1. upsert_bars 幂等
# ---------------------------------------------------------------------------


def test_upsert_bars_inserts_and_counts(db_session):
    svc = GlobalIndexBarService(db_session)
    n = svc.upsert_bars(_bars("global_sp500", [100.0, 101.0, 102.0]))
    assert n == 3
    assert db_session.query(GlobalIndexDailyBar).count() == 3


def test_upsert_bars_is_idempotent(db_session):
    """同批插两次：行数不变."""
    svc = GlobalIndexBarService(db_session)
    bars = _bars("global_sp500", [100.0, 101.0, 102.0])
    svc.upsert_bars(bars)
    first = db_session.query(GlobalIndexDailyBar).count()

    svc.upsert_bars(bars)
    second = db_session.query(GlobalIndexDailyBar).count()
    assert first == second == 3


def test_upsert_bars_updates_existing_values(db_session):
    """重复 upsert 更新 O/H/L/C/V，不产生新行."""
    svc = GlobalIndexBarService(db_session)
    svc.upsert_bars(_bars("global_sp500", [100.0]))
    updated = _bars("global_sp500", [105.0])
    updated[0]["volume"] = 9999
    svc.upsert_bars(updated)

    rows = db_session.query(GlobalIndexDailyBar).all()
    assert len(rows) == 1
    assert rows[0].close == 105.0
    assert rows[0].volume == 9999


def test_upsert_bars_skips_invalid_rows(db_session):
    """缺 code / trade_date / close 的行被跳过."""
    svc = GlobalIndexBarService(db_session)
    n = svc.upsert_bars([
        {"code": "global_sp500", "trade_date": "2026-07-31", "close": 100.0},
        {"code": "global_sp500", "trade_date": None, "close": 100.0},
        {"code": "", "trade_date": "2026-07-31", "close": 100.0},
        {"code": "global_sp500", "trade_date": "2026-07-31", "close": None},
    ])
    assert n == 1
    assert db_session.query(GlobalIndexDailyBar).count() == 1


def test_upsert_bars_separates_sources(db_session):
    """同一 (code, trade_date) 不同 source 是两行."""
    svc = GlobalIndexBarService(db_session)
    n = svc.upsert_bars([
        {"code": "global_shcomp", "trade_date": "2026-07-31", "close": 3000.0,
         "source": "akshare"},
        {"code": "global_shcomp", "trade_date": "2026-07-31", "close": 3001.0,
         "source": "yfinance"},
    ])
    assert n == 2
    assert db_session.query(GlobalIndexDailyBar).count() == 2


# ---------------------------------------------------------------------------
# 2. _frame_to_bars（provider 层纯函数）
# ---------------------------------------------------------------------------


def _ohlcv_frame(rows):
    """rows: list of (date_str, open, high, low, close, volume)."""
    idx = pd.DatetimeIndex([r[0] for r in rows])
    return pd.DataFrame(
        {
            "Open": [r[1] for r in rows],
            "High": [r[2] for r in rows],
            "Low": [r[3] for r in rows],
            "Close": [r[4] for r in rows],
            "Volume": [r[5] for r in rows],
        },
        index=idx,
    )


def test_frame_to_bars_extracts_ohlcv():
    meta = IndexMeta("^GSPC", "global_sp500", "标普500", "S&P 500")
    h = _ohlcv_frame([
        ("2026-07-30", 99.0, 103.0, 98.0, 100.0, 12345),
        ("2026-07-31", 100.5, 104.0, 99.5, 102.0, 0),  # volume=0 → None
    ])
    bars = _frame_to_bars(h, meta)
    assert len(bars) == 2
    b0 = bars[0]
    assert b0["code"] == "global_sp500"
    assert b0["trade_date"] == "2026-07-30"
    assert b0["open"] == 99.0
    assert b0["high"] == 103.0
    assert b0["low"] == 98.0
    assert b0["close"] == 100.0
    assert b0["volume"] == 12345
    assert b0["source"] == "yfinance"
    assert bars[1]["volume"] is None  # 0 → None


def test_frame_to_bars_nan_open_and_volume_become_none():
    meta = IndexMeta("^GSPC", "global_sp500", "标普500", "S&P 500")
    h = _ohlcv_frame([("2026-07-31", float("nan"), 104.0, 99.5, 102.0, float("nan"))])
    bars = _frame_to_bars(h, meta)
    assert len(bars) == 1
    assert bars[0]["open"] is None
    assert bars[0]["volume"] is None
    assert bars[0]["close"] == 102.0


def test_frame_to_bars_drops_rows_without_close():
    meta = IndexMeta("^GSPC", "global_sp500", "标普500", "S&P 500")
    h = _ohlcv_frame([
        ("2026-07-30", 99.0, 103.0, 98.0, float("nan"), 100),
        ("2026-07-31", 100.5, 104.0, 99.5, 102.0, 100),
    ])
    bars = _frame_to_bars(h, meta)
    assert len(bars) == 1
    assert bars[0]["trade_date"] == "2026-07-31"


def test_frame_to_bars_invert_swaps_high_low():
    """EUR=X (invert_value=True)：全字段取倒数且 high/low 互换.

    原值 open=0.90 high=0.92 low=0.88 close=0.91 →
    倒数后 close≈1.0989，new_high = 1/0.88，new_low = 1/0.92。
    """
    meta = IndexMeta(
        "EUR=X", "usd_eur", "美元/欧元", "USD/EUR", "EUR/USD",
        invert_value=True, region="us",
    )
    h = _ohlcv_frame([("2026-07-31", 0.90, 0.92, 0.88, 0.91, 0)])
    bars = _frame_to_bars(h, meta)
    assert len(bars) == 1
    b = bars[0]
    assert b["open"] == pytest.approx(1 / 0.90)
    assert b["close"] == pytest.approx(1 / 0.91)
    # 关键：high/low 互换（1/x 单调递减）
    assert b["high"] == pytest.approx(1 / 0.88)
    assert b["low"] == pytest.approx(1 / 0.92)
    assert b["high"] > b["low"]
    assert b["volume"] is None


def test_frame_to_bars_empty_and_none_frame():
    meta = IndexMeta("^GSPC", "global_sp500", "标普500", "S&P 500")
    assert _frame_to_bars(None, meta) == []
    assert _frame_to_bars(pd.DataFrame(), meta) == []


# ---------------------------------------------------------------------------
# 3. get_detail 双分支
# ---------------------------------------------------------------------------


def test_get_detail_ohlc_branch(db_session):
    """有 bars 时走 OHLC 分支：latest/stats/ohlc 全部由 bars 计算."""
    svc = GlobalIndexBarService(db_session)
    svc.upsert_bars(_bars("global_sp500", [100.0, 101.0, 103.0]))

    detail = svc.get_detail("global_sp500")
    assert detail is not None
    assert detail["has_ohlc"] is True
    assert detail["category"] == "index"
    assert detail["ohlc"] is not None and len(detail["ohlc"]) == 3
    # 日期升序
    dates = [b["date"] for b in detail["ohlc"]]
    assert dates == sorted(dates)
    # latest：最新 close + 前一日 close
    assert detail["latest"]["value"] == 103.0
    assert detail["latest"]["prev_value"] == 101.0
    assert detail["latest"]["change_abs"] == pytest.approx(2.0)
    assert detail["latest"]["change_pct"] == pytest.approx(2 / 101 * 100)
    # stats：first/last/count + 52 周高低（high=c+2, low=c-2）
    assert detail["stats"]["count"] == 3
    assert detail["stats"]["first_period"] == "2026-07-27"
    assert detail["stats"]["last_period"] == "2026-07-29"
    assert detail["stats"]["high_52w"] == pytest.approx(105.0)
    assert detail["stats"]["low_52w"] == pytest.approx(98.0)
    assert detail["points"] == []


def test_get_detail_ohlc_meta_from_macro_indicator(db_session):
    """meta 优先取 macro_indicator 最新行."""
    db_session.add(MacroIndicator(**_macro_row(
        "global_sp500", date(2026, 7, 29), 103.0,
        region="global", name_zh="标普500", name_en="S&P 500",
        unit="指数", source="yfinance",
    )))
    db_session.commit()
    svc = GlobalIndexBarService(db_session)
    svc.upsert_bars(_bars("global_sp500", [100.0]))

    detail = svc.get_detail("global_sp500")
    assert detail["name_zh"] == "标普500"
    assert detail["name_en"] == "S&P 500"
    assert detail["region"] == "global"
    assert detail["source"] == "yfinance"


def test_get_detail_ohlc_meta_registry_fallback(db_session):
    """macro_indicator 无行时 meta 从静态 registry 兜底."""
    svc = GlobalIndexBarService(db_session)
    svc.upsert_bars(_bars("global_sp500", [100.0]))
    detail = svc.get_detail("global_sp500")
    assert detail["name_zh"] == "标普500"
    assert detail["name_en"] == "S&P 500"
    assert detail["unit"] == "指数"


def test_get_detail_fallback_to_macro_points(db_session):
    """无 bars 的 FRED 代码：回退 macro_indicator 折线."""
    db_session.add_all([
        MacroIndicator(**_macro_row("us_dgs10", date(2026, 7, 28), 4.20)),
        MacroIndicator(**_macro_row("us_dgs10", date(2026, 7, 29), 4.25)),
        MacroIndicator(**_macro_row("us_dgs10", date(2026, 7, 30), 4.30)),
    ])
    db_session.commit()

    svc = GlobalIndexBarService(db_session)
    detail = svc.get_detail("us_dgs10")
    assert detail is not None
    assert detail["has_ohlc"] is False
    assert detail["ohlc"] is None
    assert detail["category"] == "rate"
    assert len(detail["points"]) == 3
    assert detail["points"][0]["period"] == "2026-07-28"
    # latest 由 points 计算
    assert detail["latest"]["value"] == 4.30
    assert detail["latest"]["prev_value"] == 4.25
    assert detail["latest"]["change_abs"] == pytest.approx(0.05)
    assert detail["stats"]["count"] == 3
    assert detail["stats"]["high_52w"] == pytest.approx(4.30)
    assert detail["stats"]["low_52w"] == pytest.approx(4.20)


def test_get_detail_unknown_code_returns_none(db_session):
    svc = GlobalIndexBarService(db_session)
    assert svc.get_detail("not_a_real_code") is None


def test_get_detail_bars_window_and_limit(db_session):
    """时间窗过滤 + limit 取最新 N 条（升序返回）."""
    svc = GlobalIndexBarService(db_session)
    svc.upsert_bars(_bars("global_sp500", [100.0, 101.0, 102.0, 103.0, 104.0]))

    windowed = svc.get_detail(
        "global_sp500", start_date=date(2026, 7, 29), end_date=date(2026, 7, 30)
    )
    assert [b["date"] for b in windowed["ohlc"]] == ["2026-07-29", "2026-07-30"]

    limited = svc.get_detail("global_sp500", limit=2)
    assert [b["date"] for b in limited["ohlc"]] == ["2026-07-30", "2026-07-31"]


# ---------------------------------------------------------------------------
# category 规则（与前端 inferCategoryKey 逐条对齐）
# ---------------------------------------------------------------------------


def test_infer_category_matches_frontend_rules():
    assert _infer_category("us_dgs10") == "rate"
    assert _infer_category("us_dgs30") == "rate"
    assert _infer_category("us_t10y2y") == "rate"
    assert _infer_category("us_vix") == "vol"
    assert _infer_category("global_dxy") == "fx"
    assert _infer_category("global_usdjpy") == "fx"
    assert _infer_category("usd_cny") == "fx"
    assert _infer_category("usd_eur") == "fx"
    assert _infer_category("global_brent") == "commodity"
    assert _infer_category("global_wti") == "commodity"
    assert _infer_category("global_sp500") == "index"
    assert _infer_category("global_shcomp") == "index"


# ---------------------------------------------------------------------------
# 4. API 层
# ---------------------------------------------------------------------------


@pytest.fixture
def client(db_session):
    """TestClient with DB / auth overrides（与 test_china_macro 同一模式）."""

    def _override_user():
        from app.schemas.auth import UserResponse

        return UserResponse(id=1, username="tester", role="user")

    def _get_db_override():
        try:
            yield db_session
        finally:
            pass

    def _bar_service_override():
        return GlobalIndexBarService(db_session)

    app.dependency_overrides[api_deps.get_db] = _get_db_override
    app.dependency_overrides[macro_api._bar_service] = _bar_service_override
    app.dependency_overrides[macro_api.get_current_user] = _override_user

    with patch("app.api.v1.macro.SessionLocal", return_value=db_session), TestClient(app) as c:
        try:
            yield c
        finally:
            app.dependency_overrides.clear()


def test_api_detail_200_ohlc(client, db_session):
    GlobalIndexBarService(db_session).upsert_bars(
        _bars("global_sp500", [100.0, 101.0, 103.0])
    )
    resp = client.get("/api/v1/macro/indicators/global_sp500/detail")
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == "global_sp500"
    assert body["has_ohlc"] is True
    assert body["category"] == "index"
    assert len(body["ohlc"]) == 3
    assert body["ohlc"][0]["date"] == "2026-07-27"
    assert body["ohlc"][0]["open"] is not None
    assert body["ohlc"][0]["volume"] is not None
    assert body["latest"]["value"] == 103.0
    assert body["latest"]["prev_value"] == 101.0
    assert body["stats"]["count"] == 3
    assert body["points"] == []


def test_api_detail_200_fred_fallback(client, db_session):
    db_session.add_all([
        MacroIndicator(**_macro_row("us_dgs10", date(2026, 7, 29), 4.25)),
        MacroIndicator(**_macro_row("us_dgs10", date(2026, 7, 30), 4.30)),
    ])
    db_session.commit()
    resp = client.get("/api/v1/macro/indicators/us_dgs10/detail")
    assert resp.status_code == 200
    body = resp.json()
    assert body["has_ohlc"] is False
    assert body["ohlc"] is None
    assert len(body["points"]) == 2
    assert body["latest"]["value"] == 4.30


def test_api_detail_404_unknown_code(client):
    resp = client.get("/api/v1/macro/indicators/definitely_unknown/detail")
    assert resp.status_code == 404


def test_api_detail_limit_truncation(client, db_session):
    GlobalIndexBarService(db_session).upsert_bars(
        _bars("global_sp500", [100.0, 101.0, 102.0, 103.0, 104.0])
    )
    resp = client.get("/api/v1/macro/indicators/global_sp500/detail?limit=2")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["ohlc"]) == 2
    # limit 取最新 N 条，升序
    assert [b["date"] for b in body["ohlc"]] == ["2026-07-30", "2026-07-31"]


def test_api_detail_date_window_filter(client, db_session):
    GlobalIndexBarService(db_session).upsert_bars(
        _bars("global_sp500", [100.0, 101.0, 102.0, 103.0, 104.0])
    )
    resp = client.get(
        "/api/v1/macro/indicators/global_sp500/detail"
        "?start_date=2026-07-29&end_date=2026-07-30"
    )
    assert resp.status_code == 200
    body = resp.json()
    assert [b["date"] for b in body["ohlc"]] == ["2026-07-29", "2026-07-30"]
