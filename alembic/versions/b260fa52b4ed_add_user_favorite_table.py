"""Add user_favorite table

Revision ID: b260fa52b4ed
Revises: b2ccc3e42347
Create Date: 2026-06-09 22:21:41.308134

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b260fa52b4ed'
down_revision: str | Sequence[str] | None = 'b2ccc3e42347'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema — create user_favorite table only.

    NOTE: The original auto-generated migration incorrectly dropped
    etf_scan_log, notification_log, notification_config tables and
    removed a unique constraint on signal. Those drops have been
    removed; only the user_favorite table creation remains.
    """
    # Create user_favorite table
    op.create_table(
        'user_favorite',
        sa.Column('id', sa.String(50), nullable=False, comment='Composite key: username_etf_code'),
        sa.Column('username', sa.String(50), nullable=False, comment='Username from JWT token'),
        sa.Column('etf_code', sa.String(20), sa.ForeignKey('etf_info.code', ondelete='CASCADE'), nullable=False, comment='ETF code'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), comment='When this favorite was added'),
        sa.PrimaryKeyConstraint('id', name='pk_user_favorite'),
        sa.UniqueConstraint('username', 'etf_code', name='uq_user_favorite_username_etf'),
    )


def downgrade() -> None:
    """Downgrade schema — drop user_favorite table."""
    op.drop_table('user_favorite')
