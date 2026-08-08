"""add translation_attempts column to news_article

Retry bookkeeping for the auto-translation drain (2026-07-31). The
10-minute ``news_translate_10m`` job selects pending rows newest-first;
rows whose translation permanently fails (no body text from paywalled
sources, MiniMax 422 "sensitive" rejections) stayed in the selection
window forever and starved the 18.7k-row real backlog behind them.
Each failed auto-translate now increments ``translation_attempts`` and
the drain excludes rows at the cap (5). Sensitive-content rejections
are deterministic, so they jump straight to the cap.

See runbook ``docs/dev-notes/20260731-translation-drain-poison-queue.md``.

Revision ID: u7v9w1x3y5z7
Revises: t6u8v0w2x4y6
Create Date: 2026-07-31
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "u7v9w1x3y5z7"
down_revision: str | Sequence[str] | None = "t6u8v0w2x4y6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "news_article",
        sa.Column(
            "translation_attempts",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="Failed auto-translation attempts; drain skips rows at the cap",
        ),
    )


def downgrade() -> None:
    op.drop_column("news_article", "translation_attempts")
