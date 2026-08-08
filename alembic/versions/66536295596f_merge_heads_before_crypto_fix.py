"""merge_heads_before_crypto_fix

Revision ID: 66536295596f
Revises: 5aa173a041d5
Create Date: 2026-06-29 21:31:06.946524

"""
from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = '66536295596f'
down_revision: str | Sequence[str] | None = '5aa173a041d5'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
