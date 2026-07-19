"""add sw_industry_index_return table for Phase 3 sector rotation

The current sector rotation service computes per-industry returns as an
equal-weight average of constituent ETF + STOCK ``return_*`` from
``etf_indicator``. That is a practical approximation but it is NOT the
official industry index return.

This migration adds ``sw_industry_index_return`` so the sector rotation
service can switch to the official 申万2021 industry index return when
``classification="SW"``. Source: AKShare ``index_hist_sw`` (one full
history fetch per industry, since AKShare's API has no date range filter).

The fetcher runs weekly on Mondays via ``refresh_sw_industry_returns`` in
``app.tasks.sw_industry`` and UPSERTs the rows on conflict of
``(sw_l1_code, trade_date)``.

Revision ID: p1r4s0t7u8v9
Revises: c38dfe612183
Create Date: 2026-07-19
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "p1r4s0t7u8v9"
down_revision: Union[str, Sequence[str], None] = "c38dfe612183"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create sw_industry_index_return table + indexes."""
    op.create_table(
        "sw_industry_index_return",
        sa.Column(
            "sw_l1_code",
            sa.String(length=20),
            nullable=False,
            comment="申万一级行业代码 (e.g. 801080), pairs with etf_info.sw_l1_code",
        ),
        sa.Column(
            "trade_date",
            sa.Date(),
            nullable=False,
            comment="指数交易日（与 etf_indicator.trade_date 同源）",
        ),
        sa.Column(
            "close",
            sa.Numeric(precision=18, scale=4),
            nullable=True,
            comment="指数当日收盘点位",
        ),
        sa.Column(
            "return_1w",
            sa.Numeric(precision=18, scale=6),
            nullable=True,
            comment="过去 1 周（5 交易日）回报 = close(t)/close(t-5)-1",
        ),
        sa.Column(
            "return_1m",
            sa.Numeric(precision=18, scale=6),
            nullable=True,
            comment="过去 1 月（21 交易日）回报",
        ),
        sa.Column(
            "return_3m",
            sa.Numeric(precision=18, scale=6),
            nullable=True,
            comment="过去 3 月（63 交易日）回报",
        ),
        sa.Column(
            "return_6m",
            sa.Numeric(precision=18, scale=6),
            nullable=True,
            comment="过去 6 月（126 交易日）回报",
        ),
        sa.Column(
            "return_1y",
            sa.Numeric(precision=18, scale=6),
            nullable=True,
            comment="过去 1 年（252 交易日）回报",
        ),
        sa.Column(
            "source",
            sa.String(length=20),
            nullable=False,
            server_default="akshare",
            comment="数据来源标记 (akshare / tushare / fallback)",
        ),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            comment="最近一次写入时间，便于监控陈旧度",
        ),
        sa.PrimaryKeyConstraint("sw_l1_code", "trade_date", name="pk_sw_industry_index_return"),
    )
    op.create_index(
        "ix_sw_industry_index_return_trade_date",
        "sw_industry_index_return",
        ["trade_date"],
    )
    op.create_index(
        "ix_sw_industry_index_return_fetched_at",
        "sw_industry_index_return",
        ["fetched_at"],
    )


def downgrade() -> None:
    """Drop sw_industry_index_return table."""
    op.drop_index("ix_sw_industry_index_return_fetched_at", table_name="sw_industry_index_return")
    op.drop_index("ix_sw_industry_index_return_trade_date", table_name="sw_industry_index_return")
    op.drop_table("sw_industry_index_return")