"""add market_fund_flow table

Creates the market-level fund-flow table to persist East Money / akshare
``stock_market_fund_flow`` data plus derived SH/SZ aggregates from
``individual_fund_flow``.

Revision ID: 2026_07_18_0001_add_market_fund_flow_table
Revises: 2026_07_18_0000_widen_etf_indicator_return_drawdown
Create Date: 2026-07-18
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "2026_07_18_0001_add_market_fund_flow_table"
down_revision: Union[str, Sequence[str], None] = (
    "2026_07_18_0000_widen_etf_indicator_return_drawdown"
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create market_fund_flow table."""
    op.create_table(
        "market_fund_flow",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "trade_date",
            sa.Date(),
            nullable=False,
            comment="交易日期",
        ),
        sa.Column(
            "market",
            sa.String(10),
            nullable=False,
            comment="市场: SH / SZ / ALL",
        ),
        sa.Column(
            "close_price",
            sa.Numeric(12, 4),
            nullable=True,
            comment="大盘指数收盘价 (ALL 为空)",
        ),
        sa.Column(
            "pct_change",
            sa.Numeric(8, 4),
            nullable=True,
            comment="大盘指数涨跌幅 (%)",
        ),
        sa.Column(
            "main_net_inflow",
            sa.Numeric(20, 4),
            nullable=True,
            comment="主力净流入净额 (元)",
        ),
        sa.Column(
            "main_net_pct",
            sa.Numeric(8, 4),
            nullable=True,
            comment="主力净流入净占比 (%)",
        ),
        sa.Column(
            "super_large_net",
            sa.Numeric(20, 4),
            nullable=True,
            comment="超大单净额 (元)",
        ),
        sa.Column(
            "large_net",
            sa.Numeric(20, 4),
            nullable=True,
            comment="大单净额 (元)",
        ),
        sa.Column(
            "medium_net",
            sa.Numeric(20, 4),
            nullable=True,
            comment="中单净额 (元)",
        ),
        sa.Column(
            "small_net",
            sa.Numeric(20, 4),
            nullable=True,
            comment="小单净额 (元)",
        ),
        sa.Column(
            "total_amount",
            sa.Numeric(20, 4),
            nullable=True,
            comment="市场成交额 (元)",
        ),
        sa.Column(
            "source",
            sa.String(20),
            server_default="akshare",
            nullable=False,
            comment="数据来源: akshare / derived",
        ),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
            comment="抓取时间",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "trade_date", "market",
            name="uq_market_fund_flow_date_market",
        ),
    )
    op.create_index(
        "idx_market_fund_flow_date",
        "market_fund_flow",
        ["trade_date"],
    )
    op.create_index(
        "idx_market_fund_flow_market",
        "market_fund_flow",
        ["market"],
    )
    op.create_index(
        "idx_market_fund_flow_date_market",
        "market_fund_flow",
        ["trade_date", "market"],
    )


def downgrade() -> None:
    """Drop market_fund_flow table."""
    op.drop_index("idx_market_fund_flow_date_market", table_name="market_fund_flow")
    op.drop_index("idx_market_fund_flow_market", table_name="market_fund_flow")
    op.drop_index("idx_market_fund_flow_date", table_name="market_fund_flow")
    op.drop_table("market_fund_flow")
