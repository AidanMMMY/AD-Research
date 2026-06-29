"""rename etf_daily_bar to instrument_daily_bar

Revision ID: db105fd25327
Revises: 5aa173a041d5
Create Date: 2026-06-29 17:51:30.123772

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'db105fd25327'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Rename etf_daily_bar to instrument_daily_bar."""
    op.rename_table("etf_daily_bar", "instrument_daily_bar")


def downgrade() -> None:
    """Revert instrument_daily_bar back to etf_daily_bar."""
    op.rename_table("instrument_daily_bar", "etf_daily_bar")
