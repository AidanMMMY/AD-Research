"""add list_date to etf_info

Revision ID: 1505324a3d5d
Revises: a1b2c3d4e5f6
Create Date: 2026-06-29 14:57:45.101796

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1505324a3d5d'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add list_date column to etf_info."""
    op.add_column(
        'etf_info',
        sa.Column('list_date', sa.Date(), nullable=True, comment='Listing / first trading date'),
    )


def downgrade() -> None:
    """Drop list_date column from etf_info."""
    op.drop_column('etf_info', 'list_date')
