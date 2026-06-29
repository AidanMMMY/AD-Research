"""merge_heads_before_crypto_fix

Revision ID: 66536295596f
Revises: 5aa173a041d5
Create Date: 2026-06-29 21:31:06.946524

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '66536295596f'
down_revision: Union[str, Sequence[str], None] = '5aa173a041d5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
