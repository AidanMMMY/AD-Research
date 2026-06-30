"""add news_article and news_article_symbol tables

Revision ID: a1b1c2d3e4f5
Revises: 29478c7e0c25
Create Date: 2026-07-01 06:00:00.000000

Adds the master news / sentiment ingestion tables used by the
A-share RSS crawlers (Xinhua, Cninfo, Sina) and future social-media
agents (Reddit, Stocktwits). The companion ``reddit_comment_cache``
table is also added — it is owned by Agent D but lives in the same
migration to keep the news subsystem self-contained.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "a1b1c2d3e4f5"
down_revision: Union[str, Sequence[str], None] = "29478c7e0c25"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _json_type() -> sa.types.TypeEngine:
    """JSON with PostgreSQL JSONB variant; SQLite falls back to JSON."""
    return sa.JSON().with_variant(JSONB(), "postgresql")


def upgrade() -> None:
    """Create the news tables."""
    json_t = _json_type()

    op.create_table(
        "news_article",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column("source_id", sa.String(length=200), nullable=False),
        sa.Column("url", sa.String(length=1000), nullable=False),
        sa.Column("title", sa.String(length=1000), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("author", sa.String(length=200), nullable=True),
        sa.Column("language", sa.String(length=10), nullable=True),
        sa.Column("market", sa.String(length=20), nullable=True),
        sa.Column("published_at", sa.DateTime(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("category", sa.String(length=100), nullable=True),
        sa.Column("engagement", json_t, nullable=True),
        sa.Column("sentiment_score", sa.Integer(), nullable=True),
        sa.Column("sentiment_label", sa.String(length=20), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source", "source_id", name="uq_news_article_source_id"),
    )
    op.create_index(
        "ix_news_article_source_published",
        "news_article",
        ["source", "published_at"],
        unique=False,
    )
    op.create_index(
        "ix_news_article_published_at",
        "news_article",
        ["published_at"],
        unique=False,
    )
    op.create_index(
        "ix_news_article_market",
        "news_article",
        ["market"],
        unique=False,
    )

    op.create_table(
        "news_article_symbol",
        sa.Column("article_id", sa.BigInteger(), nullable=False),
        sa.Column("symbol", sa.String(length=20), nullable=False),
        sa.Column("match_type", sa.String(length=30), nullable=True),
        sa.Column("confidence", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["article_id"],
            ["news_article.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("article_id", "symbol"),
    )
    op.create_index(
        "ix_news_article_symbol_symbol",
        "news_article_symbol",
        ["symbol"],
        unique=False,
    )

    op.create_table(
        "reddit_comment_cache",
        sa.Column("reddit_id", sa.String(length=20), nullable=False),
        sa.Column("parent_id", sa.String(length=20), nullable=True),
        sa.Column("subreddit", sa.String(length=50), nullable=True),
        sa.Column("author", sa.String(length=100), nullable=True),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("score", sa.Integer(), nullable=True),
        sa.Column("controversiality", sa.Integer(), nullable=True),
        sa.Column("created_utc", sa.DateTime(), nullable=True),
        sa.Column("fetched_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("reddit_id"),
    )
    op.create_index(
        "ix_reddit_comment_cache_parent_id",
        "reddit_comment_cache",
        ["parent_id"],
        unique=False,
    )
    op.create_index(
        "ix_reddit_comment_cache_subreddit",
        "reddit_comment_cache",
        ["subreddit"],
        unique=False,
    )

    op.create_table(
        "xueqiu_user_cache",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("screen_name", sa.String(length=100), nullable=True),
        sa.Column("followers_count", sa.Integer(), nullable=True),
        sa.Column("friends_count", sa.Integer(), nullable=True),
        sa.Column("status_count", sa.Integer(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("verified", sa.Boolean(), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.create_table(
        "xueqiu_fetch_state",
        sa.Column("symbol", sa.String(length=50), nullable=False),
        sa.Column("last_max_id", sa.BigInteger(), nullable=True),
        sa.Column("last_newest_id", sa.BigInteger(), nullable=True),
        sa.Column("last_fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_fetch_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_status", sa.String(length=50), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("fetch_count", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("symbol"),
    )


def downgrade() -> None:
    """Drop the news tables. Reverses the upgrade exactly."""
    op.drop_table("xueqiu_fetch_state")
    op.drop_table("xueqiu_user_cache")
    op.drop_index("ix_reddit_comment_cache_subreddit", table_name="reddit_comment_cache")
    op.drop_index("ix_reddit_comment_cache_parent_id", table_name="reddit_comment_cache")
    op.drop_table("reddit_comment_cache")
    op.drop_index("ix_news_article_symbol_symbol", table_name="news_article_symbol")
    op.drop_table("news_article_symbol")
    op.drop_index("ix_news_article_market", table_name="news_article")
    op.drop_index("ix_news_article_published_at", table_name="news_article")
    op.drop_index("ix_news_article_source_published", table_name="news_article")
    op.drop_table("news_article")
