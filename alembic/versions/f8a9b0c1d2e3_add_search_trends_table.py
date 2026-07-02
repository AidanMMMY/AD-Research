"""add search_trends table

Revision ID: f8a9b0c1d2e3
Revises: d4e5f6a7b8c9
Create Date: 2026-07-02 14:30:00.000000

Phase 9 — Search-index observation cache (Baidu + Google Trends).
Mirrors ``app/models/search_trends.py``.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "f8a9b0c1d2e3"
down_revision: Union[str, Sequence[str], None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the ``search_trends`` table."""
    op.create_table(
        "search_trends",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False, comment="ID"),
        sa.Column("keyword", sa.String(length=120), nullable=False, comment="搜索关键词"),
        sa.Column("region", sa.String(length=16), nullable=False, server_default="CN",
                  comment="市场/区域代码"),
        sa.Column("source", sa.String(length=16), nullable=False, comment="数据来源 baidu/google"),
        sa.Column("trade_date", sa.Date(), nullable=False, comment="交易日 (UTC midnight)"),
        sa.Column("value", sa.BigInteger(), nullable=False, comment="指数值"),
        sa.Column("is_partial", sa.Boolean(), nullable=False, server_default=sa.text("false"),
                  comment="是否当日不完整"),
        sa.Column("proxy_quality", sa.String(length=16), nullable=False, server_default="high",
                  comment="数据质量 high/low"),
        sa.Column("category", sa.String(length=32), nullable=True, comment="分类: indices/stocks/macro"),
        sa.Column("fetched_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
                  nullable=True, comment="最后抓取时间"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
                  nullable=True, comment="创建时间"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("keyword", "region", "source", "trade_date",
                            name="uq_search_trends_keyword_region_source_date"),
    )
    op.create_index("ix_search_trends_keyword", "search_trends", ["keyword"])
    op.create_index("ix_search_trends_region", "search_trends", ["region"])
    op.create_index("ix_search_trends_source", "search_trends", ["source"])
    op.create_index("ix_search_trends_trade_date", "search_trends", ["trade_date"])
    op.create_index("ix_search_trends_source_date", "search_trends", ["source", "trade_date"])
    op.create_index("ix_search_trends_keyword_date", "search_trends", ["keyword", "trade_date"])
    op.create_index("ix_search_trends_region_source_date", "search_trends",
                    ["region", "source", "trade_date"])


def downgrade() -> None:
    """Drop the ``search_trends`` table."""
    op.drop_index("ix_search_trends_region_source_date", table_name="search_trends")
    op.drop_index("ix_search_trends_keyword_date", table_name="search_trends")
    op.drop_index("ix_search_trends_source_date", table_name="search_trends")
    op.drop_index("ix_search_trends_trade_date", table_name="search_trends")
    op.drop_index("ix_search_trends_source", table_name="search_trends")
    op.drop_index("ix_search_trends_region", table_name="search_trends")
    op.drop_index("ix_search_trends_keyword", table_name="search_trends")
    op.drop_table("search_trends")