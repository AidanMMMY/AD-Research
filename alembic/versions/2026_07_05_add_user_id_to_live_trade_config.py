"""add user_id to live_trade_config (owner-scope)

Adds an optional ``user_id`` foreign key on ``live_trade_config`` so each
live-trade config can be owner-scoped. Existing configs are intentionally
left at ``user_id = NULL`` — they are treated as "shared legacy" configs
and remain visible to every authenticated user.

Revision ID: 2026_07_05_add_user_id_to_live_trade_config
Revises: 2026_07_04_add_pool_user_id
Create Date: 2025-07-05 00:00:00.000000
"""

from typing import Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "2026_07_05_add_user_id_to_live_trade_config"
down_revision: Union[str, None] = "2026_07_04_add_pool_user_id"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    """Add ``user_id`` FK + index to ``live_trade_config`` (NULL-safe)."""
    op.add_column(
        "live_trade_config",
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
            comment="Owner user id (NULL = shared legacy config)",
        ),
    )
    op.create_index(
        "ix_live_trade_config_user_id",
        "live_trade_config",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    """Drop the ``user_id`` FK + index from ``live_trade_config``."""
    op.drop_index("ix_live_trade_config_user_id", table_name="live_trade_config")
    op.drop_column("live_trade_config", "user_id")
