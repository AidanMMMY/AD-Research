"""SEC EDGAR filing ORM model.

Stores metadata + optional XBRL-extracted metrics for US-listed
companies' filings (10-K, 10-Q, 20-F). The ``extraction_status`` column
tracks the lifecycle of a single filing:

    pending   → just ingested from EDGAR, no XBRL extraction yet
    success   → core GAAP concepts (Revenue, NetIncome, Assets, Equity) parsed
    failed    → XBRL extraction raised; raw payload kept for debugging

Idempotency: ``accession_number`` is the unique SEC accession (e.g.
``0000320193-23-000106``) and serves as the natural primary key.  We
use an autoincrement surrogate ``id`` for cross-table joins but every
upsert resolves to the same row.

This table is intentionally narrow — full filing text / exhibits live
in the SEC archive; we cache only the structured fields that the
research UI and AI agents need.
"""

from sqlalchemy import (
    JSON,
    Column,
    Date,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)

from app.core.database import Base


class SecFiling(Base):
    """A single SEC EDGAR filing (10-K / 10-Q / 8-K / 20-F) row.

    The ``cik`` column stores the 10-digit zero-padded string SEC
    publishes — keep it as ``String`` so we can index + filter
    directly without re-padding.  ``ticker`` is the primary US ticker
    symbol and may differ from the company's other listed tickers.
    """

    __tablename__ = "sec_filings"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="Surrogate PK")
    cik = Column(String(20), nullable=False, index=True, comment="SEC 10-digit CIK")
    ticker = Column(String(20), nullable=False, index=True, comment="Primary US ticker")
    company_name = Column(String(200), nullable=True, comment="Company name from EDGAR")
    form_type = Column(
        String(20),
        nullable=False,
        index=True,
        comment="Filing form (10-K, 10-Q, 8-K, 20-F, etc.)",
    )
    filing_date = Column(Date, nullable=False, index=True, comment="Date filed with SEC")
    report_period = Column(
        Date,
        nullable=True,
        index=True,
        comment="Period the filing reports on (e.g. fiscal quarter end)",
    )
    accession_number = Column(
        String(40),
        nullable=False,
        comment="SEC accession number (unique filing identifier)",
    )
    primary_document = Column(
        String(200),
        nullable=True,
        comment="Primary document filename within the accession directory",
    )
    filing_url = Column(
        String(500),
        nullable=True,
        comment="Direct URL to the filing index on EDGAR",
    )
    xbrl_file_path = Column(
        Text,
        nullable=True,
        comment="Optional local path to cached XBRL submission (R*.xml)",
    )
    extracted_metrics = Column(
        JSON,
        nullable=True,
        comment="Extracted GAAP metrics (Revenues, NetIncomeLoss, Assets, ...)",
    )
    extraction_status = Column(
        String(20),
        nullable=False,
        server_default="pending",
        comment="pending / success / failed — XBRL extraction state",
    )
    extracted_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp of last XBRL extraction attempt",
    )
    source = Column(
        String(50),
        nullable=False,
        server_default="sec_edgar",
        comment="Data source identifier (always sec_edgar for this table)",
    )
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="Row creation time",
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        comment="Row last-update time",
    )

    __table_args__ = (
        UniqueConstraint(
            "accession_number", name="uq_sec_filings_accession_number"
        ),
        Index("ix_sec_filings_ticker_form_date", "ticker", "form_type", "filing_date"),
        Index("ix_sec_filings_cik_filing_date", "cik", "filing_date"),
    )
