"""make signal.user_id nullable for system-generated signals

Scheduler-generated trading signals are system-wide and should be visible to
every authenticated user. Previously they were written with ``user_id=1``
(the admin), which made them invisible to non-admin users because the signal
list endpoint always filters by ``current_user.id``.

This migration relaxes ``signal.user_id`` to nullable so the scheduler can
write ``user_id=NULL`` for system signals; the query layer treats NULL as
visible to all users.

Revision ID: q3r5s7t9u1v2
Revises: p1r4s0t7u8v9
Create Date: 2026-07-19
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "q3r5s7t9u1v2"
down_revision: Union[str, Sequence[str], None] = "p1r4s0t7u8v9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Allow NULL in signal.user_id."""
    op.alter_column(
        "signal",
        "user_id",
        existing_type=sa.Integer(),
        nullable=True,
        existing_comment="Owner user ID",
        comment="Owner user ID (NULL for system-generated signals)",
    )


def downgrade() -> None:
    """Restore NOT NULL on signal.user_id (system rows get owner id 1)."""
    op.execute("UPDATE signal SET user_id = 1 WHERE user_id IS NULL")
    op.alter_column(
        "signal",
        "user_id",
        existing_type=sa.Integer(),
        nullable=False,
        existing_comment="Owner user ID (NULL for system-generated signals)",
        comment="Owner user ID",
    )
