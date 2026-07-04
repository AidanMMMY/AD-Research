"""add etf_holding table with holdings_as_of_date.

Adds a new ``etf_holding`` table that records each (ETF, underlying
security) pair the fund holds. The ``holdings_as_of_date`` column is the
reporting-period date the snapshot refers to — strictly nullable so
backfills written before the upstream provider shipped a date can
store ``NULL`` and the front-end still surfaces "as of …" hints where
the column is populated.

There was no pre-existing holdings table when this migration was
authored, so ``upgrade`` performs a full ``create_table``; ``downgrade``
drops it. The unique constraint on ``(etf_code, holding_code,
holdings_as_of_date)`` lets the same underlying appear in multiple
snapshots (one row per disclosure date).

Revision ID: 01aeaa464fc3
Revises: 197d510e8a35
Create Date: 2026-07-04
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "01aeaa464fc3"
down_revision = "197d510e8a35"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "etf_holding",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False, comment="ID"),
        sa.Column(
            "etf_code",
            sa.String(length=20),
            sa.ForeignKey("etf_info.code", ondelete="CASCADE"),
            nullable=False,
            comment="ETF / fund code",
        ),
        sa.Column(
            "holding_code",
            sa.String(length=20),
            nullable=False,
            comment="Underlying security code (e.g. 600519.SH, AAPL.US)",
        ),
        sa.Column(
            "holding_name",
            sa.String(length=200),
            nullable=True,
            comment="Underlying security display name",
        ),
        sa.Column(
            "weight",
            sa.DECIMAL(precision=10, scale=6),
            nullable=True,
            comment="Holding weight as a decimal fraction (0.05 = 5%)",
        ),
        sa.Column(
            "shares",
            sa.DECIMAL(precision=18, scale=4),
            nullable=True,
            comment="Shares held",
        ),
        sa.Column(
            "market_value",
            sa.DECIMAL(precision=18, scale=4),
            nullable=True,
            comment="Market value in base currency",
        ),
        sa.Column(
            "holdings_as_of_date",
            sa.Date(),
            nullable=True,
            comment="Reporting-period date for this snapshot (e.g. quarterly disclosure)",
        ),
        sa.Column(
            "source",
            sa.String(length=50),
            nullable=True,
            comment="Data source (csindex, sse, manual)",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=True,
            comment="Creation time",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_etf_holding"),
        sa.UniqueConstraint(
            "etf_code",
            "holding_code",
            "holdings_as_of_date",
            name="uq_etf_holding_code_date",
        ),
    )
    op.create_index("idx_etf_holding_etf", "etf_holding", ["etf_code"])
    op.create_index(
        "idx_etf_holding_as_of", "etf_holding", ["holdings_as_of_date"]
    )


def downgrade() -> None:
    op.drop_index("idx_etf_holding_as_of", table_name="etf_holding")
    op.drop_index("idx_etf_holding_etf", table_name="etf_holding")
    op.drop_table("etf_holding")