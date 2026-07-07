"""add fund_size_source to etf_info

Revision ID: 07b0e7d537c3
Revises: 2026_07_05_add_ai_cleanup_obs
Create Date: 2026-07-06 11:28:09.132160

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '07b0e7d537c3'
down_revision: Union[str, Sequence[str], None] = '2026_07_05_add_ai_cleanup_obs'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add fund_size_source column to etf_info."""
    op.add_column(
        'etf_info',
        sa.Column(
            'fund_size_source',
            sa.String(length=100),
            nullable=True,
            comment='Source/reason for fund_size value (e.g. akshare, tushare, unrecoverable: ...)',
        ),
    )


def downgrade() -> None:
    """Drop fund_size_source column from etf_info."""
    op.drop_column('etf_info', 'fund_size_source')
