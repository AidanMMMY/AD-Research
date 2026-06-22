"""add fund_size to etf_info

Revision ID: b2ccc3e42347
Revises: 57929df92f76
Create Date: 2026-06-02 04:42:06.472729

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b2ccc3e42347'
down_revision: str | Sequence[str] | None = '57929df92f76'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add fund_size column to etf_info."""
    op.add_column('etf_info', sa.Column('fund_size', sa.DECIMAL(18, 4), nullable=True, comment='Fund size in CNY'))


def downgrade() -> None:
    """Remove fund_size column from etf_info."""
    op.drop_column('etf_info', 'fund_size')
