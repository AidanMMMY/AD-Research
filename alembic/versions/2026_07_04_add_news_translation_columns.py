"""add translated_zh + translation_generated_at to news_article

Stores the DeepSeek-generated Chinese translation of an English article's
body so the news detail page can render a side-by-side bilingual view.
``translated_zh`` is the LLM output (Markdown-ish). ``translation_generated_at``
records when the translation was last produced, letting us TTL the cache
or show a "translated on" timestamp in the UI.

Both columns are nullable — non-English articles (CN/HK) never populate
them. The endpoint that writes them (``POST /news/{id}/translate``) only
operates on ``language == 'en'`` rows so non-English content keeps them
empty forever.

Revision ID: 2026_07_04_add_news_translation
Revises: 2026_07_04_add_name_zh
Create Date: 2026-07-04 16:00:00.000000
"""

from typing import Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "2026_07_04_add_news_translation"
down_revision: Union[str, None] = "2026_07_04_add_name_zh"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    """Add ``translated_zh`` and ``translation_generated_at`` to news_article."""
    op.add_column(
        "news_article",
        sa.Column(
            "translated_zh",
            sa.Text(),
            nullable=True,
            comment="DeepSeek-generated Chinese translation of body/full_content",
        ),
    )
    op.add_column(
        "news_article",
        sa.Column(
            "translation_generated_at",
            sa.DateTime(),
            nullable=True,
            comment="When the LLM translation was last produced",
        ),
    )
    # Optional index — the API endpoint looks up an article by id but
    # ops may want to count "how many translated articles do we have".
    op.create_index(
        "ix_news_article_translation_generated_at",
        "news_article",
        ["translation_generated_at"],
    )


def downgrade() -> None:
    """Drop translation columns from news_article."""
    op.drop_index(
        "ix_news_article_translation_generated_at", table_name="news_article"
    )
    op.drop_column("news_article", "translation_generated_at")
    op.drop_column("news_article", "translated_zh")