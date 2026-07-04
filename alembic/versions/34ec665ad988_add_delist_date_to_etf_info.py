"""add delist_date to etf_info

Revision ID: 34ec665ad988
Revises: 34ec665ad986
Create Date: 2026-07-05 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '34ec665ad988'
down_revision: str | Sequence[str] | None = '34ec665ad986'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add delist_date column to etf_info."""
    op.add_column('etf_info', sa.Column('delist_date', sa.Date(), nullable=True, comment='Delisting date (null if still active)'))


def downgrade() -> None:
    """Remove delist_date column from etf_info."""
    op.drop_column('etf_info', 'delist_date')
