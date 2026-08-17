"""Tests for the fulltext / summary retry caps and daily self-heal (2026-08-17).

Covers the poison-row fix for the full-content and AI-summary drains:

* Failed fetches / summaries increment ``fulltext_attempts`` /
  ``summary_attempts``; successes reset the counter to 0.
* Rows at the cap (``_MAX_FULLTEXT_ATTEMPTS`` / ``_MAX_SUMMARY_ATTEMPTS``)
  are excluded from the drain selection, so poison rows can no longer
  occupy the newest-first batch window forever.
* The daily ``news_attempts_daily_reset`` job zeroes capped rows so a
  transient outage window self-heals without a manual UPDATE (the
  2026-08-02 translation-drain lesson).

Mirrors the fixture/mocking patterns in ``test_content_fetcher.py`` and
``test_summary.py``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.services.news._model_loader import NewsArticle, load_news_models
from app.services.news.content_fetcher import (
    _MAX_FULLTEXT_ATTEMPTS,
    ContentFetcher,
    _JinaError,
)
from app.services.news.summary_service import _MAX_SUMMARY_ATTEMPTS

load_news_models()


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


def _make_article(
    db,
    *,
    source_id: str = "src-1",
    importance: int | None = 4,
    body: str | None = "央行宣布降息25个基点，并同步下调逆回购利率。" * 3,
) -> NewsArticle:
    article = NewsArticle(
        source="test_source",
        source_id=source_id,
        url=f"https://example.com/articles/{source_id}",
        url_hash=f"h-{source_id}",
        title="央行降息25个基点",
        summary="RSS 摘要",
        body=body,
        language="zh",
        market="CN",
        published_at=datetime.now(tz=UTC),
        importance=importance,
    )
    db.add(article)
    db.commit()
    return article


def _close_proof(session):
    """Wrap a test session so ``db.close()`` inside jobs is a no-op."""
    wrapper = MagicMock(wraps=session)
    wrapper.close = lambda: None
    return wrapper


# ---------------------------------------------------------------------------
# Full-content fetch attempts
# ---------------------------------------------------------------------------


class TestFulltextAttempts:
    def test_failed_fetch_increments_attempts(self, db_session) -> None:
        article = _make_article(db_session)
        assert article.fulltext_attempts == 0

        with (
            patch.object(ContentFetcher, "_fetch_html", return_value=None),
            patch.object(
                ContentFetcher, "_call_jina", side_effect=_JinaError("jina down")
            ),
        ):
            result = ContentFetcher(db_session).fetch(article.id, force=True)

        assert result.success is False
        db_session.refresh(article)
        assert article.fulltext_attempts == 1
        assert article.full_content is None

    def test_successful_fetch_resets_attempts(self, db_session) -> None:
        article = _make_article(db_session)
        article.fulltext_attempts = 3
        db_session.commit()

        body = (
            "第一段：央行宣布降息二十五个基点，并同步下调逆回购操作利率，释放流动性。\n\n"
            "第二段：市场分析人士指出，本次操作超出市场预期，债券市场收益率应声下行。\n\n"
            "第三段：后续仍需关注月度中期借贷便利续作情况，以及实体融资需求变化。"
        )
        with (
            patch.object(ContentFetcher, "_fetch_html", return_value=None),
            patch.object(ContentFetcher, "_call_jina", return_value=body),
        ):
            result = ContentFetcher(db_session).fetch(article.id, force=True)

        assert result.success is True
        db_session.refresh(article)
        assert article.fulltext_attempts == 0
        assert article.full_content is not None

    def test_drain_excludes_rows_at_cap(self, db_session) -> None:
        from app.services.news import scheduler_fetch_full_content as sffc

        poison = _make_article(db_session, source_id="poison")
        poison.fulltext_attempts = _MAX_FULLTEXT_ATTEMPTS
        fresh = _make_article(db_session, source_id="fresh")
        db_session.commit()

        fake_result = SimpleNamespace(
            success=True, ai_cleanup_status="cleaned", error=None
        )
        with (
            patch.object(
                sffc, "SessionLocal", return_value=_close_proof(db_session)
            ),
            patch(
                "app.services.news.content_fetcher.ContentFetcher"
            ) as fetcher_cls,
        ):
            fetcher_cls.return_value.fetch.return_value = fake_result
            stats = sffc.run_fetch_full_content()

        assert stats["processed"] == 1
        fetcher_cls.return_value.fetch.assert_called_once_with(
            fresh.id, force=True
        )

    def test_ingest_hook_excludes_rows_at_cap(self, db_session) -> None:
        from app.services.news import scheduler_fetch_full_content as sffc

        poison = _make_article(db_session, source_id="poison-ingest")
        poison.fulltext_attempts = _MAX_FULLTEXT_ATTEMPTS
        db_session.commit()

        settings = SimpleNamespace(
            news_content_fetch_on_ingest=True,
            news_content_ingest_time_budget_sec=120,
        )
        with (
            patch("app.config.get_settings", return_value=settings),
            patch.object(
                sffc, "SessionLocal", return_value=_close_proof(db_session)
            ),
            patch(
                "app.services.news.content_fetcher.ContentFetcher"
            ) as fetcher_cls,
        ):
            stats = sffc.fetch_full_content_for_ids([poison.id])

        assert stats["processed"] == 0
        fetcher_cls.assert_not_called()


# ---------------------------------------------------------------------------
# Summary attempts
# ---------------------------------------------------------------------------


def _patch_provider(text: str | None = "一句话中文摘要"):
    provider = MagicMock()
    provider.is_available = True
    provider.chat.return_value = text
    return patch("app.services.llm.get_llm_provider", return_value=provider), provider


class TestSummaryAttempts:
    def test_llm_failure_increments_attempts(self, db_session) -> None:
        from app.services.news.summary_service import NewsSummaryService

        article = _make_article(db_session)
        ctx, provider = _patch_provider()
        provider.chat.side_effect = RuntimeError("boom")
        with ctx:
            result = NewsSummaryService(db_session).summarize(article.id)

        assert result["reason"] == "llm_failed"
        db_session.refresh(article)
        assert article.summary_attempts == 1
        assert article.summary_zh is None

    def test_no_body_counts_as_failed_attempt(self, db_session) -> None:
        from app.services.news.summary_service import NewsSummaryService

        article = _make_article(db_session, body=None)
        article.summary = None
        article.full_content = None
        db_session.commit()

        ctx, provider = _patch_provider()
        with ctx:
            result = NewsSummaryService(db_session).summarize(article.id)

        assert result["reason"] == "no_body"
        assert provider.chat.call_count == 0
        db_session.refresh(article)
        assert article.summary_attempts == 1

    def test_provider_unavailable_does_not_count(self, db_session) -> None:
        from app.services.news.summary_service import NewsSummaryService

        article = _make_article(db_session)
        provider = MagicMock()
        provider.is_available = False
        with patch("app.services.llm.get_llm_provider", return_value=provider):
            result = NewsSummaryService(db_session).summarize(article.id)

        assert result["reason"] == "provider_unavailable"
        db_session.refresh(article)
        assert article.summary_attempts == 0

    def test_success_resets_attempts(self, db_session) -> None:
        from app.services.news.summary_service import NewsSummaryService

        article = _make_article(db_session)
        article.summary_attempts = 2
        db_session.commit()

        ctx, _ = _patch_provider()
        with ctx:
            result = NewsSummaryService(db_session).summarize(article.id)

        assert result["skipped"] is False
        db_session.refresh(article)
        assert article.summary_attempts == 0
        assert article.summary_zh is not None

    def test_pending_selection_excludes_rows_at_cap(self, db_session) -> None:
        from app.services.news.scheduler_summarize_news import _pending_summary_ids

        poison = _make_article(db_session, source_id="sum-poison")
        poison.summary_attempts = _MAX_SUMMARY_ATTEMPTS
        fresh = _make_article(db_session, source_id="sum-fresh")
        db_session.commit()

        ids = _pending_summary_ids(db_session, 10)
        assert fresh.id in ids
        assert poison.id not in ids


# ---------------------------------------------------------------------------
# Daily self-heal reset
# ---------------------------------------------------------------------------


class TestDailyAttemptsReset:
    def test_reset_zeroes_only_capped_rows(self, db_session) -> None:
        from app.services.news.scheduler_jobs import run_news_attempts_reset_job

        capped = _make_article(db_session, source_id="capped")
        capped.fulltext_attempts = _MAX_FULLTEXT_ATTEMPTS
        capped.summary_attempts = _MAX_SUMMARY_ATTEMPTS + 2
        partial = _make_article(db_session, source_id="partial")
        partial.fulltext_attempts = 2
        partial.summary_attempts = 1
        clean = _make_article(db_session, source_id="clean")
        db_session.commit()

        with patch(
            "app.core.database.SessionLocal",
            return_value=_close_proof(db_session),
        ):
            result = run_news_attempts_reset_job()

        assert result["written"] == 2
        db_session.refresh(capped)
        db_session.refresh(partial)
        db_session.refresh(clean)
        assert capped.fulltext_attempts == 0
        assert capped.summary_attempts == 0
        # Below-cap rows keep their counters — only evicted rows re-enter.
        assert partial.fulltext_attempts == 2
        assert partial.summary_attempts == 1
        assert clean.fulltext_attempts == 0
        assert clean.summary_attempts == 0

    def test_reset_is_noop_when_nothing_capped(self, db_session) -> None:
        from app.services.news.scheduler_jobs import run_news_attempts_reset_job

        _make_article(db_session)
        with patch(
            "app.core.database.SessionLocal",
            return_value=_close_proof(db_session),
        ):
            result = run_news_attempts_reset_job()

        assert result == {"fetched": 0, "written": 0}

    def test_capped_row_reenters_pool_after_reset(self, db_session) -> None:
        """End-to-end: poison row → excluded → daily reset → selectable."""
        from app.services.news.scheduler_jobs import run_news_attempts_reset_job
        from app.services.news.scheduler_summarize_news import _pending_summary_ids

        article = _make_article(db_session, source_id="revive")
        article.summary_attempts = _MAX_SUMMARY_ATTEMPTS
        db_session.commit()
        assert article.id not in _pending_summary_ids(db_session, 10)

        with patch(
            "app.core.database.SessionLocal",
            return_value=_close_proof(db_session),
        ):
            run_news_attempts_reset_job()

        assert article.id in _pending_summary_ids(db_session, 10)
