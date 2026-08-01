"""add global_index_daily_bar table

全球速览指数详情页（Batch A 数据层）：为 yfinance/akshare 覆盖的
宏观代码新增日线 OHLCV 存储，供详情页蜡烛 K 线使用。FRED 序列
继续复用 macro_indicator 折线路径，不建 bars。

复合主键 (code, trade_date, source) 保证刷新幂等；与
macro_indicator 写入路径完全独立，不影响速览页现有磁贴/折线。

Revision ID: v3w5x7y9z1a3
Revises: u7v9w1x3y5z7
Create Date: 2026-08-01
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "v3w5x7y9z1a3"
down_revision: Union[str, Sequence[str], None] = "u7v9w1x3y5z7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "global_index_daily_bar",
        sa.Column("code", sa.String(length=80), nullable=False, comment="Indicator code"),
        sa.Column("trade_date", sa.Date(), nullable=False, comment="Trade date"),
        sa.Column(
            "source",
            sa.String(length=20),
            server_default="yfinance",
            nullable=False,
            comment="Data source",
        ),
        sa.Column("open", sa.Float(), nullable=True, comment="Open price"),
        sa.Column("high", sa.Float(), nullable=True, comment="High price"),
        sa.Column("low", sa.Float(), nullable=True, comment="Low price"),
        sa.Column("close", sa.Float(), nullable=False, comment="Close price"),
        sa.Column("volume", sa.BigInteger(), nullable=True, comment="Volume"),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=True,
            comment="When this row was last upserted",
        ),
        sa.PrimaryKeyConstraint("code", "trade_date", "source"),
    )
    op.create_index(
        "ix_global_index_daily_bar_code_date",
        "global_index_daily_bar",
        ["code", "trade_date"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_global_index_daily_bar_code_date",
        table_name="global_index_daily_bar",
    )
    op.drop_table("global_index_daily_bar")
