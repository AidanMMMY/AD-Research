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

from datetime import UTC, datetime, timedelta
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
    load_news_models,
)
from app.services.news.content_fetcher import (
    CACHE_TTL,
    JINA_READER_URL,
    ContentFetcher,
)
from app.services.news.crawler.types import RawArticle
from app.services.news.normalizer import NewsNormalizer

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
        published_at=datetime.now(tz=UTC),
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
    seeded_article.full_content_fetched_at = datetime.now(tz=UTC)
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
        datetime.now(tz=UTC) - CACHE_TTL - timedelta(minutes=5)
    )
    db_session.commit()

    fake_md = (
        "# fresh markdown\n\n"
        "Hello world. This body is intentionally long so the cleaned text "
        "stays above the minimum body-length guard."
    )
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
    seeded_article.full_content_fetched_at = datetime.now(tz=UTC)
    db_session.commit()

    fake_md = (
        "# re-fetched markdown body\n\n"
        "More body content here, padded with enough extra text to clear "
        "the minimum body-length guard after cleanup."
    )
    with patch(
        "app.services.news.content_fetcher.httpx.get",
        return_value=_fake_response(fake_md),
    ):
        result = ContentFetcher(db_session).fetch(seeded_article.id, force=True)

    assert result.success is True
    assert result.cached is False
    assert result.content == fake_md


def test_invalidate_clears_cache(db_session, seeded_article) -> None:
    seeded_article.full_content = "old"
    seeded_article.full_content_fetched_at = datetime.now(tz=UTC)
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

    from app.api import deps
    from app.api.v1 import news as news_module

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
    fake_md = (
        "# hello\n\n"
        "markdown body with enough additional text to pass the minimum "
        "body-length guard once the cleanup has run."
    )
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


# ---------------------------------------------------------------------------
# Deterministic Jina extraction (M22-3 follow-up, 2026-07-11)
# ---------------------------------------------------------------------------
#
# ``ContentFetcher`` no longer asks DeepSeek to extract the article body.
# Instead it parses the structured Jina response, strips the repeated title
# and metadata, and de-duplicates paragraphs. The tests below pin the new
# behaviour so the old ``<think>`` / duplicate-title / no-body regressions
# cannot come back.


def _seed_full_text_article(db_session, body: str = "x" * 200) -> NewsArticle:
    """Create a row without ``full_content`` so the fetcher is forced
    to call Jina and run the deterministic cleanup.
    """
    normalizer = NewsNormalizer(db_session)
    raw = RawArticle(
        source="xinhua_rss",
        url="https://example.com/articles/cleanup",
        title="Cleanup test article",
        published_at=datetime.now(tz=UTC),
        body=body,
    )
    article = normalizer.normalize(raw)
    db_session.commit()
    return article


def _jina_structured(title: str, published: str, markdown: str) -> str:
    return (
        f"Title: {title}\n"
        f"URL Source: https://example.com/articles/abc\n"
        f"Published Time: {published}\n"
        f"Markdown Content:\n"
        f"{markdown}"
    )


def test_fetch_extracts_markdown_content_section(db_session) -> None:
    """Jina's plain-text response contains a ``Markdown Content:`` section."""
    article = _seed_full_text_article(db_session)
    markdown = "\n".join([
        "# Real body",
        "",
        "Paragraph one contains enough text to pass the minimum body-length "
        "threshold after the title and metadata have been stripped.",
        "",
        "Paragraph two is also reasonably long so the cleaned result is "
        "recognised as a real article body.",
    ])
    raw = _jina_structured(article.title, "2026-07-11 15:59", markdown)

    with patch(
        "app.services.news.content_fetcher.httpx.get",
        return_value=_fake_response(raw),
    ):
        result = ContentFetcher(db_session).fetch(article.id, force=True)

    assert result.success is True
    assert result.cached is False
    assert result.ai_cleanup_status == "cleaned"
    assert "Paragraph one" in result.content
    assert "Markdown Content:" not in (result.content or "")
    assert "Title:" not in (result.content or "")


def test_fetch_strips_repeated_title_and_metadata(db_session) -> None:
    """The body should not contain the article title or the date/source line."""
    article = _seed_full_text_article(db_session)
    title = article.title
    markdown = (
        f"\n# {title}\n\n"
        "2026年07月11日 15:59 21世纪经济报道\n\n"
        "真正正文开始。这是一段足够长的正文内容，用来确保清理后的长度可以通过最小阈值检查，"
        "并且仍然包含清晰的中文语义，让测试能够验证正文已经被正确提取。"
        "这里再补充一句，进一步保证清理后的正文长度稳定超过最小正文长度阈值。"
    )
    raw = _jina_structured(title, "2026-07-11 15:59", markdown)

    with patch(
        "app.services.news.content_fetcher.httpx.get",
        return_value=_fake_response(raw),
    ):
        result = ContentFetcher(db_session).fetch(article.id, force=True)

    assert result.success is True
    assert result.ai_cleanup_status == "cleaned"
    assert result.content is not None
    assert title not in result.content
    assert "2026年07月11日" not in result.content
    assert "21世纪经济报道" not in result.content
    assert "真正正文开始" in result.content


def test_fetch_removes_think_tags_from_raw(db_session) -> None:
    """Any residual ``<think>`` block (from an LLM or upstream source) is removed."""
    article = _seed_full_text_article(db_session)
    markdown = (
        "<think> The model is thinking... </think>\n\n"
        "正文内容。"
        "这一段正文故意写得长一点，确保清理后的长度可以通过最小正文长度阈值，"
        "从而完整测出 think 标签过滤之后还能拿到正文。"
        "再补充一句正文，进一步保证清理后的长度稳定超过阈值。"
    )
    raw = _jina_structured(article.title, "2026-07-11", markdown)

    with patch(
        "app.services.news.content_fetcher.httpx.get",
        return_value=_fake_response(raw),
    ):
        result = ContentFetcher(db_session).fetch(article.id, force=True)

    assert result.success is True
    assert result.ai_cleanup_status == "cleaned"
    assert result.content is not None
    assert "<think>" not in result.content
    assert "</think>" not in result.content
    assert "The model is thinking" not in result.content
    assert "正文内容" in result.content


def test_fetch_marks_failed_when_cleaned_body_too_short(db_session) -> None:
    """If Jina only returns the title and date, the cleanup marks failure and the raw title+date is NOT cached."""
    article = _seed_full_text_article(db_session)
    title = article.title
    # This reproduces the user-reported bug: title + date but no real body.
    markdown = f"# {title}\n\n2026年07月11日 15:59 21世纪经济报道\n"
    raw = _jina_structured(title, "2026-07-11 15:59", markdown)

    with patch(
        "app.services.news.content_fetcher.httpx.get",
        return_value=_fake_response(raw),
    ):
        result = ContentFetcher(db_session).fetch(article.id, force=True)

    # The extraction is reported as a failure so the UI does not render
    # the useless title+date as the full content.
    assert result.success is False
    assert result.ai_cleanup_status == "failed"
    assert result.error and "Jina" in result.error
    # The fallback content is the article summary/body, not raw Jina.
    assert result.content is not None
    assert result.content != title  # not just the title repeated

    # The raw title+date is NOT persisted on the row.
    db_session.refresh(article)
    assert article.full_content is None
    assert article.ai_cleanup_status == "failed"
    assert article.ai_cleaned_at is not None


def test_fetch_de_duplicates_repeated_paragraphs(db_session) -> None:
    """Some sites render the same paragraph twice; keep only one copy."""
    article = _seed_full_text_article(db_session)
    para = "这是一段重要的正文内容，不应该重复出现。我们特意把它写长一点，保证清理后的整体长度可以通过最小正文长度阈值。"
    markdown = f"\n{para}\n\n{para}\n\n第二段不同的内容，也需要足够长以避免被误判为无正文。"
    raw = _jina_structured(article.title, "2026-07-11", markdown)

    with patch(
        "app.services.news.content_fetcher.httpx.get",
        return_value=_fake_response(raw),
    ):
        result = ContentFetcher(db_session).fetch(article.id, force=True)

    assert result.success is True
    assert result.ai_cleanup_status == "cleaned"
    assert result.content is not None
    # Should appear only once.
    assert result.content.count("这是一段重要的正文内容") == 1
    assert "第二段不同的内容" in result.content


def test_fetch_article_dict_exposes_ai_cleanup_fields(
    fastapi_client, seeded_article
) -> None:
    """The article detail endpoint must serialise the two new fields
    so the frontend banner can render."""
    resp = fastapi_client.get(f"/news/{seeded_article.id}")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # Both fields are present, both may be ``null`` for an article
    # the scheduler never reached.
    assert "ai_cleaned_at" in body
    assert "ai_cleanup_status" in body
    assert body["ai_cleanup_status"] is None
    assert body["ai_cleaned_at"] is None


def test_health_endpoint_includes_ai_cleanup_24h(fastapi_client) -> None:
    """``GET /news/health`` now carries the ``ai_cleanup_24h`` block."""
    resp = fastapi_client.get("/news/health")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "ai_cleanup_24h" in body
    block = body["ai_cleanup_24h"]
    assert set(block.keys()) == {
        "total",
        "cleaned",
        "skipped",
        "failed",
        "cleaned_pct",
        "alert_threshold_pct",
        "alert",
    }
    # Empty DB → all zeros, no alert.
    assert block["total"] == 0
    assert block["cleaned"] == 0
    assert block["skipped"] == 0
    assert block["failed"] == 0
    assert block["cleaned_pct"] == 0.0
    assert block["alert_threshold_pct"] == 70.0
    assert block["alert"] is False
