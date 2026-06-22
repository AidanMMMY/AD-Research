"""add amount to indicator, soft delete pools, signal unique constraint

Revision ID: 218634bf5756
Revises: e5e15960fc3f
Create Date: 2026-06-21 23:40:41.203291

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '218634bf5756'
down_revision: str | Sequence[str] | None = 'e5e15960fc3f'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add turnover amount to ETFIndicator so the liquidity scoring dimension
    # can use it (it previously referenced a field that did not exist).
    op.add_column(
        'etf_indicator',
        sa.Column(
            'amount',
            sa.DECIMAL(precision=18, scale=4),
            nullable=True,
            comment='Turnover amount',
        ),
    )

    # Add soft-delete support to ETF pools so deletion does not wipe history.
    op.add_column(
        'etf_pools',
        sa.Column(
            'deleted_at',
            sa.DateTime(timezone=True),
            nullable=True,
            comment='Deletion time (NULL = active)',
        ),
    )

    # Enforce uniqueness of signals per (strategy, ETF, date) to prevent duplicates.
    op.drop_constraint('signal_unique_strategy_etf_date', 'signal', type_='unique')
    op.create_unique_constraint(
        'uq_signal_strategy_etf_date',
        'signal',
        ['strategy_id', 'etf_code', 'trade_date'],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('uq_signal_strategy_etf_date', 'signal', type_='unique')
    op.create_unique_constraint(
        'signal_unique_strategy_etf_date',
        'signal',
        ['strategy_id', 'etf_code', 'trade_date'],
    )
    op.drop_column('etf_pools', 'deleted_at')
    op.drop_column('etf_indicator', 'amount')
