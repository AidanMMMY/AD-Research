"""add summary_zh column to news_article

Stores the AI-generated one-sentence Chinese summary (≤80 字) so the
news feed can render a digest line under each headline without an
on-demand LLM call. Filled by the 10-minute ``news_summarize_10m``
drain job (``app/services/news/scheduler_summarize_news.py``) for
articles with ``importance >= 3``, regardless of language — a Chinese
headline still gets a summary because a summary is not a title
restated (方向 D, docs/dev-notes/20260729-mobile-ui-redesign-research.md).

Revision ID: t6u8v0w2x4y6
Revises: s5t7u9v1w3x5
Create Date: 2026-07-29
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "t6u8v0w2x4y6"
down_revision: Union[str, Sequence[str], None] = "s5t7u9v1w3x5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "news_article",
        sa.Column(
            "summary_zh",
            sa.String(length=500),
            nullable=True,
            comment="AI-generated one-sentence Chinese summary (<=80 chars, drain job news_summarize_10m)",
        ),
    )


def downgrade() -> None:
    op.drop_column("news_article", "summary_zh")
