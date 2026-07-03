"""add name_zh column to etf_info

Revision ID: 2026_07_04_add_name_zh
Revises: b836989fd958
Create Date: 2026-07-04 12:00:00.000000

Add nullable Chinese name column for US (and any future foreign-market)
instruments so the unified instrument list can surface ``name_zh`` next
to the existing English ``name``.  Filled by the
``scripts/backfill_us_chinese_names.py`` backfill job (East Money as
primary source).
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "2026_07_04_add_name_zh"
down_revision: Union[str, Sequence[str], None] = "b836989fd958"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add ``name_zh`` VARCHAR(200) NULL column to ``etf_info``."""
    op.add_column(
        "etf_info",
        sa.Column("name_zh", sa.String(length=200), nullable=True,
                  comment="Chinese name (primarily for US/HK/JP foreign listings)"),
    )


def downgrade() -> None:
    """Drop ``name_zh`` column from ``etf_info``."""
    op.drop_column("etf_info", "name_zh")