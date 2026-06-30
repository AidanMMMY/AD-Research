"""Xueqiu-specific ORM tables.

The raw posts themselves are stored in the (Agent-B-owned) ``news_article``
table once it lands — the engagement / symbol metadata fits into its
``engagement`` JSONB + ``extra`` columns. This file only declares:

* ``XueqiuUserCache`` — cached user-profile snapshots (7-day TTL).
* ``XueqiuFetchState`` — per-symbol incremental-cursor state so we can
  resume timeline fetches without re-downloading pages.
"""

from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, Column, DateTime, Integer, String, Text, func

from app.core.database import Base


class XueqiuUserCache(Base):
    """Cached Xueqiu user profile.

    Refreshed on first sight and again only after ``fetched_at`` is older
    than the cache TTL (7 days by default in the scheduler).
    """

    __tablename__ = "xueqiu_user_cache"

    user_id = Column(BigInteger, primary_key=True, comment="Xueqiu user id")
    screen_name = Column(String(100), comment="Display name (snowflake)")
    followers_count = Column(Integer, comment="Followers count")
    friends_count = Column(Integer, comment="Followed accounts")
    status_count = Column(Integer, comment="Number of posts authored")
    description = Column(Text, comment="Profile bio / signature")
    verified = Column(Boolean, default=False, comment="Verified-account flag")
    fetched_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        comment="Last refresh time (UTC)",
    )


class XueqiuFetchState(Base):
    """Per-symbol incremental-cursor state for the timeline fetcher.

    ``last_max_id`` is the smallest post id observed in the previous
    successful page — Xueqiu returns posts in descending-id order, so a
    page where the smallest id is ``N`` means ``max_id=-1`` (next call)
    can be replaced with ``max_id=N`` to skip duplicates. We store the
    *latest* (newest) id actually written as well so a full restart
    picks up cleanly.
    """

    __tablename__ = "xueqiu_fetch_state"

    symbol = Column(String(50), primary_key=True, comment="Internal symbol (e.g. 600519.SH)")
    last_max_id = Column(BigInteger, comment="Oldest id seen in the last page (next-page cursor)")
    last_newest_id = Column(BigInteger, comment="Newest post id successfully written")
    last_fetched_at = Column(DateTime(timezone=True), comment="When the last fetch completed")
    next_fetch_at = Column(
        DateTime(timezone=True),
        comment="Earliest time the next fetch is allowed (throttling)",
    )
    last_status = Column(String(50), default="ok", comment="ok / error / skipped / auth_failed")
    last_error = Column(Text, comment="Last error message (cleared on success)")
    fetch_count = Column(Integer, default=0, comment="Number of successful fetches")
