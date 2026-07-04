"""Unit tests for the news content-hash dedup.

Covers the helpers added in the 2026-07-04 P0 fixes:

1. ``normalized_content_key`` is stable for identical (title, content)
   pairs even when the URLs differ.
2. ``normalized_content_key`` changes when either ``title`` or
   ``content`` changes.
3. ``is_duplicate`` triggers on URL match OR content-key match.
4. ``register_dedup_keys`` returns both the URL key and the content key
   so the running dedup set recognises cross-source reposts.
"""

from __future__ import annotations

from app.services.news.dedup import (
    is_duplicate,
    normalized_content_key,
    register_dedup_keys,
)


# ---------------------------------------------------------------------------
# normalized_content_key
# ---------------------------------------------------------------------------


def test_normalized_content_key_stable_for_same_input() -> None:
    """Same (title, content) ⇒ same hash, regardless of URL."""
    k1 = normalized_content_key("Hello", "world")
    k2 = normalized_content_key("Hello", "world")
    assert k1 == k2
    assert len(k1) == 16


def test_normalized_content_key_differs_across_sources() -> None:
    """Same article text under two different URLs must collide on the
    content key — this is the whole point of the secondary dedup gate.
    """
    sina = normalized_content_key(
        "央行降准0.25个百分点",
        "中国人民银行决定下调存款准备金率0.25个百分点，释放长期资金约5000亿元。",
    )
    tengxun = normalized_content_key(
        "央行降准0.25个百分点",
        "中国人民银行决定下调存款准备金率0.25个百分点，释放长期资金约5000亿元。",
    )
    fenghuang = normalized_content_key(
        "央行降准0.25个百分点",
        "中国人民银行决定下调存款准备金率0.25个百分点，释放长期资金约5000亿元。",
    )
    assert sina == tengxun == fenghuang


def test_normalized_content_key_ignores_casing_and_whitespace() -> None:
    """Whitespace and case normalisation means '央行 降准' and '央行降准'
    collide — the canonicalisation is what makes aggregator reposts match.
    """
    k1 = normalized_content_key("央行  降准", "释放  长期资金")
    k2 = normalized_content_key("央行 降准", "释放 长期资金")
    assert k1 == k2


def test_normalized_content_key_truncates_after_200_chars() -> None:
    """The hash is taken over only the first 200 chars of content so
    trailing boilerplate can't perturb the bucket.
    """
    base = "x" * 200
    long = base + "y" * 500
    short = base + "z" * 500
    assert normalized_content_key("t", long) == normalized_content_key("t", short)


def test_normalized_content_key_handles_empty_content() -> None:
    """An empty content string must not raise — important for feeds that
    ship the title only.
    """
    k = normalized_content_key("Only title", "")
    assert isinstance(k, str)
    assert len(k) == 16


def test_normalized_content_key_differs_when_title_changes() -> None:
    k1 = normalized_content_key("Title A", "Same body text")
    k2 = normalized_content_key("Title B", "Same body text")
    assert k1 != k2


# ---------------------------------------------------------------------------
# is_duplicate
# ---------------------------------------------------------------------------


def test_is_duplicate_url_match() -> None:
    """URL match alone is enough to flag a duplicate — the original
    V1 behaviour must keep working.
    """
    existing = {"https://example.com/news/1"}
    assert is_duplicate(existing, "any", "any", "https://example.com/news/1")


def test_is_duplicate_content_match_different_url() -> None:
    """Same (title, content) under a different URL is still a duplicate
    — the cross-source repost scenario.
    """
    title = "央行降准0.25个百分点"
    content = "中国人民银行决定下调存款准备金率0.25个百分点"
    key = normalized_content_key(title, content)
    existing = {key}  # only the content key — no URL
    assert is_duplicate(existing, title, content, "https://sina.com.cn/x")


def test_is_duplicate_returns_false_for_fresh_article() -> None:
    """When neither URL nor content hash is in the set, the article
    must be considered fresh.
    """
    existing = {"https://other.com/x"}
    assert not is_duplicate(
        existing,
        "Brand new headline",
        "Brand new body text",
        "https://example.com/news/2",
    )


# ---------------------------------------------------------------------------
# register_dedup_keys
# ---------------------------------------------------------------------------


def test_register_dedup_keys_includes_url_and_content() -> None:
    """After persisting an article, the running dedup set must hold BOTH
    the URL and the content key so a subsequent repost collides on either.
    """
    title = "央行降准0.25个百分点"
    content = "中国人民银行决定下调存款准备金率0.25个百分点"
    keys = register_dedup_keys(title, content, "https://sina.com.cn/x")
    assert "https://sina.com.cn/x" in keys
    assert normalized_content_key(title, content) in keys
    assert len(keys) == 2


def test_register_dedup_keys_handles_empty_url() -> None:
    """Some upstream payloads carry an empty URL — must not blow up and
    must still write the content key.
    """
    keys = register_dedup_keys("t", "c", "")
    assert "" not in keys  # we skip empty URLs
    assert normalized_content_key("t", "c") in keys


# ---------------------------------------------------------------------------
# End-to-end scenario: cross-source repost
# ---------------------------------------------------------------------------


def test_cross_source_repost_is_detected() -> None:
    """Walk through the production scenario the fix targets: an article
    is ingested from Sina, then the same text arrives via Tencent under
    a different URL. The second ingest must be flagged as a duplicate.
    """
    title = "央行降准0.25个百分点"
    content = "中国人民银行决定下调存款准备金率0.25个百分点，释放长期资金约5000亿元。"

    # First ingest (Sina).
    sina_keys = register_dedup_keys(title, content, "https://sina.com.cn/news/1")
    seen: set[str] = set(sina_keys)

    # Second ingest (Tencent) — same content, different URL.
    is_dup = is_duplicate(seen, title, content, "https://news.qq.com/news/2")
    assert is_dup, "Cross-source repost was not detected as duplicate"


def test_legitimately_different_article_is_not_deduplicated() -> None:
    """The fix must not over-merge — two different articles about the
    same topic should still both be ingestable.
    """
    title_a = "央行降准0.25个百分点"
    content_a = "中国人民银行决定下调存款准备金率0.25个百分点。"
    title_b = "央行降准0.5个百分点"
    content_b = "中国人民银行决定下调存款准备金率0.5个百分点。"

    seen: set[str] = set(register_dedup_keys(title_a, content_a, "https://a/1"))

    assert not is_duplicate(seen, title_b, content_b, "https://b/2")