"""add users table

Revision ID: e5e15960fc3f
Revises: b260fa52b4ed
Create Date: 2026-06-21 18:57:07.119252

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e5e15960fc3f'
down_revision: str | Sequence[str] | None = 'b260fa52b4ed'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema — create users table only."""
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False, comment='User ID'),
        sa.Column('username', sa.String(length=50), nullable=False, comment='Login username'),
        sa.Column('password_hash', sa.String(length=255), nullable=False, comment='Bcrypt password hash'),
        sa.Column('role', sa.String(length=20), nullable=False, comment='User role'),
        sa.Column('is_active', sa.Boolean(), nullable=False, comment='Is active'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True, comment='Creation time'),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True, comment='Last update time'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('username')
    )


def downgrade() -> None:
    """Downgrade schema — drop users table."""
    op.drop_table('users')
