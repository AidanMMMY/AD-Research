"""Shared pytest fixtures for service-level tests.

Provides an in-memory SQLite database and a session fixture that service
tests can use to exercise real ORM flows without touching the dev DB.
"""

import os
from urllib.parse import urlparse, urlunparse

# ── Redis 测试隔离（2026-08-17，审计遗留第 3 条）────────────────────────
# 问题：测试默认沿用 settings.redis_url（redis://localhost:6379/0，与开发库
# 共享 db 0）。service 层的 cache_set（etf:*/screen:* 等键，TTL 300-600s）
# 会跨测试、跨运行残留——例如 test_etf_service 先缓存了空库结果，后续测试
# seed 数据后仍读到 stale 缓存，造成偶发失败。
# 方案（选型 A 变体）：在任何 app 模块导入前把 REDIS_URL 强制指向独立的
# db 15（保留原 host/port，CI 的 redis service 与本地 redis-server 均适用），
# 再由下方的 autouse fixture 在每个测试前后对该 db 做 flushdb。
# 只 flush db 15，绝不触碰开发库 db 0。
# 注意：项目未使用 pytest-xdist；若未来引入并行，需按 worker 分 db
# （redis 默认仅 16 个 db，需同步调大 `databases` 配置）或改用键前缀隔离。
_TEST_REDIS_DB = 15


def _redis_url_with_db(base_url: str, db: int) -> str:
    """Return ``base_url`` with its database number replaced by ``db``."""
    return urlunparse(urlparse(base_url)._replace(path=f"/{db}"))


# 必须在 import app.* 之前设置——get_settings() 是 lru_cache 的，首次调用
# 即固化 redis_url。环境变量优先级高于 .env，因此开发机的 .env 不会盖掉它。
os.environ["REDIS_URL"] = _redis_url_with_db(
    os.environ.get("REDIS_URL", "redis://localhost:6379/0"), _TEST_REDIS_DB
)

import pytest  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.core.database import Base  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _isolated_test_redis():
    """Point the shared Redis client at the test-only db and reset its caches.

    Defensively clears the lru_caches on get_settings / get_redis_client so
    the client is guaranteed to target db 15 even if something imported app
    modules before this conftest ran. Yields None when Redis is unreachable
    (tests that need a real Redis keep their pre-existing skip/fail
    behaviour; CI and local dev both run redis-server).
    """
    from app.config import get_settings
    from app.core import redis_client

    get_settings.cache_clear()
    redis_client.get_redis_client.cache_clear()

    client = redis_client.get_redis_client()
    try:
        client.ping()
    except Exception:
        yield None
        return

    # 安全断言：flushdb 只准落在测试专用 db，防止误清开发库。
    actual_db = client.connection_pool.connection_kwargs.get("db")
    assert actual_db == _TEST_REDIS_DB, (
        f"测试 Redis 客户端指向 db {actual_db}，拒绝 flush（应为 db {_TEST_REDIS_DB}）"
    )

    client.flushdb()
    yield client
    client.flushdb()


@pytest.fixture(autouse=True)
def _flush_test_redis(_isolated_test_redis):
    """Flush the test-only Redis db before AND after every test function.

    Guarantees cache isolation between tests regardless of which service
    layer wrote which key (the previous per-file ``screen:*``/``etf:*``
    pattern sweeps only covered a subset of keys and only some test files).
    """
    client = _isolated_test_redis
    if client is not None:
        client.flushdb()
    yield
    if client is not None:
        client.flushdb()


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
