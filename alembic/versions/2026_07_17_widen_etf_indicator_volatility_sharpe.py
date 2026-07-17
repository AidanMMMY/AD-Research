"""widen etf_indicator volatility and sharpe columns

Revision ID: 2026_07_17_widen_etf_indicator_volatility_sharpe
Revises: 2026_07_17_add_instrument_daily_bar_trade_date_index
Create Date: 2026-07-17

将 ``etf_indicator`` 表的 ``volatility_20d``、``volatility_60d``、
``sharpe_1y`` 三列从 ``numeric(8,4)`` 扩宽到 ``numeric(12,4)``，
避免个别高波动个股（如 600653.SH volatility_20d ≈ 36629.75）
写入时触发 ``NumericValueOutOfRange`` 并导致整个 SQL chunk 失败回退。

生产环境已在 2026-07-17 通过 ``ALTER TABLE`` 手工扩宽；本迁移用于
保证后续新环境/CI 的 schema 与模型一致。
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "2026_07_17_widen_etf_indicator_volatility_sharpe"
down_revision = "2026_07_17_add_instrument_daily_bar_trade_date_index"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "etf_indicator",
        "volatility_20d",
        existing_type=sa.Numeric(8, 4),
        type_=sa.Numeric(12, 4),
        existing_nullable=True,
    )
    op.alter_column(
        "etf_indicator",
        "volatility_60d",
        existing_type=sa.Numeric(8, 4),
        type_=sa.Numeric(12, 4),
        existing_nullable=True,
    )
    op.alter_column(
        "etf_indicator",
        "sharpe_1y",
        existing_type=sa.Numeric(8, 4),
        type_=sa.Numeric(12, 4),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "etf_indicator",
        "volatility_20d",
        existing_type=sa.Numeric(12, 4),
        type_=sa.Numeric(8, 4),
        existing_nullable=True,
    )
    op.alter_column(
        "etf_indicator",
        "volatility_60d",
        existing_type=sa.Numeric(12, 4),
        type_=sa.Numeric(8, 4),
        existing_nullable=True,
    )
    op.alter_column(
        "etf_indicator",
        "sharpe_1y",
        existing_type=sa.Numeric(12, 4),
        type_=sa.Numeric(8, 4),
        existing_nullable=True,
    )
