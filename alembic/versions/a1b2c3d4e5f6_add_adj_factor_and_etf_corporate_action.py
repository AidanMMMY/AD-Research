"""add adj_factor and etf_corporate_action table

Revision ID: a1b2c3d4e5f6
Revises: 7d05c7c0d4f0
Create Date: 2026-06-29

Add split/dividend adjustment factor to etf_daily_bar and a new
etf_corporate_action table to audit corporate actions.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "7d05c7c0d4f0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add adj_factor to etf_daily_bar
    op.add_column(
        "etf_daily_bar",
        sa.Column(
            "adj_factor",
            sa.DECIMAL(18, 8),
            nullable=False,
            server_default="1.0",
            comment="Adjustment factor: close * adj_factor = adjusted close",
        ),
    )

    # Create corporate actions table
    op.create_table(
        "etf_corporate_action",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("etf_code", sa.String(20), nullable=False, comment="Instrument code"),
        sa.Column("action_date", sa.Date(), nullable=False, comment="Effective date"),
        sa.Column(
            "action_type",
            sa.String(20),
            nullable=False,
            comment="Action type: split / reverse_split / dividend",
        ),
        sa.Column(
            "ratio",
            sa.DECIMAL(18, 8),
            nullable=False,
            comment="Split ratio or dividend adjustment factor",
        ),
        sa.Column("source", sa.String(50), comment="Data source"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["etf_code"],
            ["etf_info.code"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "etf_code",
            "action_date",
            "action_type",
            name="uq_corp_action_code_date_type",
        ),
    )
    op.create_index(
        "idx_corp_action_code",
        "etf_corporate_action",
        ["etf_code"],
    )
    op.create_index(
        "idx_corp_action_date",
        "etf_corporate_action",
        ["action_date"],
    )


def downgrade() -> None:
    op.drop_index("idx_corp_action_date", table_name="etf_corporate_action")
    op.drop_index("idx_corp_action_code", table_name="etf_corporate_action")
    op.drop_table("etf_corporate_action")
    op.drop_column("etf_daily_bar", "adj_factor")
