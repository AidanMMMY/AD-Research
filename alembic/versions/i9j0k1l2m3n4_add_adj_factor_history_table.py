"""add adj_factor_history table

Creates the authoritative A-share cumulative adjustment factor history
 table. ``adj_factor`` is cumulative and front-adjusted from Tushare:

     true 前复权 close = raw_close * adj_factor / latest_adj_factor

``instrument_daily_bar.adj_factor`` continues to be maintained for
backwards compatibility with existing indicator calculations.

Revision ID: i9j0k1l2m3n4
Revises: h8i9j0k1l2m3
Create Date: 2026-07-18
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'i9j0k1l2m3n4'
down_revision: Union[str, Sequence[str], None] = 'h8i9j0k1l2m3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create adj_factor_history table."""
    op.create_table(
        'adj_factor_history',
        sa.Column(
            'etf_code',
            sa.String(20),
            sa.ForeignKey('etf_info.code', ondelete='CASCADE'),
            nullable=False,
            comment='Instrument code (e.g. 600519.SH)',
        ),
        sa.Column(
            'trade_date',
            sa.Date(),
            nullable=False,
            comment='Trade date',
        ),
        sa.Column(
            'adj_factor',
            sa.DECIMAL(18, 8),
            nullable=False,
            comment='Cumulative front-adjusted adjustment factor from Tushare',
        ),
        sa.Column(
            'source',
            sa.String(20),
            server_default='tushare',
            comment='Data source (tushare)',
        ),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            comment='Creation time',
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            comment='Update time',
        ),
        sa.PrimaryKeyConstraint('etf_code', 'trade_date'),
        sa.UniqueConstraint(
            'etf_code',
            'trade_date',
            name='uq_adj_factor_history_code_date',
        ),
    )
    op.create_index(
        'idx_adj_factor_history_code',
        'adj_factor_history',
        ['etf_code'],
    )
    op.create_index(
        'idx_adj_factor_history_date',
        'adj_factor_history',
        ['trade_date'],
    )


def downgrade() -> None:
    """Drop adj_factor_history table."""
    op.drop_index('idx_adj_factor_history_date', table_name='adj_factor_history')
    op.drop_index('idx_adj_factor_history_code', table_name='adj_factor_history')
    op.drop_table('adj_factor_history')
