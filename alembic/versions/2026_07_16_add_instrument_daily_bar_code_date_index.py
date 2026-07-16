"""add idx_instrument_daily_bar_code_date

Revision ID: 2026_07_16_add_instrument_daily_bar_code_date_index
Revises: 2026_07_16_add_web_vitals_log
Create Date: 2026-07-16

Speeds up the health-check data-staleness probe (``max(trade_date)`` per
market) and any other lookups of the latest bar for a given ETF code.

ops incident 2026-07-16: the previous per-market join scanned the whole
``instrument_daily_bar`` table (tens of millions of rows) and made
``/health`` time out, which cascaded into QueuePool exhaustion and a
site outage.
"""

from __future__ import annotations

from alembic import op

revision = "2026_07_16_add_instrument_daily_bar_code_date_index"
down_revision = "2026_07_16_add_web_vitals_log"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # CREATE INDEX CONCURRENTLY cannot run inside a transaction.
    op.execute("COMMIT")
    op.execute(
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS "
        "idx_instrument_daily_bar_code_date "
        "ON instrument_daily_bar (etf_code, trade_date DESC)"
    )


def downgrade() -> None:
    op.execute("COMMIT")
    op.execute(
        "DROP INDEX CONCURRENTLY IF EXISTS idx_instrument_daily_bar_code_date"
    )
