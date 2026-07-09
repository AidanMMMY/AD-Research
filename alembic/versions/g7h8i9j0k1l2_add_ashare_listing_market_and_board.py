"""add A-share listing_market and board columns to etf_info

Adds ``listing_market`` (上海/深圳/北京) and ``board`` (主板/创业板/科创板/北交所)
columns to ``etf_info``. Both columns are nullable because non-A-share
instruments do not carry a board.

The mapping logic lives in ``app.data.providers.tushare_provider``:

* ``listing_market`` is derived from the ``exchange`` code (SH/SZ/BJ).
* ``board`` is derived from the numeric code prefix:

  - 60xxxx / 00xxxx -> 主板
  - 30xxxx          -> 创业板
  - 68xxxx          -> 科创板
  - 8xxxxx / 92xxxx / 43xxxx (BJ) -> 北交所

The existing ``a_share_stock_discovery`` pipeline is updated to write
both fields on every upsert, and a backfill helper (see the
``backfill_ashare_listing_market_and_board`` script in ``scripts/``)
populates the columns for rows that already exist.

Revision ID: g7h8i9j0k1l2
Revises: c8d4e5f6a7b8
Create Date: 2026-07-09
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "g7h8i9j0k1l2"
down_revision = "c8d4e5f6a7b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "etf_info",
        sa.Column(
            "listing_market",
            sa.String(length=20),
            nullable=True,
            comment="Listing market (上海/深圳/北京) for A-share instruments",
        ),
    )
    op.add_column(
        "etf_info",
        sa.Column(
            "board",
            sa.String(length=20),
            nullable=True,
            comment="A-share board (主板/创业板/科创板/北交所)",
        ),
    )
    op.create_index(
        "idx_etf_info_listing_market",
        "etf_info",
        ["listing_market"],
    )
    op.create_index(
        "idx_etf_info_board",
        "etf_info",
        ["board"],
    )


def downgrade() -> None:
    op.drop_index("idx_etf_info_board", table_name="etf_info")
    op.drop_index("idx_etf_info_listing_market", table_name="etf_info")
    op.drop_column("etf_info", "board")
    op.drop_column("etf_info", "listing_market")