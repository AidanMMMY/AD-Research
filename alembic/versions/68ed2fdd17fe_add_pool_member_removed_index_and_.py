"""add pool member removed index and favorite username fk

Revision ID: 68ed2fdd17fe
Revises: 53a042707fc0
Create Date: 2026-06-24 17:29:03.202978

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '68ed2fdd17fe'
down_revision: str | Sequence[str] | None = '53a042707fc0'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Prevent duplicate soft-deleted pool member records with the same timestamp.
    op.create_index(
        'uq_pool_member_removed',
        'pool_member',
        ['pool_id', 'etf_code', 'removed_at'],
        unique=True,
        postgresql_where=sa.text('removed_at IS NOT NULL'),
    )

    # Enforce referential integrity and cascade delete for user favorites.
    op.create_foreign_key(
        None,
        'user_favorite',
        'users',
        ['username'],
        ['username'],
        ondelete='CASCADE',
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(None, 'user_favorite', type_='foreignkey')
    op.drop_index(
        'uq_pool_member_removed',
        table_name='pool_member',
        postgresql_where=sa.text('removed_at IS NOT NULL'),
    )
