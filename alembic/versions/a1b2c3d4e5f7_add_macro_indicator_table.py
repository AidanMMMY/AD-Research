"""add macro_indicator table

Revision ID: a1b2c3d4e5f7
Revises: f6a7b8c9d0e1
Create Date: 2026-07-02 10:00:00.000000

Adds the ``macro_indicator`` table for time-series macro-economic
observations (FRED for US initially; NBS/PBOC for CN later).  Unique
constraint on (code, region, period, source) makes daily upserts
idempotent.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f7"
down_revision: str | None = "c9a8b7d6e5f4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "macro_indicator",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("code", sa.String(80), nullable=False),
        sa.Column("region", sa.String(20), nullable=False),
        sa.Column("name_zh", sa.String(120), nullable=False),
        sa.Column("unit", sa.String(40), nullable=False, server_default=sa.text("''")),
        sa.Column("period", sa.Date(), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column(
            "source",
            sa.String(20),
            nullable=False,
            server_default=sa.text("'fred'"),
        ),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "code", "region", "period", "source",
            name="uq_macro_indicator_code_region_period_source",
        ),
    )
    op.create_index("ix_macro_indicator_code", "macro_indicator", ["code"])
    op.create_index("ix_macro_indicator_region", "macro_indicator", ["region"])
    op.create_index(
        "ix_macro_indicator_region_code", "macro_indicator", ["region", "code"]
    )
    op.create_index(
        "ix_macro_indicator_code_period", "macro_indicator", ["code", "period"]
    )
    op.add_column(
        "macro_indicator",
        sa.Column(
            "name_en", sa.String(length=120), nullable=True, comment="Indicator English name"
        ),
    )


def downgrade() -> None:
    op.drop_column("macro_indicator", "name_en")
    op.drop_index("ix_macro_indicator_code_period", table_name="macro_indicator")
    op.drop_index("ix_macro_indicator_region_code", table_name="macro_indicator")
    op.drop_index("ix_macro_indicator_region", table_name="macro_indicator")
    op.drop_index("ix_macro_indicator_code", table_name="macro_indicator")
    op.drop_table("macro_indicator")