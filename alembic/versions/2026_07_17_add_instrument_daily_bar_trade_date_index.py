"""add idx_instrument_daily_bar_trade_date

Revision ID: 2026_07_17_add_instrument_daily_bar_trade_date_index
Revises: 2026_07_16_add_instrument_daily_bar_code_date_index
Create Date: 2026-07-17

Adds a single-column index on ``trade_date`` so the health-check probe
``SELECT max(trade_date) FROM instrument_daily_bar`` can use an Index Only
Scan instead of scanning the full table or the composite index.

The existing ``idx_instrument_daily_bar_code_date`` composite index is kept
because it still accelerates "latest bar for a given etf_code" lookups.
"""

from __future__ import annotations

from alembic import op

revision = "2026_07_17_add_instrument_daily_bar_trade_date_index"
down_revision = "2026_07_16_add_instrument_daily_bar_code_date_index"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # CREATE INDEX CONCURRENTLY cannot run inside a transaction.
    op.execute("COMMIT")
    op.execute(
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS "
        "idx_instrument_daily_bar_trade_date "
        "ON instrument_daily_bar (trade_date DESC)"
    )


def downgrade() -> None:
    op.execute("COMMIT")
    op.execute(
        "DROP INDEX CONCURRENTLY IF EXISTS idx_instrument_daily_bar_trade_date"
    )
