"""add user_id to etf_pools (M21-3 Pool/Favorites/Portfolio P1)

Adds an optional ``user_id`` foreign key on ``etf_pools`` so pools can be
owner-scoped. Existing pools are intentionally left at ``user_id = NULL``
— they are treated as "shared legacy" pools and remain visible to every
authenticated user via the read filter (admin users always see all
pools). No backfill to a super-user is performed.

Revision ID: 2026_07_04_add_pool_user_id
Revises: 2026_07_04_add_news_symbol_names
Create Date: 2026-07-04 19:30:00.000000
"""

from typing import Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "2026_07_04_add_pool_user_id"
down_revision: Union[str, None] = "2026_07_04_add_news_symbol_names"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    """Add ``user_id`` FK + index to ``etf_pools`` (NULL-safe)."""
    op.add_column(
        "etf_pools",
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
            comment="Owner user id (NULL = shared legacy pool)",
        ),
    )
    op.create_index(
        "ix_etf_pools_user_id",
        "etf_pools",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    """Drop the ``user_id`` FK + index from ``etf_pools``."""
    op.drop_index("ix_etf_pools_user_id", table_name="etf_pools")
    op.drop_column("etf_pools", "user_id")