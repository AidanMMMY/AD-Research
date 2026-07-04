"""add period_type and announce_date to stock_fundamental.

Adds two strictly-nullable metadata columns to ``stock_fundamental`` so
PE/PB/ROE snapshots can carry the reporting period they were sourced
from (``Q1`` / ``Q2`` / ``Q3`` / ``Annual`` / ``TTM``) plus the public
release date. Existing rows keep their pre-migration NULL — no data
backfill is performed here.

Revision ID: 197d510e8a35
Revises: 2026_07_04_add_pool_user_id
Create Date: 2026-07-04
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "197d510e8a35"
down_revision = "2026_07_04_add_pool_user_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "stock_fundamental",
        sa.Column(
            "period_type",
            sa.String(length=10),
            nullable=True,
            server_default="TTM",
            comment="Reporting period: Q1|Q2|Q3|Annual|TTM (TTM = trailing twelve months)",
        ),
    )
    op.add_column(
        "stock_fundamental",
        sa.Column(
            "announce_date",
            sa.DateTime(),
            nullable=True,
            comment="Public release date for this snapshot",
        ),
    )


def downgrade() -> None:
    op.drop_column("stock_fundamental", "announce_date")
    op.drop_column("stock_fundamental", "period_type")