"""Enrich news_article schema with LLM + dedup columns.

Revision ID: b2_news_schema_enrich
Revises: a1b1c2d3e4f5
Create Date: 2026-07-01
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "b2_news_schema_enrich"
down_revision = "a1b1c2d3e4f5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    json_t = JSONB().with_variant(sa.JSON(), "sqlite")

    # 1. url_hash: add the column (Agent B migration did not include it),
    # backfill from md5(url), then enforce NOT NULL + UNIQUE.
    bind = op.get_bind()
    has_url_hash = bind.execute(sa.text(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name = 'news_article' AND column_name = 'url_hash'"
    )).first() is not None
    if not has_url_hash:
        op.add_column("news_article", sa.Column("url_hash", sa.String(length=32), nullable=True))
    op.execute("UPDATE news_article SET url_hash = md5(url) WHERE url_hash IS NULL OR url_hash = ''")
    op.alter_column("news_article", "url_hash",
                    existing_type=sa.String(length=32),
                    nullable=False)
    # Skip the index if it already exists (idempotency for re-runs)
    idx_exists = bind.execute(sa.text(
        "SELECT 1 FROM pg_indexes WHERE indexname = 'ix_news_article_url_hash'"
    )).first() is not None
    if not idx_exists:
        op.create_index("ix_news_article_url_hash", "news_article", ["url_hash"], unique=True)

    # 2. 文本 + 抓取相关
    op.add_column("news_article", sa.Column("body", sa.Text(), nullable=True))
    op.add_column("news_article", sa.Column("body_html", sa.Text(), nullable=True))
    op.add_column("news_article", sa.Column("author_followers", sa.Integer(), nullable=True))
    op.add_column("news_article", sa.Column("content_hash", sa.String(length=32), nullable=True))
    idx2 = bind.execute(sa.text(
        "SELECT 1 FROM pg_indexes WHERE indexname = 'ix_news_article_content_hash'"
    )).first() is not None
    if not idx2:
        op.create_index("ix_news_article_content_hash", "news_article", ["content_hash"])

    # 3. LLM 字段（Agent E）
    op.add_column("news_article", sa.Column("sentiment_confidence", sa.Float(), nullable=True))
    op.add_column("news_article", sa.Column("sentiment_drivers", json_t, nullable=True))
    op.add_column("news_article", sa.Column("event_category", sa.String(length=50), nullable=True))
    op.add_column("news_article", sa.Column("importance", sa.SmallInteger(), nullable=True))
    op.add_column("news_article", sa.Column("sentiment_processed_at", sa.DateTime(), nullable=True))

    # 4. published_at DESC 索引（列表查询主力）
    idx3 = bind.execute(sa.text(
        "SELECT 1 FROM pg_indexes WHERE indexname = 'ix_news_article_published_desc'"
    )).first() is not None
    if not idx3:
        op.create_index("ix_news_article_published_desc", "news_article", [sa.text("published_at DESC")])


def downgrade() -> None:
    op.drop_index("ix_news_article_published_desc", table_name="news_article")
    op.drop_column("news_article", "sentiment_processed_at")
    op.drop_column("news_article", "importance")
    op.drop_column("news_article", "event_category")
    op.drop_column("news_article", "sentiment_drivers")
    op.drop_column("news_article", "sentiment_confidence")
    op.drop_index("ix_news_article_content_hash", table_name="news_article")
    op.drop_column("news_article", "content_hash")
    op.drop_column("news_article", "author_followers")
    op.drop_column("news_article", "body_html")
    op.drop_column("news_article", "body")
    op.drop_index("ix_news_article_url_hash", table_name="news_article")
    op.alter_column("news_article", "url_hash",
                    existing_type=sa.String(length=32),
                    nullable=True)