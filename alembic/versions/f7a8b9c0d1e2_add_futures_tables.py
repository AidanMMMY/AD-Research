"""add futures tables

Revision ID: f7a8b9c0d1e2
Revises: f6a7b8c9d0e1
Create Date: 2026-07-02 12:00:00.000000

Creates two new tables for the Phase-8 China domestic futures pipelines:

* futures_contracts  - main continuous contract metadata (one row per
  symbol like CU0 / M0 / IF0 / SC0, refreshed monthly)
* futures_daily_bars - daily OHLCV rows including futures-specific
  settlement price and open interest, refreshed daily
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "f7a8b9c0d1e2"
down_revision: Union[str, Sequence[str], None] = "f6a7b8c9d0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create futures_contracts and futures_daily_bars tables."""
    op.create_table(
        "futures_contracts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False, comment="ID"),
        sa.Column(
            "code",
            sa.String(length=20),
            nullable=False,
            comment="Main contract code, e.g. CU0/M0/IF0",
        ),
        sa.Column("name", sa.String(length=200), nullable=False, comment="Display name"),
        sa.Column(
            "exchange",
            sa.String(length=10),
            nullable=False,
            comment="Exchange code: SHFE/DCE/CZCE/CFFEX/INE/GFEX",
        ),
        sa.Column(
            "product",
            sa.String(length=20),
            nullable=False,
            comment="Category: 金属/能源化工/农产品/金融期货",
        ),
        sa.Column("list_date", sa.Date(), comment="Contract listing date"),
        sa.Column("delist_date", sa.Date(), comment="Contract delist date (informational)"),
        sa.Column("contract_size", sa.DECIMAL(precision=18, scale=4), comment="Contract multiplier"),
        sa.Column("price_unit", sa.String(length=20), comment="Price unit"),
        sa.Column("quote_unit", sa.String(length=20), comment="Quote unit"),
        sa.Column(
            "underlying_instrument",
            sa.String(length=20),
            comment="Current leading specific contract code, e.g. CU2606",
        ),
        sa.Column(
            "is_main",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("TRUE"),
            comment="Is this a main continuous contract",
        ),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), comment="Last time akshare listed this main contract"),
        sa.Column(
            "source",
            sa.String(length=50),
            server_default="akshare",
            comment="Data source",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            comment="Creation time",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            comment="Update time",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_futures_contracts_code"),
    )
    op.create_index("idx_futures_contracts_code", "futures_contracts", ["code"])
    op.create_index("idx_futures_contracts_exchange", "futures_contracts", ["exchange"])
    op.create_index("idx_futures_contracts_product", "futures_contracts", ["product"])
    op.create_index("idx_futures_contracts_is_main", "futures_contracts", ["is_main"])
    op.create_index(
        "idx_futures_contracts_ex_product",
        "futures_contracts",
        ["exchange", "product"],
    )

    op.create_table(
        "futures_daily_bars",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False, comment="ID"),
        sa.Column("code", sa.String(length=20), nullable=False, comment="Futures main contract code"),
        sa.Column("trade_date", sa.Date(), nullable=False, comment="Trade date"),
        sa.Column("open", sa.DECIMAL(precision=12, scale=4), comment="Open price"),
        sa.Column("high", sa.DECIMAL(precision=12, scale=4), comment="High price"),
        sa.Column("low", sa.DECIMAL(precision=12, scale=4), comment="Low price"),
        sa.Column("close", sa.DECIMAL(precision=12, scale=4), comment="Close price"),
        sa.Column("settle", sa.DECIMAL(precision=12, scale=4), comment="Settlement price"),
        sa.Column("pre_settle", sa.DECIMAL(precision=12, scale=4), comment="Previous settlement price"),
        sa.Column("volume", sa.BigInteger(), comment="Volume (lots)"),
        sa.Column("open_interest", sa.BigInteger(), comment="Open interest"),
        sa.Column("turnover", sa.DECIMAL(precision=20, scale=4), comment="Turnover in CNY"),
        sa.Column("warehouse_receipts", sa.BigInteger(), comment="Warehouse receipts (best effort)"),
        sa.Column(
            "source",
            sa.String(length=50),
            server_default="akshare",
            comment="Data source",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            comment="Creation time",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "code", "trade_date", name="uq_futures_daily_bar_code_date"
        ),
    )
    op.create_index("idx_futures_daily_bar_code", "futures_daily_bars", ["code"])
    op.create_index("idx_futures_daily_bar_date", "futures_daily_bars", ["trade_date"])
    op.create_index(
        "idx_futures_daily_bar_code_date",
        "futures_daily_bars",
        ["code", "trade_date"],
    )


def downgrade() -> None:
    op.drop_index("idx_futures_daily_bar_code_date", table_name="futures_daily_bars")
    op.drop_index("idx_futures_daily_bar_date", table_name="futures_daily_bars")
    op.drop_index("idx_futures_daily_bar_code", table_name="futures_daily_bars")
    op.drop_table("futures_daily_bars")
    op.drop_index("idx_futures_contracts_ex_product", table_name="futures_contracts")
    op.drop_index("idx_futures_contracts_is_main", table_name="futures_contracts")
    op.drop_index("idx_futures_contracts_product", table_name="futures_contracts")
    op.drop_index("idx_futures_contracts_exchange", table_name="futures_contracts")
    op.drop_index("idx_futures_contracts_code", table_name="futures_contracts")
    op.drop_table("futures_contracts")
