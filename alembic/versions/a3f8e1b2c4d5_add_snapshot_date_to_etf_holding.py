"""add snapshot_date to etf_holding

Adds a dedicated ``snapshot_date`` column on ``etf_holding`` so the
quarterly ETL pipeline can upsert by ``(etf_code, snapshot_date,
holding_code)`` instead of ``delete + insert`` per snapshot. The
legacy ``holdings_as_of_date`` column is preserved (and kept in sync
by the ETL) for backwards compatibility with the API and front-end.

This migration is **idempotent against the existing data layout**:

* The ``snapshot_date`` column is added as **nullable** so the
  ``ALTER TABLE`` succeeds even if the table already has rows.
* A data-migration step copies ``holdings_as_of_date`` into
  ``snapshot_date`` for every existing row, then keeps both columns
  aligned going forward.
* The legacy unique constraint
  ``uq_etf_holding_code_date (etf_code, holding_code, holdings_as_of_date)``
  is dropped and replaced with
  ``uq_etf_holding_snapshot_code (etf_code, snapshot_date, holding_code)``.
  Since the backfill sets ``snapshot_date = holdings_as_of_date``,
  no row violates the new constraint — the rewrite is purely
  semantic.
* The single-column ``idx_etf_holding_as_of`` index is dropped and
  replaced with a composite ``idx_etf_holding_etf_snapshot`` index
  that the latest-snapshot query path (per-ETF, newest snapshot) and
  the historical ``?date=YYYY-MM-DD`` query path both benefit from.

Revision ID: a3f8e1b2c4d5
Revises: 07b0e7d537c3
Create Date: 2026-07-08
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "a3f8e1b2c4d5"
down_revision = "07b0e7d537c3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add ``snapshot_date`` and rewire uniqueness / indexes around it."""
    bind = op.get_bind()

    # 1. Add the new column. Nullable so the ALTER TABLE is safe even
    #    when ``etf_holding`` already holds rows.
    op.add_column(
        "etf_holding",
        sa.Column(
            "snapshot_date",
            sa.Date(),
            nullable=True,
            comment=(
                "Reporting-period date used as upsert identity "
                "(quarterly disclosure date)"
            ),
        ),
    )

    # 2. Backfill: copy ``holdings_as_of_date`` into ``snapshot_date``
    #    for every existing row. Rows with NULL ``holdings_as_of_date``
    #    stay NULL in ``snapshot_date`` — they are pre-migration and
    #    cannot be attributed to any quarter.
    if bind.dialect.name == "postgresql":
        op.execute(
            "UPDATE etf_holding "
            "SET snapshot_date = holdings_as_of_date "
            "WHERE holdings_as_of_date IS NOT NULL"
        )
    else:
        # Generic SQL that works on SQLite + MySQL too.
        op.execute(
            "UPDATE etf_holding "
            "SET snapshot_date = holdings_as_of_date"
        )

    # 3. Swap the unique constraint to use ``snapshot_date`` instead
    #    of ``holdings_as_of_date``. After backfill the two columns
    #    are equal so no row violates the new constraint.
    op.drop_constraint("uq_etf_holding_code_date", "etf_holding", type_="unique")
    op.create_unique_constraint(
        "uq_etf_holding_snapshot_code",
        "etf_holding",
        ["etf_code", "snapshot_date", "holding_code"],
    )

    # 4. Replace the single-column index with a composite index that
    #    serves both the "latest snapshot per ETF" and the historical
    #    "by (etf, snapshot_date)" lookup paths.
    op.drop_index("idx_etf_holding_as_of", table_name="etf_holding")
    op.create_index(
        "idx_etf_holding_etf_snapshot",
        "etf_holding",
        ["etf_code", "snapshot_date"],
    )

    # 5. Single-column index on ``snapshot_date`` for queries that
    #    scan across ETFs (e.g. "list the most recent reporting
    #    date globally"). Matches the model-level ``index=True``.
    op.create_index(
        op.f("idx_etf_holding_snapshot_date"),
        "etf_holding",
        ["snapshot_date"],
    )


def downgrade() -> None:
    """Reverse the snapshot_date introduction.

    Restores the pre-migration layout exactly: drops the new
    unique constraint / indexes, the ``snapshot_date`` column,
    and re-creates the legacy ``uq_etf_holding_code_date`` /
    ``idx_etf_holding_as_of`` artifacts. The
    ``holdings_as_of_date`` column is untouched — it was never
    modified by this migration.
    """
    op.drop_index(
        op.f("idx_etf_holding_snapshot_date"), table_name="etf_holding"
    )
    op.drop_index("idx_etf_holding_etf_snapshot", table_name="etf_holding")
    op.create_index(
        "idx_etf_holding_as_of", "etf_holding", ["holdings_as_of_date"]
    )
    op.drop_constraint(
        "uq_etf_holding_snapshot_code", "etf_holding", type_="unique"
    )
    op.create_unique_constraint(
        "uq_etf_holding_code_date",
        "etf_holding",
        ["etf_code", "holding_code", "holdings_as_of_date"],
    )
    op.drop_column("etf_holding", "snapshot_date")