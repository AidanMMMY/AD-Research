"""Tests for the news AI one-sentence summary pipeline (方向 D, 2026-07-29).

Covers:

* Service unit tests with a stubbed LLM provider — persist + cache
  sentinel, ≤80-char truncation, empty-body skip, Chinese articles are
  summarized too (summary ≠ title restated), prompt contains the
  quality constraints, provider-unavailable skip.
* Drain job tests — importance gate (≥3), ordering, provider
  unavailable = skipped run without touching rows.
* API serialization — list + detail expose ``summary_zh``.

Mirrors the fixture/patching patterns in ``test_translation.py`` and
``test_ingest_full_content.py``.
"""

from __future__ import annotations

from datetime import datetime, timezone
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
    """Fresh in-memory SQLite with only the news tables created."""
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
    id = 1
    username = "tester"
    role = "user"


@pytest.fixture
def api_client(news_db, fake_redis, monkeypatch):
    """FastAPI TestClient with get_db + auth stubbed."""
    from app.api.v1 import news as news_module

    def _override_db():
        try:
            yield news_db
        finally:
            pass

    def _override_user():
        return _FakeUser()

    monkeypatch.setattr(news_module, "get_redis_client", lambda: fake_redis)

    test_app = FastAPI()
    test_app.include_router(news_module.router, prefix="/api/v1/news")
    test_app.dependency_overrides[news_module.get_db] = _override_db
    test_app.dependency_overrides[news_module.get_current_user] = _override_user
    with TestClient(test_app) as client:
        yield client
    test_app.dependency_overrides.clear()


def _make_article(
    news_db,
    *,
    title: str = "美联储宣布降息25个基点",
    body: str | None = "美联储在7月议息会议上宣布降息25个基点，联邦基金利率降至4.00%-4.25%。",
    language: str = "zh",
    importance: int = 4,
    source_id: str = "s-1",
) -> NewsArticle:
    now = datetime.now(tz=timezone.utc)
    a = NewsArticle(
        source="cls",
        source_id=source_id,
        url=f"https://example.com/{source_id}",
        url_hash=f"hash-{source_id}",
        title=title,
        body=body,
        language=language,
        market="cn_a",
        importance=importance,
        published_at=now,
    )
    news_db.add(a)
    news_db.commit()
    news_db.refresh(a)
    return a


def _patch_provider(summary_text: str = "美联储降息25个基点至4.00%-4.25%，为年内首次。"):
    """Patch ``get_llm_provider`` so no real network call is made."""
    fake_provider = MagicMock()
    fake_provider.is_available = True
    fake_provider.chat.return_value = summary_text
    return patch(
        "app.services.llm.get_llm_provider",
        return_value=fake_provider,
    ), fake_provider


class _UnavailableProvider:
    is_available = False

    def chat(self, *a, **k):  # pragma: no cover
        return ""


# ---------------------------------------------------------------------------
# Service unit tests
# ---------------------------------------------------------------------------


class TestNewsSummaryService:
    def test_summarize_persists(self, news_db):
        from app.services.news.summary_service import NewsSummaryService

        article = _make_article(news_db)
        ctx, fake_provider = _patch_provider()
        with ctx:
            result = NewsSummaryService(news_db).summarize(article.id)

        assert result["skipped"] is False
        assert result["summary"] == "美联储降息25个基点至4.00%-4.25%，为年内首次。"
        news_db.refresh(article)
        assert article.summary_zh == result["summary"]
        assert fake_provider.chat.call_count == 1

    def test_chinese_article_is_summarized(self, news_db):
        """No language gate — a Chinese headline still gets a digest."""
        from app.services.news.summary_service import NewsSummaryService

        article = _make_article(news_db, language="zh")
        ctx, fake_provider = _patch_provider()
        with ctx:
            result = NewsSummaryService(news_db).summarize(article.id)

        assert result["skipped"] is False
        assert fake_provider.chat.call_count == 1

    def test_long_output_truncated_to_80_chars(self, news_db):
        from app.services.news.summary_service import (
            MAX_SUMMARY_CHARS,
            NewsSummaryService,
        )

        article = _make_article(news_db)
        ctx, _ = _patch_provider("长" * 200)
        with ctx:
            result = NewsSummaryService(news_db).summarize(article.id)

        assert result["skipped"] is False
        assert len(result["summary"]) <= MAX_SUMMARY_CHARS
        assert result["summary"].endswith("…")
        news_db.refresh(article)
        assert article.summary_zh == result["summary"]

    def test_empty_body_skipped_without_llm(self, news_db):
        from app.services.news.summary_service import NewsSummaryService

        article = _make_article(news_db, body=None)
        article.summary = None
        article.full_content = None
        news_db.commit()

        ctx, fake_provider = _patch_provider()
        with ctx:
            result = NewsSummaryService(news_db).summarize(article.id)

        assert result["skipped"] is True
        assert result["reason"] == "no_body"
        assert fake_provider.chat.call_count == 0
        news_db.refresh(article)
        assert article.summary_zh is None

    def test_cached_row_skipped_without_llm(self, news_db):
        from app.services.news.summary_service import NewsSummaryService

        article = _make_article(news_db)
        article.summary_zh = "已有摘要"
        news_db.commit()

        ctx, fake_provider = _patch_provider("不应被调用")
        with ctx:
            result = NewsSummaryService(news_db).summarize(article.id)

        assert result["skipped"] is True
        assert result["reason"] == "cached"
        assert fake_provider.chat.call_count == 0

    def test_prompt_contains_quality_constraints(self, news_db):
        from app.services.news.summary_service import NewsSummaryService

        article = _make_article(news_db)
        ctx, fake_provider = _patch_provider()
        with ctx:
            NewsSummaryService(news_db).summarize(article.id)

        system = fake_provider.chat.call_args.kwargs["system"]
        assert "80" in system
        assert "不复述标题" in system or "不要复述标题" in system
        assert "评价性词汇" in system
        # Title + body are both fed to the model.
        user = fake_provider.chat.call_args.kwargs["messages"][0]["content"]
        assert article.title in user
        assert "降息25个基点" in user

    def test_provider_unavailable_skips(self, news_db):
        from app.services.news.summary_service import NewsSummaryService

        article = _make_article(news_db)
        with patch(
            "app.services.llm.get_llm_provider",
            return_value=_UnavailableProvider(),
        ):
            result = NewsSummaryService(news_db).summarize(article.id)

        assert result["skipped"] is True
        assert result["reason"] == "provider_unavailable"
        news_db.refresh(article)
        assert article.summary_zh is None

    def test_think_tags_stripped(self, news_db):
        from app.services.news.summary_service import NewsSummaryService

        article = _make_article(news_db)
        ctx, _ = _patch_provider("<think>reasoning…</think>一句话摘要")
        with ctx:
            result = NewsSummaryService(news_db).summarize(article.id)

        assert result["summary"] == "一句话摘要"
        news_db.refresh(article)
        assert article.summary_zh == "一句话摘要"

    def test_llm_failure_leaves_row_untouched(self, news_db):
        from app.services.news.summary_service import NewsSummaryService

        article = _make_article(news_db)
        ctx, fake_provider = _patch_provider()
        fake_provider.chat.side_effect = RuntimeError("boom")
        with ctx:
            result = NewsSummaryService(news_db).summarize(article.id)

        assert result["skipped"] is True
        assert result["reason"] == "llm_failed"
        news_db.refresh(article)
        assert article.summary_zh is None


# ---------------------------------------------------------------------------
# Drain job tests
# ---------------------------------------------------------------------------


class TestSummarizeDrain:
    def _run_drain(self, news_db, provider):
        """Run the drain with ``SessionLocal`` patched to the test session.

        The drain job calls ``db.close()``; wrap the session so close is
        a no-op and the fixture's instances stay attached for asserts.
        """
        from app.services.news import scheduler_summarize_news as ssn

        wrapper = MagicMock(wraps=news_db)
        wrapper.close = lambda: None
        with (
            patch("app.core.database.SessionLocal", return_value=wrapper),
            patch("app.services.llm.get_llm_provider", return_value=provider),
        ):
            return ssn.run_summarize_pending(batch_size=10)

    def test_summarizes_pending_important_articles(self, news_db):
        article = _make_article(news_db, importance=4)
        fake_provider = MagicMock()
        fake_provider.is_available = True
        fake_provider.chat.return_value = "一句话中文摘要"

        result = self._run_drain(news_db, fake_provider)

        assert result["fetched"] == 1
        assert result["written"] == 1
        news_db.refresh(article)
        assert article.summary_zh == "一句话中文摘要"

    def test_importance_gate_excludes_low_importance(self, news_db):
        low = _make_article(news_db, importance=2, source_id="low")
        unrated = _make_article(news_db, source_id="unrated")
        unrated.importance = None
        news_db.commit()

        fake_provider = MagicMock()
        fake_provider.is_available = True
        fake_provider.chat.return_value = "摘要"

        result = self._run_drain(news_db, fake_provider)

        assert result["fetched"] == 0
        assert result["written"] == 0
        news_db.refresh(low)
        news_db.refresh(unrated)
        assert low.summary_zh is None
        assert unrated.summary_zh is None
        assert fake_provider.chat.call_count == 0

    def test_already_summarized_rows_not_refetched(self, news_db):
        done = _make_article(news_db, importance=5, source_id="done")
        done.summary_zh = "已有摘要"
        news_db.commit()

        fake_provider = MagicMock()
        fake_provider.is_available = True
        fake_provider.chat.return_value = "新摘要"

        result = self._run_drain(news_db, fake_provider)

        assert result["fetched"] == 0
        assert fake_provider.chat.call_count == 0
        news_db.refresh(done)
        assert done.summary_zh == "已有摘要"

    def test_provider_unavailable_records_skipped_run(self, news_db):
        article = _make_article(news_db, importance=5)

        result = self._run_drain(news_db, _UnavailableProvider())

        assert result["written"] == 0
        assert result["reason"] == "provider_unavailable"
        news_db.refresh(article)
        assert article.summary_zh is None


# ---------------------------------------------------------------------------
# API serialization tests
# ---------------------------------------------------------------------------


class TestSummarySerialization:
    def test_list_includes_summary_zh(self, api_client, news_db):
        article = _make_article(news_db)
        article.summary_zh = "列表摘要"
        news_db.commit()

        resp = api_client.get("/api/v1/news")
        assert resp.status_code == 200, resp.text
        items = resp.json()["items"]
        match = [i for i in items if i["id"] == article.id]
        assert match and match[0]["summary_zh"] == "列表摘要"

    def test_detail_includes_summary_zh(self, api_client, news_db):
        article = _make_article(news_db)
        article.summary_zh = "详情摘要"
        news_db.commit()

        resp = api_client.get(f"/api/v1/news/{article.id}")
        assert resp.status_code == 200, resp.text
        assert resp.json()["summary_zh"] == "详情摘要"

    def test_summary_zh_null_when_unsummarized(self, api_client, news_db):
        article = _make_article(news_db)

        resp = api_client.get(f"/api/v1/news/{article.id}")
        assert resp.status_code == 200
        assert resp.json()["summary_zh"] is None
