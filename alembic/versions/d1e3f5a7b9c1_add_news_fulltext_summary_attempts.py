"""add fulltext_attempts / summary_attempts columns to news_article

Retry bookkeeping for the full-content fetch drain and the AI summary
drain (2026-08-17), mirroring ``translation_attempts``
(u7v9w1x3y5z7). Both 10-minute jobs select pending rows newest-first;
rows whose fetch / summary keeps failing (anti-bot pages, dead URLs,
LLM outage windows) stayed in the selection window forever, burning
Jina / LLM quota every tick and starving the real backlog behind them.
Each failed attempt now increments the counter and the drains exclude
rows at the cap (5); the daily ``news_attempts_daily_reset`` job zeroes
capped rows so transient failures self-heal without a manual reset.

Revision ID: d1e3f5a7b9c1
Revises: f0b2d4e6f8a1
Create Date: 2026-08-17
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d1e3f5a7b9c1"
down_revision: str | Sequence[str] | None = "f0b2d4e6f8a1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "news_article",
        sa.Column(
            "fulltext_attempts",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="Failed full-content fetch attempts; drain skips rows at the cap",
        ),
    )
    op.add_column(
        "news_article",
        sa.Column(
            "summary_attempts",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="Failed AI summary attempts; drain skips rows at the cap",
        ),
    )


def downgrade() -> None:
    op.drop_column("news_article", "summary_attempts")
    op.drop_column("news_article", "fulltext_attempts")
