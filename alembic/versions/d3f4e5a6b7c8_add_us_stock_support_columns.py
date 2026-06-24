"""add US stock support columns to etf_info

Revision ID: d3f4e5a6b7c8
Revises: cc4a0526b90f
Create Date: 2025-06-25

Add instrument_type, sector, industry, market_cap, and country columns
to the etf_info table to support US equities alongside existing ETFs.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import DECIMAL, Column, String


# revision identifiers, used by Alembic.
revision: str = "d3f4e5a6b7c8"
down_revision: Union[str, None] = "cc4a0526b90f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "etf_info",
        sa.Column(
            "instrument_type",
            sa.String(20),
            server_default="ETF",
            comment="Instrument type: ETF or STOCK",
        ),
    )
    op.add_column(
        "etf_info",
        sa.Column("sector", sa.String(100), comment="GICS sector"),
    )
    op.add_column(
        "etf_info",
        sa.Column("industry", sa.String(100), comment="GICS industry"),
    )
    op.add_column(
        "etf_info",
        sa.Column(
            "market_cap",
            sa.DECIMAL(18, 4),
            comment="Market capitalization",
        ),
    )
    op.add_column(
        "etf_info",
        sa.Column("country", sa.String(50), comment="Country of listing"),
    )
    op.create_index(
        "idx_etf_info_instrument_type",
        "etf_info",
        ["instrument_type"],
    )


def downgrade() -> None:
    op.drop_index("idx_etf_info_instrument_type", table_name="etf_info")
    op.drop_column("etf_info", "country")
    op.drop_column("etf_info", "market_cap")
    op.drop_column("etf_info", "industry")
    op.drop_column("etf_info", "sector")
    op.drop_column("etf_info", "instrument_type")
