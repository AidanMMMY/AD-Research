"""add_is_synthetic_and_fix_pool_constraints

Revision ID: 53a042707fc0
Revises: 218634bf5756
Create Date: 2026-06-22 00:16:01.166659

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '53a042707fc0'
down_revision: str | Sequence[str] | None = '218634bf5756'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Mark synthetic daily bars so demo/filled data can be distinguished.
    op.add_column(
        'etf_daily_bar',
        sa.Column(
            'is_synthetic',
            sa.Boolean(),
            nullable=False,
            server_default=sa.text('false'),
            comment='Whether this bar is synthetic/demo data',
        ),
    )

    # Fix PoolMember unique constraint: enforce uniqueness only on active members.
    op.drop_constraint('uq_pool_member_pool_etf_removed', 'pool_member', type_='unique')
    op.create_index(
        'uq_pool_member_active',
        'pool_member',
        ['pool_id', 'etf_code'],
        unique=True,
        postgresql_where=sa.text('removed_at IS NULL'),
    )

    # Add soft-delete to PoolWeight and use a partial unique index on active weights.
    op.add_column(
        'pool_weight',
        sa.Column(
            'removed_at',
            sa.DateTime(timezone=True),
            nullable=True,
            comment='Removed time (NULL = active)',
        ),
    )
    op.drop_constraint('uq_pool_weight_pool_etf', 'pool_weight', type_='unique')
    op.create_index(
        'uq_pool_weight_active',
        'pool_weight',
        ['pool_id', 'etf_code'],
        unique=True,
        postgresql_where=sa.text('removed_at IS NULL'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Before recreating the unique constraint on pool_weight, clean up duplicate
    # soft-deleted rows so the constraint can be enforced. Keep the latest removed_at.
    op.execute("""
        DELETE FROM pool_weight a
        USING pool_weight b
        WHERE a.id < b.id
          AND a.pool_id = b.pool_id
          AND a.etf_code = b.etf_code
          AND a.removed_at IS NOT NULL
          AND b.removed_at IS NOT NULL
    """)

    op.drop_index('uq_pool_weight_active', table_name='pool_weight', postgresql_where=sa.text('removed_at IS NULL'))
    op.create_unique_constraint('uq_pool_weight_pool_etf', 'pool_weight', ['pool_id', 'etf_code'])
    op.drop_column('pool_weight', 'removed_at')

    op.drop_index('uq_pool_member_active', table_name='pool_member', postgresql_where=sa.text('removed_at IS NULL'))
    op.create_unique_constraint('uq_pool_member_pool_etf_removed', 'pool_member', ['pool_id', 'etf_code', 'removed_at'])
    op.drop_column('etf_daily_bar', 'is_synthetic')
