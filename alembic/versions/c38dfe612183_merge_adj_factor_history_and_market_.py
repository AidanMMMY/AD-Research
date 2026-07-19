"""merge adj_factor_history and market_fund_flow heads

Revision ID: c38dfe612183
Revises: i9j0k1l2m3n4, 2026_07_18_0001_add_market_fund_flow_table
Create Date: 2026-07-18 22:43:23.263024

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c38dfe612183'
down_revision: Union[str, Sequence[str], None] = ('i9j0k1l2m3n4', '2026_07_18_0001_add_market_fund_flow_table')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
