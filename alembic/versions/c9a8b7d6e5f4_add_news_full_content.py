"""Add full_content / full_content_fetched_at to news_article.

Stores the body returned by Jina Reader (https://r.jina.ai/{url}) so the
detail page can render full text on demand instead of forcing a click
through to the original site. The two new columns are nullable; the
fetcher fills them lazily when a user clicks the load button on the
detail page and a 24h TTL prevents re-hitting Jina on every open.

Revision ID: c9a8b7d6e5f4
Revises: 1c9321d3cb37
Create Date: 2026-07-01
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c9a8b7d6e5f4"
down_revision = "1c9321d3cb37"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "news_article",
        sa.Column(
            "full_content",
            sa.Text(),
            nullable=True,
            comment="Fetched full body via Jina Reader",
        ),
    )
    op.add_column(
        "news_article",
        sa.Column(
            "full_content_fetched_at",
            sa.DateTime(),
            nullable=True,
            comment="When Jina Reader fetch last ran (cache TTL anchor)",
        ),
    )


def downgrade() -> None:
    op.drop_column("news_article", "full_content_fetched_at")
    op.drop_column("news_article", "full_content")
