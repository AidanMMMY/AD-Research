"""create fund_flow tables (方案 C: 免费资金流调研报告)

Revision ID: 2026_07_14_create_fund_flow_tables
Revises: 2026_07_14_create_company_disclosure_route
Create Date: 2026-07-14

Adds four tables for the **free** capital-flow data layer:

* ``individual_fund_flow`` — 个股主力/超大/大/中/小单 净流入 (akshare)
* ``sector_fund_flow``     — 行业 / 概念 / 地域 板块资金流 (akshare)
* ``etf_fund_flow``        — ETF 折溢价 / 份额变化 / 推算净流入 (akshare)
* ``flow_signal``          — 综合资金信号：主力 + 融资 + 龙虎榜 + 股东户数
                              + AH 溢价 + 大宗 + composite_score (JSONB)

All monetary fields are in 元 (CNY) and use ``Numeric(20, 4)`` to match
the existing microstructure table conventions.  Each table has an
idempotency-friendly unique constraint on (key, trade_date) so the
daily refresh is safe to re-run.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "2026_07_14_create_fund_flow_tables"
down_revision = "2026_07_14_create_company_disclosure_route"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. individual_fund_flow: 个股主力/超大/大/中/小单 资金流
    # ------------------------------------------------------------------
    op.create_table(
        "individual_fund_flow",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("ts_code", sa.String(length=20), nullable=False, comment="证券代码 (含后缀)"),
        sa.Column("trade_date", sa.Date(), nullable=False, comment="交易日期"),
        sa.Column("main_net_inflow", sa.Numeric(20, 4), nullable=True, comment="主力净流入净额 (元)"),
        sa.Column("main_net_pct", sa.Numeric(8, 4), nullable=True, comment="主力净流入净占比 (%)"),
        sa.Column("super_large_net", sa.Numeric(20, 4), nullable=True, comment="超大单净额 (元)"),
        sa.Column("super_large_pct", sa.Numeric(8, 4), nullable=True, comment="超大单净占比 (%)"),
        sa.Column("large_net", sa.Numeric(20, 4), nullable=True, comment="大单净额 (元)"),
        sa.Column("large_pct", sa.Numeric(8, 4), nullable=True, comment="大单净占比 (%)"),
        sa.Column("medium_net", sa.Numeric(20, 4), nullable=True, comment="中单净额 (元)"),
        sa.Column("medium_pct", sa.Numeric(8, 4), nullable=True, comment="中单净占比 (%)"),
        sa.Column("small_net", sa.Numeric(20, 4), nullable=True, comment="小单净额 (元)"),
        sa.Column("small_pct", sa.Numeric(8, 4), nullable=True, comment="小单净占比 (%)"),
        sa.Column(
            "source",
            sa.String(length=20),
            server_default=sa.text("'akshare'"),
            nullable=False,
            comment="数据来源: akshare | eastmoney",
        ),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
            comment="抓取时间",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_individual_fund_flow"),
        sa.UniqueConstraint(
            "ts_code", "trade_date", name="uq_individual_fund_flow_ts_code_date"
        ),
    )
    op.create_index(
        "ix_individual_fund_flow_trade_date",
        "individual_fund_flow",
        ["trade_date"],
    )
    op.create_index(
        "ix_individual_fund_flow_main_net",
        "individual_fund_flow",
        ["trade_date", "main_net_inflow"],
    )

    # ------------------------------------------------------------------
    # 2. sector_fund_flow: 行业 / 概念 / 地域 板块资金流
    # ------------------------------------------------------------------
    op.create_table(
        "sector_fund_flow",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("sector_name", sa.String(length=100), nullable=False, comment="板块名称"),
        sa.Column(
            "sector_type",
            sa.String(length=20),
            nullable=False,
            comment="板块类型: 行业 / 概念 / 地域",
        ),
        sa.Column("trade_date", sa.Date(), nullable=False, comment="交易日期"),
        sa.Column("main_net_inflow", sa.Numeric(20, 4), nullable=True, comment="板块主力净流入 (元)"),
        sa.Column("main_net_pct", sa.Numeric(8, 4), nullable=True, comment="主力净流入净占比 (%)"),
        sa.Column("super_large_net", sa.Numeric(20, 4), nullable=True, comment="超大单净额 (元)"),
        sa.Column("large_net", sa.Numeric(20, 4), nullable=True, comment="大单净额 (元)"),
        sa.Column(
            "leading_stock",
            sa.String(length=100),
            nullable=True,
            comment="领涨股代码/名称 (akshare 原始字段)",
        ),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
            comment="抓取时间",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_sector_fund_flow"),
        sa.UniqueConstraint(
            "sector_name",
            "sector_type",
            "trade_date",
            name="uq_sector_fund_flow_sector_type_date",
        ),
    )
    op.create_index(
        "ix_sector_fund_flow_trade_date",
        "sector_fund_flow",
        ["trade_date"],
    )
    op.create_index(
        "ix_sector_fund_flow_main_net",
        "sector_fund_flow",
        ["trade_date", "main_net_inflow"],
    )

    # ------------------------------------------------------------------
    # 3. etf_fund_flow: ETF 折溢价 / 份额变化 / 推算净流入
    # ------------------------------------------------------------------
    op.create_table(
        "etf_fund_flow",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("ts_code", sa.String(length=20), nullable=False, comment="ETF 代码 (含后缀)"),
        sa.Column("trade_date", sa.Date(), nullable=False, comment="交易日期"),
        sa.Column("price", sa.Numeric(12, 4), nullable=True, comment="收盘价 (元)"),
        sa.Column("net_value", sa.Numeric(12, 4), nullable=True, comment="IOPV / 单位净值 (元)"),
        sa.Column(
            "premium_rate",
            sa.Numeric(8, 4),
            nullable=True,
            comment="折溢价率 (%) = (市价-净值)/净值*100",
        ),
        sa.Column(
            "shares_outstanding",
            sa.Numeric(20, 4),
            nullable=True,
            comment="总份额 (份)",
        ),
        sa.Column(
            "shares_change",
            sa.Numeric(20, 4),
            nullable=True,
            comment="当日份额变化 (份) = 申赎代理变量",
        ),
        sa.Column("turnover", sa.Numeric(20, 4), nullable=True, comment="成交额 (元)"),
        sa.Column(
            "inferred_net_inflow",
            sa.Numeric(20, 4),
            nullable=True,
            comment="推算资金净流入 (元) ≈ shares_change × price",
        ),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
            comment="抓取时间",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_etf_fund_flow"),
        sa.UniqueConstraint(
            "ts_code", "trade_date", name="uq_etf_fund_flow_ts_code_date"
        ),
    )
    op.create_index(
        "ix_etf_fund_flow_trade_date", "etf_fund_flow", ["trade_date"]
    )
    op.create_index(
        "ix_etf_fund_flow_inferred_net",
        "etf_fund_flow",
        ["trade_date", "inferred_net_inflow"],
    )

    # ------------------------------------------------------------------
    # 4. flow_signal: 综合资金信号 (聚合多源)
    # ------------------------------------------------------------------
    op.create_table(
        "flow_signal",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("ts_code", sa.String(length=20), nullable=False, comment="证券代码 (含后缀)"),
        sa.Column("trade_date", sa.Date(), nullable=False, comment="交易日期"),
        # 直接信号
        sa.Column(
            "main_net_inflow",
            sa.Numeric(20, 4),
            nullable=True,
            comment="主力资金净流入 (元) (akshare 个股资金流)",
        ),
        # 间接信号
        sa.Column(
            "margin_net_change",
            sa.Numeric(20, 4),
            nullable=True,
            comment="融资余额日变化 (元) — 正=融资买入加杠杆",
        ),
        sa.Column(
            "lhb_net_buy",
            sa.Numeric(20, 4),
            nullable=True,
            comment="龙虎榜机构净买额 (元) — 当日有龙虎榜时写入",
        ),
        sa.Column(
            "shareholder_count_change",
            sa.Numeric(20, 4),
            nullable=True,
            comment="股东户数环比变化 (户) — 负数=筹码集中",
        ),
        sa.Column(
            "ah_premium",
            sa.Numeric(8, 4),
            nullable=True,
            comment="AH 溢价率 (%) — 仅 A+H 股票",
        ),
        sa.Column(
            "block_trade_net",
            sa.Numeric(20, 4),
            nullable=True,
            comment="大宗交易净买额 (元) — 买方-卖方",
        ),
        # 综合评分
        sa.Column(
            "composite_score",
            sa.Numeric(8, 4),
            nullable=True,
            comment="综合资金情绪评分 [-100, +100]；正=资金净流入，负=资金净流出",
        ),
        sa.Column(
            "score_breakdown",
            sa.JSON(),
            nullable=True,
            comment="各分量贡献明细: { main: x, margin: y, lhb: z, ... }",
        ),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
            comment="抓取时间",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_flow_signal"),
        sa.UniqueConstraint(
            "ts_code", "trade_date", name="uq_flow_signal_ts_code_date"
        ),
    )
    op.create_index(
        "ix_flow_signal_trade_date", "flow_signal", ["trade_date"]
    )
    op.create_index(
        "ix_flow_signal_composite",
        "flow_signal",
        [sa.text("composite_score DESC")],
    )


def downgrade() -> None:
    # Drop in reverse order
    op.drop_index("ix_flow_signal_composite", table_name="flow_signal")
    op.drop_index("ix_flow_signal_trade_date", table_name="flow_signal")
    op.drop_table("flow_signal")

    op.drop_index("ix_etf_fund_flow_inferred_net", table_name="etf_fund_flow")
    op.drop_index("ix_etf_fund_flow_trade_date", table_name="etf_fund_flow")
    op.drop_table("etf_fund_flow")

    op.drop_index("ix_sector_fund_flow_main_net", table_name="sector_fund_flow")
    op.drop_index("ix_sector_fund_flow_trade_date", table_name="sector_fund_flow")
    op.drop_table("sector_fund_flow")

    op.drop_index("ix_individual_fund_flow_main_net", table_name="individual_fund_flow")
    op.drop_index("ix_individual_fund_flow_trade_date", table_name="individual_fund_flow")
    op.drop_table("individual_fund_flow")
