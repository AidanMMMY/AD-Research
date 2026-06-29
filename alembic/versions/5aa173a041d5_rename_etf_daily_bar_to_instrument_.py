"""rename etf_daily_bar to instrument_daily_bar

Revision ID: 5aa173a041d5
Revises: 1505324a3d5d
Create Date: 2026-06-29 16:19:39.422099

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5aa173a041d5'
down_revision: Union[str, Sequence[str], None] = '1505324a3d5d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Rename etf_daily_bar to instrument_daily_bar."""
    op.rename_table("etf_daily_bar", "instrument_daily_bar")


def downgrade() -> None:
    """Revert instrument_daily_bar back to etf_daily_bar."""
    op.rename_table("instrument_daily_bar", "etf_daily_bar")
