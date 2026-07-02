"""Unit tests for :mod:`app.services.news.content_fetcher`.

We exercise the three interesting branches:

1. **Empty / missing rows** — return ``success=False`` without ever
   calling Jina.
2. **Fresh cache hit** — the stored body is recent enough that we
   must not re-fetch.
3. **Cache miss + successful Jina** — we record the body and the
   ``full_content_fetched_at`` timestamp.
4. **Cache miss + Jina failure** — we bubble a structured ``error``
   and leave the row untouched (Jina errors are not persisted as
   content).

We stub :func:`httpx.get` rather than running a real server.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.services.news._model_loader import (
    NewsArticle,
    NewsArticleSymbol,
    load_news_models,
)
from app.services.news.content_fetcher import (
    CACHE_TTL,
    JINA_READER_URL,
    ContentFetcher,
)
from app.services.news.normalizer import NewsNormalizer
from app.services.news.crawler.types import RawArticle


# Force the model loader to materialise now so we can use ``NewsArticle``
# against an in-memory SQLite schema.
load_news_models()


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
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def seeded_article(db_session):
    normalizer = NewsNormalizer(db_session)
    raw = RawArticle(
        source="xinhua_rss",
        url="https://example.com/articles/abc",
        title="Headline",
        published_at=datetime.now(tz=timezone.utc),
        body="A short blurb.",
    )
    article = normalizer.normalize(raw)
    db_session.commit()
    assert article is not None and article.id is not None
    return article


def _fake_response(text: str, status_code: int = 200) -> SimpleNamespace:
    return SimpleNamespace(status_code=status_code, text=text)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_fetch_missing_article(db_session) -> None:
    fetcher = ContentFetcher(db_session)
    result = fetcher.fetch(999_999)
    assert result.success is False
    assert result.cached is False
    assert "not found" in (result.error or "")


def test_fetch_empty_url(db_session, seeded_article) -> None:
    seeded_article.url = ""
    result = ContentFetcher(db_session).fetch(seeded_article.id)
    assert result.success is False
    assert "no url" in (result.error or "")


def test_fetch_uses_fresh_cache(db_session, seeded_article) -> None:
    body = "Fully cached body that should not trigger a network call."
    seeded_article.full_content = body
    seeded_article.full_content_fetched_at = datetime.now(tz=timezone.utc)
    db_session.commit()

    with patch(
        "app.services.news.content_fetcher.httpx.get"
    ) as mocked_get:
        result = ContentFetcher(db_session).fetch(seeded_article.id)

    assert result.success is True
    assert result.cached is True
    assert result.content == body
    mocked_get.assert_not_called()


def test_fetch_stale_cache_triggers_request(db_session, seeded_article) -> None:
    seeded_article.full_content = "old content"
    seeded_article.full_content_fetched_at = (
        datetime.now(tz=timezone.utc) - CACHE_TTL - timedelta(minutes=5)
    )
    db_session.commit()

    fake_md = "# fresh markdown\n\nHello world"
    with patch(
        "app.services.news.content_fetcher.httpx.get",
        return_value=_fake_response(fake_md),
    ) as mocked_get:
        result = ContentFetcher(db_session).fetch(seeded_article.id)

    assert result.success is True
    assert result.cached is False
    assert result.content == fake_md
    mocked_get.assert_called_once()
    expected_url = f"{JINA_READER_URL}/{seeded_article.url}"
    assert mocked_get.call_args.args[0] == expected_url

    # Persisted to DB
    db_session.refresh(seeded_article)
    assert seeded_article.full_content == fake_md
    assert seeded_article.full_content_fetched_at is not None


def test_fetch_truncates_oversized_body(db_session, seeded_article) -> None:
    from app.services.news.content_fetcher import MAX_CONTENT_CHARS

    huge = "x" * (MAX_CONTENT_CHARS + 500)
    with patch(
        "app.services.news.content_fetcher.httpx.get",
        return_value=_fake_response(huge),
    ):
        result = ContentFetcher(db_session).fetch(seeded_article.id)

    assert result.success is True
    assert result.content is not None
    # Truncation marker at the bottom adds a few more chars.
    assert len(result.content) <= MAX_CONTENT_CHARS + 80
    assert "已截断" in result.content


def test_fetch_handles_jina_http_error(db_session, seeded_article) -> None:
    with patch(
        "app.services.news.content_fetcher.httpx.get",
        return_value=_fake_response("rate limited", status_code=429),
    ):
        result = ContentFetcher(db_session).fetch(seeded_article.id)

    assert result.success is False
    assert result.cached is False
    assert "429" in (result.error or "")
    # Row untouched
    db_session.refresh(seeded_article)
    assert seeded_article.full_content is None


def test_fetch_handles_network_timeout(db_session, seeded_article) -> None:
    import httpx

    with patch(
        "app.services.news.content_fetcher.httpx.get",
        side_effect=httpx.TimeoutException("boom"),
    ):
        result = ContentFetcher(db_session).fetch(seeded_article.id)

    assert result.success is False
    assert "timeout" in (result.error or "").lower()


def test_force_flag_bypasses_cache(db_session, seeded_article) -> None:
    seeded_article.full_content = "fresh enough"
    seeded_article.full_content_fetched_at = datetime.now(tz=timezone.utc)
    db_session.commit()

    with patch(
        "app.services.news.content_fetcher.httpx.get",
        return_value=_fake_response("# re-fetched"),
    ):
        result = ContentFetcher(db_session).fetch(seeded_article.id, force=True)

    assert result.success is True
    assert result.cached is False
    assert result.content == "# re-fetched"


def test_invalidate_clears_cache(db_session, seeded_article) -> None:
    seeded_article.full_content = "old"
    seeded_article.full_content_fetched_at = datetime.now(tz=timezone.utc)
    db_session.commit()

    ok = ContentFetcher(db_session).invalidate(seeded_article.id)
    assert ok is True
    db_session.refresh(seeded_article)
    assert seeded_article.full_content is None
    assert seeded_article.full_content_fetched_at is None


# ---------------------------------------------------------------------------
# Endpoint smoke
# ---------------------------------------------------------------------------

@pytest.fixture
def fastapi_client(db_session, seeded_article):
    """Mount the news router with auth + DB overridden so we can hit
    ``POST /news/{id}/fetch-content`` without spinning up Postgres.
    """
    from fastapi import FastAPI
    from app.api.v1 import news as news_module
    from app.api import deps

    # Auth override → return a dummy user.
    def _fake_user():
        return SimpleNamespace(username="tester")

    # DB override → return our in-memory session.
    def _get_db():
        try:
            yield db_session
        finally:
            pass

    app_root = FastAPI()
    # Some news routes use the literal "" path, which FastAPI rejects
    # at include_router time when the router prefix is also "". Mount
    # the router under a non-empty prefix instead.
    app_root.include_router(news_module.router, prefix="/news")

    app_root.dependency_overrides[deps.get_current_user] = _fake_user
    app_root.dependency_overrides[deps.get_db] = _get_db

    with TestClient(app_root) as client:
        yield client


def test_fetch_endpoint_success(fastapi_client, seeded_article) -> None:
    fake_md = "# hello\n\nmarkdown body"
    with patch(
        "app.services.news.content_fetcher.httpx.get",
        return_value=_fake_response(fake_md),
    ):
        resp = fastapi_client.post(
            f"/news/{seeded_article.id}/fetch-content"
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is True
    assert body["cached"] is False
    assert body["content"] == fake_md


def test_fetch_endpoint_missing_article(fastapi_client) -> None:
    resp = fastapi_client.post("/news/424242/fetch-content")
    assert resp.status_code == 404
