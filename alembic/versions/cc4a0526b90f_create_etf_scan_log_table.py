"""create etf_scan_log table

Revision ID: cc4a0526b90f
Revises: 68ed2fdd17fe
Create Date: 2026-06-25 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "cc4a0526b90f"
down_revision: str | Sequence[str] | None = "68ed2fdd17fe"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "etf_scan_log",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("scan_date", sa.Date(), nullable=False),
        sa.Column("new_count", sa.Integer(), nullable=True),
        sa.Column("delisted_count", sa.Integer(), nullable=True),
        sa.Column("changed_count", sa.Integer(), nullable=True),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=True),
        sa.Column("error_msg", sa.String(length=500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("etf_scan_log")
