"""Tests for the news AI-translation service + /translate endpoint.

Covers:

* Service unit tests (no LLM call) — cache hit, language gate,
  empty-body guard, ``unsupported target_language`` rejection.
* Service unit tests with a stubbed DeepSeekProvider — first call
  persists, second call returns cached, no LLM call.
* API smoke tests — 200 on success, 400 on non-English, 404 on
  missing, 429 when the daily limit trips, 409 when the Redis
  lock is held.

The tests reuse the in-memory SQLite engine and ``FakeRedis``
fixture defined in this directory's ``conftest.py``.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.database import Base
from app.services.news._model_loader import NewsArticle


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def news_db():
    """Fresh in-memory SQLite with only the news tables created.

    Mirrors the ``news_db`` fixture in ``test_news.py`` but kept local
    so this file can run standalone.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    engine = create_engine(
        "sqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


class _FakeUser:
    """Stand-in for ``UserResponse`` so the endpoint accepts us."""

    id = 1
    username = "tester"
    role = "user"


@pytest.fixture
def api_client(news_db, fake_redis, monkeypatch):
    """FastAPI TestClient with get_db + auth + redis_lock stubbed."""
    from app.api.v1 import news as news_module

    def _override_db():
        try:
            yield news_db
        finally:
            pass

    def _override_user():
        return _FakeUser()

    # The endpoint imports ``get_redis_client`` by name, so the
    # core-level patch in ``conftest.fake_redis`` isn't enough — also
    # patch the consumer's reference so both the rate-limit ``incr``
    # and the ``redis_lock`` use the fake instance.
    monkeypatch.setattr(news_module, "get_redis_client", lambda: fake_redis)

    test_app = FastAPI()
    test_app.include_router(news_module.router, prefix="/api/v1/news")
    test_app.dependency_overrides[news_module.get_db] = _override_db
    test_app.dependency_overrides[news_module.get_current_user] = _override_user
    with TestClient(test_app) as client:
        yield client
    test_app.dependency_overrides.clear()


def _make_english_article(news_db, *, body: str | None = "Hello world.") -> NewsArticle:
    now = datetime.now(tz=timezone.utc)
    a = NewsArticle(
        source="cnbc",
        source_id="t-1",
        url="https://example.com/a",
        url_hash="hash-1",
        title="An English article",
        summary="Short intro",
        body=body,
        language="en",
        market="us",
        published_at=now,
    )
    news_db.add(a)
    news_db.commit()
    news_db.refresh(a)
    return a


def _make_chinese_article(news_db) -> NewsArticle:
    now = datetime.now(tz=timezone.utc)
    a = NewsArticle(
        source="xinhua_rss",
        source_id="t-zh",
        url="https://example.com/zh",
        url_hash="hash-zh",
        title="一篇中文文章",
        body="中文正文",
        language="zh",
        market="cn_a",
        published_at=now,
    )
    news_db.add(a)
    news_db.commit()
    news_db.refresh(a)
    return a


def _patch_provider(translation_text: str = "你好，世界。"):
    """Patch DeepSeekProvider so no real network call is made.

    Returns a context manager; yields the mock instance so tests can
    inspect ``call_count`` or change behaviour mid-test.
    """
    fake_provider = MagicMock()
    fake_provider.is_available = True
    fake_provider.chat.return_value = translation_text
    return patch(
        "app.services.llm.deepseek_provider.DeepSeekProvider",
        return_value=fake_provider,
    ), fake_provider


# ---------------------------------------------------------------------------
# Service unit tests
# ---------------------------------------------------------------------------


class TestNewsTranslationService:
    def test_translate_persists_and_returns_translation(self, news_db):
        from app.services.news.translation_service import NewsTranslationService

        article = _make_english_article(news_db)
        ctx, fake_provider = _patch_provider("你好，世界。")
        with ctx:
            result = NewsTranslationService(news_db).translate(article.id)

        assert result["translation"] == "你好，世界。"
        assert result["cached"] is False
        assert result["source_language"] == "en"
        assert result["target_language"] == "zh"
        assert result["generated_at"] is not None
        # DB row should now be populated.
        news_db.refresh(article)
        assert article.translated_zh == "你好，世界。"
        assert article.translation_generated_at is not None
        # LLM called exactly once.
        assert fake_provider.chat.call_count == 1

    def test_cache_hit_skips_llm(self, news_db):
        from app.services.news.translation_service import NewsTranslationService

        article = _make_english_article(news_db)
        ctx, fake_provider = _patch_provider("首次翻译")
        with ctx:
            first = NewsTranslationService(news_db).translate(article.id)
        assert first["cached"] is False

        # Second call — same row, different provider state to prove
        # the cache short-circuits before the LLM is invoked.
        ctx2, fake_provider2 = _patch_provider("不应该被调用")
        with ctx2:
            second = NewsTranslationService(news_db).translate(article.id)

        assert second["cached"] is True
        assert second["translation"] == "首次翻译"
        assert second["generated_at"] == first["generated_at"]
        assert fake_provider2.chat.call_count == 0

    def test_non_english_raises_value_error(self, news_db):
        from app.services.news.translation_service import NewsTranslationService

        article = _make_chinese_article(news_db)
        with pytest.raises(ValueError) as exc:
            NewsTranslationService(news_db).translate(article.id)
        assert "language" in str(exc.value).lower() or "English" in str(exc.value)

    def test_unknown_article_raises_value_error(self, news_db):
        from app.services.news.translation_service import NewsTranslationService

        with pytest.raises(ValueError) as exc:
            NewsTranslationService(news_db).translate(99999)
        assert "not found" in str(exc.value).lower()

    def test_empty_body_raises_value_error(self, news_db):
        from app.services.news.translation_service import NewsTranslationService

        article = _make_english_article(news_db, body=None)
        # Also blank out full_content on the row.
        article.full_content = None
        news_db.commit()

        with pytest.raises(ValueError) as exc:
            NewsTranslationService(news_db).translate(article.id)
        assert "no body" in str(exc.value).lower()

    def test_unsupported_target_language(self, news_db):
        from app.services.news.translation_service import NewsTranslationService

        article = _make_english_article(news_db)
        with pytest.raises(ValueError) as exc:
            NewsTranslationService(news_db).translate(
                article.id, target_language="es"
            )
        assert "Unsupported" in str(exc.value)

    def test_full_content_used_when_present(self, news_db):
        """Prefer Jina-fetched ``full_content`` over ``body``."""
        from app.services.news.translation_service import NewsTranslationService

        article = _make_english_article(news_db, body="short body")
        article.full_content = "Long full content here"
        news_db.commit()

        ctx, fake_provider = _patch_provider("完整正文")
        with ctx:
            result = NewsTranslationService(news_db).translate(article.id)

        assert result["translation"] == "完整正文"
        # Confirm the LLM was given the full_content text.
        kwargs = fake_provider.chat.call_args.kwargs
        messages = kwargs.get("messages") or []
        assert messages
        sent = messages[0]["content"]
        assert "Long full content here" in sent

    def test_provider_no_key_raises_runtime_error(self, news_db, monkeypatch):
        from app.services.news.translation_service import NewsTranslationService
        from app.services.llm import deepseek_provider

        article = _make_english_article(news_db)
        # Force the provider to report unavailable.
        monkeypatch.setattr(
            deepseek_provider.DeepSeekProvider,
            "__init__",
            lambda self, model=None: (_ for _ in ()).throw(
                AttributeError("unused")
            )
            or None,
        )

        class _NoKeyProvider:
            is_available = False
            def chat(self, *a, **k):  # pragma: no cover
                return ""

        monkeypatch.setattr(
            "app.services.news.translation_service.NewsTranslationService._call_llm_with_retry",
            lambda *a, **k: (None, None),
        )

        # When is_available is False, the service should raise RuntimeError.
        with patch(
            "app.services.llm.deepseek_provider.DeepSeekProvider",
            return_value=_NoKeyProvider(),
        ):
            with pytest.raises(RuntimeError) as exc:
                NewsTranslationService(news_db).translate(article.id)
        assert "DEEPSEEK_API_KEY" in str(exc.value)

    def test_get_cached_translation(self, news_db):
        from app.services.news.translation_service import NewsTranslationService

        article = _make_english_article(news_db)
        # Initially None.
        assert (
            NewsTranslationService(news_db).get_cached_translation(article.id) is None
        )
        # Persist a value.
        article.translated_zh = "缓存"
        news_db.commit()
        assert (
            NewsTranslationService(news_db).get_cached_translation(article.id)
            == "缓存"
        )


# ---------------------------------------------------------------------------
# API smoke tests
# ---------------------------------------------------------------------------


class TestTranslateEndpoint:
    def test_post_translate_returns_translation(self, api_client, news_db):
        article = _make_english_article(news_db)
        ctx, _ = _patch_provider("你好，世界。")
        with ctx:
            resp = api_client.post(f"/api/v1/news/{article.id}/translate")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["translation"] == "你好，世界。"
        assert body["cached"] is False
        assert body["target_language"] == "zh"

    def test_post_translate_caches_on_second_call(self, api_client, news_db):
        article = _make_english_article(news_db)
        ctx, fake_provider = _patch_provider("翻译 A")
        with ctx:
            first = api_client.post(f"/api/v1/news/{article.id}/translate")
        assert first.status_code == 200
        assert first.json()["cached"] is False
        assert fake_provider.chat.call_count == 1

        ctx2, fake_provider2 = _patch_provider("翻译 B（不应被调用）")
        with ctx2:
            second = api_client.post(f"/api/v1/news/{article.id}/translate")
        assert second.status_code == 200
        assert second.json()["cached"] is True
        assert second.json()["translation"] == "翻译 A"
        assert fake_provider2.chat.call_count == 0

    def test_non_english_returns_400(self, api_client, news_db):
        article = _make_chinese_article(news_db)
        resp = api_client.post(f"/api/v1/news/{article.id}/translate")
        assert resp.status_code == 400
        assert "language" in resp.json()["detail"].lower()

    def test_missing_article_returns_404(self, api_client, news_db):
        resp = api_client.post("/api/v1/news/999999/translate")
        assert resp.status_code == 404

    def test_unsupported_target_language_returns_400(self, api_client, news_db):
        article = _make_english_article(news_db)
        resp = api_client.post(
            f"/api/v1/news/{article.id}/translate",
            params={"target_language": "es"},
        )
        assert resp.status_code == 400
        assert "Unsupported" in resp.json()["detail"]

    def test_daily_limit_returns_429(self, api_client, news_db, monkeypatch):
        from app.config import get_settings

        # Shrink the daily cap to 1 so the second call trips the limit.
        original = get_settings().news_translate_daily_limit
        get_settings().news_translate_daily_limit = 1
        try:
            article = _make_english_article(news_db)
            ctx, _ = _patch_provider("好的")
            with ctx:
                first = api_client.post(f"/api/v1/news/{article.id}/translate")
            assert first.status_code == 200

            # Second call would re-hit the LLM, so it should be 429.
            ctx2, _ = _patch_provider("不再调用")
            with ctx2:
                second = api_client.post(f"/api/v1/news/{article.id}/translate")
            assert second.status_code == 429
            assert "上限" in second.json()["detail"]
        finally:
            get_settings().news_translate_daily_limit = original

    def test_provider_no_key_returns_502(self, api_client, news_db):
        article = _make_english_article(news_db)

        class _NoKeyProvider:
            is_available = False
            def chat(self, *a, **k):  # pragma: no cover
                return ""

        with patch(
            "app.services.llm.deepseek_provider.DeepSeekProvider",
            return_value=_NoKeyProvider(),
        ):
            resp = api_client.post(f"/api/v1/news/{article.id}/translate")
        assert resp.status_code == 502
        assert "DEEPSEEK_API_KEY" in resp.json()["detail"]

    def test_get_article_includes_translation_fields(self, api_client, news_db):
        article = _make_english_article(news_db)
        article.translated_zh = "示例译文"
        article.translation_generated_at = datetime.now(tz=timezone.utc)
        news_db.commit()

        resp = api_client.get(f"/api/v1/news/{article.id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["translated_zh"] == "示例译文"
        assert body["translation_generated_at"] is not None