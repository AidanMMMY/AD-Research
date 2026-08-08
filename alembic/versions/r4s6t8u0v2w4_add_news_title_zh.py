"""add title_zh column to news_article

Stores the AI-generated Chinese translation of the article title so the
news list + detail pages can render Chinese-first titles for non-Chinese
sources without an on-demand LLM call. Filled at ingestion time by the
auto-translation pipeline (``scheduler_translate_news``).

Revision ID: r4s6t8u0v2w4
Revises: q3r5s7t9u1v2
Create Date: 2026-07-26
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "r4s6t8u0v2w4"
down_revision: str | Sequence[str] | None = "q3r5s7t9u1v2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "news_article",
        sa.Column(
            "title_zh",
            sa.String(length=1000),
            nullable=True,
            comment="AI-generated Chinese translation of title (auto-filled at ingestion)",
        ),
    )


def downgrade() -> None:
    op.drop_column("news_article", "title_zh")
