"""Shared pytest fixtures for service-level tests.

Provides an in-memory SQLite database and a session fixture that service
tests can use to exercise real ORM flows without touching the dev DB.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base


@pytest.fixture
def db_session():
    """Yield a fresh in-memory SQLite session backed by a clean schema.

    Tables are created on the in-memory engine so service tests can
    use real SQLAlchemy queries without depending on the dev database.
    """
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    Session_ = sessionmaker(bind=engine)
    session = Session_()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture
def db_session_module():
    """Module-scoped in-memory SQLite session (shared across a test file)."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    Session_ = sessionmaker(bind=engine)
    session = Session_()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture(autouse=True)
def _clear_score_analysis_cache():
    """每个测试前后清空评分 / 分析域的 Redis 缓存键。

    scoring_service 的 "每市场最新评分日期" 缓存（``scores:latest_dates:*``）
    与 analysis_service 的 ranking/screen 结果缓存（``analysis:*``）挂在
    真实 Redis 上；测试用的是内存 SQLite，主键每次运行从 1 重新自增，
    不清缓存会被上一次运行 / 上一个测试的陈旧键污染（参照
    test_screening.py 对 ``screen:*`` 的同款处理）。Redis 不可用时静默跳过。
    """
    def _clear():
        try:
            from app.core.redis_client import get_redis_client

            client = get_redis_client()
            for pattern in ("scores:latest_dates:*", "analysis:*"):
                for key in client.scan_iter(match=pattern):
                    client.delete(key)
        except Exception:
            pass

    _clear()
    yield
    _clear()
