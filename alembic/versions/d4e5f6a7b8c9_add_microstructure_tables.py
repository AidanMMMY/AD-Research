"""add microstructure tables

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-07-02 14:20:00.000000

Phase 7 — A-share micro-structure data:

* ``lhb_records``         龙虎榜 (Top-list) disclosures
* ``hsgt_flows``          沪深港通 daily flows
* ``margin_balances``     融资融券 per-stock per-exchange balances
* ``restricted_releases`` 限售解禁 schedule

Mirrors ``app/models/microstructure.py``.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, Sequence[str], None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the 4 micro-structure tables."""
    op.create_table(
        "lhb_records",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False, comment="ID"),
        sa.Column("trade_date", sa.Date(), nullable=False, comment="交易日期"),
        sa.Column("ts_code", sa.String(length=20), nullable=False, comment="证券代码"),
        sa.Column("name", sa.String(length=64), nullable=False, comment="证券简称"),
        sa.Column("close", sa.Numeric(precision=12, scale=4), nullable=True, comment="收盘价"),
        sa.Column("pct_change", sa.Numeric(precision=10, scale=4), nullable=True, comment="涨跌幅 %"),
        sa.Column("turnover_rate", sa.Numeric(precision=10, scale=4), nullable=True, comment="换手率 %"),
        sa.Column("amount", sa.Numeric(precision=20, scale=4), nullable=True, comment="成交额"),
        sa.Column("lhb_buy_amount", sa.Numeric(precision=20, scale=4), nullable=True, comment="龙虎榜买入额"),
        sa.Column("lhb_sell_amount", sa.Numeric(precision=20, scale=4), nullable=True, comment="龙虎榜卖出额"),
        sa.Column("lhb_net_amount", sa.Numeric(precision=20, scale=4), nullable=True, comment="龙虎榜净额"),
        sa.Column("total_buy", sa.Numeric(precision=20, scale=4), nullable=True, comment="总买入额"),
        sa.Column("total_sell", sa.Numeric(precision=20, scale=4), nullable=True, comment="总卖出额"),
        sa.Column("total_net", sa.Numeric(precision=20, scale=4), nullable=True, comment="总净额"),
        sa.Column("net_buy_amt", sa.Numeric(precision=20, scale=4), nullable=True, comment="买方净额"),
        sa.Column("buy_seat_count", sa.Integer(), nullable=True, comment="买方营业部个数"),
        sa.Column("sell_seat_count", sa.Integer(), nullable=True, comment="卖方营业部个数"),
        sa.Column("reason", sa.String(length=256), nullable=False, comment="上榜原因"),
        sa.Column("source", sa.String(length=32), nullable=False, server_default="akshare", comment="数据来源"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False,
                  comment="入库时间"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("trade_date", "ts_code", "reason", name="uq_lhb_records_trade_date_ts_code_reason"),
    )
    op.create_index("ix_lhb_records_trade_date", "lhb_records", ["trade_date"])
    op.create_index("ix_lhb_records_ts_code", "lhb_records", ["ts_code"])
    op.create_index("ix_lhb_records_trade_date_amount", "lhb_records", ["trade_date", "lhb_net_amount"])

    op.create_table(
        "hsgt_flows",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False, comment="ID"),
        sa.Column("trade_date", sa.Date(), nullable=False, comment="交易日期"),
        sa.Column("type", sa.String(length=16), nullable=False, comment="资金流向类型"),
        sa.Column("buy_amount", sa.Numeric(precision=20, scale=4), nullable=True, comment="买入成交额"),
        sa.Column("sell_amount", sa.Numeric(precision=20, scale=4), nullable=True, comment="卖出成交额"),
        sa.Column("net_amount", sa.Numeric(precision=20, scale=4), nullable=True, comment="净流入"),
        sa.Column("balance", sa.Numeric(precision=20, scale=4), nullable=True, comment="当日余额"),
        sa.Column("source", sa.String(length=32), nullable=False, server_default="akshare", comment="数据来源"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False,
                  comment="入库时间"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("trade_date", "type", name="uq_hsgt_flows_trade_date_type"),
    )
    op.create_index("ix_hsgt_flows_trade_date", "hsgt_flows", ["trade_date"])
    op.create_index("ix_hsgt_flows_type", "hsgt_flows", ["type"])

    op.create_table(
        "margin_balances",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False, comment="ID"),
        sa.Column("trade_date", sa.Date(), nullable=False, comment="交易日期"),
        sa.Column("ts_code", sa.String(length=20), nullable=False, comment="证券代码"),
        sa.Column("name", sa.String(length=64), nullable=False, comment="证券简称"),
        sa.Column("financing_balance", sa.Numeric(precision=20, scale=4), nullable=True, comment="融资余额"),
        sa.Column("financing_buy", sa.Numeric(precision=20, scale=4), nullable=True, comment="融资买入额"),
        sa.Column("securities_balance", sa.Numeric(precision=20, scale=4), nullable=True, comment="融券余额"),
        sa.Column("securities_sell", sa.Numeric(precision=20, scale=4), nullable=True, comment="融券卖出量"),
        sa.Column("exchange", sa.String(length=8), nullable=False, comment="交易所: SSE / SZSE"),
        sa.Column("source", sa.String(length=32), nullable=False, server_default="akshare", comment="数据来源"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False,
                  comment="入库时间"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("trade_date", "ts_code", name="uq_margin_balances_trade_date_ts_code"),
    )
    op.create_index("ix_margin_balances_trade_date", "margin_balances", ["trade_date"])
    op.create_index("ix_margin_balances_ts_code", "margin_balances", ["ts_code"])
    op.create_index("ix_margin_balances_exchange_trade_date", "margin_balances", ["exchange", "trade_date"])

    op.create_table(
        "restricted_releases",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False, comment="ID"),
        sa.Column("ts_code", sa.String(length=20), nullable=False, comment="证券代码"),
        sa.Column("name", sa.String(length=64), nullable=False, comment="证券简称"),
        sa.Column("restricted_date", sa.Date(), nullable=False, comment="解禁日期"),
        sa.Column("restricted_type", sa.String(length=64), nullable=False, server_default="", comment="限售类型"),
        sa.Column("restricted_number", sa.Numeric(precision=20, scale=4), nullable=True, comment="解禁数量"),
        sa.Column("restricted_amount", sa.Numeric(precision=20, scale=4), nullable=True, comment="解禁市值"),
        sa.Column("lift_ratio", sa.Numeric(precision=10, scale=4), nullable=True, comment="占总股本比例 %"),
        sa.Column("source", sa.String(length=32), nullable=False, server_default="akshare", comment="数据来源"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False,
                  comment="入库时间"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ts_code", "restricted_date", "restricted_type",
                            name="uq_restricted_releases_ts_code_date_type"),
    )
    op.create_index("ix_restricted_releases_ts_code", "restricted_releases", ["ts_code"])
    op.create_index("ix_restricted_releases_restricted_date", "restricted_releases", ["restricted_date"])


def downgrade() -> None:
    """Drop the 4 micro-structure tables."""
    op.drop_index("ix_restricted_releases_restricted_date", table_name="restricted_releases")
    op.drop_index("ix_restricted_releases_ts_code", table_name="restricted_releases")
    op.drop_table("restricted_releases")
    op.drop_index("ix_margin_balances_exchange_trade_date", table_name="margin_balances")
    op.drop_index("ix_margin_balances_ts_code", table_name="margin_balances")
    op.drop_index("ix_margin_balances_trade_date", table_name="margin_balances")
    op.drop_table("margin_balances")
    op.drop_index("ix_hsgt_flows_type", table_name="hsgt_flows")
    op.drop_index("ix_hsgt_flows_trade_date", table_name="hsgt_flows")
    op.drop_table("hsgt_flows")
    op.drop_index("ix_lhb_records_trade_date_amount", table_name="lhb_records")
    op.drop_index("ix_lhb_records_ts_code", table_name="lhb_records")
    op.drop_index("ix_lhb_records_trade_date", table_name="lhb_records")
    op.drop_table("lhb_records")