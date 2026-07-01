"""add_listing_events_table

Revision ID: 1c9321d3cb37
Revises: 997c17ed0dfd
Create Date: 2026-07-01 17:50:05.305487

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "1c9321d3cb37"
down_revision: Union[str, Sequence[str], None] = "997c17ed0dfd"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "listing_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("ts_code", sa.String(length=20), nullable=False, comment="Tushare 证券代码"),
        sa.Column("sub_code", sa.String(length=20), nullable=True, comment="申购代码"),
        sa.Column("name", sa.String(length=64), nullable=False, comment="证券简称"),
        sa.Column("market", sa.String(length=8), nullable=False, comment="交易所后缀: SH/SZ/BJ"),
        sa.Column("board", sa.String(length=16), nullable=False, comment="板块: 主板/创业板/科创板/北交所"),
        sa.Column("industry", sa.String(length=64), nullable=True, comment="CSRC 行业"),
        sa.Column("issue_date", sa.Date(), nullable=True, comment="上网发行日期"),
        sa.Column("list_date", sa.Date(), nullable=True, comment="上市日期"),
        sa.Column("issue_price", sa.Numeric(12, 4), nullable=True, comment="发行价 (元)"),
        sa.Column("pe_ratio", sa.Numeric(10, 4), nullable=True, comment="发行市盈率"),
        sa.Column("limit_amount", sa.Numeric(18, 4), nullable=True, comment="申购上限 (万元)"),
        sa.Column("funds_raised", sa.Numeric(20, 4), nullable=True, comment="募集资金 (万元)"),
        sa.Column("market_amount", sa.Numeric(20, 4), nullable=True, comment="发行后总股本 (万股)"),
        sa.Column("sponsor", sa.String(length=128), nullable=True, comment="保荐机构"),
        sa.Column("underwriter", sa.String(length=256), nullable=True, comment="承销商"),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default="unknown",
            comment="状态: upcoming/subscribing/listed/unknown",
        ),
        sa.Column(
            "source",
            sa.String(length=32),
            nullable=False,
            server_default="tushare",
            comment="数据来源",
        ),
        sa.Column("raw_payload", sa.JSON(), nullable=True, comment="上游原始记录"),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            comment="抓取时间",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            comment="创建时间",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            comment="更新时间",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ts_code", name="uq_listing_events_ts_code"),
    )
    op.create_index("ix_listing_events_list_date", "listing_events", ["list_date"])
    op.create_index("ix_listing_events_issue_date", "listing_events", ["issue_date"])
    op.create_index("ix_listing_events_status", "listing_events", ["status"])
    op.create_index(
        "ix_listing_events_market_board", "listing_events", ["market", "board"]
    )
    op.create_index("ix_listing_events_industry", "listing_events", ["industry"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_listing_events_industry", table_name="listing_events")
    op.drop_index("ix_listing_events_market_board", table_name="listing_events")
    op.drop_index("ix_listing_events_status", table_name="listing_events")
    op.drop_index("ix_listing_events_issue_date", table_name="listing_events")
    op.drop_index("ix_listing_events_list_date", table_name="listing_events")
    op.drop_table("listing_events")
