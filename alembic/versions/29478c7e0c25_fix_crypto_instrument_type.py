"""fix_crypto_instrument_type

Revision ID: 29478c7e0c25
Revises: 66536295596f
Create Date: 2026-06-29 21:32:56.103515

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '29478c7e0c25'
down_revision: Union[str, Sequence[str], None] = '66536295596f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Set instrument_type='CRYPTO' for all crypto market instruments.

    Crypto instruments were previously inserted with the default
    instrument_type='ETF' because ETFInfo.instrument_type has a server
    default of 'ETF'. This migration fixes existing rows and the code
    paths that create crypto instruments have been updated to explicitly
    set instrument_type='CRYPTO'.
    """
    op.execute(
        sa.text(
            "UPDATE etf_info SET instrument_type = 'CRYPTO' "
            "WHERE market = 'CRYPTO' AND instrument_type != 'CRYPTO'"
        )
    )


def downgrade() -> None:
    """No-op: we cannot safely revert the type assignment."""
    pass
