"""add etf_holding_failed table

Phase 2 of the ETF holdings ETL rewrite: with the bulk Tushare pull
(``fund_portfolio(period=YYYYMMDD, offset, limit)``) replacing the
legacy 1 500-call loop, the only ETFs that fail to refresh in a
quarterly run are the ones Tushare does not yet have data for AND
Akshare also cannot cover. We log those into ``etf_holding_failed``
so the operator can spot persistently-failing ETFs that need manual
intervention (delisted, renumbered, removed from Tushare universe, etc.).

The pipeline upserts into this table on every run, bumping
``retry_count`` when the ETF was already in the blacklist.

Revision ID: c8d4e5f6a7b8
Revises: b5e2c8f4a1d3
Create Date: 2026-07-08
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "c8d4e5f6a7b8"
down_revision = "b5e2c8f4a1d3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "etf_holding_failed",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "etf_code",
            sa.String(length=20),
            sa.ForeignKey("etf_info.code", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "retry_count",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
        sa.Column(
            "last_attempt_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=True,
        ),
    )
    op.create_index(
        "idx_etf_holding_failed_last_attempt",
        "etf_holding_failed",
        ["last_attempt_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_etf_holding_failed_last_attempt", table_name="etf_holding_failed",
    )
    op.drop_table("etf_holding_failed")
