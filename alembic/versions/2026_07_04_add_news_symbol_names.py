"""Add name/name_zh to news_article_symbol.

Caches the instrument display name at ingestion time so the news detail
page can render code + Chinese label without an extra lookup. Existing
rows remain NULL until the next crawl or a backfill job runs.

Revision ID: 2026_07_04_add_news_symbol_names
Revises: 2026_07_04_add_news_translation
Create Date: 2026-07-04 17:00:00.000000
"""

from typing import Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "2026_07_04_add_news_symbol_names"
down_revision: Union[str, None] = "2026_07_04_add_news_translation"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    """Add ``name`` and ``name_zh`` to ``news_article_symbol``."""
    op.add_column(
        "news_article_symbol",
        sa.Column(
            "name",
            sa.String(length=200),
            nullable=True,
            comment="Instrument display name",
        ),
    )
    op.add_column(
        "news_article_symbol",
        sa.Column(
            "name_zh",
            sa.String(length=200),
            nullable=True,
            comment="Chinese display name",
        ),
    )


def downgrade() -> None:
    """Drop name columns from ``news_article_symbol``."""
    op.drop_column("news_article_symbol", "name_zh")
    op.drop_column("news_article_symbol", "name")
