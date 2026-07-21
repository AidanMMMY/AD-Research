"""Tests for the ingestion-time full-content hook (2026-07-21).

``scheduler_jobs._write_to_db`` (and the Xueqiu persist closure) call
:func:`fetch_full_content_for_ids` right after new rows are committed so
the detail page has a cleaned body immediately. The hook must be
fail-safe, bounded by a time budget, and honour the
``news_content_fetch_on_ingest`` settings toggle.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.services.news import scheduler_fetch_full_content as sffc
from app.services.news._model_loader import load_news_models
from app.services.news.content_fetcher import FetchResult
from app.services.news.crawler.types import RawArticle
from app.services.news.normalizer import NewsNormalizer

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
    session_local = sessionmaker(bind=engine)
    session = session_local()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def seeded_article(db_session):
    """A row with a short blurb so ``full_content`` stays ``None``."""
    normalizer = NewsNormalizer(db_session)
    raw = RawArticle(
        source="xinhua_rss",
        url="https://example.com/articles/ingest",
        title="Ingest hook article",
        published_at=datetime.now(tz=UTC),
        body="A short blurb.",
    )
    article = normalizer.normalize(raw)
    db_session.commit()
    assert article is not None and article.full_content is None
    return article


def _settings(fetch_on_ingest: bool = True, budget: int = 120) -> SimpleNamespace:
    return SimpleNamespace(
        news_content_fetch_on_ingest=fetch_on_ingest,
        news_content_ingest_time_budget_sec=budget,
    )


def test_hook_disabled_by_settings(db_session, seeded_article) -> None:
    with (
        patch("app.config.get_settings", return_value=_settings(False)),
        patch("app.services.news.content_fetcher.ContentFetcher") as fetcher_cls,
    ):
        stats = sffc.fetch_full_content_for_ids([seeded_article.id])
    assert stats["processed"] == 0
    fetcher_cls.assert_not_called()


def test_hook_zero_time_budget_is_noop(db_session, seeded_article) -> None:
    with (
        patch("app.config.get_settings", return_value=_settings()),
        patch("app.services.news.content_fetcher.ContentFetcher") as fetcher_cls,
    ):
        stats = sffc.fetch_full_content_for_ids([seeded_article.id], time_budget_sec=0)
    assert stats["processed"] == 0
    fetcher_cls.assert_not_called()


def test_hook_fetches_missing_full_content(db_session, seeded_article) -> None:
    fake_result = FetchResult(
        success=True, content="body", cached=False, ai_cleanup_status="cleaned"
    )
    with (
        patch("app.config.get_settings", return_value=_settings()),
        patch.object(sffc, "SessionLocal", return_value=db_session),
        patch("app.services.news.content_fetcher.ContentFetcher") as fetcher_cls,
    ):
        fetcher_cls.return_value.fetch.return_value = fake_result
        stats = sffc.fetch_full_content_for_ids([seeded_article.id], time_budget_sec=60)

    assert stats["processed"] == 1
    assert stats["success"] == 1
    assert stats["ai_cleaned"] == 1
    fetcher_cls.return_value.fetch.assert_called_once_with(seeded_article.id, force=True)


def test_hook_swallows_unexpected_errors(db_session, seeded_article) -> None:
    """A broken fetcher must never break the crawl tick."""
    with (
        patch("app.config.get_settings", return_value=_settings()),
        patch.object(sffc, "SessionLocal", return_value=db_session),
        patch("app.services.news.content_fetcher.ContentFetcher") as fetcher_cls,
    ):
        fetcher_cls.return_value.fetch.side_effect = RuntimeError("boom")
        stats = sffc.fetch_full_content_for_ids([seeded_article.id], time_budget_sec=60)
    assert stats["processed"] == 1
    assert stats["failed"] == 1


def test_write_to_db_triggers_ingest_fetch(db_session) -> None:
    """``_write_to_db`` passes only the newly-written ids to the hook."""
    from app.services.news import scheduler_jobs

    raw_new = RawArticle(
        source="sina",
        url="https://example.com/articles/new-1",
        title="Brand new article",
        published_at=datetime.now(tz=UTC),
        body="short",
    )
    # Pre-seed a duplicate so we can prove only new ids are passed.
    normalizer = NewsNormalizer(db_session)
    dup_raw = RawArticle(
        source="sina",
        url="https://example.com/articles/dup-1",
        title="Duplicate article",
        published_at=datetime.now(tz=UTC),
        body="short",
    )
    assert normalizer.normalize(dup_raw) is not None
    db_session.commit()

    with (
        patch("app.core.database.SessionLocal", return_value=db_session),
        patch(
            "app.services.news.scheduler_fetch_full_content" ".fetch_full_content_for_ids"
        ) as hook,
    ):
        written = scheduler_jobs._write_to_db([raw_new, dup_raw])

    assert written == 1
    hook.assert_called_once()
    ids = hook.call_args.args[0]
    assert len(ids) == 1
    assert isinstance(ids[0], int)
