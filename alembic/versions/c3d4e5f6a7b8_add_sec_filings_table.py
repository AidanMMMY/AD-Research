"""add sec_filings table

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-07-02 14:10:00.000000

Phase 6 — SEC EDGAR ingestion: cache 10-K / 10-Q / 20-F filings for the
S&P 500 universe + extracted XBRL metrics.  Mirrors ``app/models/sec_filing.py``.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, Sequence[str], None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the ``sec_filings`` table."""
    op.create_table(
        "sec_filings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False, comment="Surrogate PK"),
        sa.Column("cik", sa.String(length=20), nullable=False, comment="SEC 10-digit CIK"),
        sa.Column("ticker", sa.String(length=20), nullable=False, comment="Primary US ticker"),
        sa.Column("company_name", sa.String(length=200), nullable=True, comment="Company name from EDGAR"),
        sa.Column("form_type", sa.String(length=20), nullable=False, comment="Filing form (10-K, 10-Q, 8-K, 20-F, etc.)"),
        sa.Column("filing_date", sa.Date(), nullable=False, comment="Date filed with SEC"),
        sa.Column("report_period", sa.Date(), nullable=True, comment="Period the filing reports on"),
        sa.Column("accession_number", sa.String(length=40), nullable=False, comment="SEC accession number"),
        sa.Column("primary_document", sa.String(length=200), nullable=True, comment="Primary document filename"),
        sa.Column("filing_url", sa.String(length=500), nullable=True, comment="EDGAR index URL"),
        sa.Column("xbrl_file_path", sa.Text(), nullable=True, comment="Cached XBRL R*.xml path"),
        sa.Column("extracted_metrics", sa.JSON(), nullable=True, comment="Extracted GAAP metrics"),
        sa.Column("extraction_status", sa.String(length=20), nullable=False, server_default="pending",
                  comment="pending / success / failed"),
        sa.Column("extracted_at", sa.DateTime(timezone=True), nullable=True, comment="Last extraction attempt"),
        sa.Column("source", sa.String(length=50), nullable=False, server_default="sec_edgar",
                  comment="Data source identifier"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False,
                  comment="Row creation time"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False,
                  comment="Row last-update time"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("accession_number", name="uq_sec_filings_accession_number"),
    )
    op.create_index("ix_sec_filings_cik", "sec_filings", ["cik"])
    op.create_index("ix_sec_filings_ticker", "sec_filings", ["ticker"])
    op.create_index("ix_sec_filings_form_type", "sec_filings", ["form_type"])
    op.create_index("ix_sec_filings_filing_date", "sec_filings", ["filing_date"])
    op.create_index("ix_sec_filings_report_period", "sec_filings", ["report_period"])
    op.create_index("ix_sec_filings_ticker_form_date", "sec_filings", ["ticker", "form_type", "filing_date"])
    op.create_index("ix_sec_filings_cik_filing_date", "sec_filings", ["cik", "filing_date"])


def downgrade() -> None:
    """Drop the ``sec_filings`` table."""
    op.drop_index("ix_sec_filings_cik_filing_date", table_name="sec_filings")
    op.drop_index("ix_sec_filings_ticker_form_date", table_name="sec_filings")
    op.drop_index("ix_sec_filings_report_period", table_name="sec_filings")
    op.drop_index("ix_sec_filings_filing_date", table_name="sec_filings")
    op.drop_index("ix_sec_filings_form_type", table_name="sec_filings")
    op.drop_index("ix_sec_filings_ticker", table_name="sec_filings")
    op.drop_index("ix_sec_filings_cik", table_name="sec_filings")
    op.drop_table("sec_filings")