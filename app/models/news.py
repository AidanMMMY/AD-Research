"""News / social-media ORM models.

Stores raw articles and posts from RSS feeds, SEC filings and Reddit,
plus a normalised many-to-many link to instrument codes. Engagement
metadata (upvotes, comments, ratios) is kept in a JSONB column so
source-specific fields do not require schema changes.

Tables:
  - news_article           : one row per article / post
  - news_article_symbol    : many-to-many ticker link
  - reddit_comment_cache   : optional second-level discussion cache
"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.core.database import Base


# Use JSON type with fallback for SQLite tests.
try:  # pragma: no cover - import-time branch
    from sqlalchemy import JSON  # type: ignore
    _JSON_TYPE = JSON().with_variant(JSONB(), "postgresql")
except Exception:  # pragma: no cover
    from sqlalchemy import JSON  # type: ignore
    _JSON_TYPE = JSON()


class NewsArticle(Base):
    """A news article or social-media post.

    The combination of (source, source_id) is unique, allowing safe
    upserts and de-duplication without a UUID primary key.
    """

    __tablename__ = "news_article"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source = Column(String(50), nullable=False, comment="yahoo_finance | cnbc | sec_edgar | reddit | ...")
    source_id = Column(String(200), nullable=False, comment="Source-native id (guid, sec accession, reddit id)")
    url = Column(String(1000), nullable=False)
    url_hash = Column(String(32), nullable=False, unique=True, index=True, comment="MD5(url) for dedup")
    content_hash = Column(String(32), index=True, comment="simhash for near-duplicate detection")
    title = Column(String(1000), nullable=False)
    summary = Column(Text, comment="Body excerpt or RSS summary")
    body = Column(Text, comment="Full body if available")
    body_html = Column(Text, comment="Raw HTML body for re-parsing")
    full_content = Column(Text, comment="Fetched full body via Jina Reader (cached)")
    full_content_fetched_at = Column(
        DateTime,
        comment="When the Jina Reader fetch last ran (for cache TTL)",
    )
    author = Column(String(200))
    author_followers = Column(Integer, comment="Followers/fans for retail sources (Xueqiu/Reddit)")
    language = Column(String(10), default="en")
    market = Column(String(20), default="US", comment="US / HK / CN / CRYPTO / GLOBAL")
    published_at = Column(DateTime, nullable=False, index=True)
    fetched_at = Column(DateTime, server_default=func.now(), nullable=False)
    # Optional "category" tag (top news, earnings, 8-K, options, DD, ...)
    category = Column(String(100))
    # Engagement / source-specific metrics (score, upvote_ratio, num_comments,
    # subreddit, flair, cik, form, ...). Free-form JSON.
    engagement = Column(_JSON_TYPE, comment="Source-specific engagement JSON")
    # Sentiment placeholder for Agent E. Stays NULL until the LLM pass runs.
    sentiment_score = Column(Integer, comment="-100..100 placeholder for Agent E")
    sentiment_label = Column(String(20), comment="bullish | bearish | neutral")
    sentiment_confidence = Column(Float, comment="0..1 LLM confidence")
    sentiment_drivers = Column(_JSON_TYPE, comment="List of driver keywords from LLM")
    event_category = Column(String(50), comment="earnings|m&a|product|macro|regulation|guidance|analyst|legal|rumor|other")
    importance = Column(SmallInteger, comment="1..5 LLM importance rating")
    sentiment_processed_at = Column(DateTime, comment="When LLM sentiment was filled")
    # Chinese translation cache, filled on demand by the
    # ``/news/{id}/translate`` endpoint. Populated only for English
    # articles (the API enforces ``language == 'en'`` before writing).
    translated_zh = Column(
        Text, comment="DeepSeek-generated Chinese translation of body / full_content"
    )
    translation_generated_at = Column(
        DateTime, comment="When the LLM translation was last produced"
    )

    symbols = relationship(
        "NewsArticleSymbol",
        back_populates="article",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint("source", "source_id", name="uq_news_article_source_id"),
        Index("ix_news_article_source_published", "source", "published_at"),
        Index("ix_news_article_published_desc", published_at.desc()),
    )


class NewsArticleSymbol(Base):
    """Many-to-many link between an article and the instrument(s) it covers.

    ``symbol`` is the internal code (``AAPL.US``, ``TSLA.US``, ...).
    ``match_type`` records whether the ticker was found in the title,
    body, cashtag, subreddit name, etc. — useful for tuning extraction.
    """

    __tablename__ = "news_article_symbol"

    article_id = Column(
        BigInteger,
        ForeignKey("news_article.id", ondelete="CASCADE"),
        primary_key=True,
    )
    symbol = Column(String(20), primary_key=True, comment="Internal code, e.g. AAPL.US")
    match_type = Column(String(30), comment="title | body | cashtag | subreddit")
    confidence = Column(Integer, default=100, comment="0..100 extraction confidence")

    article = relationship("NewsArticle", back_populates="symbols")

    __table_args__ = (
        Index("ix_news_article_symbol_symbol", "symbol"),
    )


class RedditCommentCache(Base):
    """Cache of Reddit comments (second-level discussion)."""

    __tablename__ = "reddit_comment_cache"

    reddit_id = Column(String(20), primary_key=True, comment="Reddit comment id (t1_xxx)")
    parent_id = Column(String(20), index=True, comment="Parent post or comment id")
    subreddit = Column(String(50), index=True)
    author = Column(String(100))
    body = Column(Text)
    score = Column(Integer, default=0)
    controversiality = Column(Integer, default=0)
    created_utc = Column(DateTime)
    fetched_at = Column(DateTime, server_default=func.now(), nullable=False)
