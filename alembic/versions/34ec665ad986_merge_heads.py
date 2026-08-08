"""merge heads

Revision ID: 34ec665ad986
Revises: 01aeaa464fc3, 2026_07_05_add_user_id_to_live_trade_config
Create Date: 2026-07-05 01:08:05.657661

"""
from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = '34ec665ad986'
down_revision: str | Sequence[str] | None = ('01aeaa464fc3', '2026_07_05_add_user_id_to_live_trade_config')
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
