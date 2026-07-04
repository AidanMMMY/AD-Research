"""add ai_cleaned_at + ai_cleanup_status to news_article

Makes the AI cleanup stage in ``ContentFetcher._clean_with_ai``
observable. Until now any DeepSeek failure (missing key, HTTP timeout,
short / empty response) was silently swallowed — the row's
``full_content`` got the raw Jina Markdown and the caller happily
reported ``success=True`` to the scheduler.

Two new columns break that silence:

* ``ai_cleaned_at`` (``TIMESTAMPTZ NULL``) — wall-clock timestamp of
  the last attempt, no matter the outcome. ``NULL`` means the
  scheduler never reached the article.
* ``ai_cleanup_status`` (``VARCHAR(16) NULL``) — four-value enum:

    - ``cleaned``     — DeepSeek call succeeded, ``full_content`` is the
      cleaned body.
    - ``skipped``     — DeepSeek was not configured (``is_available``
      was False). ``full_content`` keeps the raw Jina Markdown on
      purpose so the reader still gets *something*.
    - ``failed``      — DeepSeek was configured but the call raised
      (HTTP 5xx, timeout, rate-limit, …). ``full_content`` again keeps
      the raw Jina Markdown.
    - ``not_attempted`` — never set today; reserved for a future batch
      re-fetch path. Kept as a valid value so ops dashboards don't
      break if a future job sets it explicitly.

Both columns are ``NULL`` by default; we deliberately do **not** set a
``DEFAULT 'not_attempted'`` so the absence of a value still means
"this row was never processed" rather than "this row was processed and
the AI was a no-op".

The ``ix_news_article_ai_cleanup_status`` index lets ops dashboards
fast-path the ``WHERE ai_cleanup_status = 'failed'`` alarm query.

Revision ID: 2026_07_05_add_ai_cleanup_obs
Revises: 2026_07_05_add_user_id_to_8_business_tables
Create Date: 2026-07-05 12:00:00.000000
"""

from typing import Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "2026_07_05_add_ai_cleanup_obs"
down_revision: Union[str, None] = "2026_07_05_add_user_id_to_8_business_tables"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    """Add observability columns + status index to ``news_article``."""
    op.add_column(
        "news_article",
        sa.Column(
            "ai_cleaned_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment=(
                "Timestamp of the last AI-cleanup attempt. NULL means "
                "the scheduler never reached this article."
            ),
        ),
    )
    op.add_column(
        "news_article",
        sa.Column(
            "ai_cleanup_status",
            sa.String(length=16),
            nullable=True,
            comment=(
                "cleaned | skipped | failed | not_attempted. NULL "
                "means the scheduler never reached this article."
            ),
        ),
    )
    op.create_index(
        "ix_news_article_ai_cleanup_status",
        "news_article",
        ["ai_cleanup_status"],
    )


def downgrade() -> None:
    """Drop observability columns + status index from ``news_article``."""
    op.drop_index(
        "ix_news_article_ai_cleanup_status", table_name="news_article"
    )
    op.drop_column("news_article", "ai_cleanup_status")
    op.drop_column("news_article", "ai_cleaned_at")
