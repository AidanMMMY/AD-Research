"""News dedup helpers.

Provides the content-based dedup key used to catch republished articles
that share the same (title + leading body) under different URLs — the
most common pattern being cross-source forwarding (Sina / Phoenix /
Tencent picking up a single primary-source story and rewriting the URL).

The original URL-based dedup in :mod:`app.services.news.normalizer` and
:mod:`app.services.sentiment_service` is **kept as a first-class key**;
the helpers below only add the secondary content key so a hit on either
side is sufficient to mark the article as a duplicate.

The hash intentionally uses only ``title + content[:200]`` — that
captures the headline + first paragraph (which is what aggregators
typically rewrite first), while ignoring trailing boilerplate that
ads and embed codes can perturb. ``hashlib.md5`` is fine here: this is
not a security primitive, just a 16-char bucket key.
"""

from __future__ import annotations

import hashlib


def normalized_content_key(title: str, content: str) -> str:
    """Return a 16-char content-based dedup bucket for an article.

    Args:
        title: Article headline (any case).
        content: Article body / summary. Only the first 200 chars are
            fed into the hash.

    Returns:
        16-char hex digest suitable for use as a set member.
    """
    norm = " ".join((title + " " + (content or "")[:200]).lower().split())
    return hashlib.md5(norm.encode("utf-8", errors="ignore")).hexdigest()[:16]


def is_duplicate(
    existing_keys: set[str],
    title: str,
    content: str,
    url: str,
) -> bool:
    """Return True if either the URL key or the content key is in the set.

    Args:
        existing_keys: A set that holds both URL keys and content keys
            populated from prior ingestion calls. The caller is
            responsible for keeping both key flavors in the set when
            adding a new article — see :func:`register_dedup_keys`.
        title: New article headline.
        content: New article body / summary.
        url: New article canonical URL.
    """
    if url and url in existing_keys:
        return True
    if normalized_content_key(title, content) in existing_keys:
        return True
    return False


def register_dedup_keys(title: str, content: str, url: str) -> set[str]:
    """Return the set of dedup keys that should be stored for an article.

    Callers should add the result to their running ``existing_keys`` set
    after a successful insert. Both the URL and the content hash are
    included so a later article hitting either side is recognised as a
    duplicate.
    """
    keys: set[str] = set()
    if url:
        keys.add(url)
    keys.add(normalized_content_key(title, content))
    return keys