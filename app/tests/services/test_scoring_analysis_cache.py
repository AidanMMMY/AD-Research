"""评分 / 分析域 Redis 缓存行为测试（2026-08-17 性能修复）。

覆盖：
- ``ScoringService._latest_dates_by_market``：GROUP BY 结果写入缓存、
  缓存命中时不再读 DB、``calculate_daily_scores`` 完成后主动失效；
- ``AnalysisService.ranking`` / ``screen``：结果缓存、参数哈希分 key、
  缓存命中时不再读 DB；
- Redis 故障时 ``try_cache_*`` 静默回退 DB（热路径不 5xx）。

测试用进程内 FakeRedis（patch ``app.core.cache.get_redis_client``），
不依赖真实 Redis；项目未引入 fakeredis，参照
``app/tests/news/conftest.py`` 的最小 shim 模式。
"""

from __future__ import annotations

import fnmatch
from datetime import date
from typing import Any

import pytest

from app.models.etf import ETFIndicator, ETFInfo
from app.models.scoring import ETFScore
from app.services.analysis_service import AnalysisService
from app.services.scoring_service import ScoringService


class _FakeRedis:
    """最小内存 Redis：仅覆盖 cache.py 用到的 get/setex/scan_iter/delete。"""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    def get(self, key: str) -> str | None:
        return self.store.get(key)

    def setex(self, key: str, ttl: int, value: Any) -> bool:
        self.store[key] = str(value)
        return True

    def delete(self, *keys: str) -> int:
        n = 0
        for k in keys:
            if k in self.store:
                del self.store[k]
                n += 1
        return n

    def scan_iter(self, match: str):
        for k in list(self.store.keys()):
            if fnmatch.fnmatchcase(k, match):
                yield k


@pytest.fixture
def fake_redis(monkeypatch) -> _FakeRedis:
    r = _FakeRedis()
    # app.core.cache 在模块 import 时把 get_redis_client 绑进了自己的
    # 命名空间，必须 patch cache 模块里的引用才生效。
    monkeypatch.setattr("app.core.cache.get_redis_client", lambda: r)
    return r


def _seed_scores(db_session, service: ScoringService):
    """A股/US 各一只 ETF，US 评分日期领先一天；返回 template。"""
    template = service.create_template(
        name="Cache-Test",
        description="cache",
        weights={"return": 0.3, "risk": 0.3, "sharpe": 0.4},
    )
    db_session.add_all(
        [
            ETFInfo(code="CACHE_A1", name="A Fund", market="A股", category="Equity"),
            ETFInfo(code="CACHE_U1", name="U Fund", market="US", category="Equity"),
        ]
    )
    db_session.add_all(
        [
            ETFScore(
                etf_code="CACHE_A1", trade_date=date(2024, 7, 29),
                template_id=template.id, composite_score=60, rank_overall=1,
            ),
            ETFScore(
                etf_code="CACHE_U1", trade_date=date(2024, 7, 29),
                template_id=template.id, composite_score=50, rank_overall=2,
            ),
            ETFScore(
                etf_code="CACHE_U1", trade_date=date(2024, 7, 30),
                template_id=template.id, composite_score=70, rank_overall=1,
            ),
        ]
    )
    db_session.commit()
    return template


def test_latest_dates_cached_across_get_and_count(db_session, fake_redis):
    """get_scores + count_scores（一次 GET /scores 请求）只 GROUP BY 一次。"""
    from sqlalchemy import event

    service = ScoringService(db_session)
    template = _seed_scores(db_session, service)

    group_by_count = 0

    def _count_group_by(conn, cursor, statement, parameters, context, executemany):
        nonlocal group_by_count
        s = statement.lower()
        if "group by" in s and "etf_score" in s:
            group_by_count += 1

    engine = db_session.get_bind()
    event.listen(engine, "before_cursor_execute", _count_group_by)
    try:
        scores = service.get_scores(template_id=template.id)
        assert {s["etf_code"] for s in scores} == {"CACHE_A1", "CACHE_U1"}
        assert group_by_count == 1, "冷缓存应做一次 GROUP BY"

        cache_key = f"scores:latest_dates:{template.id}"
        assert cache_key in fake_redis.store, "首次查询后映射应已写入缓存"

        # 热缓存：count_scores / 再次 get_scores 都不再触发 GROUP BY
        assert service.count_scores(template_id=template.id) == 2
        warm = service.get_scores(template_id=template.id)
        assert {s["etf_code"] for s in warm} == {"CACHE_A1", "CACHE_U1"}
        assert group_by_count == 1, "缓存命中后不应再扫 etf_score"
    finally:
        event.remove(engine, "before_cursor_execute", _count_group_by)


def test_latest_dates_cache_invalidated_after_calculation(db_session, fake_redis):
    """calculate_daily_scores 完成后主动失效 latest_dates 缓存。"""
    service = ScoringService(db_session)
    template = _seed_scores(db_session, service)

    service.get_scores(template_id=template.id)
    cache_key = f"scores:latest_dates:{template.id}"
    assert cache_key in fake_redis.store

    # 显式 trade_date + 无指标：走完全程但不写任何评分，
    # 结尾仍应主动清掉 scores:latest_dates:*。
    service.calculate_daily_scores(trade_date=date(2024, 7, 31))

    assert not any(
        k.startswith("scores:latest_dates:") for k in fake_redis.store
    ), "评分计算完成后 latest_dates 缓存应被主动失效"


def test_get_scores_cold_and_warm_cache_agree(db_session, fake_redis):
    """冷缓存（DB GROUP BY）与热缓存（Redis 映射）结果必须一致。"""
    service = ScoringService(db_session)
    template = _seed_scores(db_session, service)

    cold = service.get_scores(template_id=template.id)
    warm = service.get_scores(template_id=template.id)
    assert [(s["etf_code"], s["trade_date"]) for s in cold] == [
        (s["etf_code"], s["trade_date"]) for s in warm
    ]


def _seed_indicators(db_session):
    db_session.add_all(
        [
            ETFInfo(code="ANA_1", name="Fund One", market="A股", category="Equity"),
            ETFInfo(code="ANA_2", name="Fund Two", market="US", category="Bond"),
        ]
    )
    db_session.add_all(
        [
            ETFIndicator(
                etf_code="ANA_1", trade_date=date(2024, 8, 1),
                rsi14=55.0, sharpe_1y=1.5, volatility_20d=0.15,
            ),
            ETFIndicator(
                etf_code="ANA_2", trade_date=date(2024, 8, 1),
                rsi14=30.0, sharpe_1y=0.5, volatility_20d=0.08,
            ),
        ]
    )
    db_session.commit()


def test_analysis_ranking_result_cached(db_session, fake_redis):
    service = AnalysisService(db_session)
    _seed_indicators(db_session)

    items = service.ranking(sort_by="sharpe_1y", limit=10)
    assert [i["etf_code"] for i in items] == ["ANA_1", "ANA_2"]
    assert any(k.startswith("analysis:ranking:") for k in fake_redis.store)

    # 缓存命中：清空表后同参数查询仍返回缓存结果
    db_session.query(ETFIndicator).delete()
    db_session.commit()
    cached_items = service.ranking(sort_by="sharpe_1y", limit=10)
    assert cached_items == items

    # 参数不同 → key 哈希不同 → 缓存未命中 → 查到空表
    miss_items = service.ranking(sort_by="sharpe_1y", limit=5)
    assert miss_items == []


def test_analysis_screen_result_cached(db_session, fake_redis):
    service = AnalysisService(db_session)
    _seed_indicators(db_session)

    items = service.screen(rsi_min=50.0)
    assert [i["etf_code"] for i in items] == ["ANA_1"]
    assert any(k.startswith("analysis:screen:") for k in fake_redis.store)

    db_session.query(ETFIndicator).delete()
    db_session.commit()
    assert service.screen(rsi_min=50.0) == items
    # 不同筛选条件 → 未命中
    assert service.screen(rsi_min=10.0) == []


def test_redis_outage_falls_back_to_db(db_session, monkeypatch):
    """Redis 挂掉时 try_cache_* 静默回退，热路径不炸。"""
    def _boom():
        raise ConnectionError("redis down")

    monkeypatch.setattr("app.core.cache.get_redis_client", _boom)

    scoring = ScoringService(db_session)
    template = _seed_scores(db_session, scoring)
    scores = scoring.get_scores(template_id=template.id)
    assert {s["etf_code"] for s in scores} == {"CACHE_A1", "CACHE_U1"}

    analysis = AnalysisService(db_session)
    _seed_indicators(db_session)
    assert len(analysis.ranking(sort_by="sharpe_1y", limit=10)) == 2
    assert len(analysis.screen()) == 2
