"""widen etf_indicator return and drawdown columns

Revision ID: 2026_07_18_0000_widen_etf_indicator_return_drawdown
Revises: 2026_07_17_widen_etf_indicator_volatility_sharpe
Create Date: 2026-07-18

将 ``etf_indicator`` 表的 ``return_1w``、``return_1m``、``return_3m``、
``return_6m``、``return_1y`` 以及 ``max_drawdown_1y`` 从 ``numeric(8,4)``
扩宽到 ``numeric(18,6)``，避免像 600601.SH 这类出现极端收益/回撤的
个券写入时触发 ``NumericValueOutOfRange`` 并导致整个 indicator chunk
失败回退。
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "2026_07_18_0000_widen_etf_indicator_return_drawdown"
down_revision = "2026_07_17_widen_etf_indicator_volatility_sharpe"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "etf_indicator",
        "return_1w",
        existing_type=sa.Numeric(8, 4),
        type_=sa.Numeric(18, 6),
        existing_nullable=True,
    )
    op.alter_column(
        "etf_indicator",
        "return_1m",
        existing_type=sa.Numeric(8, 4),
        type_=sa.Numeric(18, 6),
        existing_nullable=True,
    )
    op.alter_column(
        "etf_indicator",
        "return_3m",
        existing_type=sa.Numeric(8, 4),
        type_=sa.Numeric(18, 6),
        existing_nullable=True,
    )
    op.alter_column(
        "etf_indicator",
        "return_6m",
        existing_type=sa.Numeric(8, 4),
        type_=sa.Numeric(18, 6),
        existing_nullable=True,
    )
    op.alter_column(
        "etf_indicator",
        "return_1y",
        existing_type=sa.Numeric(8, 4),
        type_=sa.Numeric(18, 6),
        existing_nullable=True,
    )
    op.alter_column(
        "etf_indicator",
        "max_drawdown_1y",
        existing_type=sa.Numeric(8, 4),
        type_=sa.Numeric(18, 6),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "etf_indicator",
        "return_1w",
        existing_type=sa.Numeric(18, 6),
        type_=sa.Numeric(8, 4),
        existing_nullable=True,
    )
    op.alter_column(
        "etf_indicator",
        "return_1m",
        existing_type=sa.Numeric(18, 6),
        type_=sa.Numeric(8, 4),
        existing_nullable=True,
    )
    op.alter_column(
        "etf_indicator",
        "return_3m",
        existing_type=sa.Numeric(18, 6),
        type_=sa.Numeric(8, 4),
        existing_nullable=True,
    )
    op.alter_column(
        "etf_indicator",
        "return_6m",
        existing_type=sa.Numeric(18, 6),
        type_=sa.Numeric(8, 4),
        existing_nullable=True,
    )
    op.alter_column(
        "etf_indicator",
        "return_1y",
        existing_type=sa.Numeric(18, 6),
        type_=sa.Numeric(8, 4),
        existing_nullable=True,
    )
    op.alter_column(
        "etf_indicator",
        "max_drawdown_1y",
        existing_type=sa.Numeric(18, 6),
        type_=sa.Numeric(8, 4),
        existing_nullable=True,
    )
