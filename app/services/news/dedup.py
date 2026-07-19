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
import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from simhash import Simhash, SimhashIndex
from sqlalchemy import select

from app.services.news._model_loader import NewsArticle

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


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
    return (bool(url) and url in existing_keys) or normalized_content_key(
        title, content
    ) in existing_keys


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


# ---------------------------------------------------------------------------
# 64-bit simhash near-duplicate detection
# ---------------------------------------------------------------------------


def _load_simhash_rows(
    db: Session,
    sources: list[str] | None = None,
    days: int = 7,
    limit: int = 5000,
) -> list[tuple[int, str, datetime]]:
    """Fetch articles with a content hash for near-dup comparison.

    Returns rows as ``(id, content_hash, published_at)``.  Articles are
    filtered to the last ``days`` days and optionally to a set of sources.
    The result is capped by ``limit`` and ordered by ``published_at`` desc
    so newer articles are prioritised when the cap is hit.
    """
    cutoff = datetime.utcnow() - timedelta(days=days)
    stmt = (
        select(NewsArticle.id, NewsArticle.content_hash, NewsArticle.published_at)
        .where(NewsArticle.content_hash.isnot(None))
        .where(NewsArticle.published_at >= cutoff)
        .order_by(NewsArticle.published_at.desc())
        .limit(limit)
    )
    if sources:
        stmt = stmt.where(NewsArticle.source.in_(sources))
    return [(row.id, row.content_hash, row.published_at) for row in db.execute(stmt).all()]


def _build_simhash_index(
    rows: list[tuple[int, str, datetime]], threshold_bits: int
) -> SimhashIndex:
    """Build a :class:`SimhashIndex` from decimal content_hash strings."""
    index = SimhashIndex()
    for article_id, content_hash, _published_at in rows:
        try:
            sh = Simhash(value=int(content_hash), f=64)
        except (TypeError, ValueError) as exc:
            logger.warning("simhash parse failed for article %s: %s", article_id, exc)
            continue
        # ``SimhashIndex.add`` accepts a (key, simhash) tuple.
        index.add(str(article_id), sh)
    return index


def find_near_duplicates(
    db: Session,
    threshold_bits: int = 3,
    sources: list[str] | None = None,
    limit: int = 5000,
    days: int = 7,
) -> list[tuple[int, int, int]]:
    """Find near-duplicate article pairs using 64-bit simhash.

    Args:
        db: SQLAlchemy session.
        threshold_bits: Maximum Hamming distance to consider a duplicate.
        sources: Optional list of ``news_article.source`` values to restrict.
        limit: Maximum number of recent articles to load into memory.
        days: Look-back window for ``published_at``.

    Returns:
        A list of ``(article_id_a, article_id_b, distance)`` tuples where
        ``a < b`` and distance is the Hamming distance between the two
        content hashes.  The list is sorted by distance ascending.
    """
    rows = _load_simhash_rows(db, sources=sources, days=days, limit=limit)
    if len(rows) < 2:
        return []

    hash_by_id: dict[int, str] = {}
    simhash_by_id: dict[int, Simhash] = {}
    for article_id, content_hash, _published_at in rows:
        try:
            sh = Simhash(value=int(content_hash), f=64)
        except (TypeError, ValueError) as exc:
            logger.warning("simhash parse failed for article %s: %s", article_id, exc)
            continue
        hash_by_id[article_id] = content_hash
        simhash_by_id[article_id] = sh

    index = SimhashIndex([], k=threshold_bits)
    for article_id, sh in simhash_by_id.items():
        index.add(str(article_id), sh)

    pairs: set[tuple[int, int]] = set()
    results: list[tuple[int, int, int]] = []

    for article_id, sh in simhash_by_id.items():
        near_key_strs = index.get_near_dups(sh)
        for key_str in near_key_strs:
            other_id = int(key_str)
            if other_id <= article_id:
                continue
            other_sh = simhash_by_id.get(other_id)
            if other_sh is None:
                continue
            distance = sh.distance(other_sh)
            if distance <= threshold_bits and (article_id, other_id) not in pairs:
                pairs.add((article_id, other_id))
                results.append((article_id, other_id, distance))

    results.sort(key=lambda x: x[2])
    return results


def mark_duplicates(
    db: Session,
    pairs: list[tuple[int, int, int]],
) -> int:
    """Mark the newer article of each pair as ``duplicate_of`` the older.

    Only writes when the candidate's ``duplicate_of`` is currently ``NULL``
    so already-resolved chains are not overwritten.

    Returns:
        Number of rows actually updated.
    """
    if not pairs:
        return 0

    involved_ids = {aid for aid, bid, _ in pairs} | {bid for aid, bid, _ in pairs}
    rows = (
        db.query(NewsArticle.id, NewsArticle.published_at, NewsArticle.duplicate_of)
        .filter(NewsArticle.id.in_(involved_ids))
        .all()
    )
    meta: dict[int, tuple[datetime | None, int | None]] = {
        row.id: (row.published_at, row.duplicate_of) for row in rows
    }

    updated = 0
    for aid, bid, _distance in pairs:
        a_pub, a_dup = meta.get(aid, (None, None))
        b_pub, b_dup = meta.get(bid, (None, None))
        if a_pub is None or b_pub is None:
            continue

        # Point the newer article at the older one.
        if a_pub >= b_pub and a_dup is None:
            target = bid
            candidate_id = aid
        elif b_pub > a_pub and b_dup is None:
            target = aid
            candidate_id = bid
        else:
            continue

        try:
            db.query(NewsArticle).filter(NewsArticle.id == candidate_id).update(
                {"duplicate_of": target},
                synchronize_session=False,
            )
            updated += 1
        except Exception as exc:
            logger.warning("mark_duplicates: failed to update %s: %s", candidate_id, exc)
            db.rollback()

    try:
        db.commit()
    except Exception as exc:
        logger.warning("mark_duplicates: commit failed: %s", exc)
        db.rollback()
        return 0

    return updated
